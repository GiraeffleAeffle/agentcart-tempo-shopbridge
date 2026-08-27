// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AgentCartMerchantRegistry} from "../contracts/AgentCartMerchantRegistry.sol";
import {AgentCartMerchantDiscoveryFacets} from "../contracts/AgentCartMerchantDiscoveryFacets.sol";
import {IAgentCartMerchantDiscoveryFacets} from "../contracts/interfaces/IAgentCartMerchantDiscoveryFacets.sol";

interface DiscoveryVm {
    function prank(address sender) external;
    function expectRevert(bytes calldata revertData) external;
}

contract AgentCartMerchantDiscoveryFacetsTest {
    DiscoveryVm private constant VM = DiscoveryVm(address(uint160(uint256(keccak256("hevm cheat code")))));

    address private constant MERCHANT = address(0x1000000000000000000000000000000000000001);
    address private constant OTHER = address(0x1000000000000000000000000000000000000002);
    bytes32 private constant DOMAIN_HASH = keccak256("facet-shop.example");
    bytes32 private constant RECORD_HASH = keccak256("facet-record-v1");
    bytes32 private constant RECORD_HASH_2 = keccak256("facet-record-v2");
    bytes32 private constant REASON_HASH = keccak256("facet-revoke");
    string private constant RECORD_URI = "https://facet-shop.example/.well-known/record.json";

    AgentCartMerchantRegistry private registry;
    AgentCartMerchantDiscoveryFacets private facets;
    bytes32 private recordId;

    function setUp() public {
        registry = new AgentCartMerchantRegistry(address(this));
        facets = new AgentCartMerchantDiscoveryFacets(address(registry));
        VM.prank(MERCHANT);
        recordId = registry.register(DOMAIN_HASH, RECORD_HASH, RECORD_URI);
    }

    function testControllerPublishesCurrentSortedCategorySet() public {
        bytes32[] memory categories = _sortedCategories();
        VM.prank(MERCHANT);
        (bytes32 setHash, uint64 generation) = facets.publish(recordId, RECORD_HASH, categories);

        IAgentCartMerchantDiscoveryFacets.FacetState memory state = facets.facetState(recordId);
        require(setHash == keccak256(abi.encodePacked(categories)), "set hash mismatch");
        require(state.recordHash == RECORD_HASH, "record hash mismatch");
        require(state.categorySetHash == setHash, "stored set hash mismatch");
        require(state.generation == generation && generation == 1, "generation mismatch");
        require(state.categoryCount == 2, "category count mismatch");
        require(facets.isCurrent(recordId), "published facets not current");
        require(facets.registry() == address(registry), "registry address mismatch");
    }

    function testNonControllerAndWrongRecordHashFailClosed() public {
        bytes32[] memory categories = _sortedCategories();
        VM.prank(OTHER);
        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantDiscoveryFacets.NotController.selector));
        facets.publish(recordId, RECORD_HASH, categories);

        VM.prank(MERCHANT);
        VM.expectRevert(
            abi.encodeWithSelector(
                AgentCartMerchantDiscoveryFacets.RecordHashMismatch.selector, RECORD_HASH, RECORD_HASH_2
            )
        );
        facets.publish(recordId, RECORD_HASH_2, categories);
    }

    function testCategorySetMustBeBoundedNonZeroUniqueAndSorted() public {
        bytes32[] memory empty = new bytes32[](0);
        VM.prank(MERCHANT);
        VM.expectRevert(
            abi.encodeWithSelector(AgentCartMerchantDiscoveryFacets.CategoryCountInvalid.selector, uint256(0))
        );
        facets.publish(recordId, RECORD_HASH, empty);

        bytes32[] memory invalid = new bytes32[](2);
        invalid[0] = bytes32(uint256(1));
        invalid[1] = bytes32(0);
        VM.prank(MERCHANT);
        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantDiscoveryFacets.CategoryHashZero.selector, 1));
        facets.publish(recordId, RECORD_HASH, invalid);

        invalid[1] = invalid[0];
        VM.prank(MERCHANT);
        VM.expectRevert(
            abi.encodeWithSelector(AgentCartMerchantDiscoveryFacets.CategoryHashesNotStrictlySorted.selector, 1)
        );
        facets.publish(recordId, RECORD_HASH, invalid);

        invalid[0] = bytes32(uint256(2));
        invalid[1] = bytes32(uint256(1));
        VM.prank(MERCHANT);
        VM.expectRevert(
            abi.encodeWithSelector(AgentCartMerchantDiscoveryFacets.CategoryHashesNotStrictlySorted.selector, 1)
        );
        facets.publish(recordId, RECORD_HASH, invalid);
    }

    function testRegistryUpdateInvalidatesOldFacetsUntilRepublished() public {
        bytes32[] memory categories = _sortedCategories();
        VM.prank(MERCHANT);
        facets.publish(recordId, RECORD_HASH, categories);

        VM.prank(MERCHANT);
        registry.update(recordId, RECORD_HASH_2, RECORD_URI);
        require(!facets.isCurrent(recordId), "old facets survived record update");

        VM.prank(MERCHANT);
        facets.publish(recordId, RECORD_HASH_2, categories);
        IAgentCartMerchantDiscoveryFacets.FacetState memory state = facets.facetState(recordId);
        require(state.recordHash == RECORD_HASH_2, "replacement record hash mismatch");
        require(state.generation == 2, "replacement generation mismatch");
        require(facets.isCurrent(recordId), "replacement facets not current");
    }

    function testClearIsCurrentButCannotRouteAStaleDeclaration() public {
        VM.prank(MERCHANT);
        facets.publish(recordId, RECORD_HASH, _sortedCategories());
        VM.prank(MERCHANT);
        uint64 generation = facets.clear(recordId, RECORD_HASH);

        IAgentCartMerchantDiscoveryFacets.FacetState memory state = facets.facetState(recordId);
        require(generation == 2, "clear generation mismatch");
        require(state.categorySetHash == bytes32(0), "clear set hash mismatch");
        require(state.categoryCount == 0, "clear category count mismatch");
        require(facets.isCurrent(recordId), "cleared state should match current record");
    }

    function testRevokedRecordCannotPublish() public {
        VM.prank(MERCHANT);
        registry.revoke(recordId, REASON_HASH);
        VM.prank(MERCHANT);
        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantDiscoveryFacets.RecordNotActive.selector));
        facets.publish(recordId, RECORD_HASH, _sortedCategories());
    }

    function _sortedCategories() private pure returns (bytes32[] memory categories) {
        categories = new bytes32[](2);
        bytes32 first = keccak256("coffee");
        bytes32 second = keccak256("tea");
        if (first < second) {
            categories[0] = first;
            categories[1] = second;
        } else {
            categories[0] = second;
            categories[1] = first;
        }
    }
}
