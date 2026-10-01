// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AgentCartMerchantRegistryV2} from "../contracts/AgentCartMerchantRegistryV2.sol";
import {AgentCartMerchantDiscoveryFacetsV2} from "../contracts/AgentCartMerchantDiscoveryFacetsV2.sol";
import {IAgentCartMerchantRegistry as Registry} from "../contracts/interfaces/IAgentCartMerchantRegistry.sol";
import {BondTokenFixture, VmV2} from "./AgentCartMerchantRegistryV2.t.sol";

interface VmDiscoveryLogs {
    struct Log {
        bytes32[] topics;
        bytes data;
        address emitter;
    }
    function recordLogs() external;
    function getRecordedLogs() external returns (Log[] memory);
}

contract DiscoveryV2Fixture {
    VmV2 internal constant vm = VmV2(address(uint160(uint256(keccak256("hevm cheat code")))));
    address internal constant A = address(0xA1);
    address internal constant B = address(0xB1);
    bytes32 internal constant REASON = keccak256("reason");
    string internal constant URI = "https://shop.example/record.json";
    AgentCartMerchantRegistryV2 internal registry;
    AgentCartMerchantDiscoveryFacetsV2 internal facets;
    BondTokenFixture internal token;

    function _setUp() internal {
        token = new BondTokenFixture();
        registry = new AgentCartMerchantRegistryV2(address(this), address(token), 100);
        registry.scheduleGovernanceAction(registry.validatorActionHash(A, true));
        registry.scheduleGovernanceAction(registry.validatorActionHash(B, true));
        vm.warp(block.timestamp + 2 days);
        registry.setValidator(A, true);
        registry.setValidator(B, true);
        facets = new AgentCartMerchantDiscoveryFacetsV2(address(registry));
    }

    function _admit(bytes32 domain, address controller, bytes32 hash, bytes32 entity) internal {
        uint64 expiry = uint64(block.timestamp + 60 days);
        vm.prank(A);
        registry.voteAdmission(domain, controller, hash, entity, expiry, REASON);
        vm.prank(B);
        registry.voteAdmission(domain, controller, hash, entity, expiry, REASON);
    }

    function _register(uint256 seed) internal returns (bytes32 id) {
        address shop = address(uint160(0x1000 + seed));
        bytes32 domain = keccak256(abi.encode("domain", seed));
        bytes32 hash = keccak256(abi.encode("record", seed));
        _admit(domain, shop, hash, keccak256(abi.encode("entity", seed)));
        token.mint(shop, 100);
        vm.prank(shop);
        uint256 beforeGas = gasleft();
        id = registry.register(domain, hash, URI);
        require(beforeGas - gasleft() < 500000, "registration scans historical records");
    }

    function _publish(bytes32 id, uint256 first, uint256 count) internal {
        bytes32[] memory categories = new bytes32[](count);
        for (uint256 i; i < count; i++) categories[i] = bytes32(first + i);
        Registry.Record memory current = registry.record(id);
        vm.prank(current.controller);
        facets.publish(id, current.recordHash, categories);
    }

    function _suspend(bytes32 id) internal {
        vm.prank(A);
        registry.suspend(id, REASON);
        vm.prank(B);
        registry.suspend(id, REASON);
        vm.warp(block.timestamp + 2 days);
        vm.prank(A);
        registry.suspend(id, REASON);
    }

    function _unsuspend(bytes32 id) internal {
        vm.prank(A);
        registry.unsuspend(id);
        vm.prank(B);
        registry.unsuspend(id);
        vm.warp(block.timestamp + 2 days);
        vm.prank(A);
        registry.unsuspend(id);
    }

    function _assertIndexedSet(bytes32[] memory ids) internal view {
        bool[] memory membership = new bool[](ids.length);
        for (uint256 i; i < ids.length; i++) (membership[i],,,) = registry.eligibility(ids[i]);
        _assertIndexedSet(ids, membership);
    }

    function _assertIndexedSet(bytes32[] memory ids, bool[] memory membership) internal view {
        uint256 expected;
        for (uint256 i; i < ids.length; i++) {
            if (membership[i]) expected++;
            uint256 occurrences;
            for (uint256 j; j < registry.indexedRecordCount(); j++) {
                if (registry.indexedRecordIdAt(j) == ids[i]) occurrences++;
            }
            require(occurrences == (membership[i] ? 1 : 0), "indexed membership differs from model");
        }
        require(registry.indexedRecordCount() == expected, "unexpected indexed member");
    }

    function _assertCategory(bytes32 category, bytes32[] memory expected) internal view {
        require(facets.categoryRecordCount(category) == expected.length, "category count");
        for (uint256 i; i < expected.length; i++) {
            uint256 occurrences;
            for (uint256 j; j < expected.length; j++) {
                (bytes32 id, uint64 generation) = facets.categoryRecordAt(category, j);
                if (id == expected[i]) occurrences++;
                require(generation == facets.facetState(id).generation, "candidate generation");
            }
            require(occurrences == 1, "category duplicate or missing member");
        }
    }
}

contract AgentCartMerchantDiscoveryV2Test is DiscoveryV2Fixture {
    function setUp() public {
        _setUp();
    }

    function testExpiryPruneRenewalAndRefreshNeverDuplicateIndexedRecords() public {
        bytes32[] memory ids = new bytes32[](4);
        bool[] memory membership = new bool[](4);
        for (uint256 i; i < 3; i++) {
            ids[i] = _register(i);
            membership[i] = true;
        }
        _publish(ids[1], 1, 8);
        vm.warp(block.timestamp + 60 days);
        ids[3] = _register(3);
        membership[3] = true;
        _assertIndexedSet(ids, membership);
        require(facets.isCurrent(ids[1]), "freshness marker is not eligibility");
        (bool eligible,,,) = registry.eligibility(ids[1]);
        require(!eligible && registry.record(ids[1]).status == Registry.Status.Active);
        vm.expectRevert(AgentCartMerchantRegistryV2.RecordIneligible.selector);
        registry.refreshIndexedRecord(ids[1]);
        VmDiscoveryLogs logVm = VmDiscoveryLogs(address(vm));
        logVm.recordLogs();
        registry.pruneIneligible(ids[1]);
        VmDiscoveryLogs.Log[] memory logs = logVm.getRecordedLogs();
        require(logs.length == 1 && logs[0].emitter == address(registry));
        require(logs[0].topics.length == 2 && logs[0].topics[0] == keccak256("IndexedRecordPruned(bytes32)"));
        require(logs[0].topics[1] == ids[1], "pruned event record");
        membership[1] = false;
        require(registry.indexedRecordIdAt(1) == ids[3], "prune must swap the final candidate");
        _assertIndexedSet(ids, membership);
        logVm.recordLogs();
        registry.pruneIneligible(ids[1]);
        require(logVm.getRecordedLogs().length == 0, "repeat prune must not emit removal");
        facets.prune(ids[1]);
        require(!facets.isCurrent(ids[1]));
        for (uint256 i = 1; i <= 8; i++) require(facets.categoryRecordCount(bytes32(i)) == 0);
        Registry.Record memory current = registry.record(ids[1]);
        _admit(current.domainHash, current.controller, current.recordHash, registry.entityId(ids[1]));
        vm.prank(current.controller);
        registry.renewAdmission(ids[1]);
        membership[1] = true;
        _assertIndexedSet(ids, membership);
        registry.refreshIndexedRecord(ids[1]);
        registry.refreshIndexedRecord(ids[1]);
        vm.prank(current.controller);
        registry.renewAdmission(ids[1]);
        _assertIndexedSet(ids, membership);
        vm.expectRevert(AgentCartMerchantRegistryV2.RecordStillEligible.selector);
        registry.pruneIneligible(ids[1]);
        registry.pruneIneligible(ids[0]);
        registry.pruneIneligible(ids[2]);
        membership[0] = false;
        membership[2] = false;
        _assertIndexedSet(ids, membership);
        require(!facets.isCurrent(ids[1]), "renewal must not revive pruned categories");
        _publish(ids[1], 1, 8);
        registry.refreshIndexedRecord(ids[1]);
        _assertIndexedSet(ids, membership);
        require(facets.isCurrent(ids[1]) && facets.facetState(ids[1]).generation == 3);
        vm.expectRevert(AgentCartMerchantRegistryV2.UnknownRecord.selector);
        registry.pruneIneligible(bytes32(uint256(999)));
        vm.expectRevert(AgentCartMerchantRegistryV2.UnknownRecord.selector);
        registry.refreshIndexedRecord(bytes32(uint256(999)));
    }

    function testUpdateAndControllerRotationRecoverPrunedRecords() public {
        bytes32[] memory ids = new bytes32[](2);
        ids[0] = _register(0);
        ids[1] = _register(1);
        vm.warp(block.timestamp + 60 days);
        registry.pruneIneligible(ids[0]);
        registry.pruneIneligible(ids[1]);
        Registry.Record memory first = registry.record(ids[0]);
        bytes32 hash = keccak256("recovered update");
        _admit(first.domainHash, first.controller, hash, registry.entityId(ids[0]));
        vm.prank(first.controller);
        registry.update(ids[0], hash, URI);
        Registry.Record memory second = registry.record(ids[1]);
        address replacement = address(0x9999);
        _admit(second.domainHash, replacement, hash, registry.entityId(ids[1]));
        vm.prank(second.controller);
        registry.setController(ids[1], replacement, hash, URI);
        _assertIndexedSet(ids);
        registry.refreshIndexedRecord(ids[0]);
        registry.refreshIndexedRecord(ids[1]);
        _assertIndexedSet(ids);
    }

    function testExpiredUnsuspensionStaysUnindexedUntilRenewal() public {
        bytes32[] memory ids = new bytes32[](1);
        ids[0] = _register(0);
        _suspend(ids[0]);
        vm.warp(block.timestamp + 60 days);
        _unsuspend(ids[0]);
        require(registry.record(ids[0]).status == Registry.Status.Active);
        _assertIndexedSet(ids);
        Registry.Record memory current = registry.record(ids[0]);
        _admit(current.domainHash, current.controller, current.recordHash, registry.entityId(ids[0]));
        vm.prank(current.controller);
        registry.renewAdmission(ids[0]);
        _assertIndexedSet(ids);
    }

    function testGlobalPauseCannotEvictOtherwiseEligibleRecord() public {
        bytes32[] memory ids = new bytes32[](1);
        ids[0] = _register(0);
        _publish(ids[0], 1, 1);
        registry.scheduleGovernanceAction(keccak256(abi.encode("pause", true)));
        vm.warp(block.timestamp + 2 days);
        registry.setWritesPaused(true);
        (bool eligible,,,) = registry.eligibility(ids[0]);
        require(!eligible);
        vm.expectRevert(AgentCartMerchantRegistryV2.RecordStillEligible.selector);
        registry.pruneIneligible(ids[0]);
        vm.expectRevert(AgentCartMerchantRegistryV2.RecordIneligible.selector);
        registry.refreshIndexedRecord(ids[0]);
        require(registry.indexedRecordCount() == 1 && registry.indexedRecordIdAt(0) == ids[0]);
        vm.prank(address(0xBEEF));
        facets.prune(ids[0]);
        require(facets.categoryRecordCount(bytes32(uint256(1))) == 1, "pause cleared current facets");
        registry.scheduleGovernanceAction(keccak256(abi.encode("pause", false)));
        vm.warp(block.timestamp + 2 days);
        registry.setWritesPaused(false);
        _assertIndexedSet(ids);
        require(facets.isCurrent(ids[0]), "unpause must preserve facets");
        require(facets.categoryRecordCount(bytes32(uint256(1))) == 1, "categories lost after unpause");
    }

    function testQuorumInvalidationCannotEvictOtherwiseEligibleRecord() public {
        bytes32 id = _register(0);
        _publish(id, 1, 1);
        address third = address(0xC1);
        registry.scheduleGovernanceAction(registry.validatorActionHash(third, true));
        vm.warp(block.timestamp + 2 days);
        registry.setValidator(third, true);
        registry.scheduleGovernanceAction(registry.validatorActionHash(A, false));
        vm.warp(block.timestamp + 2 days);
        registry.setValidator(A, false);
        (bool eligible,,,) = registry.eligibility(id);
        require(!eligible, "removed validator must invalidate admission quorum");
        vm.expectRevert(AgentCartMerchantRegistryV2.RecordStillEligible.selector);
        registry.pruneIneligible(id);
        require(registry.indexedRecordCount() == 1 && registry.indexedRecordIdAt(0) == id);
        vm.prank(address(0xBEEF));
        facets.prune(id);
        require(facets.categoryRecordCount(bytes32(uint256(1))) == 1, "quorum cleared current facets");
        Registry.Record memory current = registry.record(id);
        bytes32 entity = registry.entityId(id);
        uint64 expiry = uint64(block.timestamp + 60 days);
        vm.prank(B);
        registry.voteAdmission(current.domainHash, current.controller, current.recordHash, entity, expiry, REASON);
        vm.prank(third);
        registry.voteAdmission(current.domainHash, current.controller, current.recordHash, entity, expiry, REASON);
        vm.prank(current.controller);
        registry.renewAdmission(id);
        registry.refreshIndexedRecord(id);
        require(registry.indexedRecordCount() == 1 && registry.indexedRecordIdAt(0) == id);
    }

    function testUnsuspendDuringAdmissionQuorumShortfallReindexesRecord() public {
        bytes32 id = _register(0);
        _suspend(id);
        address third = address(0xC1);
        registry.scheduleGovernanceAction(registry.validatorActionHash(third, true));
        vm.warp(block.timestamp + 2 days);
        registry.setValidator(third, true);
        registry.scheduleGovernanceAction(registry.validatorActionHash(A, false));
        vm.warp(block.timestamp + 2 days);
        registry.setValidator(A, false);
        vm.prank(B);
        registry.unsuspend(id);
        vm.prank(third);
        registry.unsuspend(id);
        vm.warp(block.timestamp + 2 days);
        vm.prank(B);
        registry.unsuspend(id);
        (bool eligible,,,) = registry.eligibility(id);
        require(!eligible, "admission quorum should still be missing");
        require(registry.indexedRecordCount() == 1 && registry.indexedRecordIdAt(0) == id,
            "record-specific recovery must reindex without admission quorum");
        Registry.Record memory current = registry.record(id);
        (,bytes32 entity,uint64 expiry,) = registry.eligibility(id);
        vm.prank(B);
        registry.voteAdmission(current.domainHash, current.controller, current.recordHash, entity, expiry, REASON);
        vm.prank(third);
        registry.voteAdmission(current.domainHash, current.controller, current.recordHash, entity, expiry, REASON);
        (eligible,,,) = registry.eligibility(id);
        require(eligible, "recovered admission must be eligible");
        require(registry.indexedRecordIdAt(0) == id, "recovery must not need manual refresh");
    }

    function testEntityRestoreRecoversPrunedActiveSiblingWithoutRevivingSlashedRecord() public {
        bytes32 slashed = _register(0);
        bytes32 entity = registry.entityId(slashed);
        address siblingController = address(0x9999);
        bytes32 siblingDomain = keccak256("same entity domain");
        bytes32 siblingHash = keccak256("same entity hash");
        _admit(siblingDomain, siblingController, siblingHash, entity);
        token.mint(siblingController, 100);
        vm.prank(siblingController);
        bytes32 sibling = registry.register(siblingDomain, siblingHash, URI);
        _publish(sibling, 1, 8);
        vm.prank(A);
        registry.proposeSlash(slashed, 60, address(0x5555), REASON, URI);
        vm.prank(B);
        registry.proposeSlash(slashed, 60, address(0x5555), REASON, URI);
        vm.warp(block.timestamp + 2 days);
        registry.executeSlash(slashed);
        require(registry.record(sibling).status == Registry.Status.Active && facets.isCurrent(sibling));
        (bool eligible,,,) = registry.eligibility(sibling);
        require(!eligible && registry.indexedRecordCount() == 1, "blocked sibling remains pending prune");
        registry.pruneIneligible(sibling);
        facets.prune(sibling);
        require(registry.indexedRecordCount() == 0 && facets.categoryRecordCount(bytes32(uint256(1))) == 0);
        vm.expectRevert(AgentCartMerchantRegistryV2.RecordIneligible.selector);
        registry.refreshIndexedRecord(sibling);
        vm.prank(A);
        registry.restoreEntity(entity, REASON);
        vm.prank(B);
        registry.restoreEntity(entity, REASON);
        vm.warp(block.timestamp + 2 days);
        vm.prank(A);
        registry.restoreEntity(entity, REASON);
        registry.refreshIndexedRecord(sibling);
        registry.refreshIndexedRecord(sibling);
        require(registry.indexedRecordCount() == 1 && registry.indexedRecordIdAt(0) == sibling);
        vm.expectRevert(AgentCartMerchantRegistryV2.RecordIneligible.selector);
        registry.refreshIndexedRecord(slashed);
        require(registry.record(slashed).status == Registry.Status.Revoked && !facets.isCurrent(sibling));
        _publish(sibling, 1, 8);
        require(facets.isCurrent(sibling) && facets.facetState(sibling).generation == 3);
    }

    function testLifecycleMembershipAndSwapRemoval() public {
        bytes32[] memory ids = new bytes32[](4);
        for (uint256 i; i < 4; i++) ids[i] = _register(i);
        _assertIndexedSet(ids);
        _suspend(ids[1]);
        require(registry.indexedRecordIdAt(1) == ids[3], "middle removal must move last");
        _assertIndexedSet(ids);
        _unsuspend(ids[1]);
        _assertIndexedSet(ids);
        vm.prank(registry.record(ids[3]).controller);
        registry.revoke(ids[3], REASON);
        _assertIndexedSet(ids);
        // Remove the element moved by the first swap, then revoke an already unindexed suspension.
        _suspend(ids[0]);
        vm.prank(registry.record(ids[0]).controller);
        registry.revoke(ids[0], REASON);
        _assertIndexedSet(ids);
        registry.scheduleGovernanceAction(registry.forceRevokeActionHash(ids[2], REASON));
        vm.warp(block.timestamp + 2 days);
        registry.forceRevoke(ids[2], REASON);
        _assertIndexedSet(ids);
        vm.prank(registry.record(ids[1]).controller);
        registry.revoke(ids[1], REASON);
        _assertIndexedSet(ids);
        vm.expectRevert(abi.encodeWithSignature("Panic(uint256)", 0x32));
        registry.indexedRecordIdAt(0);
    }

    function testCurrentURITracksHashAndControllerWithoutChangingRecordABI() public {
        bytes32 id = _register(1);
        require(keccak256(bytes(registry.recordURI(id))) == keccak256(bytes(URI)));
        Registry.Record memory previous = registry.record(id);
        bytes32 nextHash = keccak256("updated");
        _admit(previous.domainHash, previous.controller, nextHash, registry.entityId(id));
        vm.prank(previous.controller);
        registry.update(id, nextHash, "https://shop.example/updated.json");
        require(registry.record(id).recordHash == nextHash);
        require(keccak256(bytes(registry.recordURI(id))) == keccak256("https://shop.example/updated.json"));
        _admit(previous.domainHash, address(0x9999), keccak256("rotated"), registry.entityId(id));
        vm.prank(previous.controller);
        registry.setController(id, address(0x9999), keccak256("rotated"), "https://shop.example/rotated.json");
        require(registry.record(id).controller == address(0x9999));
        require(keccak256(bytes(registry.recordURI(id))) == keccak256("https://shop.example/rotated.json"));
        require(registry.indexedRecordCount() == 1 && registry.indexedRecordIdAt(0) == id);
        require(bytes(registry.recordURI(bytes32(uint256(999)))).length == 0);
    }

    function testSupersessionReplacesActiveIdAndStoresActivationURI() public {
        bytes32 oldId = _register(1);
        _publish(oldId, 1, 2);
        Registry.Record memory old = registry.record(oldId);
        address replacement = address(0x9999);
        bytes32 hash = keccak256("replacement");
        _admit(old.domainHash, replacement, hash, registry.entityId(oldId));
        token.mint(replacement, 100);
        vm.prank(replacement);
        (bytes32 newId,) = registry.requestSupersession(old.domainHash, hash, REASON, URI, URI);
        require(registry.indexedRecordCount() == 1 && bytes(registry.recordURI(newId)).length == 0);
        vm.prank(A);
        registry.approveSupersession(newId, hash, URI);
        vm.prank(B);
        registry.approveSupersession(newId, hash, URI);
        vm.warp(block.timestamp + 2 days);
        vm.prank(replacement);
        registry.activateSupersession(newId, "https://replacement.example/record.json");
        require(registry.indexedRecordCount() == 1 && registry.indexedRecordIdAt(0) == newId);
        require(registry.record(oldId).status == Registry.Status.Revoked && !facets.isCurrent(oldId));
        require(keccak256(bytes(registry.recordURI(newId))) == keccak256("https://replacement.example/record.json"));
        facets.prune(oldId);
        require(facets.categoryRecordCount(bytes32(uint256(1))) == 0);
    }

    function testSlashAndEntityRestoreNeverResurrectRevokedRecord() public {
        bytes32 id = _register(1);
        _publish(id, 1, 8);
        vm.prank(A);
        registry.proposeSlash(id, 60, address(0x9999), REASON, URI);
        vm.prank(B);
        registry.proposeSlash(id, 60, address(0x9999), REASON, URI);
        vm.warp(block.timestamp + 2 days);
        registry.executeSlash(id);
        require(registry.indexedRecordCount() == 0 && !facets.isCurrent(id));
        bytes32 entity = registry.entityId(id);
        vm.prank(A);
        registry.restoreEntity(entity, REASON);
        vm.prank(B);
        registry.restoreEntity(entity, REASON);
        vm.warp(block.timestamp + 2 days);
        vm.prank(A);
        registry.restoreEntity(entity, REASON);
        require(!registry.blockedEntities(entity));
        require(registry.indexedRecordCount() == 0 && registry.record(id).status == Registry.Status.Revoked);
        facets.prune(id);
        for (uint256 i = 1; i <= 8; i++) require(facets.categoryRecordCount(bytes32(i)) == 0);
        Registry.Record memory old = registry.record(id);
        _admit(old.domainHash, address(0x9999), keccak256("reentry"), entity);
        token.mint(address(0x9999), 100);
        vm.prank(address(0x9999));
        bytes32 replacement = registry.register(old.domainHash, keccak256("reentry"), URI);
        require(registry.indexedRecordCount() == 1 && registry.indexedRecordIdAt(0) == replacement);
    }

    function testCategoryUpdateClearAndMovedIndexRemoval() public {
        bytes32 first = _register(1);
        bytes32 second = _register(2);
        bytes32 third = _register(3);
        _publish(first, 1, 2);
        _publish(second, 1, 2);
        _publish(third, 1, 2);
        _publish(first, 2, 2);
        require(facets.categoryRecordCount(bytes32(uint256(1))) == 2);
        (bytes32 moved,) = facets.categoryRecordAt(bytes32(uint256(1)), 0);
        require(moved == third);
        Registry.Record memory current = registry.record(third);
        vm.prank(current.controller);
        facets.clear(third, current.recordHash);
        bytes32[] memory expected = new bytes32[](1);
        expected[0] = second;
        _assertCategory(bytes32(uint256(1)), expected);
        expected = new bytes32[](2);
        expected[0] = first;
        expected[1] = second;
        _assertCategory(bytes32(uint256(2)), expected);
        require(facets.facetState(first).generation == 2 && facets.facetState(third).categoryCount == 0);
        vm.expectRevert(abi.encodeWithSignature("Panic(uint256)", 0x32));
        facets.categoryRecordAt(bytes32(uint256(1)), 1);
    }

    function testPruneRequiresStalenessAndSameHashGenerationCannotRevive() public {
        bytes32 id = _register(1);
        _publish(id, 1, 8);
        facets.prune(id);
        require(facets.categoryRecordCount(bytes32(uint256(1))) == 1 && facets.facetState(id).generation == 1);
        _suspend(id);
        require(!facets.isCurrent(id));
        _unsuspend(id);
        require(!facets.isCurrent(id), "same hash suspension must not revive facets");
        facets.prune(id);
        require(facets.facetState(id).generation == 2 && facets.facetState(id).categoryCount == 0);
        for (uint256 i = 1; i <= 8; i++) require(facets.categoryRecordCount(bytes32(i)) == 0);
        facets.prune(id);
        require(facets.facetState(id).generation == 2, "repeat prune must not change generation");
        _publish(id, 1, 1);
        require(facets.isCurrent(id) && facets.facetState(id).generation == 3);
        Registry.Record memory current = registry.record(id);
        _admit(current.domainHash, current.controller, current.recordHash, registry.entityId(id));
        vm.prank(current.controller);
        registry.update(id, current.recordHash, URI);
        require(!facets.isCurrent(id), "same-hash update must invalidate old generation");
        facets.prune(id);
        require(facets.categoryRecordCount(bytes32(uint256(1))) == 0);
        _publish(id, 1, 1);
        bytes32 changed = keccak256("changed hash");
        _admit(current.domainHash, current.controller, changed, registry.entityId(id));
        vm.prank(current.controller);
        registry.update(id, changed, URI);
        require(!facets.isCurrent(id), "hash change must invalidate facets");
        facets.prune(id);
        require(facets.categoryRecordCount(bytes32(uint256(1))) == 0);
    }

    function testPublishAuthorizationAndCategoryBoundsAreAtomic() public {
        bytes32 id = _register(1);
        _publish(id, 1, 8);
        Registry.Record memory current = registry.record(id);
        bytes32[] memory categories = new bytes32[](1);
        categories[0] = bytes32(uint256(1));
        vm.expectRevert(AgentCartMerchantDiscoveryFacetsV2.NotController.selector);
        facets.publish(id, current.recordHash, categories);
        vm.prank(current.controller);
        vm.expectRevert(abi.encodeWithSelector(AgentCartMerchantDiscoveryFacetsV2.RecordHashMismatch.selector, current.recordHash, bytes32(uint256(1))));
        facets.clear(id, bytes32(uint256(1)));
        for (uint256 count; count <= 9; count += 9) {
            vm.prank(current.controller);
            vm.expectRevert(abi.encodeWithSelector(AgentCartMerchantDiscoveryFacetsV2.CategoryCountInvalid.selector, count));
            facets.publish(id, current.recordHash, new bytes32[](count));
        }
        categories[0] = bytes32(0);
        vm.prank(current.controller);
        vm.expectRevert(abi.encodeWithSelector(AgentCartMerchantDiscoveryFacetsV2.CategoryHashZero.selector, 0));
        facets.publish(id, current.recordHash, categories);
        categories = new bytes32[](2);
        categories[0] = bytes32(uint256(2));
        categories[1] = bytes32(uint256(2));
        vm.prank(current.controller);
        vm.expectRevert(abi.encodeWithSelector(AgentCartMerchantDiscoveryFacetsV2.CategoryHashesNotStrictlySorted.selector, 1));
        facets.publish(id, current.recordHash, categories);
        categories[1] = bytes32(uint256(1));
        vm.prank(current.controller);
        vm.expectRevert(abi.encodeWithSelector(AgentCartMerchantDiscoveryFacetsV2.CategoryHashesNotStrictlySorted.selector, 1));
        facets.publish(id, current.recordHash, categories);
        require(facets.facetState(id).generation == 1 && facets.facetState(id).categoryCount == 8);
        for (uint256 i = 1; i <= 8; i++) require(facets.categoryRecordCount(bytes32(i)) == 1);
        _suspend(id);
        vm.prank(current.controller);
        vm.expectRevert(AgentCartMerchantDiscoveryFacetsV2.RecordNotActive.selector);
        facets.clear(id, current.recordHash);
        vm.prank(current.controller);
        vm.expectRevert(AgentCartMerchantDiscoveryFacetsV2.RecordNotActive.selector);
        facets.publish(id, current.recordHash, categories);
    }

    function testFuzzSwapRemovalAndCategoryGeneration(uint8 sizeSeed, uint8 removeSeed, uint8 categorySeed) public {
        uint256 size = 2 + uint256(sizeSeed) % 10;
        uint256 removeIndex = uint256(removeSeed) % size;
        uint256 categoryCount = 1 + uint256(categorySeed) % 8;
        bytes32[] memory ids = new bytes32[](size);
        for (uint256 i; i < size; i++) {
            ids[i] = _register(i);
            _publish(ids[i], 1, categoryCount);
        }
        vm.prank(registry.record(ids[removeIndex]).controller);
        registry.revoke(ids[removeIndex], REASON);
        facets.prune(ids[removeIndex]);
        _assertIndexedSet(ids);
        bytes32[] memory survivors = new bytes32[](size - 1);
        uint256 cursor;
        for (uint256 i; i < size; i++) if (i != removeIndex) survivors[cursor++] = ids[i];
        for (uint256 category = 1; category <= categoryCount; category++) _assertCategory(bytes32(category), survivors);
        // Exercise the mapping index of the candidate moved by swap-removal.
        bytes32 next = survivors[survivors.length - 1];
        Registry.Record memory current = registry.record(next);
        vm.prank(current.controller);
        facets.clear(next, current.recordHash);
        require(facets.categoryRecordCount(bytes32(uint256(1))) == size - 2);
    }

    function testGasRegisterRevokePublishClearAndPruneBoundedByRecord() public {
        bytes32 id = _register(1);
        _publish(id, 1, 8);
        for (uint256 i = 2; i < 34; i++) _publish(_register(i), 1, 8);
        bytes32 extra = _register(34);
        uint256 publishGas = gasleft();
        _publish(extra, 1, 8);
        require(publishGas - gasleft() < 1200000, "publish scans category candidates");
        Registry.Record memory extraRecord = registry.record(extra);
        vm.prank(extraRecord.controller);
        uint256 clearGas = gasleft();
        facets.clear(extra, extraRecord.recordHash);
        require(clearGas - gasleft() < 400000, "clear scans category candidates");
        vm.prank(extraRecord.controller);
        registry.revoke(extra, REASON);
        vm.prank(registry.record(id).controller);
        uint256 beforeGas = gasleft();
        registry.revoke(id, REASON);
        require(beforeGas - gasleft() < 200000, "revoke scans indexed set");
        beforeGas = gasleft();
        facets.prune(id);
        require(beforeGas - gasleft() < 400000, "prune scans category candidates");
        require(registry.indexedRecordCount() == 32);
        for (uint256 i = 1; i <= 8; i++) require(facets.categoryRecordCount(bytes32(i)) == 32);
    }

    function testGasPruneIneligibleBoundedByRecord() public {
        bytes32 first = _register(0);
        for (uint256 i = 1; i < 34; i++) _register(i);
        vm.warp(block.timestamp + 60 days);
        uint256 beforeGas = gasleft();
        registry.pruneIneligible(first);
        require(beforeGas - gasleft() < 100000, "prune ineligible scans indexed records");
        require(registry.indexedRecordCount() == 33 && registry.record(first).status == Registry.Status.Active);
        registry.pruneIneligible(first);
        require(registry.indexedRecordCount() == 33);
    }
}
