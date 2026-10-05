// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IAgentCartMerchantRegistry} from "./IAgentCartMerchantRegistry.sol";

/// @notice Storage discovery for new v2 deployments; the v1 Record ABI is unchanged.
interface IAgentCartMerchantRegistryV2 is IAgentCartMerchantRegistry {
    event IndexedRecordPruned(bytes32 indexed recordId);

    /// @dev Unordered eligible-or-pending-prune set, not a substitute for eligibility.
    /// Read all getters at one finalized block; swap-removal can change indices between blocks.
    function indexedRecordCount() external view returns (uint256);
    function indexedRecordIdAt(uint256 index) external view returns (bytes32);
    function recordURI(bytes32 recordId) external view returns (string memory);

    function eligibility(bytes32 recordId)
        external
        view
        returns (bool eligible, bytes32 entity, uint64 expiresAt, uint256 bond);

    /// @notice Record-specific eligibility, excluding global pause and admission quorum.
    function hasRecordEligibility(bytes32 recordId) external view returns (bool);

    /// @notice Remove a known record failing record-specific eligibility. Eligible records
    /// and records ineligible only due to global pause/quorum changes are rejected.
    /// Repeated removal is a no-op; the record itself and its status are not changed.
    function pruneIneligible(bytes32 recordId) external;

    /// @notice Idempotently index a known eligible record after bounded, entity-wide recovery.
    function refreshIndexedRecord(bytes32 recordId) external;
}
