// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IAgentCartMerchantRegistryV2} from "./interfaces/IAgentCartMerchantRegistryV2.sol";
import {IAgentCartMerchantRegistry} from "./interfaces/IAgentCartMerchantRegistry.sol";
import {IAgentCartMerchantDiscoveryFacetsV2} from "./interfaces/IAgentCartMerchantDiscoveryFacetsV2.sol";

/// @notice Separate deployment keeps the deployed v1 event-only facets unchanged.
/// Category sets are bounded per record. isCurrent marks registry status/hash/generation;
/// eligibility is a separate buyer check and ineligible categories can be pruned permissionlessly.
contract AgentCartMerchantDiscoveryFacetsV2 is IAgentCartMerchantDiscoveryFacetsV2 {
    error ZeroAddress();
    error NotController();
    error RecordNotActive();
    error RecordHashMismatch(bytes32 expected, bytes32 actual);
    error CategoryCountInvalid(uint256 count);
    error CategoryHashZero(uint256 index);
    error CategoryHashesNotStrictlySorted(uint256 index);

    uint256 public constant MAX_CATEGORY_COUNT = 8;

    struct CategoryRecord {
        bytes32 recordId;
        uint64 generation;
    }

    IAgentCartMerchantRegistryV2 private immutable _registry;
    mapping(bytes32 => FacetState) private _facetStates;
    mapping(bytes32 => uint64) private _registryGenerations;
    mapping(bytes32 => bytes32[]) private _recordCategories;
    mapping(bytes32 => CategoryRecord[]) private _categoryRecords;
    mapping(bytes32 => mapping(bytes32 => uint256)) private _categoryIndexPlusOne;

    constructor(address registryAddress) {
        if (registryAddress == address(0)) revert ZeroAddress();
        _registry = IAgentCartMerchantRegistryV2(registryAddress);
        // Require the storage-discovery ABI, rather than silently accepting a v1 registry.
        _registry.indexedRecordCount();
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
        for (uint256 index; index < count; index++) {
            bytes32 categoryHash = categoryHashes[index];
            if (categoryHash == bytes32(0)) revert CategoryHashZero(index);
            if (index != 0 && categoryHash <= previous) revert CategoryHashesNotStrictlySorted(index);
            previous = categoryHash;
        }

        _removeCategories(recordId);
        categorySetHash = keccak256(abi.encodePacked(categoryHashes));
        generation = _facetStates[recordId].generation + 1;
        _facetStates[recordId] = FacetState(current.recordHash, categorySetHash, generation, uint8(count));
        _registryGenerations[recordId] = current.attestationGeneration;
        emit CategorySetPublished(recordId, current.recordHash, categorySetHash, generation, uint8(count));
        for (uint256 index; index < count; index++) {
            bytes32 categoryHash = categoryHashes[index];
            _recordCategories[recordId].push(categoryHash);
            _categoryRecords[categoryHash].push(CategoryRecord(recordId, generation));
            _categoryIndexPlusOne[categoryHash][recordId] = _categoryRecords[categoryHash].length;
            emit CategoryDeclared(categoryHash, recordId, generation);
        }
    }

    function clear(bytes32 recordId, bytes32 expectedRecordHash) external returns (uint64 generation) {
        IAgentCartMerchantRegistry.Record memory current = _requireCurrentController(recordId, expectedRecordHash);
        _removeCategories(recordId);
        generation = _facetStates[recordId].generation + 1;
        _facetStates[recordId] = FacetState(current.recordHash, bytes32(0), generation, 0);
        _registryGenerations[recordId] = current.attestationGeneration;
        emit CategorySetPublished(recordId, current.recordHash, bytes32(0), generation, 0);
    }

    function facetState(bytes32 recordId) external view returns (FacetState memory) {
        return _facetStates[recordId];
    }

    function isCurrent(bytes32 recordId) public view returns (bool) {
        IAgentCartMerchantRegistry.Record memory current = _registry.record(recordId);
        FacetState storage facets = _facetStates[recordId];
        return current.status == IAgentCartMerchantRegistry.Status.Active && facets.generation != 0
            && facets.recordHash == current.recordHash
            && _registryGenerations[recordId] == current.attestationGeneration;
    }

    function categoryRecordCount(bytes32 categoryHash) external view returns (uint256) {
        return _categoryRecords[categoryHash].length;
    }

    function categoryRecordAt(bytes32 categoryHash, uint256 index)
        external
        view
        returns (bytes32 recordId, uint64 generation)
    {
        CategoryRecord storage candidate = _categoryRecords[categoryHash][index];
        return (candidate.recordId, candidate.generation);
    }

    function prune(bytes32 recordId) external {
        if (_recordCategories[recordId].length == 0) return;
        if (isCurrent(recordId) && _registry.hasRecordEligibility(recordId)) return;
        _removeCategories(recordId);
        uint64 generation = _facetStates[recordId].generation + 1;
        _facetStates[recordId] = FacetState(bytes32(0), bytes32(0), generation, 0);
        delete _registryGenerations[recordId];
        emit CategorySetPublished(recordId, bytes32(0), bytes32(0), generation, 0);
    }

    function _removeCategories(bytes32 recordId) private {
        bytes32[] storage categories = _recordCategories[recordId];
        for (uint256 index; index < categories.length; index++) {
            bytes32 categoryHash = categories[index];
            CategoryRecord[] storage candidates = _categoryRecords[categoryHash];
            uint256 indexPlusOne = _categoryIndexPlusOne[categoryHash][recordId];
            uint256 candidateIndex = indexPlusOne - 1;
            uint256 lastIndex = candidates.length - 1;
            if (candidateIndex != lastIndex) {
                CategoryRecord memory moved = candidates[lastIndex];
                candidates[candidateIndex] = moved;
                _categoryIndexPlusOne[categoryHash][moved.recordId] = indexPlusOne;
            }
            candidates.pop();
            delete _categoryIndexPlusOne[categoryHash][recordId];
        }
        delete _recordCategories[recordId];
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
