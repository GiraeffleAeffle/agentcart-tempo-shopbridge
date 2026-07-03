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

    address public owner;
    bool public writesPaused;

    mapping(bytes32 => Record) private _records;
    mapping(bytes32 => bytes32) public recordIdForDomain;
    mapping(bytes32 => bool) public revokedRecordHashes;
    mapping(address => bool) public validators;

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

        emit MerchantUpdated(recordId, recordHash, recordURI);
    }

    function setController(bytes32 recordId, address newController) external whenWritesOpen onlyController(recordId) {
        if (newController == address(0)) revert ZeroAddress();

        Record storage stored = _records[recordId];
        _requireStatus(stored, Status.Active);
        stored.controller = newController;
        stored.updatedAt = _now64();
        stored.attestedAt = 0;
        stored.attestationExpiresAt = 0;

        emit ControllerChanged(recordId, newController);
    }

    function revoke(bytes32 recordId, bytes32 reasonHash) external whenWritesOpen onlyController(recordId) {
        _requireNonZero(reasonHash);

        Record storage stored = _records[recordId];
        if (stored.status == Status.Revoked) {
            revert InvalidStatus(Status.Active, stored.status);
        }
        revokedRecordHashes[stored.recordHash] = true;
        delete recordIdForDomain[stored.domainHash];
        stored.status = Status.Revoked;
        stored.updatedAt = _now64();
        stored.attestedAt = 0;
        stored.attestationExpiresAt = 0;

        emit MerchantRevoked(recordId, reasonHash);
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

        stored.attestedAt = _now64();
        stored.attestationExpiresAt = expiresAt;

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

        emit MerchantFlagged(recordId, msg.sender, challengeType, evidenceURI);
    }

    function record(bytes32 recordId) external view returns (Record memory) {
        return _records[recordId];
    }

    function isAttestationCurrent(bytes32 recordId) external view returns (bool) {
        Record storage stored = _records[recordId];
        return
            stored.status == Status.Active && stored.attestedAt != 0 && stored.attestationExpiresAt >= block.timestamp;
    }

    function computeRecordId(bytes32 domainHash, address controller) public view returns (bytes32) {
        if (controller == address(0)) revert ZeroAddress();
        return
            keccak256(
                abi.encode("agentcart.merchant.registry.v1", block.chainid, address(this), domainHash, controller)
            );
    }

    function setValidator(address validator, bool enabled) external onlyOwner {
        if (validator == address(0)) revert ZeroAddress();
        validators[validator] = enabled;
        emit ValidatorSet(validator, enabled);
    }

    function setWritesPaused(bool paused) external onlyOwner {
        writesPaused = paused;
        emit WritesPaused(paused);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
        address previousOwner = owner;
        owner = newOwner;
        emit OwnershipTransferred(previousOwner, newOwner);
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

    function _now64() private view returns (uint64) {
        return uint64(block.timestamp);
    }
}
