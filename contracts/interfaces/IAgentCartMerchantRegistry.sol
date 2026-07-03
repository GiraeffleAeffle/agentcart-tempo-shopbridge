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
        Status status;
    }

    struct Supersession {
        address controller;
        bytes32 domainHash;
        bytes32 previousRecordId;
        bytes32 recordHash;
        bytes32 reasonHash;
        uint64 requestedAt;
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

    function supersession(bytes32 pendingRecordId) external view returns (Supersession memory);

    function recordIdForDomain(bytes32 domainHash) external view returns (bytes32);

    function revokedRecordHashes(bytes32 recordHash) external view returns (bool);

    function validators(address validator) external view returns (bool);

    function owner() external view returns (address);

    function writesPaused() external view returns (bool);

    function isAttestationCurrent(bytes32 recordId) external view returns (bool);

    function setValidator(address validator, bool enabled) external;

    function setWritesPaused(bool paused) external;

    function transferOwnership(address newOwner) external;

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

    event WritesPaused(bool paused);

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
}
