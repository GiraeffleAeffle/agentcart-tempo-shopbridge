// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IAgentCartMerchantRegistry} from "./interfaces/IAgentCartMerchantRegistry.sol";

contract AgentCartMerchantRegistry is IAgentCartMerchantRegistry {
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
    uint64 public constant GOVERNANCE_DELAY_SECONDS = 1 days;
    uint64 public constant GOVERNANCE_EXECUTION_WINDOW_SECONDS = 7 days;

    address public owner;
    address public pendingOwner;
    bool public writesPaused;
    uint16 public validatorCount;
    uint16 public attestationThreshold = 1;

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
    mapping(address => bool) private _validatorListed;

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

    constructor(address initialOwner) {
        owner = initialOwner == address(0) ? msg.sender : initialOwner;
        emit OwnershipTransferred(address(0), owner);
    }

    function register(bytes32 domainHash, bytes32 recordHash, string calldata recordURI)
        external
        whenWritesOpen
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
        stored.recordHash = recordHash;
        stored.updatedAt = _now64();
        stored.attestedAt = 0;
        stored.attestationExpiresAt = 0;
        stored.attestationGeneration += 1;
        stored.attestationCount = 0;

        emit MerchantUpdated(recordId, recordHash, recordURI);
    }

    function setController(
        bytes32 recordId,
        address newController,
        bytes32 newRecordHash,
        string calldata recordURI
    ) external whenWritesOpen onlyController(recordId) {
        if (newController == address(0)) revert ZeroAddress();
        _requireActiveRecordHash(newRecordHash);
        _requireNonEmptyUri(recordURI);

        Record storage stored = _records[recordId];
        _requireStatus(stored, Status.Active);
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
        _requireOwnerOrValidator();
        _requireNonEmptyUri(evidenceURI);

        Supersession storage pending = _supersessions[pendingRecordId];
        if (pending.controller == address(0)) revert UnknownSupersession();
        if (recordHash != pending.recordHash) {
            revert RecordHashMismatch(pending.recordHash, recordHash);
        }

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

        Record storage previous = _records[pending.previousRecordId];
        bool previousController = previous.status == Status.Active && previous.controller == msg.sender;
        if (msg.sender != pending.controller && msg.sender != owner && !validators[msg.sender] && !previousController) {
            revert NotController();
        }

        delete _supersessions[pendingRecordId];
        emit SupersessionCanceled(pendingRecordId, msg.sender, reasonHash);
    }

    function activateSupersession(bytes32 pendingRecordId, string calldata recordURI) external whenWritesOpen {
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
        if (msg.sender != owner && !validators[msg.sender]) revert NotValidator();
        _requireNonZero(reasonHash);

        Record storage stored = _existingRecord(recordId);
        _requireStatus(stored, Status.Active);
        stored.status = Status.Suspended;
        stored.updatedAt = _now64();
        stored.attestedAt = 0;
        stored.attestationExpiresAt = 0;
        stored.attestationGeneration += 1;
        stored.attestationCount = 0;

        emit MerchantSuspended(recordId, reasonHash);
    }

    function unsuspend(bytes32 recordId) external whenWritesOpen {
        if (msg.sender != owner && !validators[msg.sender]) revert NotValidator();

        Record storage stored = _existingRecord(recordId);
        _requireStatus(stored, Status.Suspended);
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
                abi.encode("agentcart.merchant.registry.v1", block.chainid, address(this), domainHash, controller)
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
            validatorCount = enabled ? validatorCount + 1 : validatorCount - 1;
            if (enabled && !_validatorListed[validator]) {
                _validatorListed[validator] = true;
                _validatorList.push(validator);
            }
            validatorEnabledAt[validator] = enabled ? _now64() : 0;
        }
        validators[validator] = enabled;
        emit ValidatorSet(validator, enabled);
    }

    function setAttestationThreshold(uint16 threshold) external onlyOwner {
        if (threshold == 0) revert InvalidAttestationThreshold(threshold);
        _consumeGovernanceAction(attestationThresholdActionHash(threshold));
        attestationThreshold = threshold;
        emit AttestationThresholdSet(threshold);
    }

    function setWritesPaused(bool paused) external onlyOwner {
        writesPaused = paused;
        emit WritesPaused(paused);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
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
        if (msg.sender != owner && !validators[msg.sender]) revert NotValidator();
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
        if (bytes(uri).length == 0) revert EmptyURI();
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
            if (!validators[validator]) continue;

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
