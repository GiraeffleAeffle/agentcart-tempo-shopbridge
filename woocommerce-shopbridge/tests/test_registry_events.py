import json
import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN_INCLUDES = ROOT / "woocommerce-shopbridge" / "agentcart-shopbridge" / "includes"
IDENTITY_MODULE = PLUGIN_INCLUDES / "class-agentcart-shopbridge-onchain-identity.php"
EVENTS_MODULE = PLUGIN_INCLUDES / "class-agentcart-shopbridge-registry-events.php"


@unittest.skipUnless(shutil.which("php"), "php is required for registry event projection tests")
class RegistryEventsBehaviorTests(unittest.TestCase):
    reference_time = 1787745900  # 2026-08-26T12:05:00Z
    identity = {
        "controller": "0x" + "11" * 20,
        "chain_id": "eip155:42431",
        "registry_address": "0x" + "22" * 20,
        "record_id": "0x" + "33" * 32,
    }
    current_hash = "44" * 32

    def run_php(self, document: dict) -> dict:
        script = f"""<?php
define('ABSPATH', '/');
require {json.dumps(str(IDENTITY_MODULE))};
require {json.dumps(str(EVENTS_MODULE))};
echo json_encode(AgentCart_ShopBridge_Registry_Events::project(
    json_decode({json.dumps(json.dumps(document))}, true),
    json_decode({json.dumps(json.dumps(self.identity))}, true),
    {json.dumps(self.current_hash)},
    [
        'merchant_id' => 'tea-shop',
        'name' => 'Tea Shop',
        'domain' => 'tea.example',
        'manifest_url' => 'https://tea.example/.well-known/agentcart.json',
    ],
    {self.reference_time}
));
"""
        completed = subprocess.run(["php"], input=script, text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def finalized_document(self) -> dict:
        return {
            "schema": "agentcart.onchain_registry_contract_events.v1",
            "implementation": "agentcart.onchain_registry_rpc_indexer.v1",
            "chain_id": self.identity["chain_id"],
            "registry_address": self.identity["registry_address"],
            "finality": {
                "block_tag": "finalized",
                "block_number": 140,
                "block_hash": "0x" + "55" * 32,
                "block_time": "2026-08-26T12:00:00Z",
                "indexed_from_block": 100,
                "indexed_to_block": 140,
            },
            "indexed_at": "2026-08-26T12:00:00Z",
            "complete": True,
            "errors": [],
            "events": [
                {
                    "event": "MerchantRegistered",
                    "block_number": 110,
                    "block_hash": "0x" + "a1" * 32,
                    "transaction_hash": "0x" + "b1" * 32,
                    "log_index": 0,
                    "args": {
                        "recordId": self.identity["record_id"],
                        "controller": self.identity["controller"],
                        "recordHash": "0x" + "66" * 32,
                    },
                },
                {
                    "event": "MerchantRevoked",
                    "block_number": 120,
                    "block_hash": "0x" + "a2" * 32,
                    "transaction_hash": "0x" + "b2" * 32,
                    "log_index": 0,
                    "args": {"recordId": self.identity["record_id"]},
                },
                {
                    "event": "MerchantRegistered",
                    "block_number": 130,
                    "block_hash": "0x" + "a3" * 32,
                    "transaction_hash": "0x" + "b3" * 32,
                    "log_index": 1,
                    "args": {
                        "recordId": self.identity["record_id"],
                        "controller": self.identity["controller"],
                        "recordHash": "0x" + self.current_hash,
                    },
                },
            ],
        }

    def test_replays_finalized_revoke_and_recovery_to_the_exact_current_record(self) -> None:
        result = self.run_php(self.finalized_document())

        self.assertEqual(result["errors"], [])
        self.assertFalse(result["onchain_source"]["chain_valid"])
        self.assertTrue(result["onchain_source"]["snapshot_valid"])
        self.assertFalse(result["onchain_source"]["canonical_chain_verified"])
        self.assertEqual(result["onchain_source"]["verification_mode"], "operator_snapshot")
        self.assertTrue(result["onchain_source"]["complete"])
        self.assertEqual(result["onchain_source"]["finality"]["block_tag"], "finalized")
        self.assertEqual(result["current_record"]["match_type"], "record_hash")
        self.assertEqual(result["current_record"]["registry_record_hash"], self.current_hash)
        self.assertTrue(result["current_record"]["eligible"])
        self.assertEqual(result["current_record"]["onchain_identity"]["record_id"], self.identity["record_id"])

    def test_requires_the_pinned_rpc_indexer_implementation(self) -> None:
        document = self.finalized_document()
        document["implementation"] = "friendlier-but-unreviewed-indexer.v2"

        result = self.run_php(document)

        self.assertFalse(result["onchain_source"]["snapshot_valid"])
        self.assertEqual(result["current_record"], [])
        self.assertIn("events_implementation_invalid", result["errors"])

    def test_requires_hashed_events_in_one_strictly_increasing_log_order(self) -> None:
        cases = {
            "missing block hash": (0, "block_hash", None, "events_entry_block_hash_invalid"),
            "malformed transaction hash": (
                1,
                "transaction_hash",
                "0x1234",
                "events_entry_transaction_hash_invalid",
            ),
            "duplicate log position": (1, "block_number", 110, "events_order_invalid"),
        }
        for label, (event_index, field, value, expected_error) in cases.items():
            with self.subTest(label=label):
                document = self.finalized_document()
                if value is None:
                    document["events"][event_index].pop(field)
                else:
                    document["events"][event_index][field] = value
                if label == "duplicate log position":
                    document["events"][event_index]["log_index"] = 0

                result = self.run_php(document)

                self.assertFalse(result["onchain_source"]["snapshot_valid"])
                self.assertEqual(result["current_record"], [])
                self.assertIn(expected_error, result["errors"])

    def test_requires_fresh_index_and_finalized_block_timestamps(self) -> None:
        cases = {
            "stale index": ("indexed_at", "2026-08-26T11:54:59Z", "events_indexed_at_invalid"),
            "stale finalized block": (
                "block_time",
                "2026-08-26T11:54:59Z",
                "events_finality_block_time_invalid",
            ),
            "future index": ("indexed_at", "2026-08-26T12:10:01Z", "events_indexed_at_invalid"),
        }
        for label, (field, value, expected_error) in cases.items():
            with self.subTest(label=label):
                document = self.finalized_document()
                if field == "block_time":
                    document["finality"][field] = value
                else:
                    document[field] = value

                result = self.run_php(document)

                self.assertFalse(result["onchain_source"]["snapshot_valid"])
                self.assertEqual(result["current_record"], [])
                self.assertIn(expected_error, result["errors"])

    def test_requires_strict_snapshot_and_finality_field_types(self) -> None:
        cases = {
            "non-boolean completeness": (
                lambda document: document.__setitem__("complete", 1),
                "events_snapshot_incomplete",
            ),
            "missing errors list": (
                lambda document: document.pop("errors"),
                "events_snapshot_has_errors",
            ),
            "string finalized block": (
                lambda document: document["finality"].__setitem__("block_number", "140"),
                "events_finality_invalid",
            ),
            "non-list events": (
                lambda document: document.__setitem__("events", "not-a-list"),
                "events_entries_invalid",
            ),
        }
        for label, (mutate, expected_error) in cases.items():
            with self.subTest(label=label):
                document = self.finalized_document()
                mutate(document)

                result = self.run_php(document)

                self.assertFalse(result["onchain_source"]["snapshot_valid"])
                self.assertEqual(result["current_record"], [])
                self.assertIn(expected_error, result["errors"])

    def test_later_hash_or_invalid_source_never_projects_the_current_record(self) -> None:
        changed = self.finalized_document()
        changed["events"].append(
            {
                "event": "MerchantUpdated",
                "block_number": 135,
                "block_hash": "0x" + "a4" * 32,
                "transaction_hash": "0x" + "b4" * 32,
                "log_index": 0,
                "args": {
                    "recordId": self.identity["record_id"],
                    "recordHash": "0x" + "77" * 32,
                },
            }
        )
        self.assertEqual(self.run_php(changed)["current_record"], [])

        wrong_chain = self.finalized_document()
        wrong_chain["chain_id"] = "eip155:1"
        result = self.run_php(wrong_chain)
        self.assertFalse(result["onchain_source"]["snapshot_valid"])
        self.assertEqual(result["current_record"], [])
        self.assertIn("events_chain_id_mismatch", result["errors"])


if __name__ == "__main__":
    unittest.main()
