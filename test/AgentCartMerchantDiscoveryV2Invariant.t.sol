// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {DiscoveryV2Fixture} from "./AgentCartMerchantDiscoveryV2.t.sol";
import {IAgentCartMerchantRegistry as Registry} from "../contracts/interfaces/IAgentCartMerchantRegistry.sol";

/// @dev Independent model tracks eligible-or-pending-prune registry membership and category
/// generation/freshness. Time advances do not remove candidates; explicit pruning does,
/// and renewal restores membership without duplicate candidates.
contract DiscoveryV2Handler is DiscoveryV2Fixture {
    bytes32[] private _ids;
    mapping(bytes32 => uint8) private _categories;
    mapping(bytes32 => uint64) private _generation;
    mapping(bytes32 => bool) private _fresh;
    mapping(bytes32 => bool) private _indexed;
    mapping(bytes32 => uint64) private _expiresAt;
    mapping(bytes32 => Registry.Status) private _status;
    uint256 private _updates;

    constructor() {
        _setUp();
        for (uint256 i; i < 4; i++) _registerModeled();
    }

    function register() external {
        if (_ids.length < 12) _registerModeled();
    }

    function _registerModeled() private {
        bytes32 id = _register(_ids.length);
        _ids.push(id);
        _indexed[id] = true;
        _expiresAt[id] = uint64(block.timestamp + 60 days);
        _status[id] = Registry.Status.Active;
    }

    function _modelEligible(bytes32 id) private view returns (bool) {
        return _status[id] == Registry.Status.Active && _expiresAt[id] > block.timestamp;
    }

    function advanceTime(uint8 daySeed) external {
        vm.warp(block.timestamp + (1 + uint256(daySeed) % 90) * 1 days);
    }

    function pruneIneligible(uint8 seed) external {
        bytes32 id = _ids[uint256(seed) % _ids.length];
        if (_modelEligible(id)) return;
        registry.pruneIneligible(id);
        _indexed[id] = false;
    }

    function renew(uint8 seed) external {
        bytes32 id = _ids[uint256(seed) % _ids.length];
        if (_status[id] != Registry.Status.Active) return;
        Registry.Record memory current = registry.record(id);
        _admit(current.domainHash, current.controller, current.recordHash, registry.entityId(id));
        vm.prank(current.controller);
        registry.renewAdmission(id);
        _expiresAt[id] = uint64(block.timestamp + 60 days);
        _indexed[id] = true;
    }

    function refresh(uint8 seed) external {
        bytes32 id = _ids[uint256(seed) % _ids.length];
        if (!_modelEligible(id)) return;
        registry.refreshIndexedRecord(id);
        _indexed[id] = true;
    }

    function publish(uint8 seed, uint8 categoryMask) external {
        bytes32 id = _ids[uint256(seed) % _ids.length];
        Registry.Record memory current = registry.record(id);
        if (current.status != Registry.Status.Active) return;
        if (categoryMask == 0) categoryMask = 1;
        uint256 count;
        for (uint256 i; i < 8; i++) if ((uint256(categoryMask) & (1 << i)) != 0) count++;
        bytes32[] memory categories = new bytes32[](count);
        uint256 cursor;
        for (uint256 i; i < 8; i++) {
            if ((uint256(categoryMask) & (1 << i)) != 0) categories[cursor++] = bytes32(i + 1);
        }
        vm.prank(current.controller);
        facets.publish(id, current.recordHash, categories);
        _categories[id] = categoryMask;
        _generation[id]++;
        _fresh[id] = true;
    }

    function clear(uint8 seed) external {
        bytes32 id = _ids[uint256(seed) % _ids.length];
        Registry.Record memory current = registry.record(id);
        if (current.status != Registry.Status.Active) return;
        vm.prank(current.controller);
        facets.clear(id, current.recordHash);
        _categories[id] = 0;
        _generation[id]++;
        _fresh[id] = true;
    }

    function prune(uint8 seed) external {
        bytes32 id = _ids[uint256(seed) % _ids.length];
        facets.prune(id);
        if (_categories[id] != 0 && (!_fresh[id] || !_modelEligible(id))) {
            _categories[id] = 0;
            _generation[id]++;
            _fresh[id] = false;
        }
    }

    function update(uint8 seed, bool sameHash) external {
        bytes32 id = _ids[uint256(seed) % _ids.length];
        Registry.Record memory current = registry.record(id);
        if (current.status != Registry.Status.Active) return;
        bytes32 nextHash = sameHash ? current.recordHash : keccak256(abi.encode("updated", id, ++_updates));
        _admit(current.domainHash, current.controller, nextHash, registry.entityId(id));
        vm.prank(current.controller);
        registry.update(id, nextHash, URI);
        _fresh[id] = false;
        _expiresAt[id] = uint64(block.timestamp + 60 days);
        _indexed[id] = true;
    }

    function suspendOrUnsuspend(uint8 seed) external {
        bytes32 id = _ids[uint256(seed) % _ids.length];
        Registry.Status status = _status[id];
        if (status == Registry.Status.Active) {
            _suspend(id);
            _status[id] = Registry.Status.Suspended;
            _indexed[id] = false;
        } else if (status == Registry.Status.Suspended) {
            _unsuspend(id);
            _status[id] = Registry.Status.Active;
            _indexed[id] = _modelEligible(id);
        } else return;
        _fresh[id] = false;
    }

    function revoke(uint8 seed) external {
        bytes32 id = _ids[uint256(seed) % _ids.length];
        Registry.Record memory current = registry.record(id);
        if (current.status == Registry.Status.Revoked) return;
        vm.prank(current.controller);
        registry.revoke(id, REASON);
        _fresh[id] = false;
        _status[id] = Registry.Status.Revoked;
        _indexed[id] = false;
    }

    function assertIndexedAndCategories() external view {
        bool[] memory membership = new bool[](_ids.length);
        for (uint256 i; i < _ids.length; i++) membership[i] = _indexed[_ids[i]];
        _assertIndexedSet(_ids, membership);
        for (uint256 i; i < _ids.length; i++) {
            bytes32 id = _ids[i];
            require(registry.record(id).status == _status[id], "status differs from lifecycle model");
            (bool eligible,,,) = registry.eligibility(id);
            require(eligible == _modelEligible(id), "eligibility differs from expiry model");
            if (eligible) require(_indexed[id], "eligible member missing from index");
            require(facets.isCurrent(id) == _fresh[id], "freshness differs from lifecycle model");
            require(facets.facetState(id).generation == _generation[id], "publication generation differs");
            uint256 count;
            for (uint256 bit; bit < 8; bit++) if ((uint256(_categories[id]) & (1 << bit)) != 0) count++;
            require(facets.facetState(id).categoryCount == count, "record category count differs");
            if (_fresh[id]) require(facets.facetState(id).recordHash == registry.record(id).recordHash);
        }
        for (uint256 category; category < 8; category++) {
            uint256 count;
            for (uint256 i; i < _ids.length; i++) {
                if ((uint256(_categories[_ids[i]]) & (1 << category)) != 0) count++;
            }
            bytes32[] memory expected = new bytes32[](count);
            uint256 cursor;
            for (uint256 i; i < _ids.length; i++) {
                if ((uint256(_categories[_ids[i]]) & (1 << category)) != 0) expected[cursor++] = _ids[i];
            }
            _assertCategory(bytes32(category + 1), expected);
        }
    }
}

contract AgentCartMerchantDiscoveryV2InvariantTest {
    struct FuzzSelector {
        address addr;
        bytes4[] selectors;
    }

    DiscoveryV2Handler private handler;

    function setUp() public {
        handler = new DiscoveryV2Handler();
    }

    function targetContracts() external view returns (address[] memory targets) {
        targets = new address[](1);
        targets[0] = address(handler);
    }

    function targetSelectors() external view returns (FuzzSelector[] memory targets) {
        targets = new FuzzSelector[](1);
        bytes4[] memory selectors = new bytes4[](11);
        selectors[0] = DiscoveryV2Handler.register.selector;
        selectors[1] = DiscoveryV2Handler.publish.selector;
        selectors[2] = DiscoveryV2Handler.clear.selector;
        selectors[3] = DiscoveryV2Handler.prune.selector;
        selectors[4] = DiscoveryV2Handler.update.selector;
        selectors[5] = DiscoveryV2Handler.suspendOrUnsuspend.selector;
        selectors[6] = DiscoveryV2Handler.revoke.selector;
        selectors[7] = DiscoveryV2Handler.advanceTime.selector;
        selectors[8] = DiscoveryV2Handler.pruneIneligible.selector;
        selectors[9] = DiscoveryV2Handler.renew.selector;
        selectors[10] = DiscoveryV2Handler.refresh.selector;
        targets[0] = FuzzSelector(address(handler), selectors);
    }

    /// forge-config: default.invariant.runs = 64
    /// forge-config: default.invariant.depth = 64
    function invariantIndexedMembershipAndBoundedCategorySets() public view {
        handler.assertIndexedAndCategories();
    }

    function testStatefulModelSmoke() public {
        handler.publish(0, 255);
        handler.publish(1, 255);
        handler.publish(2, 255);
        handler.assertIndexedAndCategories();
        handler.advanceTime(60);
        handler.assertIndexedAndCategories();
        handler.pruneIneligible(0);
        handler.pruneIneligible(1);
        handler.pruneIneligible(1);
        handler.prune(0);
        handler.prune(1);
        handler.assertIndexedAndCategories();
        handler.renew(0);
        handler.refresh(0);
        handler.renew(0);
        handler.update(1, true);
        handler.assertIndexedAndCategories();
        handler.suspendOrUnsuspend(1);
        handler.suspendOrUnsuspend(1);
        handler.revoke(2);
        handler.assertIndexedAndCategories();
        handler.prune(0);
        handler.prune(1);
        handler.prune(2);
        handler.assertIndexedAndCategories();
        handler.publish(1, 129);
        handler.clear(1);
        handler.register();
        handler.publish(4, 255);
        handler.assertIndexedAndCategories();
    }
}
