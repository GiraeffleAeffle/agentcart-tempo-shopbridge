// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IAgentCartMerchantRegistry} from "./interfaces/IAgentCartMerchantRegistry.sol";
import {IAgentCartMerchantDiscoveryFacets} from "./interfaces/IAgentCartMerchantDiscoveryFacets.sol";

contract AgentCartMerchantDiscoveryFacets is IAgentCartMerchantDiscoveryFacets {
    error ZeroAddress();
    error NotController();
    error RecordNotActive();
    error RecordHashMismatch(bytes32 expected, bytes32 actual);
    error CategoryCountInvalid(uint256 count);
    error CategoryHashZero(uint256 index);
    error CategoryHashesNotStrictlySorted(uint256 index);

    uint256 public constant MAX_CATEGORY_COUNT = 8;

    IAgentCartMerchantRegistry private immutable _registry;
    mapping(bytes32 => FacetState) private _facetStates;

    constructor(address registryAddress) {
        if (registryAddress == address(0)) revert ZeroAddress();
        _registry = IAgentCartMerchantRegistry(registryAddress);
    }

    function registry() external view returns (address) {
        return address(_registry);
    }

    function publish(bytes32 recordId, bytes32 expectedRecordHash, bytes32[] calldata categoryHashes)
        external
        returns (bytes32 categorySetHash, uint64 generation)
    {
        IAgentCartMerchantRegistry.Record memory current = _requireCurrentController(recordId, expectedRecordHash);
        uint256 count = categoryHashes.length;
        if (count == 0 || count > MAX_CATEGORY_COUNT) revert CategoryCountInvalid(count);

        bytes32 previous;
        for (uint256 index = 0; index < count; index++) {
            bytes32 categoryHash = categoryHashes[index];
            if (categoryHash == bytes32(0)) revert CategoryHashZero(index);
            if (index != 0 && categoryHash <= previous) revert CategoryHashesNotStrictlySorted(index);
            previous = categoryHash;
        }

        categorySetHash = keccak256(abi.encodePacked(categoryHashes));
        generation = _facetStates[recordId].generation + 1;
        _facetStates[recordId] = FacetState({
            recordHash: current.recordHash,
            categorySetHash: categorySetHash,
            generation: generation,
            categoryCount: uint8(count)
        });

        emit CategorySetPublished(recordId, current.recordHash, categorySetHash, generation, uint8(count));
        for (uint256 index = 0; index < count; index++) {
            emit CategoryDeclared(categoryHashes[index], recordId, generation);
        }
    }

    function clear(bytes32 recordId, bytes32 expectedRecordHash) external returns (uint64 generation) {
        IAgentCartMerchantRegistry.Record memory current = _requireCurrentController(recordId, expectedRecordHash);
        generation = _facetStates[recordId].generation + 1;
        _facetStates[recordId] = FacetState({
            recordHash: current.recordHash,
            categorySetHash: bytes32(0),
            generation: generation,
            categoryCount: 0
        });
        emit CategorySetPublished(recordId, current.recordHash, bytes32(0), generation, 0);
    }

    function facetState(bytes32 recordId) external view returns (FacetState memory) {
        return _facetStates[recordId];
    }

    function isCurrent(bytes32 recordId) external view returns (bool) {
        IAgentCartMerchantRegistry.Record memory current = _registry.record(recordId);
        FacetState memory facets = _facetStates[recordId];
        return current.status == IAgentCartMerchantRegistry.Status.Active && facets.generation != 0
            && facets.recordHash == current.recordHash;
    }

    function _requireCurrentController(bytes32 recordId, bytes32 expectedRecordHash)
        private
        view
        returns (IAgentCartMerchantRegistry.Record memory current)
    {
        current = _registry.record(recordId);
        if (current.status != IAgentCartMerchantRegistry.Status.Active) revert RecordNotActive();
        if (current.controller != msg.sender) revert NotController();
        if (current.recordHash != expectedRecordHash) {
            revert RecordHashMismatch(current.recordHash, expectedRecordHash);
        }
    }
}
