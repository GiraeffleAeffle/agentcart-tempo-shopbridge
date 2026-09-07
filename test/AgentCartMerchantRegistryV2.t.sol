// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AgentCartMerchantRegistryV2, IRegistryBondToken} from "../contracts/AgentCartMerchantRegistryV2.sol";
import {IAgentCartMerchantRegistry as Registry} from "../contracts/interfaces/IAgentCartMerchantRegistry.sol";

interface VmV2 {
    function prank(address sender) external;
    function expectRevert(bytes4 selector) external;
    function expectRevert(bytes calldata data) external;
    function warp(uint256 timestamp) external;
}

contract BondTokenFixture is IRegistryBondToken {
    mapping(address => uint256) public balanceOf;
    bool public failTransfer;

    function mint(address account, uint256 amount) external {
        balanceOf[account] += amount;
    }

    function setFailTransfer(bool value) external {
        failTransfer = value;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        if (failTransfer) return false;
        require(balanceOf[from] >= amount);
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        if (failTransfer) return false;
        require(balanceOf[msg.sender] >= amount);
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract AgentCartMerchantRegistryV2Test {
    VmV2 private constant vm = VmV2(address(uint160(uint256(keccak256("hevm cheat code")))));
    address private constant A = address(0xA1);
    address private constant B = address(0xB1);
    address private constant C = address(0xC1);
    address private constant SHOP = address(0x101);
    address private constant BUYER = address(0x102);
    bytes32 private constant DOMAIN = keccak256("shop.example");
    bytes32 private constant HASH = keccak256("record");
    bytes32 private constant ENTITY = keccak256("verified-owner");
    bytes32 private constant EVIDENCE = keccak256("independent-domain-business-and-payout-checks");
    bytes32 private constant REASON = keccak256("proven_non_delivery");
    string private constant URI = "https://shop.example/record.json";
    AgentCartMerchantRegistryV2 private registry;
    BondTokenFixture private token;

    function setUp() public {
        token = new BondTokenFixture();
        registry = new AgentCartMerchantRegistryV2(address(this), address(token), 100);
        _validator(A, true);
        _validator(B, true);
        _validator(C, true);
        token.mint(SHOP, 1000);
    }

    function _validator(address who, bool enabled) private {
        registry.scheduleGovernanceAction(registry.validatorActionHash(who, enabled));
        vm.warp(block.timestamp + 2 days);
        registry.setValidator(who, enabled);
    }

    function _admit(address controller, bytes32 hash, bytes32 entity) private {
        uint64 expiry = uint64(block.timestamp + 60 days);
        vm.prank(A);
        registry.voteAdmission(DOMAIN, controller, hash, entity, expiry, EVIDENCE);
        vm.prank(B);
        registry.voteAdmission(DOMAIN, controller, hash, entity, expiry, EVIDENCE);
    }

    function _register() private returns (bytes32 id) {
        _admit(SHOP, HASH, ENTITY);
        vm.prank(SHOP);
        return registry.register(DOMAIN, HASH, URI);
    }

    function _slash(bytes32 id) private {
        vm.prank(A);
        registry.proposeSlash(id, 60, BUYER, REASON, URI);
        vm.prank(B);
        registry.proposeSlash(id, 60, BUYER, REASON, URI);
    }

    function testUnadmittedWalletCannotSquatDomain() public {
        vm.prank(SHOP);
        vm.expectRevert(AgentCartMerchantRegistryV2.InvalidAdmission.selector);
        registry.register(DOMAIN, HASH, URI);
        require(registry.recordIdForDomain(DOMAIN) == 0);
    }

    function testOneValidatorCannotAdmitAndAdmissionCannotBeFrontRun() public {
        uint64 expiry = uint64(block.timestamp + 60 days);
        vm.prank(A);
        registry.voteAdmission(DOMAIN, SHOP, HASH, ENTITY, expiry, EVIDENCE);
        vm.prank(SHOP);
        vm.expectRevert(AgentCartMerchantRegistryV2.InvalidAdmission.selector);
        registry.register(DOMAIN, HASH, URI);
        vm.prank(B);
        registry.voteAdmission(DOMAIN, SHOP, HASH, ENTITY, expiry, EVIDENCE);
        vm.prank(BUYER);
        vm.expectRevert(AgentCartMerchantRegistryV2.InvalidAdmission.selector);
        registry.register(DOMAIN, HASH, URI);
        vm.prank(SHOP);
        bytes32 id = registry.register(DOMAIN, HASH, URI);
        (bool eligible, bytes32 entity,, uint256 bond) = registry.eligibility(id);
        require(eligible && entity == ENTITY && bond == 100 && token.balanceOf(address(registry)) == 100);
    }

    function testRejectedBondTransferCannotCreateListing() public {
        _admit(SHOP, HASH, ENTITY);
        token.setFailTransfer(true);
        vm.prank(SHOP);
        vm.expectRevert(AgentCartMerchantRegistryV2.BondUnavailable.selector);
        registry.register(DOMAIN, HASH, URI);
        require(registry.recordIdForDomain(DOMAIN) == 0);
    }

    function testUpdateAndRotationRequireFreshAdmissionAndPreserveEntity() public {
        bytes32 id = _register();
        bytes32 nextHash = keccak256("next");
        vm.prank(SHOP);
        vm.expectRevert(AgentCartMerchantRegistryV2.InvalidAdmission.selector);
        registry.update(id, nextHash, URI);
        _admit(BUYER, nextHash, keccak256("different owner"));
        vm.prank(SHOP);
        vm.expectRevert(AgentCartMerchantRegistryV2.InvalidAdmission.selector);
        registry.setController(id, BUYER, nextHash, URI);
        _admit(BUYER, nextHash, ENTITY);
        vm.prank(SHOP);
        registry.setController(id, BUYER, nextHash, URI);
        require(registry.entityId(id) == ENTITY && registry.bondBalance(id) == 100);
    }

    function testExpiredAdmissionIsIneligible() public {
        bytes32 id = _register();
        vm.warp(block.timestamp + 61 days);
        (bool eligible,,,) = registry.eligibility(id);
        require(!eligible);
    }

    function testRenewalRequiresFreshQuorumAndPreservesRecordAndBond() public {
        bytes32 id = _register();
        vm.warp(block.timestamp + 61 days);
        (bool approved,,) = registry.admission(DOMAIN, SHOP, HASH);
        require(!approved);
        vm.prank(SHOP);
        vm.expectRevert(AgentCartMerchantRegistryV2.InvalidAdmission.selector);
        registry.renewAdmission(id);
        _admit(SHOP, HASH, ENTITY);
        (approved,,) = registry.admission(DOMAIN, SHOP, HASH);
        require(approved);
        (bool eligible,,,) = registry.eligibility(id);
        require(!eligible); // New votes are not bound until the merchant renews.
        vm.prank(BUYER);
        vm.expectRevert(AgentCartMerchantRegistryV2.NotController.selector);
        registry.renewAdmission(id);
        vm.prank(SHOP);
        registry.renewAdmission(id);
        (eligible,,,) = registry.eligibility(id);
        require(eligible && registry.bondBalance(id) == 100 && registry.record(id).recordHash == HASH);
    }

    function testSuspensionRequiresQuorumAndDelayAndCannotReuseVotes() public {
        bytes32 id = _register();
        vm.prank(A);
        registry.suspend(id, REASON);
        require(registry.record(id).status == Registry.Status.Active);
        vm.prank(B);
        registry.suspend(id, REASON);
        require(registry.record(id).status == Registry.Status.Active);
        vm.warp(block.timestamp + 2 days);
        vm.prank(A);
        registry.suspend(id, REASON);
        require(registry.record(id).status == Registry.Status.Suspended);
        vm.prank(A);
        registry.unsuspend(id);
        vm.prank(B);
        registry.unsuspend(id);
        vm.warp(block.timestamp + 2 days);
        vm.prank(A);
        registry.unsuspend(id);
        vm.prank(A);
        registry.suspend(id, REASON);
        require(registry.record(id).status == Registry.Status.Active);
    }

    function testSingleValidatorCannotSlashOrFreezeWithdrawal() public {
        bytes32 id = _register();
        vm.prank(A);
        registry.proposeSlash(id, 60, BUYER, REASON, URI);
        vm.expectRevert(AgentCartMerchantRegistryV2.InvalidSanction.selector);
        registry.executeSlash(id);
        vm.prank(SHOP);
        registry.revoke(id, REASON);
        vm.warp(block.timestamp + 30 days);
        vm.prank(SHOP);
        registry.withdrawBond(id);
        require(token.balanceOf(SHOP) == 1000);
    }

    function testQuorumSlashingCompensatesBuyerAndBlocksEntityReentry() public {
        bytes32 id = _register();
        _slash(id);
        vm.expectRevert(AgentCartMerchantRegistryV2.InvalidSanction.selector);
        registry.executeSlash(id);
        vm.warp(block.timestamp + 2 days);
        registry.executeSlash(id);
        require(token.balanceOf(BUYER) == 60 && registry.bondBalance(id) == 40);
        require(registry.blockedEntities(ENTITY));
        require(registry.record(id).status == Registry.Status.Revoked);
        vm.prank(A);
        vm.expectRevert(AgentCartMerchantRegistryV2.InvalidAdmission.selector);
        registry.voteAdmission(DOMAIN, BUYER, keccak256("new shop"), ENTITY, uint64(block.timestamp + 1 days), EVIDENCE);
        vm.expectRevert(AgentCartMerchantRegistryV2.InvalidSanction.selector);
        registry.executeSlash(id);
    }

    function testAppealRequiresFreshQuorumAndCannotBeIgnoredForExecution() public {
        bytes32 id = _register();
        _slash(id);
        vm.prank(SHOP);
        registry.appealSlash(id, keccak256("delivery proof"));
        vm.warp(block.timestamp + 7 days);
        vm.expectRevert(AgentCartMerchantRegistryV2.InvalidSanction.selector);
        registry.executeSlash(id);
        vm.prank(A);
        registry.reviewAppeal(id);
        vm.expectRevert(AgentCartMerchantRegistryV2.InvalidSanction.selector);
        registry.executeSlash(id);
        vm.prank(B);
        registry.reviewAppeal(id);
        registry.executeSlash(id);
        require(token.balanceOf(BUYER) == 60);
    }

    function testBondExitDelayAndPendingSanctionHold() public {
        bytes32 id = _register();
        vm.prank(SHOP);
        registry.revoke(id, REASON);
        vm.prank(SHOP);
        vm.expectRevert(AgentCartMerchantRegistryV2.BondUnavailable.selector);
        registry.withdrawBond(id);
        vm.warp(block.timestamp + 29 days);
        _slash(id);
        vm.warp(block.timestamp + 1 days);
        vm.prank(SHOP);
        vm.expectRevert(AgentCartMerchantRegistryV2.BondUnavailable.selector);
        registry.withdrawBond(id);
        vm.warp(block.timestamp + 10 days);
        vm.prank(SHOP);
        registry.withdrawBond(id);
        require(registry.bondBalance(id) == 0);
    }

    function testValidatorChurnHasBoundedCostAndRevokesOldAdmissions() public {
        bytes32 id = _register();
        _validator(A, false);
        (bool eligible,,,) = registry.eligibility(id);
        require(!eligible);
        _validator(A, true);
        (eligible,,,) = registry.eligibility(id);
        require(!eligible);
        for (uint160 i = 1000; i < 1020; i++) {
            _validator(address(i), true);
            _validator(address(i), false);
        }
        require(registry.validatorCount() == 3);
        uint256 beforeGas = gasleft();
        registry.record(id);
        require(beforeGas - gasleft() < 100000, "historical validators increased work");
    }

    function testQuorumCannotBeReducedToOneAndOwnerPauseIsDelayed() public {
        registry.scheduleGovernanceAction(registry.attestationThresholdActionHash(1));
        vm.warp(block.timestamp + 2 days);
        vm.expectRevert(
            abi.encodeWithSelector(AgentCartMerchantRegistryV2.InvalidAttestationThreshold.selector, uint16(1))
        );
        registry.setAttestationThreshold(1);
        vm.expectRevert(
            abi.encodeWithSelector(
                AgentCartMerchantRegistryV2.UnknownGovernanceAction.selector, keccak256(abi.encode("pause", true))
            )
        );
        registry.setWritesPaused(true);
        registry.scheduleGovernanceAction(keccak256(abi.encode("pause", true)));
        vm.expectRevert(
            abi.encodeWithSelector(
                AgentCartMerchantRegistryV2.GovernanceActionNotReady.selector, uint64(block.timestamp + 2 days)
            )
        );
        registry.setWritesPaused(true);
        vm.warp(block.timestamp + 2 days);
        registry.setWritesPaused(true);
        require(registry.writesPaused());
    }
}
