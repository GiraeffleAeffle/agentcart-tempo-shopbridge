import json
import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
READINESS_MODULE = (
    ROOT
    / "woocommerce-shopbridge"
    / "agentcart-shopbridge"
    / "includes"
    / "class-agentcart-shopbridge-registry-readiness.php"
)


@unittest.skipUnless(shutil.which("php"), "php is required for registry readiness tests")
class RegistryReadinessBehaviorTests(unittest.TestCase):
    reference_time = 1787745900  # 2026-08-26T12:05:00Z
    identity = {
        "controller": "0x" + "11" * 20,
        "chain_id": "eip155:42431",
        "registry_address": "0x" + "22" * 20,
        "record_id": "0x" + "33" * 32,
    }
    record_hash = "44" * 32

    def run_php(self, metadata_ready: bool, identity: dict, record_hash: str, health: dict) -> dict:
        script = f"""<?php
define('ABSPATH', '/');
require {json.dumps(str(READINESS_MODULE))};
echo json_encode(AgentCart_ShopBridge_Registry_Readiness::evaluate(
    {"true" if metadata_ready else "false"},
    json_decode({json.dumps(json.dumps(identity))}, true),
    {json.dumps(record_hash)},
    json_decode({json.dumps(json.dumps(health))}, true),
    {self.reference_time}
));
"""
        completed = subprocess.run(["php"], input=script, text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def finalized_health(self) -> dict:
        return {
            "state": "verified",
            "checked_at": "2026-08-26T12:00:00Z",
            "record_hash": self.record_hash,
            "health": {
                "ok": True,
                "onchain_source": {
                    "enabled": True,
                    "chain_valid": True,
                    "canonical_chain_verified": True,
                    "verification_mode": "direct_rpc",
                    "complete": True,
                    "chain_id": self.identity["chain_id"],
                    "registry_address": self.identity["registry_address"],
                    "finality": {
                        "block_tag": "finalized",
                        "block_number": 123,
                        "block_hash": "0x" + "55" * 32,
                        "block_time": "2026-08-26T12:00:00Z",
                        "state_selector": "block_hash_require_canonical",
                    },
                },
                "current_record": {
                    "match_type": "record_hash",
                    "registry_record_hash": self.record_hash,
                    "state": "verified",
                    "eligible": True,
                    "onchain_identity": {
                        **self.identity,
                        "record_hash": self.record_hash,
                        "status": "mapped",
                    },
                },
            },
        }

    def test_only_an_exact_finalized_identity_is_ready(self) -> None:
        result = self.run_php(True, self.identity, self.record_hash, self.finalized_health())
        self.assertEqual(result["state"], "finalized_current")
        self.assertTrue(result["ready"])
        self.assertEqual(result["finality"]["block_number"], 123)

    def test_metadata_identity_and_check_states_are_distinct(self) -> None:
        self.assertEqual(self.run_php(False, {}, self.record_hash, {})["state"], "metadata_incomplete")
        self.assertEqual(self.run_php(True, {}, self.record_hash, {})["state"], "identity_required")
        self.assertEqual(self.run_php(True, self.identity, self.record_hash, {})["state"], "not_checked")

    def test_hosted_success_or_unfinalized_source_never_counts_as_onchain(self) -> None:
        hosted_only = self.finalized_health()
        hosted_only["health"]["onchain_source"] = {}
        self.assertEqual(
            self.run_php(True, self.identity, self.record_hash, hosted_only)["state"],
            "source_unverified",
        )

        latest = self.finalized_health()
        latest["health"]["onchain_source"]["finality"]["block_tag"] = "latest"
        self.assertEqual(
            self.run_php(True, self.identity, self.record_hash, latest)["state"],
            "source_unverified",
        )

        operator_snapshot = self.finalized_health()
        operator_snapshot["health"]["onchain_source"].update(
            {
                "canonical_chain_verified": False,
                "verification_mode": "operator_snapshot",
            }
        )
        self.assertEqual(
            self.run_php(True, self.identity, self.record_hash, operator_snapshot)["state"],
            "source_unverified",
        )

        moving_block_tag = self.finalized_health()
        moving_block_tag["health"]["onchain_source"]["finality"]["state_selector"] = "moving_finalized_tag"
        self.assertEqual(
            self.run_php(True, self.identity, self.record_hash, moving_block_tag)["state"],
            "source_unverified",
        )

    def test_stale_health_check_or_finalized_block_never_counts_as_current(self) -> None:
        cases = {
            "saved check": ("checked_at", "2026-08-26T11:54:59Z"),
            "finalized block": ("block_time", "2026-08-26T11:54:59Z"),
        }
        for label, (field, value) in cases.items():
            with self.subTest(label=label):
                health = self.finalized_health()
                if field == "checked_at":
                    health[field] = value
                else:
                    health["health"]["onchain_source"]["finality"][field] = value

                result = self.run_php(True, self.identity, self.record_hash, health)

                self.assertEqual(result["state"], "source_unverified")
                self.assertFalse(result["ready"])

    def test_claim_change_after_check_requires_an_onchain_update(self) -> None:
        stale = self.finalized_health()
        stale["record_hash"] = "66" * 32
        result = self.run_php(True, self.identity, self.record_hash, stale)
        self.assertEqual(result["state"], "onchain_update_required")
        self.assertFalse(result["ready"])


if __name__ == "__main__":
    unittest.main()
