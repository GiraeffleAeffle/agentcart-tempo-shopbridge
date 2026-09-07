"""Exercise actual PHP verification/readiness through independent RPC transcripts."""
import copy
import json
import subprocess
import unittest

import test_registry_rpc as legacy


class RegistryV2RpcTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.RegistryRpcBehaviorTests()
        self.fixture.descriptor = {
            **self.fixture.descriptor,
            "registry_version": 2,
            "witness_rpc_url": "https://witness.example",
        }
        self.primary = self.fixture.responses()
        self.primary["eth_getBlockByNumber:0x96"] = copy.deepcopy(self.primary["eth_getBlockByNumber:finalized"])
        self.admission_key = "eth_call:0x46a18c77" + self.fixture.record_id[2:] + ":hash:0x" + "55" * 32 + ":canonical"
        self.admission()
        self.witness = copy.deepcopy(self.primary)

    def admission(self, eligible=1, entity=6, expiry=None, bond=2**256 - 1):
        self.primary[self.admission_key] = "0x" + "".join(f"{n:064x}" for n in (
            eligible, entity, expiry if expiry is not None else self.fixture.now + 120, bond))

    def run_verify(self, **kwargs):
        return self.fixture.run_php(self.primary, witness=self.witness, **kwargs)

    def assert_closed(self, result, reason=None):
        self.assertFalse(result["onchain_source"]["chain_valid"])
        self.assertFalse(result["current_record"])
        self.assertTrue(result["errors"])
        if reason:
            self.assertIn(reason, result["errors"])

    def test_operator_configuration_and_uint256_bond_work_end_to_end(self):
        result = self.run_verify(configured=True, readiness_time=self.fixture.now)
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["readiness"]["ready"])
        self.assertEqual(result["current_record"]["admission"]["bond_base_units_hex"], "0x" + "f" * 64)
        self.assertTrue(result["onchain_source"]["witness_agreement"])
        self.assertNotIn("rpc_url", json.dumps(result))

    def test_witness_disagreement_on_each_required_state_read_fails_closed(self):
        for key in self.primary:
            if key == "eth_getBlockByNumber:finalized" or key.startswith("eth_call:0xe26ec9d5"):
                continue
            with self.subTest(key=key):
                self.witness = copy.deepcopy(self.primary)
                self.witness[key] = "0xdead"
                self.assert_closed(self.run_verify())

    def test_different_finalized_heights_use_common_lower_block(self):
        for provider in (self.primary, self.witness):
            other = self.witness if provider is self.primary else self.primary
            provider["eth_getBlockByNumber:finalized"] = {
                "number": "0x97", "hash": "0x" + "77" * 32, "timestamp": hex(self.fixture.now - 30)}
            result = self.run_verify()
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["onchain_source"]["finality"]["block_number"], 150)
            provider["eth_getBlockByNumber:finalized"] = copy.deepcopy(other["eth_getBlockByNumber:finalized"])

    def test_finalized_head_must_match_common_number_hash(self):
        self.witness["eth_getBlockByNumber:finalized"]["hash"] = "0x" + "77" * 32
        self.assert_closed(self.run_verify(), "rpc_witness_finality_mismatch")

    def test_both_heads_and_common_block_must_be_fresh(self):
        for key in ("eth_getBlockByNumber:finalized", "eth_getBlockByNumber:0x96"):
            for offset in (-601, 301):
                with self.subTest(key=key, offset=offset):
                    self.setUp()
                    self.witness[key]["timestamp"] = hex(self.fixture.now + offset)
                    self.assert_closed(self.run_verify())

    def test_ineligible_missing_entity_missing_bond_expired_or_malformed(self):
        for values in ({"eligible": 0}, {"eligible": 2}, {"entity": 0}, {"bond": 0},
                       {"expiry": self.fixture.now}, {"expiry": self.fixture.now - 1}):
            with self.subTest(values=values):
                self.admission(**values)
                self.witness = copy.deepcopy(self.primary)
                self.assert_closed(self.run_verify())
        self.primary[self.admission_key] = "0x01"
        self.witness = copy.deepcopy(self.primary)
        self.assert_closed(self.run_verify(), "rpc_admission_result_invalid")

    def test_admission_expiry_invalidates_still_fresh_cached_health(self):
        result = self.run_verify(readiness_time=self.fixture.now + 121)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["readiness"]["state"], "admission_required")
        self.assertFalse(result["readiness"]["ready"])

    def test_configuration_change_invalidates_cached_health(self):
        changed = {**self.fixture.descriptor, "witness_rpc_url": "https://new-witness.example"}
        result = self.run_verify(readiness_time=self.fixture.now, readiness_descriptor=changed)
        self.assertEqual(result["readiness"]["state"], "source_unverified")

    def test_absent_same_host_or_unsafe_witness_is_rejected_before_rpc(self):
        for url in (None, "https://rpc.example/other", "http://witness.example", "https://127.0.0.1",
                    "https://a:b@witness.example", "https://witness.example:8443", "https://foo.localhost"):
            with self.subTest(url=url):
                self.fixture.descriptor["witness_rpc_url"] = url
                self.assert_closed(self.run_verify())

    def test_invalid_explicit_configuration_never_uses_pilot_fallback(self):
        for descriptor in ({}, {"registry_version": 1}, {"registry_version": 2}, "invalid"):
            with self.subTest(descriptor=descriptor):
                self.fixture.descriptor = descriptor
                self.assert_closed(self.run_verify(configured=True), "rpc_deployment_descriptor_invalid")

    def test_pinned_runtime_still_required_when_both_providers_agree(self):
        self.fixture.descriptor["runtime_code_sha256"] = "0" * 64
        self.assert_closed(self.run_verify(), "rpc_runtime_code_hash_mismatch")

    def test_selector_matches_compiled_contract_abi(self):
        result = subprocess.run(["node", "--input-type=module", "-e",
            'import {toFunctionSelector} from "viem"; console.log(toFunctionSelector("eligibility(bytes32)"));'],
            cwd=legacy.ROOT / "gateway", capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "0x46a18c77")

    def test_wordpress_transport_batches_both_views_and_blocks_unsafe_redirects(self):
        result = self.fixture.run_default_transport_php(self.primary)
        self.assertEqual(result["result"]["errors"], [])
        self.assertEqual(result["batch_count"], 6)
        self.assertEqual(result["rpc_urls"].count("https://witness.example"), 3)
        self.assertEqual(result["rpc_timeouts"], [8] * 6)
        self.assertEqual(result["unsafe_url_guards"], [True] * 6)

    def test_agreed_malformed_creation_boundary_is_not_empty_code(self):
        for code in (None, "0x00"):
            with self.subTest(code=code):
                self.primary[f"eth_getCode:{self.fixture.registry}:0x63"] = code
                self.witness = copy.deepcopy(self.primary)
                self.assert_closed(self.run_verify(), "rpc_deployment_not_creation_boundary")
