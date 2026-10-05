// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IAgentCartMerchantDiscoveryFacets} from "./IAgentCartMerchantDiscoveryFacets.sol";

interface IAgentCartMerchantDiscoveryFacetsV2 is IAgentCartMerchantDiscoveryFacets {
    /// @dev Unordered candidate sets, not eligibility. Read at one finalized block and
    /// verify registry eligibility, isCurrent, record hash, and the returned facet generation.
    function categoryRecordCount(bytes32 categoryHash) external view returns (uint256);
    function categoryRecordAt(bytes32 categoryHash, uint256 index)
        external
        view
        returns (bytes32 recordId, uint64 generation);

    /// @notice Remove categories if their registry status/hash/generation is stale or the
    /// record is ineligible. isCurrent alone deliberately does not attest eligibility.
    function prune(bytes32 recordId) external;
}
