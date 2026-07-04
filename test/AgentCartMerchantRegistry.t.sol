// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AgentCartMerchantRegistry} from "../contracts/AgentCartMerchantRegistry.sol";
import {IAgentCartMerchantRegistry} from "../contracts/interfaces/IAgentCartMerchantRegistry.sol";

interface Vm {
    function prank(address sender) external;
    function expectRevert(bytes calldata revertData) external;
    function warp(uint256 timestamp) external;
}

contract AgentCartMerchantRegistryTest {
    Vm private constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    AgentCartMerchantRegistry private registry;

    address private constant MERCHANT = address(0x1000000000000000000000000000000000000001);
    address private constant MERCHANT_2 = address(0x1000000000000000000000000000000000000002);
    address private constant VALIDATOR = address(0x2000000000000000000000000000000000000001);
    address private constant VALIDATOR_2 = address(0x2000000000000000000000000000000000000002);
    address private constant VALIDATOR_3 = address(0x2000000000000000000000000000000000000003);
    address private constant NEW_CONTROLLER = address(0x3000000000000000000000000000000000000001);
    address private constant NEW_OWNER = address(0x4000000000000000000000000000000000000001);

    bytes32 private constant DOMAIN_HASH = keccak256("fixture-shop.example");
    bytes32 private constant RECORD_HASH = keccak256("record-v1");
    bytes32 private constant RECORD_HASH_2 = keccak256("record-v2");
    bytes32 private constant RESULT_HASH = keccak256("validator-result");
    bytes32 private constant RESULT_HASH_2 = keccak256("validator-result-2");
    bytes32 private constant RESULT_HASH_3 = keccak256("validator-result-3");
    bytes32 private constant REASON_HASH = keccak256("merchant-revoke");
    bytes32 private constant FLAG_TYPE = keccak256("domain_proof_mismatch");

    string private constant RECORD_URI = "https://fixture-shop.example/.well-known/agentcart-registry-bundle.json";
    string private constant EVIDENCE_URI = "https://registry.agentcart.eu/evidence/fixture-shop";

    function setUp() public {
        registry = new AgentCartMerchantRegistry(address(this));
        _executeValidatorChange(VALIDATOR, true);
    }

    function testRegisterStoresRecordAndDomainIndex() public {
        bytes32 recordId = _register(MERCHANT, RECORD_HASH);
        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);

        require(stored.controller == MERCHANT, "controller mismatch");
        require(stored.recordHash == RECORD_HASH, "record hash mismatch");
        require(stored.domainHash == DOMAIN_HASH, "domain hash mismatch");
        require(stored.status == IAgentCartMerchantRegistry.Status.Active, "status mismatch");
        require(registry.recordIdForDomain(DOMAIN_HASH) == recordId, "domain index mismatch");
    }

    function testUpdateClearsAttestationAndRejectsOldHash() public {
        bytes32 recordId = _registerAndAttest();

        VM.prank(MERCHANT);
        registry.update(recordId, RECORD_HASH_2, RECORD_URI);

        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);
        require(stored.recordHash == RECORD_HASH_2, "updated hash mismatch");
        require(stored.attestedAt == 0, "attestation timestamp not cleared");
        require(stored.attestationExpiresAt == 0, "attestation expiry not cleared");
        require(stored.attestationCount == 0, "attestation count not cleared");

        VM.prank(VALIDATOR);
        VM.expectRevert(
            abi.encodeWithSelector(AgentCartMerchantRegistry.RecordHashMismatch.selector, RECORD_HASH_2, RECORD_HASH)
        );
        registry.attest(recordId, RECORD_HASH, RESULT_HASH, uint64(block.timestamp + 1 days), EVIDENCE_URI);
    }

    function testControllerRotationClearsAttestation() public {
        bytes32 recordId = _registerAndAttest();

        VM.prank(MERCHANT);
        registry.setController(recordId, NEW_CONTROLLER);

        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);
        require(stored.controller == NEW_CONTROLLER, "controller not rotated");
        require(stored.attestedAt == 0, "attestation timestamp not cleared");
        require(stored.attestationExpiresAt == 0, "attestation expiry not cleared");
        require(stored.attestationCount == 0, "attestation count not cleared");
    }

    function testRevokeIsMonotonicAndFreesDomain() public {
        bytes32 recordId = _register(MERCHANT, RECORD_HASH);

        VM.prank(MERCHANT);
        registry.revoke(recordId, REASON_HASH);

        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);
        require(stored.status == IAgentCartMerchantRegistry.Status.Revoked, "not revoked");
        require(registry.revokedRecordHashes(RECORD_HASH), "record hash not revoked");
        require(registry.recordIdForDomain(DOMAIN_HASH) == bytes32(0), "domain not released");

        VM.prank(MERCHANT_2);
        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantRegistry.RevokedRecordHash.selector, RECORD_HASH));
        registry.register(DOMAIN_HASH, RECORD_HASH, RECORD_URI);

        _register(MERCHANT_2, RECORD_HASH_2);
    }

    function testSuspendClearsAttestationAndFlagIsEventOnly() public {
        bytes32 recordId = _registerAndAttest();

        VM.prank(VALIDATOR);
        registry.flag(recordId, FLAG_TYPE, EVIDENCE_URI);
        require(registry.record(recordId).status == IAgentCartMerchantRegistry.Status.Active, "flag changed status");

        uint64 nextFlagAt = registry.nextFlagAvailableAt(recordId, VALIDATOR);
        VM.prank(VALIDATOR);
        VM.expectRevert(
            abi.encodeWithSelector(AgentCartMerchantRegistry.FlagCooldownActive.selector, recordId, nextFlagAt)
        );
        registry.flag(recordId, FLAG_TYPE, EVIDENCE_URI);

        VM.warp(uint256(nextFlagAt));
        VM.prank(VALIDATOR);
        registry.flag(recordId, FLAG_TYPE, EVIDENCE_URI);
        require(
            registry.record(recordId).status == IAgentCartMerchantRegistry.Status.Active, "second flag changed status"
        );

        VM.prank(VALIDATOR);
        registry.suspend(recordId, REASON_HASH);
        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);
        require(stored.status == IAgentCartMerchantRegistry.Status.Suspended, "not suspended");
        require(stored.attestedAt == 0, "attestation timestamp not cleared");
        require(stored.attestationExpiresAt == 0, "attestation expiry not cleared");
        require(stored.attestationCount == 0, "attestation count not cleared");
    }

    function testAttestationRequiresConfiguredThreshold() public {
        _executeValidatorChange(VALIDATOR_2, true);
        _executeThresholdChange(2);

        bytes32 recordId = _register(MERCHANT, RECORD_HASH);
        uint64 firstExpiry = uint64(block.timestamp + 1 days);

        VM.prank(VALIDATOR);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH, firstExpiry, EVIDENCE_URI);

        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);
        IAgentCartMerchantRegistry.Attestation memory validatorAttestation = registry.attestation(recordId, VALIDATOR);
        require(stored.attestationCount == 1, "first count mismatch");
        require(stored.attestedAt == 0, "threshold reached too early");
        require(!registry.isAttestationCurrent(recordId), "current before threshold");
        require(validatorAttestation.recordHash == RECORD_HASH, "validator record hash mismatch");
        require(validatorAttestation.resultHash == RESULT_HASH, "validator result hash mismatch");
        require(validatorAttestation.expiresAt == firstExpiry, "validator expiry mismatch");

        VM.prank(VALIDATOR);
        uint64 refreshedFirstExpiry = uint64(firstExpiry + 1 hours);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH, refreshedFirstExpiry, EVIDENCE_URI);
        stored = registry.record(recordId);
        require(stored.attestationCount == 1, "duplicate validator increased count");

        VM.prank(VALIDATOR_2);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH_2, uint64(firstExpiry + 2 hours), EVIDENCE_URI);

        stored = registry.record(recordId);
        require(stored.attestationCount == 2, "quorum count mismatch");
        require(stored.attestedAt != 0, "quorum timestamp missing");
        require(stored.attestationExpiresAt == refreshedFirstExpiry, "aggregate expiry not conservative");
        require(registry.isAttestationCurrent(recordId), "quorum not current");
    }

    function testAttestationQuorumRecoversAfterPartialExpiry() public {
        _executeValidatorChange(VALIDATOR_2, true);
        _executeThresholdChange(2);

        bytes32 recordId = _register(MERCHANT, RECORD_HASH);
        uint64 firstExpiry = uint64(block.timestamp + 100);
        uint64 secondExpiry = uint64(block.timestamp + 200);

        VM.prank(VALIDATOR);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH, firstExpiry, EVIDENCE_URI);
        VM.prank(VALIDATOR_2);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH_2, secondExpiry, EVIDENCE_URI);

        require(registry.isAttestationCurrent(recordId), "initial quorum not current");
        require(registry.record(recordId).attestationExpiresAt == firstExpiry, "initial expiry mismatch");

        VM.warp(uint256(firstExpiry) + 1);
        require(!registry.isAttestationCurrent(recordId), "quorum should lapse after first expiry");

        VM.prank(VALIDATOR);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH, uint64(block.timestamp + 300), EVIDENCE_URI);

        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);
        require(stored.attestationCount == 2, "valid second attestation not recounted");
        require(stored.attestationExpiresAt == secondExpiry, "recovered quorum expiry mismatch");
        require(registry.isAttestationCurrent(recordId), "quorum did not recover");
    }

    function testShortValidatorExpiryDoesNotVetoQuorumWhenThresholdStillMet() public {
        _executeValidatorChange(VALIDATOR_2, true);
        _executeValidatorChange(VALIDATOR_3, true);
        _executeThresholdChange(2);

        bytes32 recordId = _register(MERCHANT, RECORD_HASH);
        uint64 firstExpiry = uint64(block.timestamp + 100);
        uint64 secondExpiry = uint64(block.timestamp + 300);
        uint64 thirdExpiry = uint64(block.timestamp + 400);

        VM.prank(VALIDATOR);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH, firstExpiry, EVIDENCE_URI);
        VM.prank(VALIDATOR_2);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH_2, secondExpiry, EVIDENCE_URI);
        VM.prank(VALIDATOR_3);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH_3, thirdExpiry, EVIDENCE_URI);

        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);
        require(stored.attestationCount == 3, "three attestations not counted");
        require(stored.attestationExpiresAt == secondExpiry, "threshold expiry should ignore one short expiry");

        VM.warp(uint256(firstExpiry) + 1);

        stored = registry.record(recordId);
        require(stored.attestationCount == 2, "remaining quorum not counted");
        require(stored.attestationExpiresAt == secondExpiry, "remaining quorum expiry mismatch");
        require(registry.isAttestationCurrent(recordId), "single short expiry vetoed quorum");
    }

    function testValidatorReenableDoesNotReviveOldAttestation() public {
        _executeValidatorChange(VALIDATOR_2, true);
        _executeThresholdChange(2);

        bytes32 recordId = _register(MERCHANT, RECORD_HASH);
        VM.prank(VALIDATOR);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH, uint64(block.timestamp + 10 days), EVIDENCE_URI);
        VM.prank(VALIDATOR_2);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH_2, uint64(block.timestamp + 10 days), EVIDENCE_URI);
        require(registry.isAttestationCurrent(recordId), "initial quorum not current");

        _executeValidatorChange(VALIDATOR_2, false);
        require(!registry.isAttestationCurrent(recordId), "disabled validator still counted");

        _executeValidatorChange(VALIDATOR_2, true);
        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);
        require(stored.attestationCount == 1, "old attestation revived after reenable");
        require(!registry.isAttestationCurrent(recordId), "reenable revived quorum");

        VM.prank(VALIDATOR_2);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH_2, uint64(block.timestamp + 10 days), EVIDENCE_URI);
        require(registry.isAttestationCurrent(recordId), "fresh attestation did not restore quorum");
    }

    function testGovernanceActionsRequireDelay() public {
        bytes32 actionHash = registry.validatorActionHash(VALIDATOR_2, true);

        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantRegistry.UnknownGovernanceAction.selector, actionHash));
        registry.setValidator(VALIDATOR_2, true);

        uint64 readyAt = registry.scheduleGovernanceAction(actionHash);
        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantRegistry.GovernanceActionNotReady.selector, readyAt));
        registry.setValidator(VALIDATOR_2, true);

        VM.warp(uint256(readyAt));
        registry.setValidator(VALIDATOR_2, true);

        require(registry.validators(VALIDATOR_2), "validator not enabled");
        require(registry.validatorCount() == 2, "validator count mismatch");

        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantRegistry.UnknownGovernanceAction.selector, actionHash));
        registry.setValidator(VALIDATOR_2, true);
    }

    function testGovernanceActionsExpire() public {
        bytes32 actionHash = registry.validatorActionHash(VALIDATOR_2, true);
        uint64 readyAt = registry.scheduleGovernanceAction(actionHash);
        uint64 expiredAt = readyAt + registry.GOVERNANCE_EXECUTION_WINDOW_SECONDS();

        VM.warp(uint256(expiredAt) + 1);
        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantRegistry.GovernanceActionExpired.selector, expiredAt));
        registry.setValidator(VALIDATOR_2, true);

        readyAt = registry.scheduleGovernanceAction(actionHash);
        VM.warp(uint256(readyAt));
        registry.setValidator(VALIDATOR_2, true);
        require(registry.validators(VALIDATOR_2), "validator not enabled after reschedule");
    }

    function testOwnershipTransferRequiresAcceptance() public {
        registry.transferOwnership(NEW_OWNER);

        require(registry.owner() == address(this), "owner changed before acceptance");
        require(registry.pendingOwner() == NEW_OWNER, "pending owner mismatch");

        VM.prank(MERCHANT);
        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantRegistry.NotPendingOwner.selector));
        registry.acceptOwnership();

        VM.prank(NEW_OWNER);
        registry.acceptOwnership();

        require(registry.owner() == NEW_OWNER, "owner not accepted");
        require(registry.pendingOwner() == address(0), "pending owner not cleared");

        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantRegistry.NotOwner.selector));
        registry.setWritesPaused(true);

        VM.prank(NEW_OWNER);
        registry.setWritesPaused(true);
        require(registry.writesPaused(), "new owner cannot pause writes");
    }

    function testSquatterCannotPermanentlyBlockDomainSupersession() public {
        bytes32 squatterRecordId = _register(MERCHANT_2, RECORD_HASH_2);

        VM.prank(MERCHANT);
        VM.expectRevert(
            abi.encodeWithSelector(
                AgentCartMerchantRegistry.DomainAlreadyRegistered.selector, DOMAIN_HASH, squatterRecordId
            )
        );
        registry.register(DOMAIN_HASH, RECORD_HASH, RECORD_URI);

        VM.prank(MERCHANT);
        (bytes32 pendingRecordId, uint64 availableAt) =
            registry.requestSupersession(DOMAIN_HASH, RECORD_HASH, REASON_HASH, RECORD_URI, EVIDENCE_URI);

        IAgentCartMerchantRegistry.Supersession memory pending = registry.supersession(pendingRecordId);
        require(pending.controller == MERCHANT, "pending controller mismatch");
        require(pending.previousRecordId == squatterRecordId, "previous record mismatch");
        require(pending.recordHash == RECORD_HASH, "pending hash mismatch");

        VM.prank(MERCHANT);
        VM.expectRevert(
            abi.encodeWithSelector(AgentCartMerchantRegistry.SupersessionNotApproved.selector, pendingRecordId)
        );
        registry.activateSupersession(pendingRecordId, RECORD_URI);

        availableAt = _approveSupersession(pendingRecordId, RECORD_HASH);

        VM.prank(MERCHANT);
        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantRegistry.SupersessionNotReady.selector, availableAt));
        registry.activateSupersession(pendingRecordId, RECORD_URI);

        VM.warp(uint256(availableAt) + 1);
        VM.prank(MERCHANT);
        registry.activateSupersession(pendingRecordId, RECORD_URI);

        IAgentCartMerchantRegistry.Record memory squatter = registry.record(squatterRecordId);
        IAgentCartMerchantRegistry.Record memory recovered = registry.record(pendingRecordId);
        require(squatter.status == IAgentCartMerchantRegistry.Status.Revoked, "squatter not revoked");
        require(registry.revokedRecordHashes(RECORD_HASH_2), "squatter hash not revoked");
        require(registry.recordIdForDomain(DOMAIN_HASH) == pendingRecordId, "domain not recovered");
        require(recovered.controller == MERCHANT, "recovered controller mismatch");
        require(recovered.recordHash == RECORD_HASH, "recovered record hash mismatch");
        require(recovered.status == IAgentCartMerchantRegistry.Status.Active, "recovered not active");
    }

    function testPermissionlessSupersessionCannotEvictAttestedIncumbent() public {
        bytes32 incumbentRecordId = _registerAndAttest();

        VM.prank(MERCHANT_2);
        (bytes32 pendingRecordId, uint64 availableAt) =
            registry.requestSupersession(DOMAIN_HASH, RECORD_HASH_2, REASON_HASH, RECORD_URI, EVIDENCE_URI);

        VM.warp(uint256(availableAt) + 1);
        VM.prank(MERCHANT_2);
        VM.expectRevert(
            abi.encodeWithSelector(AgentCartMerchantRegistry.SupersessionNotApproved.selector, pendingRecordId)
        );
        registry.activateSupersession(pendingRecordId, RECORD_URI);

        IAgentCartMerchantRegistry.Record memory incumbent = registry.record(incumbentRecordId);
        require(incumbent.status == IAgentCartMerchantRegistry.Status.Active, "incumbent was evicted");
        require(!registry.revokedRecordHashes(RECORD_HASH), "incumbent hash was burned");
        require(registry.recordIdForDomain(DOMAIN_HASH) == incumbentRecordId, "domain slot changed");

        VM.prank(MERCHANT);
        registry.cancelSupersession(pendingRecordId, REASON_HASH);
        VM.prank(MERCHANT_2);
        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantRegistry.UnknownSupersession.selector));
        registry.activateSupersession(pendingRecordId, RECORD_URI);
    }

    function testSupersessionTargetChangeFailsClosed() public {
        bytes32 originalRecordId = _register(MERCHANT_2, RECORD_HASH_2);

        VM.prank(MERCHANT);
        (bytes32 pendingRecordId, uint64 availableAt) =
            registry.requestSupersession(DOMAIN_HASH, RECORD_HASH, REASON_HASH, RECORD_URI, EVIDENCE_URI);

        availableAt = _approveSupersession(pendingRecordId, RECORD_HASH);

        VM.prank(MERCHANT_2);
        registry.revoke(originalRecordId, REASON_HASH);

        bytes32 replacementRecordId = _register(NEW_CONTROLLER, keccak256("record-v3"));

        VM.warp(uint256(availableAt) + 1);
        VM.prank(MERCHANT);
        VM.expectRevert(
            abi.encodeWithSelector(
                AgentCartMerchantRegistry.SupersessionTargetChanged.selector, originalRecordId, replacementRecordId
            )
        );
        registry.activateSupersession(pendingRecordId, RECORD_URI);
    }

    function testOwnerForceRevokeFreesSquattedDomain() public {
        bytes32 squatterRecordId = _register(MERCHANT_2, RECORD_HASH_2);

        VM.prank(MERCHANT);
        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantRegistry.NotOwner.selector));
        registry.forceRevoke(squatterRecordId, REASON_HASH);

        bytes32 actionHash = registry.forceRevokeActionHash(squatterRecordId, REASON_HASH);
        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantRegistry.UnknownGovernanceAction.selector, actionHash));
        registry.forceRevoke(squatterRecordId, REASON_HASH);

        _executeForceRevoke(squatterRecordId, REASON_HASH);

        IAgentCartMerchantRegistry.Record memory squatter = registry.record(squatterRecordId);
        require(squatter.status == IAgentCartMerchantRegistry.Status.Revoked, "squatter not force revoked");
        require(registry.revokedRecordHashes(RECORD_HASH_2), "squatter hash not revoked");
        require(registry.recordIdForDomain(DOMAIN_HASH) == bytes32(0), "domain not released");

        _register(MERCHANT, RECORD_HASH);
    }

    function _register(address controller, bytes32 recordHash) private returns (bytes32 recordId) {
        VM.prank(controller);
        return registry.register(DOMAIN_HASH, recordHash, RECORD_URI);
    }

    function _registerAndAttest() private returns (bytes32 recordId) {
        recordId = _register(MERCHANT, RECORD_HASH);

        VM.prank(VALIDATOR);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH, uint64(block.timestamp + 1 days), EVIDENCE_URI);

        require(registry.isAttestationCurrent(recordId), "not attested");
        require(registry.record(recordId).attestationCount == 1, "attestation count mismatch");
    }

    function _approveSupersession(bytes32 pendingRecordId, bytes32 recordHash) private returns (uint64 availableAt) {
        VM.prank(VALIDATOR);
        return registry.approveSupersession(pendingRecordId, recordHash, EVIDENCE_URI);
    }

    function _executeValidatorChange(address validator, bool enabled) private {
        bytes32 actionHash = registry.validatorActionHash(validator, enabled);
        uint64 readyAt = registry.scheduleGovernanceAction(actionHash);
        VM.warp(uint256(readyAt));
        registry.setValidator(validator, enabled);
    }

    function _executeThresholdChange(uint16 threshold) private {
        bytes32 actionHash = registry.attestationThresholdActionHash(threshold);
        uint64 readyAt = registry.scheduleGovernanceAction(actionHash);
        VM.warp(uint256(readyAt));
        registry.setAttestationThreshold(threshold);
    }

    function _executeForceRevoke(bytes32 recordId, bytes32 reasonHash) private {
        bytes32 actionHash = registry.forceRevokeActionHash(recordId, reasonHash);
        uint64 readyAt = registry.scheduleGovernanceAction(actionHash);
        VM.warp(uint256(readyAt));
        registry.forceRevoke(recordId, reasonHash);
    }
}
