// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IAgentCartMerchantRegistry} from "./interfaces/IAgentCartMerchantRegistry.sol";

interface IRegistryBondToken {
    function balanceOf(address account) external view returns (uint256);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

/// @notice New deployment only. Admissions attest offchain checks; they do not prove delivery.
contract AgentCartMerchantRegistryV2 is IAgentCartMerchantRegistry {
    error InvalidAdmission();
    error ValidatorSetBound();
    error BondUnavailable();
    error InvalidSanction();
    error ReentrantCall();

    uint16 public constant MAX_VALIDATORS = 16;
    uint64 public constant BOND_EXIT_DELAY = 30 days;
    uint64 public constant VOTE_LIFETIME = 7 days;
    IRegistryBondToken public immutable bondToken;
    uint256 public immutable minimumBond;
    mapping(address => uint64) public validatorEpoch;
    mapping(bytes32 => mapping(address => uint64)) private _attestationEpoch;
    mapping(bytes32 => mapping(address => uint64)) private _voteEpoch;
    mapping(bytes32 => mapping(address => uint64)) private _voteTime;
    mapping(bytes32 => uint64) private _decisionReadyAt;
    mapping(bytes32 => bool) private _decisionsUsed;
    mapping(bytes32 => bytes32) private _approvedAdmission;
    mapping(bytes32 => bytes32) private _recordAdmission;
    mapping(bytes32 => bytes32) public entityId;
    mapping(bytes32 => bool) public blockedEntities;
    mapping(bytes32 => uint256) public bondBalance;
    mapping(bytes32 => uint64) public bondExitAt;
    bool private _entered;

    struct Admission {
        bytes32 entity;
        uint64 expiresAt;
    }

    struct Sanction {
        bytes32 action;
        bytes32 reason;
        address beneficiary;
        uint256 amount;
        uint64 readyAt;
        bool appealed;
    }
    mapping(bytes32 => Admission) private _admissions;
    mapping(bytes32 => Sanction) public sanctions;
    mapping(bytes32 => bool) public closedCases;

    event AdmissionVote(
        bytes32 indexed approval, bytes32 indexed entity, address indexed validator, bytes32 evidenceHash
    );
    event BondDeposited(bytes32 indexed recordId, uint256 amount);
    event AdmissionRenewed(bytes32 indexed recordId, bytes32 indexed approval);
    event BondWithdrawn(bytes32 indexed recordId, uint256 amount);
    event DecisionVote(bytes32 indexed action, address indexed validator);
    event SanctionScheduled(
        bytes32 indexed recordId,
        bytes32 indexed reason,
        uint256 amount,
        address beneficiary,
        uint64 readyAt,
        string evidenceURI
    );
    event SanctionAppealed(bytes32 indexed recordId, bytes32 evidenceHash, uint64 reviewAt);
    event BondSlashed(
        bytes32 indexed recordId, bytes32 indexed entity, uint256 amount, address beneficiary, bytes32 reason
    );

    modifier nonReentrant() {
        if (_entered) revert ReentrantCall();
        _entered = true;
        _;
        _entered = false;
    }

    function voteAdmission(
        bytes32 domainHash,
        address controller,
        bytes32 recordHash,
        bytes32 entity,
        uint64 expiresAt,
        bytes32 evidenceHash
    ) external onlyValidator whenWritesOpen returns (bytes32 approval) {
        if (
            controller == address(0) || domainHash == 0 || recordHash == 0 || entity == 0 || evidenceHash == 0
                || expiresAt <= block.timestamp || expiresAt > block.timestamp + 90 days || blockedEntities[entity]
        ) revert InvalidAdmission();
        bytes32 binding = keccak256(abi.encode(domainHash, controller, recordHash));
        approval = keccak256(abi.encode("admission", binding, entity, expiresAt, evidenceHash));
        _admissions[approval] = Admission(entity, expiresAt);
        if (_vote(approval)) _approvedAdmission[binding] = approval;
        emit AdmissionVote(approval, entity, msg.sender, evidenceHash);
    }

    function _bindAdmission(bytes32 recordId, bytes32 domainHash, address controller, bytes32 recordHash) private {
        bytes32 approval = _approvedAdmission[keccak256(abi.encode(domainHash, controller, recordHash))];
        Admission memory admitted = _admissions[approval];
        if (admitted.expiresAt <= block.timestamp || blockedEntities[admitted.entity] || !_hasQuorum(approval)) {
            revert InvalidAdmission();
        }
        if (entityId[recordId] != 0 && entityId[recordId] != admitted.entity) revert InvalidAdmission();
        entityId[recordId] = admitted.entity;
        _recordAdmission[recordId] = approval;
    }

    /// @notice Approval available for a future register, update, rotation, or renewal.
    function admission(bytes32 domainHash, address controller, bytes32 recordHash)
        external
        view
        returns (bool approved, bytes32 entity, uint64 expiresAt)
    {
        bytes32 approval = _approvedAdmission[keccak256(abi.encode(domainHash, controller, recordHash))];
        Admission memory admitted = _admissions[approval];
        entity = admitted.entity;
        expiresAt = admitted.expiresAt;
        approved = !writesPaused && entity != 0 && !blockedEntities[entity] && expiresAt > block.timestamp
            && _hasQuorum(approval);
    }

    /// @notice Bind fresh validator approval without changing the merchant document.
    function renewAdmission(bytes32 recordId) external whenWritesOpen onlyController(recordId) {
        Record storage stored = _records[recordId];
        _requireStatus(stored, Status.Active);
        _bindAdmission(recordId, stored.domainHash, msg.sender, stored.recordHash);
        emit AdmissionRenewed(recordId, _recordAdmission[recordId]);
    }

    function eligibility(bytes32 recordId)
        external
        view
        returns (bool eligible, bytes32 entity, uint64 expiresAt, uint256 bond)
    {
        bytes32 approval = _recordAdmission[recordId];
        Admission memory admitted = _admissions[approval];
        entity = entityId[recordId];
        expiresAt = admitted.expiresAt;
        bond = bondBalance[recordId];
        eligible = !writesPaused && _records[recordId].status == Status.Active && entity != 0
            && !blockedEntities[entity] && expiresAt > block.timestamp && bond >= minimumBond
            && _hasAdmissionQuorum(approval);
    }

    function _collectBond(bytes32 recordId, address payer) private {
        uint256 beforeBalance = bondToken.balanceOf(address(this));
        if (
            !bondToken.transferFrom(payer, address(this), minimumBond)
                || bondToken.balanceOf(address(this)) != beforeBalance + minimumBond
        ) revert BondUnavailable();
        bondBalance[recordId] += minimumBond;
        emit BondDeposited(recordId, minimumBond);
    }

    function withdrawBond(bytes32 recordId) external onlyController(recordId) nonReentrant {
        Sanction memory sanction = sanctions[recordId];
        if (
            _records[recordId].status != Status.Revoked || bondExitAt[recordId] == 0
                || block.timestamp < bondExitAt[recordId]
                || (sanction.readyAt != 0 && block.timestamp <= sanction.readyAt + VOTE_LIFETIME)
        ) revert BondUnavailable();
        uint256 amount = bondBalance[recordId];
        if (amount == 0) revert BondUnavailable();
        bondBalance[recordId] = 0;
        if (!bondToken.transfer(msg.sender, amount)) revert BondUnavailable();
        emit BondWithdrawn(recordId, amount);
    }

    /// @notice Validators adjudicate documented misconduct, never price competition.
    /// Quorum schedules a monetary sanction; one validator cannot freeze a bond.
    function proposeSlash(
        bytes32 recordId,
        uint256 amount,
        address beneficiary,
        bytes32 reason,
        string calldata evidenceURI
    ) external onlyValidator whenWritesOpen {
        _existingRecord(recordId);
        _requireNonEmptyUri(evidenceURI);
        if (
            amount == 0 || amount > bondBalance[recordId] || beneficiary == address(0) || reason == 0
                || closedCases[keccak256(abi.encode(recordId, reason))]
                || (bondExitAt[recordId] != 0 && block.timestamp >= bondExitAt[recordId])
        ) revert InvalidSanction();
        Sanction memory existing = sanctions[recordId];
        if (existing.readyAt != 0 && block.timestamp <= existing.readyAt + VOTE_LIFETIME) revert InvalidSanction();
        bytes32 action =
            keccak256(abi.encode("slash", recordId, amount, beneficiary, reason, keccak256(bytes(evidenceURI))));
        if (_vote(action)) {
            uint64 readyAt = _now64() + GOVERNANCE_DELAY_SECONDS;
            sanctions[recordId] = Sanction(action, reason, beneficiary, amount, readyAt, false);
            closedCases[keccak256(abi.encode(recordId, reason))] = true;
            emit SanctionScheduled(recordId, reason, amount, beneficiary, readyAt, evidenceURI);
        }
    }

    function appealSlash(bytes32 recordId, bytes32 evidenceHash) external onlyController(recordId) {
        Sanction storage sanction = sanctions[recordId];
        if (sanction.readyAt == 0 || sanction.appealed || block.timestamp >= sanction.readyAt || evidenceHash == 0) {
            revert InvalidSanction();
        }
        sanction.appealed = true;
        sanction.action = keccak256(abi.encode("appeal", sanction.action, evidenceHash));
        // A fresh quorum must review the appeal. Silence expires the sanction.
        sanction.readyAt = _now64() + VOTE_LIFETIME;
        emit SanctionAppealed(recordId, evidenceHash, sanction.readyAt);
    }

    function reviewAppeal(bytes32 recordId) external onlyValidator whenWritesOpen {
        Sanction memory sanction = sanctions[recordId];
        if (!sanction.appealed || block.timestamp > sanction.readyAt + VOTE_LIFETIME) revert InvalidSanction();
        _vote(sanction.action);
    }

    function executeSlash(bytes32 recordId) external nonReentrant {
        Sanction memory sanction = sanctions[recordId];
        if (
            sanction.readyAt == 0 || block.timestamp < sanction.readyAt
                || block.timestamp > sanction.readyAt + VOTE_LIFETIME || !_hasQuorum(sanction.action)
                || sanction.amount > bondBalance[recordId]
        ) revert InvalidSanction();
        delete sanctions[recordId];
        bondBalance[recordId] -= sanction.amount;
        blockedEntities[entityId[recordId]] = true;
        if (_records[recordId].status != Status.Revoked) _revoke(recordId, sanction.reason);
        if (!bondToken.transfer(sanction.beneficiary, sanction.amount)) revert BondUnavailable();
        emit BondSlashed(recordId, entityId[recordId], sanction.amount, sanction.beneficiary, sanction.reason);
    }

    function restoreEntity(bytes32 entity, bytes32 reason) external onlyValidator whenWritesOpen {
        if (!blockedEntities[entity] || reason == 0) revert InvalidAdmission();
        if (_delayedVote(keccak256(abi.encode("restoreEntity", entity, reason)))) blockedEntities[entity] = false;
    }

    function _vote(bytes32 action) private returns (bool) {
        _voteEpoch[action][msg.sender] = validatorEpoch[msg.sender];
        _voteTime[action][msg.sender] = _now64();
        emit DecisionVote(action, msg.sender);
        return _hasQuorum(action);
    }

    function _hasQuorum(bytes32 action) private view returns (bool) {
        return _voteCount(action, true) >= attestationThreshold;
    }

    function _hasAdmissionQuorum(bytes32 action) private view returns (bool) {
        return _voteCount(action, false) >= attestationThreshold;
    }

    function _voteCount(bytes32 action, bool expiring) private view returns (uint16 count) {
        for (uint256 i; i < _validatorList.length; i++) {
            address validator = _validatorList[i];
            uint64 votedAt = _voteTime[action][validator];
            if (
                votedAt != 0 && _voteEpoch[action][validator] == validatorEpoch[validator]
                    && (!expiring || block.timestamp <= votedAt + VOTE_LIFETIME)
            ) count++;
        }
    }

    function _delayedVote(bytes32 action) private returns (bool) {
        if (_decisionsUsed[action]) revert InvalidSanction();
        if (!_vote(action)) return false;
        uint64 ready = _decisionReadyAt[action];
        if (ready == 0 || block.timestamp > ready + VOTE_LIFETIME) {
            _decisionReadyAt[action] = _now64() + GOVERNANCE_DELAY_SECONDS;
            return false;
        }
        if (block.timestamp < ready) return false;
        _decisionsUsed[action] = true;
        return true;
    }
    error NotOwner();
    error NotController();
    error NotValidator();
    error WritesArePaused();
    error ZeroAddress();
    error ZeroHash();
    error EmptyURI();
    error UnknownRecord();
    error DomainAlreadyRegistered(bytes32 domainHash, bytes32 recordId);
    error InvalidStatus(Status expected, Status actual);
    error RevokedRecordHash(bytes32 recordHash);
    error RecordHashMismatch(bytes32 expected, bytes32 actual);
    error InvalidAttestationExpiry(uint64 expiresAt);
    error InvalidAttestationThreshold(uint16 threshold);
    error UnknownSupersession();
    error SupersessionNotApproved(bytes32 pendingRecordId);
    error SupersessionNotReady(uint64 availableAt);
    error SupersessionTargetChanged(bytes32 expectedRecordId, bytes32 actualRecordId);
    error FlagCooldownActive(bytes32 recordId, uint64 availableAt);
    error UnknownGovernanceAction(bytes32 actionHash);
    error GovernanceActionNotReady(uint64 availableAt);
    error GovernanceActionExpired(uint64 expiredAt);
    error NotPendingOwner();

    uint64 public constant SUPERSESSION_DELAY_SECONDS = 2 days;
    uint64 public constant FLAG_COOLDOWN_SECONDS = 1 hours;
    uint64 public constant GOVERNANCE_DELAY_SECONDS = 2 days;
    uint64 public constant GOVERNANCE_EXECUTION_WINDOW_SECONDS = 7 days;

    address public owner;
    address public pendingOwner;
    bool public writesPaused;
    uint16 public validatorCount;
    uint16 public attestationThreshold = 2;

    mapping(bytes32 => Record) private _records;
    mapping(bytes32 => mapping(address => Attestation)) private _attestations;
    mapping(bytes32 => Supersession) private _supersessions;
    mapping(bytes32 => bytes32) public recordIdForDomain;
    mapping(bytes32 => bool) public revokedRecordHashes;
    mapping(address => bool) public validators;
    mapping(address => uint64) public validatorEnabledAt;
    mapping(bytes32 => mapping(address => uint64)) public nextFlagAvailableAt;
    mapping(bytes32 => uint64) public governanceActionReadyAt;
    address[] private _validatorList;

    modifier onlyOwner() {
        _onlyOwner();
        _;
    }

    modifier onlyController(bytes32 recordId) {
        _onlyController(recordId);
        _;
    }

    modifier onlyValidator() {
        _onlyValidator();
        _;
    }

    modifier whenWritesOpen() {
        _whenWritesOpen();
        _;
    }

    constructor(address initialOwner, address token, uint256 registrationBond) {
        if (initialOwner == address(0) || token.code.length == 0 || registrationBond == 0) revert InvalidAdmission();
        owner = initialOwner;
        bondToken = IRegistryBondToken(token);
        minimumBond = registrationBond;
        emit OwnershipTransferred(address(0), owner);
    }

    function register(bytes32 domainHash, bytes32 recordHash, string calldata recordURI)
        external
        whenWritesOpen
        nonReentrant
        returns (bytes32 recordId)
    {
        _requireNonZero(domainHash);
        _requireActiveRecordHash(recordHash);
        _requireNonEmptyUri(recordURI);

        bytes32 existingRecordId = recordIdForDomain[domainHash];
        if (existingRecordId != bytes32(0)) {
            revert DomainAlreadyRegistered(domainHash, existingRecordId);
        }

        recordId = computeRecordId(domainHash, msg.sender);
        if (_records[recordId].status != Status.None) revert InvalidAdmission();
        _bindAdmission(recordId, domainHash, msg.sender, recordHash);
        _collectBond(recordId, msg.sender);
        _records[recordId] = Record({
            controller: msg.sender,
            recordHash: recordHash,
            domainHash: domainHash,
            updatedAt: _now64(),
            attestedAt: 0,
            attestationExpiresAt: 0,
            attestationGeneration: 0,
            attestationCount: 0,
            status: Status.Active
        });
        recordIdForDomain[domainHash] = recordId;

        emit MerchantRegistered(recordId, msg.sender, domainHash, recordHash, recordURI);
    }

    function update(bytes32 recordId, bytes32 recordHash, string calldata recordURI)
        external
        whenWritesOpen
        onlyController(recordId)
    {
        _requireActiveRecordHash(recordHash);
        _requireNonEmptyUri(recordURI);

        Record storage stored = _records[recordId];
        _requireStatus(stored, Status.Active);
        _bindAdmission(recordId, stored.domainHash, msg.sender, recordHash);
        stored.recordHash = recordHash;
        stored.updatedAt = _now64();
        stored.attestedAt = 0;
        stored.attestationExpiresAt = 0;
        stored.attestationGeneration += 1;
        stored.attestationCount = 0;

        emit MerchantUpdated(recordId, recordHash, recordURI);
    }

    function setController(bytes32 recordId, address newController, bytes32 newRecordHash, string calldata recordURI)
        external
        whenWritesOpen
        onlyController(recordId)
    {
        if (newController == address(0)) revert ZeroAddress();
        _requireActiveRecordHash(newRecordHash);
        _requireNonEmptyUri(recordURI);

        Record storage stored = _records[recordId];
        _requireStatus(stored, Status.Active);
        _bindAdmission(recordId, stored.domainHash, newController, newRecordHash);
        stored.controller = newController;
        stored.recordHash = newRecordHash;
        stored.updatedAt = _now64();
        stored.attestedAt = 0;
        stored.attestationExpiresAt = 0;
        stored.attestationGeneration += 1;
        stored.attestationCount = 0;

        emit ControllerChanged(recordId, newController, newRecordHash, recordURI);
    }

    function revoke(bytes32 recordId, bytes32 reasonHash) external whenWritesOpen onlyController(recordId) {
        _revoke(recordId, reasonHash);
    }

    function forceRevoke(bytes32 recordId, bytes32 reasonHash) external whenWritesOpen onlyOwner {
        _consumeGovernanceAction(forceRevokeActionHash(recordId, reasonHash));
        _revoke(recordId, reasonHash);
        emit MerchantForceRevoked(recordId, msg.sender, reasonHash);
    }

    function requestSupersession(
        bytes32 domainHash,
        bytes32 recordHash,
        bytes32 reasonHash,
        string calldata recordURI,
        string calldata evidenceURI
    ) external whenWritesOpen returns (bytes32 pendingRecordId, uint64 availableAt) {
        _requireNonZero(domainHash);
        _requireActiveRecordHash(recordHash);
        _requireNonZero(reasonHash);
        _requireNonEmptyUri(recordURI);
        _requireNonEmptyUri(evidenceURI);

        bytes32 previousRecordId = recordIdForDomain[domainHash];
        if (previousRecordId == bytes32(0)) {
            revert UnknownRecord();
        }

        pendingRecordId = computeRecordId(domainHash, msg.sender);
        if (pendingRecordId == previousRecordId) {
            revert DomainAlreadyRegistered(domainHash, previousRecordId);
        }

        if (_records[pendingRecordId].status != Status.None) revert InvalidAdmission();
        _bindAdmission(pendingRecordId, domainHash, msg.sender, recordHash);
        uint64 requestedAt = _now64();
        availableAt = requestedAt + SUPERSESSION_DELAY_SECONDS;
        _supersessions[pendingRecordId] = Supersession({
            controller: msg.sender,
            domainHash: domainHash,
            previousRecordId: previousRecordId,
            recordHash: recordHash,
            reasonHash: reasonHash,
            requestedAt: requestedAt,
            approvedBy: address(0),
            approvedAt: 0
        });

        emit SupersessionRequested(
            domainHash,
            previousRecordId,
            pendingRecordId,
            msg.sender,
            recordHash,
            reasonHash,
            availableAt,
            recordURI,
            evidenceURI
        );
    }

    function approveSupersession(bytes32 pendingRecordId, bytes32 recordHash, string calldata evidenceURI)
        external
        whenWritesOpen
        returns (uint64 availableAt)
    {
        _onlyValidator();
        _requireNonEmptyUri(evidenceURI);

        Supersession storage pending = _supersessions[pendingRecordId];
        if (pending.controller == address(0)) revert UnknownSupersession();
        if (recordHash != pending.recordHash) {
            revert RecordHashMismatch(pending.recordHash, recordHash);
        }

        if (!_vote(keccak256(abi.encode("supersession", pendingRecordId, recordHash, pending.requestedAt)))) return 0;
        uint64 approvedAt = _now64();
        availableAt = approvedAt + SUPERSESSION_DELAY_SECONDS;
        pending.approvedBy = msg.sender;
        pending.approvedAt = approvedAt;

        emit SupersessionApproved(
            pending.domainHash,
            pending.previousRecordId,
            pendingRecordId,
            msg.sender,
            recordHash,
            availableAt,
            evidenceURI
        );
    }

    function cancelSupersession(bytes32 pendingRecordId, bytes32 reasonHash) external whenWritesOpen {
        _requireNonZero(reasonHash);

        Supersession memory pending = _supersessions[pendingRecordId];
        if (pending.controller == address(0)) revert UnknownSupersession();

        if (msg.sender != pending.controller) {
            revert NotController();
        }

        delete _supersessions[pendingRecordId];
        emit SupersessionCanceled(pendingRecordId, msg.sender, reasonHash);
    }

    function activateSupersession(bytes32 pendingRecordId, string calldata recordURI)
        external
        whenWritesOpen
        nonReentrant
    {
        _requireNonEmptyUri(recordURI);

        Supersession memory pending = _supersessions[pendingRecordId];
        if (pending.controller == address(0)) revert UnknownSupersession();
        if (msg.sender != pending.controller) revert NotController();
        if (pending.approvedAt == 0) revert SupersessionNotApproved(pendingRecordId);

        uint64 availableAt = pending.approvedAt + SUPERSESSION_DELAY_SECONDS;
        if (block.timestamp < availableAt) {
            revert SupersessionNotReady(availableAt);
        }

        bytes32 currentRecordId = recordIdForDomain[pending.domainHash];
        if (currentRecordId != pending.previousRecordId) {
            revert SupersessionTargetChanged(pending.previousRecordId, currentRecordId);
        }

        if (!_hasQuorum(
                keccak256(abi.encode("supersession", pendingRecordId, pending.recordHash, pending.requestedAt))
            )) revert InvalidAdmission();
        _bindAdmission(pendingRecordId, pending.domainHash, pending.controller, pending.recordHash);
        _collectBond(pendingRecordId, pending.controller);
        _revoke(pending.previousRecordId, pending.reasonHash);
        _requireActiveRecordHash(pending.recordHash);

        _records[pendingRecordId] = Record({
            controller: pending.controller,
            recordHash: pending.recordHash,
            domainHash: pending.domainHash,
            updatedAt: _now64(),
            attestedAt: 0,
            attestationExpiresAt: 0,
            attestationGeneration: 0,
            attestationCount: 0,
            status: Status.Active
        });
        recordIdForDomain[pending.domainHash] = pendingRecordId;
        delete _supersessions[pendingRecordId];

        emit SupersessionActivated(
            pending.domainHash,
            pending.previousRecordId,
            pendingRecordId,
            pending.controller,
            pending.recordHash,
            recordURI
        );
        emit MerchantRegistered(pendingRecordId, pending.controller, pending.domainHash, pending.recordHash, recordURI);
    }

    function attest(
        bytes32 recordId,
        bytes32 recordHash,
        bytes32 resultHash,
        uint64 expiresAt,
        string calldata evidenceURI
    ) external whenWritesOpen onlyValidator {
        _requireNonZero(resultHash);
        _requireNonEmptyUri(evidenceURI);

        Record storage stored = _existingRecord(recordId);
        _requireStatus(stored, Status.Active);
        if (recordHash != stored.recordHash) {
            revert RecordHashMismatch(stored.recordHash, recordHash);
        }
        if (expiresAt <= block.timestamp) {
            revert InvalidAttestationExpiry(expiresAt);
        }

        _attestationEpoch[recordId][msg.sender] = validatorEpoch[msg.sender];
        Attestation storage validatorAttestation = _attestations[recordId][msg.sender];
        uint64 now64 = _now64();
        validatorAttestation.recordHash = recordHash;
        validatorAttestation.resultHash = resultHash;
        validatorAttestation.attestedAt = now64;
        validatorAttestation.expiresAt = expiresAt;
        validatorAttestation.generation = stored.attestationGeneration;
        _syncAttestationSummary(recordId, stored);

        emit MerchantAttested(recordId, msg.sender, recordHash, resultHash, expiresAt, evidenceURI);
    }

    function suspend(bytes32 recordId, bytes32 reasonHash) external whenWritesOpen {
        _onlyValidator();
        _requireNonZero(reasonHash);

        Record storage stored = _existingRecord(recordId);
        _requireStatus(stored, Status.Active);
        if (!_delayedVote(keccak256(abi.encode("suspend", recordId, stored.attestationGeneration, reasonHash)))) {
            return;
        }
        stored.status = Status.Suspended;
        stored.updatedAt = _now64();
        stored.attestedAt = 0;
        stored.attestationExpiresAt = 0;
        stored.attestationGeneration += 1;
        stored.attestationCount = 0;

        emit MerchantSuspended(recordId, reasonHash);
    }

    function unsuspend(bytes32 recordId) external whenWritesOpen {
        _onlyValidator();

        Record storage stored = _existingRecord(recordId);
        _requireStatus(stored, Status.Suspended);
        if (!_delayedVote(keccak256(abi.encode("unsuspend", recordId, stored.attestationGeneration)))) return;
        stored.attestationGeneration += 1;
        stored.status = Status.Active;
        stored.updatedAt = _now64();

        emit MerchantUnsuspended(recordId);
    }

    function flag(bytes32 recordId, bytes32 challengeType, string calldata evidenceURI) external whenWritesOpen {
        _existingRecord(recordId);
        _requireNonZero(challengeType);
        _requireNonEmptyUri(evidenceURI);

        uint64 availableAt = nextFlagAvailableAt[recordId][msg.sender];
        if (block.timestamp < availableAt) {
            revert FlagCooldownActive(recordId, availableAt);
        }
        nextFlagAvailableAt[recordId][msg.sender] = _now64() + FLAG_COOLDOWN_SECONDS;

        emit MerchantFlagged(recordId, msg.sender, challengeType, evidenceURI);
    }

    function record(bytes32 recordId) external view returns (Record memory) {
        Record memory stored = _records[recordId];
        if (stored.status == Status.Active) {
            (stored.attestationCount, stored.attestedAt, stored.attestationExpiresAt) =
                _attestationSummary(recordId, stored.recordHash, stored.attestationGeneration);
        }
        return stored;
    }

    function attestation(bytes32 recordId, address validator) external view returns (Attestation memory) {
        return _attestations[recordId][validator];
    }

    function supersession(bytes32 pendingRecordId) external view returns (Supersession memory) {
        return _supersessions[pendingRecordId];
    }

    function isAttestationCurrent(bytes32 recordId) external view returns (bool) {
        Record storage stored = _records[recordId];
        if (stored.status != Status.Active) return false;
        (uint16 count,, uint64 expiresAt) =
            _attestationSummary(recordId, stored.recordHash, stored.attestationGeneration);
        return count >= attestationThreshold && expiresAt > block.timestamp;
    }

    function computeRecordId(bytes32 domainHash, address controller) public view returns (bytes32) {
        if (controller == address(0)) revert ZeroAddress();
        return
            keccak256(
                abi.encode("agentcart.merchant.registry.v2", block.chainid, address(this), domainHash, controller)
            );
    }

    function validatorActionHash(address validator, bool enabled) public view returns (bytes32) {
        return
            keccak256(
                abi.encode("agentcart.registry.setValidator.v1", block.chainid, address(this), validator, enabled)
            );
    }

    function attestationThresholdActionHash(uint16 threshold) public view returns (bytes32) {
        return
            keccak256(
                abi.encode("agentcart.registry.setAttestationThreshold.v1", block.chainid, address(this), threshold)
            );
    }

    function forceRevokeActionHash(bytes32 recordId, bytes32 reasonHash) public view returns (bytes32) {
        return
            keccak256(
                abi.encode("agentcart.registry.forceRevoke.v1", block.chainid, address(this), recordId, reasonHash)
            );
    }

    function scheduleGovernanceAction(bytes32 actionHash) external onlyOwner returns (uint64 readyAt) {
        _requireNonZero(actionHash);
        readyAt = _now64() + GOVERNANCE_DELAY_SECONDS;
        governanceActionReadyAt[actionHash] = readyAt;
        emit GovernanceActionScheduled(actionHash, readyAt);
    }

    function cancelGovernanceAction(bytes32 actionHash) external onlyOwner {
        _requireNonZero(actionHash);
        delete governanceActionReadyAt[actionHash];
        emit GovernanceActionCanceled(actionHash);
    }

    function setValidator(address validator, bool enabled) external onlyOwner {
        if (validator == address(0)) revert ZeroAddress();
        _consumeGovernanceAction(validatorActionHash(validator, enabled));
        bool current = validators[validator];
        if (current != enabled) {
            if (enabled && validatorCount >= MAX_VALIDATORS) revert ValidatorSetBound();
            if (!enabled && validatorCount <= attestationThreshold) revert ValidatorSetBound();
            validatorCount = enabled ? validatorCount + 1 : validatorCount - 1;
            validatorEpoch[validator] += 1;
            if (enabled) {
                _validatorList.push(validator);
            } else {
                for (uint256 i; i < _validatorList.length; i++) {
                    if (_validatorList[i] == validator) {
                        _validatorList[i] = _validatorList[_validatorList.length - 1];
                        _validatorList.pop();
                        break;
                    }
                }
            }
            validatorEnabledAt[validator] = enabled ? _now64() : 0;
        }
        validators[validator] = enabled;
        emit ValidatorSet(validator, enabled);
    }

    function setAttestationThreshold(uint16 threshold) external onlyOwner {
        if (threshold < 2 || threshold > validatorCount) revert InvalidAttestationThreshold(threshold);
        _consumeGovernanceAction(attestationThresholdActionHash(threshold));
        attestationThreshold = threshold;
        emit AttestationThresholdSet(threshold);
    }

    function setWritesPaused(bool paused) external onlyOwner {
        _consumeGovernanceAction(keccak256(abi.encode("pause", paused)));
        writesPaused = paused;
        emit WritesPaused(paused);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
        _consumeGovernanceAction(keccak256(abi.encode("owner", newOwner)));
        pendingOwner = newOwner;
        emit OwnershipTransferStarted(owner, newOwner);
    }

    function acceptOwnership() external {
        if (msg.sender != pendingOwner) revert NotPendingOwner();
        address previousOwner = owner;
        owner = msg.sender;
        pendingOwner = address(0);
        emit OwnershipTransferred(previousOwner, msg.sender);
    }

    function _existingRecord(bytes32 recordId) private view returns (Record storage stored) {
        stored = _records[recordId];
        if (stored.status == Status.None) revert UnknownRecord();
    }

    function _onlyOwner() private view {
        if (msg.sender != owner) revert NotOwner();
    }

    function _onlyController(bytes32 recordId) private view {
        Record storage stored = _existingRecord(recordId);
        if (msg.sender != stored.controller) revert NotController();
    }

    function _onlyValidator() private view {
        if (!validators[msg.sender]) revert NotValidator();
    }

    function _requireOwnerOrValidator() private view {
        _onlyValidator();
    }

    function _whenWritesOpen() private view {
        if (writesPaused) revert WritesArePaused();
    }

    function _requireActiveRecordHash(bytes32 recordHash) private view {
        _requireNonZero(recordHash);
        if (revokedRecordHashes[recordHash]) {
            revert RevokedRecordHash(recordHash);
        }
    }

    function _requireNonZero(bytes32 value) private pure {
        if (value == bytes32(0)) revert ZeroHash();
    }

    function _requireNonEmptyUri(string calldata uri) private pure {
        if (bytes(uri).length == 0 || bytes(uri).length > 4096) revert EmptyURI();
    }

    function _requireStatus(Record storage stored, Status expected) private view {
        if (stored.status != expected) {
            revert InvalidStatus(expected, stored.status);
        }
    }

    function _revoke(bytes32 recordId, bytes32 reasonHash) private {
        _requireNonZero(reasonHash);

        Record storage stored = _records[recordId];
        if (stored.status == Status.None) revert UnknownRecord();
        if (stored.status == Status.Revoked) {
            revert InvalidStatus(Status.Active, stored.status);
        }
        bondExitAt[recordId] = _now64() + BOND_EXIT_DELAY;
        revokedRecordHashes[stored.recordHash] = true;
        delete recordIdForDomain[stored.domainHash];
        stored.status = Status.Revoked;
        stored.updatedAt = _now64();
        stored.attestedAt = 0;
        stored.attestationExpiresAt = 0;
        stored.attestationGeneration += 1;
        stored.attestationCount = 0;

        emit MerchantRevoked(recordId, reasonHash);
    }

    function _consumeGovernanceAction(bytes32 actionHash) private {
        uint64 availableAt = governanceActionReadyAt[actionHash];
        if (availableAt == 0) revert UnknownGovernanceAction(actionHash);
        if (block.timestamp < availableAt) revert GovernanceActionNotReady(availableAt);
        uint64 expiredAt = availableAt + GOVERNANCE_EXECUTION_WINDOW_SECONDS;
        if (block.timestamp > expiredAt) revert GovernanceActionExpired(expiredAt);
        delete governanceActionReadyAt[actionHash];
    }

    function _syncAttestationSummary(bytes32 recordId, Record storage stored) private {
        (uint16 count, uint64 attestedAt, uint64 expiresAt) =
            _attestationSummary(recordId, stored.recordHash, stored.attestationGeneration);
        stored.attestationCount = count;
        stored.attestedAt = attestedAt;
        stored.attestationExpiresAt = expiresAt;
    }

    function _attestationSummary(bytes32 recordId, bytes32 recordHash, uint64 recordGeneration)
        private
        view
        returns (uint16 count, uint64 attestedAt, uint64 expiresAt)
    {
        uint64[] memory expiries = new uint64[](_validatorList.length);
        for (uint256 index = 0; index < _validatorList.length; index++) {
            address validator = _validatorList[index];
            if (!validators[validator] || _attestationEpoch[recordId][validator] != validatorEpoch[validator]) {
                continue;
            }

            Attestation storage stored = _attestations[recordId][validator];
            if (stored.generation != recordGeneration) continue;
            if (stored.attestedAt < validatorEnabledAt[validator]) continue;
            if (stored.recordHash != recordHash || stored.expiresAt <= block.timestamp) continue;

            expiries[count] = stored.expiresAt;
            count++;
            if (stored.attestedAt > attestedAt) {
                attestedAt = stored.attestedAt;
            }
        }

        if (count < attestationThreshold) {
            return (count, 0, 0);
        }
        expiresAt = _quorumExpiresAt(expiries, count, attestationThreshold);
    }

    function _quorumExpiresAt(uint64[] memory expiries, uint16 count, uint16 threshold) private pure returns (uint64) {
        for (uint16 left = 0; left < count; left++) {
            for (uint16 right = left + 1; right < count; right++) {
                if (expiries[right] < expiries[left]) {
                    uint64 current = expiries[left];
                    expiries[left] = expiries[right];
                    expiries[right] = current;
                }
            }
        }
        return expiries[uint256(count - threshold)];
    }

    function _now64() private view returns (uint64) {
        return uint64(block.timestamp);
    }
}
