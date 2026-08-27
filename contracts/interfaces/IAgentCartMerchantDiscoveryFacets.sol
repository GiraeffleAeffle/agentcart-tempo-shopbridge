// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IAgentCartMerchantDiscoveryFacets {
    struct FacetState {
        bytes32 recordHash;
        bytes32 categorySetHash;
        uint64 generation;
        uint8 categoryCount;
    }

    function registry() external view returns (address);

    function publish(bytes32 recordId, bytes32 expectedRecordHash, bytes32[] calldata categoryHashes)
        external
        returns (bytes32 categorySetHash, uint64 generation);

    function clear(bytes32 recordId, bytes32 expectedRecordHash) external returns (uint64 generation);

    function facetState(bytes32 recordId) external view returns (FacetState memory);

    function isCurrent(bytes32 recordId) external view returns (bool);

    event CategorySetPublished(
        bytes32 indexed recordId,
        bytes32 indexed recordHash,
        bytes32 indexed categorySetHash,
        uint64 generation,
        uint8 categoryCount
    );

    event CategoryDeclared(bytes32 indexed categoryHash, bytes32 indexed recordId, uint64 indexed generation);
}
