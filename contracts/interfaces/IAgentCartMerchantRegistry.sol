// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IAgentCartMerchantRegistry {
    enum Status {
        None,
        Active,
        Revoked,
        Suspended
    }

    struct Record {
        address controller;
        bytes32 recordHash;
        bytes32 domainHash;
        uint64 updatedAt;
        uint64 attestedAt;
        uint64 attestationExpiresAt;
        uint64 attestationGeneration;
        uint16 attestationCount;
        Status status;
    }

    struct Attestation {
        bytes32 recordHash;
        bytes32 resultHash;
        uint64 attestedAt;
        uint64 expiresAt;
        uint64 generation;
    }

    struct Supersession {
        address controller;
        bytes32 domainHash;
        bytes32 previousRecordId;
        bytes32 recordHash;
        bytes32 reasonHash;
        uint64 requestedAt;
        address approvedBy;
        uint64 approvedAt;
    }

    function register(bytes32 domainHash, bytes32 recordHash, string calldata recordURI)
        external
        returns (bytes32 recordId);

    function update(bytes32 recordId, bytes32 recordHash, string calldata recordURI) external;

    function setController(bytes32 recordId, address newController) external;

    function revoke(bytes32 recordId, bytes32 reasonHash) external;

    function forceRevoke(bytes32 recordId, bytes32 reasonHash) external;

    function requestSupersession(
        bytes32 domainHash,
        bytes32 recordHash,
        bytes32 reasonHash,
        string calldata recordURI,
        string calldata evidenceURI
    ) external returns (bytes32 pendingRecordId, uint64 availableAt);

    function approveSupersession(bytes32 pendingRecordId, bytes32 recordHash, string calldata evidenceURI)
        external
        returns (uint64 availableAt);

    function cancelSupersession(bytes32 pendingRecordId, bytes32 reasonHash) external;

    function activateSupersession(bytes32 pendingRecordId, string calldata recordURI) external;

    function attest(
        bytes32 recordId,
        bytes32 recordHash,
        bytes32 resultHash,
        uint64 expiresAt,
        string calldata evidenceURI
    ) external;

    function suspend(bytes32 recordId, bytes32 reasonHash) external;

    function unsuspend(bytes32 recordId) external;

    function flag(bytes32 recordId, bytes32 challengeType, string calldata evidenceURI) external;

    function record(bytes32 recordId) external view returns (Record memory);

    function attestation(bytes32 recordId, address validator) external view returns (Attestation memory);

    function supersession(bytes32 pendingRecordId) external view returns (Supersession memory);

    function recordIdForDomain(bytes32 domainHash) external view returns (bytes32);

    function revokedRecordHashes(bytes32 recordHash) external view returns (bool);

    function validators(address validator) external view returns (bool);

    function validatorEnabledAt(address validator) external view returns (uint64);

    function validatorCount() external view returns (uint16);

    function attestationThreshold() external view returns (uint16);

    function nextFlagAvailableAt(bytes32 recordId, address flagger) external view returns (uint64);

    function governanceActionReadyAt(bytes32 actionHash) external view returns (uint64);

    function owner() external view returns (address);

    function pendingOwner() external view returns (address);

    function writesPaused() external view returns (bool);

    function isAttestationCurrent(bytes32 recordId) external view returns (bool);

    function validatorActionHash(address validator, bool enabled) external view returns (bytes32);

    function attestationThresholdActionHash(uint16 threshold) external view returns (bytes32);

    function forceRevokeActionHash(bytes32 recordId, bytes32 reasonHash) external view returns (bytes32);

    function scheduleGovernanceAction(bytes32 actionHash) external returns (uint64 readyAt);

    function cancelGovernanceAction(bytes32 actionHash) external;

    function setValidator(address validator, bool enabled) external;

    function setAttestationThreshold(uint16 threshold) external;

    function setWritesPaused(bool paused) external;

    function transferOwnership(address newOwner) external;

    function acceptOwnership() external;

    event MerchantRegistered(
        bytes32 indexed recordId,
        address indexed controller,
        bytes32 indexed domainHash,
        bytes32 recordHash,
        string recordURI
    );

    event MerchantUpdated(bytes32 indexed recordId, bytes32 recordHash, string recordURI);

    event ControllerChanged(bytes32 indexed recordId, address indexed newController);

    event MerchantRevoked(bytes32 indexed recordId, bytes32 reasonHash);

    event MerchantForceRevoked(bytes32 indexed recordId, address indexed operator, bytes32 reasonHash);

    event SupersessionRequested(
        bytes32 indexed domainHash,
        bytes32 indexed previousRecordId,
        bytes32 indexed pendingRecordId,
        address controller,
        bytes32 recordHash,
        bytes32 reasonHash,
        uint64 availableAt,
        string recordURI,
        string evidenceURI
    );

    event SupersessionApproved(
        bytes32 indexed domainHash,
        bytes32 indexed previousRecordId,
        bytes32 indexed pendingRecordId,
        address approver,
        bytes32 recordHash,
        uint64 availableAt,
        string evidenceURI
    );

    event SupersessionCanceled(bytes32 indexed pendingRecordId, address indexed operator, bytes32 reasonHash);

    event SupersessionActivated(
        bytes32 indexed domainHash,
        bytes32 indexed previousRecordId,
        bytes32 indexed recordId,
        address controller,
        bytes32 recordHash,
        string recordURI
    );

    event MerchantAttested(
        bytes32 indexed recordId,
        address indexed validator,
        bytes32 recordHash,
        bytes32 resultHash,
        uint64 expiresAt,
        string evidenceURI
    );

    event MerchantSuspended(bytes32 indexed recordId, bytes32 reasonHash);

    event MerchantUnsuspended(bytes32 indexed recordId);

    event MerchantFlagged(bytes32 indexed recordId, address indexed flagger, bytes32 challengeType, string evidenceURI);

    event ValidatorSet(address indexed validator, bool enabled);

    event AttestationThresholdSet(uint16 threshold);

    event GovernanceActionScheduled(bytes32 indexed actionHash, uint64 readyAt);

    event GovernanceActionCanceled(bytes32 indexed actionHash);

    event WritesPaused(bool paused);

    event OwnershipTransferStarted(address indexed previousOwner, address indexed newOwner);

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
}
