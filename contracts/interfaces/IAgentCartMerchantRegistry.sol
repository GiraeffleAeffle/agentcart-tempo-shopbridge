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

    function register(
        bytes32 domainHash,
        bytes32 recordHash,
        string calldata recordURI
    ) external returns (bytes32 recordId);

    function update(
        bytes32 recordId,
        bytes32 recordHash,
        string calldata recordURI
    ) external;

    function setController(bytes32 recordId, address newController) external;

    function revoke(bytes32 recordId, bytes32 reasonHash) external;

    function attest(
        bytes32 recordId,
        bytes32 recordHash,
        bytes32 resultHash,
        uint64 expiresAt,
        string calldata evidenceURI
    ) external;

    function suspend(bytes32 recordId, bytes32 reasonHash) external;

    function unsuspend(bytes32 recordId) external;

    function flag(
        bytes32 recordId,
        bytes32 challengeType,
        string calldata evidenceURI
    ) external;

    event MerchantRegistered(
        bytes32 indexed recordId,
        address indexed controller,
        bytes32 indexed domainHash,
        bytes32 recordHash,
        string recordURI
    );

    event MerchantUpdated(
        bytes32 indexed recordId,
        bytes32 recordHash,
        string recordURI
    );

    event ControllerChanged(
        bytes32 indexed recordId,
        address indexed newController
    );

    event MerchantRevoked(bytes32 indexed recordId, bytes32 reasonHash);

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

    event MerchantFlagged(
        bytes32 indexed recordId,
        address indexed flagger,
        bytes32 challengeType,
        string evidenceURI
    );
}
