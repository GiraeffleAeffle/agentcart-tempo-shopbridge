from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "gateway" / "scripts" / "registry_record.py"
TRUST_FIXTURE_PATH = ROOT / "docs" / "fixtures" / "registry" / "trust-fixtures.json"
ONCHAIN_CONTRACT_PATH = ROOT / "docs" / "fixtures" / "registry" / "onchain-adapter-contract.json"
ONCHAIN_CONTRACT_EVENTS_PATH = ROOT / "docs" / "fixtures" / "registry" / "onchain-contract-events.json"
SPEC = importlib.util.spec_from_file_location("registry_record_tool", TOOL_PATH)
registry_record_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["registry_record_tool"] = registry_record_tool
SPEC.loader.exec_module(registry_record_tool)


def shopbridge_manifest() -> dict[str, object]:
    return {
        "merchant": {
            "id": "merchant-tea-shop",
            "name": "Merchant Tea Shop",
            "merchant_of_record": {
                "name": "Merchant Tea Shop GmbH",
                "country": "DE",
                "support_email": "support@merchant.example",
            },
            "terms_url": "https://merchant.example/terms",
            "returns_url": "https://merchant.example/returns",
        },
        "manifest_url": "https://merchant.example/.well-known/agentcart.json",
        "protocols": [
            {
                "id": "agentcart-shopbridge",
                "version": "0.1",
                "role": "merchant_catalog_quote_checkout",
            },
            {
                "id": "tempo-mpp",
                "network": "testnet",
                "recipient": "0x1111111111111111111111111111111111111111",
            },
        ],
        "delivery": {
            "ship_to_countries": ["DE", "AT", "DE"],
        },
        "endpoints": {
            "catalog": "https://merchant.example/wp-json/agentcart/v1/catalog",
            "quote": "https://merchant.example/wp-json/agentcart/v1/quote",
        },
        "discovery": {
            "registry_proof": {
                "signature_alg": "https-domain-proof",
                "url": "https://merchant.example/.well-known/agentcart-registry-proof.json",
            },
        },
    }


def shopbridge_profile_manifest() -> dict[str, object]:
    manifest = shopbridge_manifest()
    manifest["protocols"] = [{"id": "agentcart-shopbridge"}]
    manifest["protocol_profiles"] = [
        {"id": "agentcart-shopbridge", "type": "commerce", "status": "available"},
        {
            "id": "mpp-http-auth",
            "type": "payment",
            "payment_protocol_id": "tempo-mpp",
            "status": "available",
            "network": "testnet",
            "recipient": "0x1111111111111111111111111111111111111111",
        },
        {
            "id": "stripe-card-mpp",
            "type": "payment",
            "payment_protocol_id": "stripe-card-mpp",
            "status": "available",
            "network_id": "acct_shop_123",
        },
    ]
    return manifest


def shopbridge_manifest_with_published_claim() -> dict[str, object]:
    manifest = shopbridge_manifest()
    manifest["discovery"] = {
        "registry_proof": {
            "signature_alg": "https-domain-proof",
            "url": "https://merchant.example/.well-known/agentcart-registry-proof.json",
        }
    }
    claim = registry_record_tool.registry_claim(manifest)
    claim["revocation_url"] = "https://merchant.example/.well-known/agentcart-registry-revocations.json"
    record = {
        **claim,
        "registry_claim_hash_alg": "sha-256",
        "registry_claim_hash": registry_record_tool.agentcart.canonical_json_hash(claim),
        "updated_at": registry_record_tool.iso_now(),
        "revoked_at": None,
        "signature_alg": "https-domain-proof",
        "signature": "",
        "proof": {
            "type": "https-well-known",
            "url": "https://merchant.example/.well-known/agentcart-registry-proof.json",
        },
    }
    manifest["discovery"] = {
        "registry_proof": {
            "signature_alg": "https-domain-proof",
            "url": "https://merchant.example/.well-known/agentcart-registry-proof.json",
        },
        "registry_claim_hash_alg": "sha-256",
        "registry_claim_hash": record["registry_claim_hash"],
        "registry_claim": claim,
        "registry_record_hash": registry_record_tool.agentcart.registry_record_hash(record),
        "registry_updated_at": record["updated_at"],
        "registry_ready": True,
        "suggested_registry_record": record,
        "revocation_url": record["revocation_url"],
    }
    return manifest


def revocation_document(record: dict[str, object], revocations: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "type": "agentcart-registry-revocations",
        "merchant_id": record["merchant_id"],
        "domain": record["domain"],
        "updated_at": record["updated_at"],
        "revocations": revocations or [],
    }


def registry_trust_fixture() -> dict[str, object]:
    return json.loads(TRUST_FIXTURE_PATH.read_text(encoding="utf-8"))


def onchain_contract_fixture() -> dict[str, object]:
    return json.loads(ONCHAIN_CONTRACT_PATH.read_text(encoding="utf-8"))


def onchain_contract_events_fixture() -> dict[str, object]:
    return json.loads(ONCHAIN_CONTRACT_EVENTS_PATH.read_text(encoding="utf-8"))


class RegistryRecordToolTests(unittest.TestCase):
    def test_builds_legacy_domain_proof_record_and_paste_back_settings(self) -> None:
        manifest = shopbridge_manifest()
        record = registry_record_tool.build_registry_record(
            manifest,
            updated_at=registry_record_tool.iso_now(),
        )
        bundle = registry_record_tool.onboarding_bundle(record)

        self.assertEqual(record["merchant_id"], "merchant-tea-shop")
        self.assertEqual(record["domain"], "merchant.example")
        self.assertEqual(record["manifest_hash"], registry_record_tool.agentcart.canonical_json_hash(manifest))
        self.assertEqual(record["ship_to_countries"], ["AT", "DE"])
        self.assertEqual(record["payment_network"], "testnet")
        self.assertEqual(record["payment_recipient"], "0x1111111111111111111111111111111111111111")
        self.assertEqual(record["signature_alg"], "https-domain-proof")
        self.assertEqual(
            record["proof"]["url"],
            "https://merchant.example/.well-known/agentcart-registry-proof.json",
        )
        self.assertEqual(
            bundle["legacy_merchant_settings"]["AGENTCART_REGISTRY_RECORD_HASH"],
            registry_record_tool.agentcart.registry_record_hash(record),
        )
        self.assertEqual(
            bundle["legacy_merchant_settings"]["AGENTCART_REGISTRY_MANIFEST_HASH"],
            registry_record_tool.agentcart.canonical_json_hash(manifest),
        )

    def test_builds_record_from_protocol_profiles_without_legacy_payment_protocols(self) -> None:
        manifest = shopbridge_profile_manifest()
        claim = registry_record_tool.registry_claim(manifest)

        self.assertEqual(claim["payment_network"], "testnet")
        self.assertEqual(claim["payment_recipient"], "0x1111111111111111111111111111111111111111")
        self.assertEqual(claim["stripe_profile_id"], "acct_shop_123")
        self.assertEqual(claim["protocol_profile_ids"], ["agentcart-shopbridge", "mpp-http-auth", "stripe-card-mpp"])
        self.assertIn("tempo-mpp", claim["supported_protocols"])
        self.assertIn("stripe-card-mpp", claim["supported_protocols"])

    def test_env_format_says_no_paste_back_for_auto_managed_claim(self) -> None:
        manifest = shopbridge_manifest_with_published_claim()
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = pathlib.Path(raw_tmp)
            manifest_file = tmp / "manifest.json"
            output_file = tmp / "env.txt"
            manifest_file.write_text(json.dumps(manifest))

            exit_code = registry_record_tool.main([
                "build",
                "--manifest-file",
                str(manifest_file),
                "--format",
                "env",
                "--output",
                str(output_file),
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                output_file.read_text(),
                "# no merchant env paste-back is required for this ShopBridge manifest\n",
            )

    def test_build_prefers_auto_managed_shopbridge_registry_claim(self) -> None:
        manifest = shopbridge_manifest_with_published_claim()

        record = registry_record_tool.build_registry_record(manifest)
        bundle = registry_record_tool.onboarding_bundle(record)

        self.assertNotIn("manifest_hash", record)
        self.assertEqual(record, manifest["discovery"]["suggested_registry_record"])
        self.assertEqual(
            record["registry_claim_hash"],
            registry_record_tool.agentcart.canonical_json_hash(manifest["discovery"]["registry_claim"]),
        )
        self.assertEqual(bundle["legacy_merchant_settings"], {})
        self.assertIn("auto-publishes", bundle["merchant_action"])

    def test_projects_shared_registry_record_to_onchain_contract_shape(self) -> None:
        trust = registry_trust_fixture()
        contract = onchain_contract_fixture()

        projection = registry_record_tool.onchain_projection(trust["base"]["record"])

        self.assertEqual(projection, contract["sample"]["onchain_record"])
        self.assertTrue(set(contract["required_onchain_fields"]).issubset(projection))
        self.assertTrue(set(contract["offchain_only_fields"]).isdisjoint(projection))

    def test_build_format_onchain_uses_plugin_published_registry_record(self) -> None:
        trust = registry_trust_fixture()
        contract = onchain_contract_fixture()
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = pathlib.Path(raw_tmp)
            manifest_file = tmp / "manifest.json"
            output_file = tmp / "onchain.json"
            manifest_file.write_text(json.dumps(trust["base"]["manifest"]), encoding="utf-8")

            exit_code = registry_record_tool.main([
                "build",
                "--manifest-file",
                str(manifest_file),
                "--format",
                "onchain",
                "--output",
                str(output_file),
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output_file.read_text(encoding="utf-8")), contract["sample"]["onchain_record"])

    def test_project_onchain_command_accepts_existing_registry_record(self) -> None:
        trust = registry_trust_fixture()
        contract = onchain_contract_fixture()
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = pathlib.Path(raw_tmp)
            record_file = tmp / "record.json"
            output_file = tmp / "onchain.json"
            record_file.write_text(json.dumps(trust["base"]["record"]), encoding="utf-8")

            exit_code = registry_record_tool.main([
                "project-onchain",
                "--record-file",
                str(record_file),
                "--output",
                str(output_file),
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output_file.read_text(encoding="utf-8")), contract["sample"]["onchain_record"])

    def test_onchain_projection_fails_closed_when_required_claim_hash_is_missing(self) -> None:
        trust = registry_trust_fixture()
        record = copy.deepcopy(trust["base"]["record"])
        record.pop("registry_claim_hash")

        with self.assertRaisesRegex(ValueError, "registry_claim_hash"):
            registry_record_tool.onchain_projection(record)

    def test_onchain_projection_rejects_malformed_claim_hash(self) -> None:
        trust = registry_trust_fixture()
        record = copy.deepcopy(trust["base"]["record"])
        record["registry_claim_hash"] = "not-a-sha256-hash"

        with self.assertRaisesRegex(ValueError, "SHA-256 hex digest"):
            registry_record_tool.onchain_projection(record)

    def test_append_only_onchain_ledger_indexes_active_and_revoked_records(self) -> None:
        trust = registry_trust_fixture()
        contract = onchain_contract_fixture()
        record_hash = contract["sample"]["onchain_record"]["record_hash"]
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = pathlib.Path(raw_tmp)
            ledger_file = tmp / "onchain-registry.jsonl"
            record_file = tmp / "record.json"
            upsert_file = tmp / "upsert.json"
            revoke_file = tmp / "revoke.json"
            index_file = tmp / "index.json"
            revoked_index_file = tmp / "revoked-index.json"
            record_file.write_text(json.dumps(trust["base"]["record"]), encoding="utf-8")

            upsert_exit = registry_record_tool.main([
                "append-onchain",
                "--ledger-file",
                str(ledger_file),
                "--operation",
                "upsert",
                "--record-file",
                str(record_file),
                "--created-at",
                "2026-06-01T00:00:00Z",
                "--output",
                str(upsert_file),
            ])
            index_exit = registry_record_tool.main([
                "index-onchain",
                "--ledger-file",
                str(ledger_file),
                "--output",
                str(index_file),
            ])
            revoke_exit = registry_record_tool.main([
                "append-onchain",
                "--ledger-file",
                str(ledger_file),
                "--operation",
                "revoke",
                "--record-hash",
                record_hash,
                "--created-at",
                "2026-06-02T00:00:00Z",
                "--reason",
                "merchant_admin_revoke",
                "--output",
                str(revoke_file),
            ])
            revoked_index_exit = registry_record_tool.main([
                "index-onchain",
                "--ledger-file",
                str(ledger_file),
                "--output",
                str(revoked_index_file),
            ])

            self.assertEqual(upsert_exit, 0)
            self.assertEqual(index_exit, 0)
            self.assertEqual(revoke_exit, 0)
            self.assertEqual(revoked_index_exit, 0)

            upsert_event = json.loads(upsert_file.read_text(encoding="utf-8"))
            index = json.loads(index_file.read_text(encoding="utf-8"))
            revoked_index = json.loads(revoked_index_file.read_text(encoding="utf-8"))

            self.assertEqual(upsert_event["schema"], "agentcart.onchain_registry_ledger_event.v1")
            self.assertEqual(upsert_event["operation"], "upsert")
            self.assertEqual(upsert_event["previous_event_hash"], "")
            self.assertEqual(upsert_event["record_hash"], record_hash)
            self.assertEqual(upsert_event["onchain_record"], contract["sample"]["onchain_record"])
            self.assertTrue(set(contract["offchain_only_fields"]).isdisjoint(upsert_event["onchain_record"]))

            self.assertEqual(index["schema"], "agentcart.onchain_registry_ledger_index.v1")
            self.assertTrue(index["verification"]["chain_valid"])
            self.assertEqual(index["records"], [contract["sample"]["onchain_record"]])
            self.assertEqual(index["revocations"], [])
            self.assertEqual(index["proof"]["record_hashes"], [record_hash])
            self.assertEqual(index["proof"]["revocation_record_hashes"], [])

            events = registry_record_tool.load_onchain_ledger_events(ledger_file)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[1]["previous_event_hash"], events[0]["event_hash"])
            self.assertTrue(registry_record_tool.verify_onchain_ledger_events(events)["chain_valid"])

            self.assertTrue(revoked_index["verification"]["chain_valid"])
            self.assertEqual(revoked_index["records"], [])
            self.assertEqual([item["record_hash"] for item in revoked_index["revocations"]], [record_hash])
            self.assertEqual(revoked_index["proof"]["record_hashes"], [])
            self.assertEqual(revoked_index["proof"]["revocation_record_hashes"], [record_hash])

    def test_onchain_ledger_index_reports_hash_chain_tampering(self) -> None:
        trust = registry_trust_fixture()
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = pathlib.Path(raw_tmp)
            ledger_file = tmp / "onchain-registry.jsonl"
            record_file = tmp / "record.json"
            upsert_file = tmp / "upsert.json"
            index_file = tmp / "index.json"
            record_file.write_text(json.dumps(trust["base"]["record"]), encoding="utf-8")
            self.assertEqual(
                registry_record_tool.main([
                    "append-onchain",
                    "--ledger-file",
                    str(ledger_file),
                    "--operation",
                    "upsert",
                    "--record-file",
                    str(record_file),
                    "--output",
                    str(upsert_file),
                ]),
                0,
            )
            event = json.loads(ledger_file.read_text(encoding="utf-8"))
            event["merchant_id"] = "tampered-shop"
            ledger_file.write_text(json.dumps(event, sort_keys=True) + "\n", encoding="utf-8")

            exit_code = registry_record_tool.main([
                "index-onchain",
                "--ledger-file",
                str(ledger_file),
                "--output",
                str(index_file),
            ])

            self.assertEqual(exit_code, 1)
            index = json.loads(index_file.read_text(encoding="utf-8"))
            self.assertFalse(index["verification"]["chain_valid"])
            self.assertEqual(index["verification"]["errors"][0]["error"], "event_hash_mismatch")
            self.assertEqual(index["records"], [])
            self.assertEqual(index["revocations"], [])

    def test_contract_events_index_to_onchain_adapter_records(self) -> None:
        contract = onchain_contract_fixture()
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = pathlib.Path(raw_tmp)
            events_file = tmp / "contract-events.json"
            output_file = tmp / "contract-index.json"
            events_file.write_text(json.dumps(onchain_contract_events_fixture()), encoding="utf-8")

            exit_code = registry_record_tool.main([
                "index-contract-events",
                "--events-file",
                str(events_file),
                "--output",
                str(output_file),
            ])

            self.assertEqual(exit_code, 0)
            index = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(index["schema"], "agentcart.onchain_registry_contract_index.v1")
            self.assertTrue(index["verification"]["chain_valid"])
            self.assertEqual(index["records"], [contract["sample"]["onchain_record"]])
            self.assertEqual(index["revocations"], [])
            self.assertEqual(index["proof"]["record_hashes"], [contract["sample"]["onchain_record"]["record_hash"]])
            self.assertEqual(index["proof"]["revocation_record_hashes"], [])
            self.assertEqual(index["attestations"][0]["record_hash"], contract["sample"]["onchain_record"]["record_hash"])
            self.assertEqual(index["flags"][0]["challenge_type"], "domain_proof_mismatch")
            self.assertEqual(index["suspensions"], [])

    def test_contract_events_ignore_governance_events(self) -> None:
        contract = onchain_contract_fixture()
        fixture = onchain_contract_events_fixture()
        fixture["events"].insert(
            1,
            {
                "event": "GovernanceActionScheduled",
                "block_number": 100,
                "block_time": "2026-06-01T00:01:00Z",
                "transaction_hash": "0x1212121212121212121212121212121212121212121212121212121212121212",
                "log_index": 1,
                "args": {
                    "actionHash": "0x1313131313131313131313131313131313131313131313131313131313131313",
                    "readyAt": 1782864060,
                },
            },
        )
        fixture["events"].insert(
            2,
            {
                "event": "ValidatorSet",
                "block_number": 100,
                "block_time": "2026-06-01T00:02:00Z",
                "transaction_hash": "0x1414141414141414141414141414141414141414141414141414141414141414",
                "log_index": 2,
                "args": {
                    "validator": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "enabled": True,
                },
            },
        )

        index = registry_record_tool.index_onchain_contract_events(fixture["events"])

        self.assertTrue(index["verification"]["chain_valid"], index)
        self.assertEqual(index["records"], [contract["sample"]["onchain_record"]])
        self.assertEqual(index["proof"]["record_hashes"], [contract["sample"]["onchain_record"]["record_hash"]])

    def test_contract_events_keep_attestations_per_validator(self) -> None:
        contract = onchain_contract_fixture()
        fixture = onchain_contract_events_fixture()
        fixture["events"].append(
            {
                "event": "MerchantAttested",
                "block_number": 106,
                "block_time": "2026-06-01T00:30:00Z",
                "transaction_hash": "0x1515151515151515151515151515151515151515151515151515151515151515",
                "log_index": 0,
                "args": {
                    "recordId": "0x4444444444444444444444444444444444444444444444444444444444444444",
                    "validator": "0xdddddddddddddddddddddddddddddddddddddddd",
                    "recordHash": "0x0e8f8493e57e69734713cbfdc16c0effda09df4e304b72c08e50ed8187a97bef",
                    "resultHash": "0xadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadad",
                    "expiresAt": 1782866100,
                    "evidenceURI": "https://registry.agentcart.eu/evidence/fixture-tea-shop/second-validator",
                },
            }
        )

        index = registry_record_tool.index_onchain_contract_events(fixture["events"])

        self.assertTrue(index["verification"]["chain_valid"], index)
        self.assertEqual(index["records"], [contract["sample"]["onchain_record"]])
        self.assertEqual(len(index["attestations"]), 2)
        self.assertEqual(
            [item["validator"] for item in index["attestations"]],
            ["0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "0xdddddddddddddddddddddddddddddddddddddddd"],
        )

    def test_contract_events_revoke_removes_active_record(self) -> None:
        contract = onchain_contract_fixture()
        fixture = onchain_contract_events_fixture()
        events = fixture["events"]
        events.append(
            {
                "event": "MerchantRevoked",
                "block_number": 106,
                "block_time": "2026-06-01T00:30:00Z",
                "transaction_hash": "0x1616161616161616161616161616161616161616161616161616161616161616",
                "log_index": 0,
                "args": {
                    "recordId": "0x4444444444444444444444444444444444444444444444444444444444444444",
                    "reasonHash": "0xefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefef",
                },
            }
        )

        index = registry_record_tool.index_onchain_contract_events(events)

        self.assertTrue(index["verification"]["chain_valid"], index)
        self.assertEqual(index["records"], [])
        self.assertEqual([item["record_hash"] for item in index["revocations"]], [contract["sample"]["onchain_record"]["record_hash"]])
        self.assertEqual(index["proof"]["record_hashes"], [])
        self.assertEqual(index["proof"]["revocation_record_hashes"], [contract["sample"]["onchain_record"]["record_hash"]])

    def test_contract_events_recovery_keeps_revoked_hash_and_reactivates_record_id(self) -> None:
        fixture = onchain_contract_events_fixture()
        registered = fixture["events"][0]
        record_id = registered["args"]["recordId"]
        original_hash = registered["onchain_record"]["record_hash"]
        recovered_hash = "26" * 32
        recovered = copy.deepcopy(registered["onchain_record"])
        recovered["record_hash"] = recovered_hash
        recovered["updated_at"] = "2026-06-01T00:40:00Z"
        events = [
            registered,
            {
                "event": "MerchantRevoked",
                "block_number": 106,
                "block_time": "2026-06-01T00:30:00Z",
                "transaction_hash": f"0x{'24' * 32}",
                "log_index": 0,
                "args": {"recordId": record_id, "reasonHash": f"0x{'25' * 32}"},
            },
            {
                "event": "MerchantRegistered",
                "block_number": 107,
                "block_time": "2026-06-01T00:40:00Z",
                "transaction_hash": f"0x{'27' * 32}",
                "log_index": 0,
                "args": {
                    "recordId": record_id,
                    "controller": registered["args"]["controller"],
                    "domainHash": registered["args"]["domainHash"],
                    "recordHash": f"0x{recovered_hash}",
                    "recordURI": "https://registry.agentcart.eu/v1/registry/onchain/records/" + recovered_hash,
                },
                "onchain_record": recovered,
            },
        ]

        index = registry_record_tool.index_onchain_contract_events(events)

        self.assertTrue(index["verification"]["chain_valid"], index)
        self.assertEqual(index["records"], [recovered])
        self.assertEqual(index["proof"]["record_hashes"], [recovered_hash])
        self.assertEqual(index["proof"]["revocation_record_hashes"], [original_hash])

    def test_contract_events_rotate_controller_and_force_revoke_committed_record(self) -> None:
        fixture = onchain_contract_events_fixture()
        events = fixture["events"][:2]
        record_id = fixture["events"][0]["args"]["recordId"]
        rotated_hash = "17" * 32
        rotated = copy.deepcopy(fixture["events"][0]["onchain_record"])
        rotated["record_hash"] = rotated_hash
        rotated["controller"] = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        events.extend(
            [
                {
                    "event": "ControllerChanged",
                    "block_number": 102,
                    "block_time": "2026-06-01T00:10:00Z",
                    "transaction_hash": "0x1717171717171717171717171717171717171717171717171717171717171717",
                    "log_index": 0,
                    "args": {
                        "recordId": record_id,
                        "newController": rotated["controller"],
                        "newRecordHash": f"0x{rotated_hash}",
                        "recordURI": rotated["registration_uri"],
                    },
                    "onchain_record": rotated,
                },
                {
                    "event": "MerchantRevoked",
                    "block_number": 103,
                    "block_time": "2026-06-01T00:15:00Z",
                    "transaction_hash": "0x1818181818181818181818181818181818181818181818181818181818181818",
                    "log_index": 0,
                    "args": {"recordId": record_id, "reasonHash": f"0x{'19' * 32}"},
                },
                {
                    "event": "MerchantForceRevoked",
                    "block_number": 103,
                    "block_time": "2026-06-01T00:15:00Z",
                    "transaction_hash": "0x1818181818181818181818181818181818181818181818181818181818181818",
                    "log_index": 1,
                    "args": {
                        "recordId": record_id,
                        "operator": "0xffffffffffffffffffffffffffffffffffffffff",
                        "reasonHash": f"0x{'19' * 32}",
                    },
                },
            ]
        )

        index = registry_record_tool.index_onchain_contract_events(events)

        self.assertTrue(index["verification"]["chain_valid"], index)
        self.assertEqual(index["records"], [])
        self.assertEqual(index["attestations"], [])
        self.assertEqual(index["revocations"][0]["record_hash"], rotated_hash)
        self.assertTrue(index["revocations"][0]["forced"])
        self.assertEqual(index["revocations"][0]["operator"], "0xffffffffffffffffffffffffffffffffffffffff")

    def test_contract_events_project_approved_supersession_activation(self) -> None:
        fixture = onchain_contract_events_fixture()
        previous = fixture["events"][0]
        previous_record_id = previous["args"]["recordId"]
        pending_record_id = f"0x{'55' * 32}"
        replacement_hash = "66" * 32
        replacement = copy.deepcopy(previous["onchain_record"])
        replacement["record_hash"] = replacement_hash
        replacement["record_id"] = pending_record_id
        replacement["controller"] = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        events = [
            previous,
            {
                "event": "SupersessionRequested",
                "block_number": 101,
                "block_time": "2026-06-01T00:05:00Z",
                "transaction_hash": "0x2020202020202020202020202020202020202020202020202020202020202020",
                "log_index": 0,
                "args": {
                    "domainHash": previous["args"]["domainHash"],
                    "previousRecordId": previous_record_id,
                    "pendingRecordId": pending_record_id,
                    "controller": replacement["controller"],
                    "recordHash": f"0x{replacement_hash}",
                    "reasonHash": f"0x{'21' * 32}",
                    "availableAt": 1783037100,
                    "recordURI": replacement["registration_uri"],
                    "evidenceURI": "https://registry.agentcart.eu/evidence/supersession-request",
                },
            },
            {
                "event": "SupersessionApproved",
                "block_number": 102,
                "block_time": "2026-06-01T00:10:00Z",
                "transaction_hash": "0x2222222222222222222222222222222222222222222222222222222222222222",
                "log_index": 0,
                "args": {
                    "domainHash": previous["args"]["domainHash"],
                    "previousRecordId": previous_record_id,
                    "pendingRecordId": pending_record_id,
                    "approver": "0xffffffffffffffffffffffffffffffffffffffff",
                    "recordHash": f"0x{replacement_hash}",
                    "availableAt": 1783037400,
                    "evidenceURI": "https://registry.agentcart.eu/evidence/supersession-approval",
                },
            },
            {
                "event": "MerchantRevoked",
                "block_number": 103,
                "block_time": "2026-06-03T00:10:00Z",
                "transaction_hash": "0x2323232323232323232323232323232323232323232323232323232323232323",
                "log_index": 0,
                "args": {"recordId": previous_record_id, "reasonHash": f"0x{'21' * 32}"},
            },
            {
                "event": "SupersessionActivated",
                "block_number": 103,
                "block_time": "2026-06-03T00:10:00Z",
                "transaction_hash": "0x2323232323232323232323232323232323232323232323232323232323232323",
                "log_index": 1,
                "args": {
                    "domainHash": previous["args"]["domainHash"],
                    "previousRecordId": previous_record_id,
                    "recordId": pending_record_id,
                    "controller": replacement["controller"],
                    "recordHash": f"0x{replacement_hash}",
                    "recordURI": replacement["registration_uri"],
                },
                "onchain_record": replacement,
            },
            {
                "event": "MerchantRegistered",
                "block_number": 103,
                "block_time": "2026-06-03T00:10:00Z",
                "transaction_hash": "0x2323232323232323232323232323232323232323232323232323232323232323",
                "log_index": 2,
                "args": {
                    "recordId": pending_record_id,
                    "controller": replacement["controller"],
                    "domainHash": previous["args"]["domainHash"],
                    "recordHash": f"0x{replacement_hash}",
                    "recordURI": replacement["registration_uri"],
                },
                "onchain_record": replacement,
            },
        ]

        index = registry_record_tool.index_onchain_contract_events(events)

        self.assertTrue(index["verification"]["chain_valid"], index)
        self.assertEqual(index["records"], [replacement])
        self.assertEqual(index["supersessions"][0]["state"], "activated")
        self.assertEqual(index["revocations"][0]["record_id"], previous_record_id)
        self.assertEqual(index["proof"]["record_hashes"], [replacement_hash])

    def test_contract_events_reject_record_hash_mismatch(self) -> None:
        fixture = onchain_contract_events_fixture()
        fixture["events"][0]["args"]["recordHash"] = "0" * 64

        index = registry_record_tool.index_onchain_contract_events(fixture["events"])

        self.assertFalse(index["verification"]["chain_valid"])
        self.assertEqual(index["verification"]["errors"][0]["error"], "onchain_record_hash_mismatch")
        self.assertEqual(index["records"], [])
        self.assertEqual(index["revocations"], [])

    def test_onchain_overlay_requires_an_exact_record_id_hash_version(self) -> None:
        chain_id = "eip155:42431"
        registry_address = "0x1111111111111111111111111111111111111111"
        first_id = "0x" + "aa" * 32
        second_id = "0x" + "bb" * 32
        first_hash = "11" * 32
        second_hash = "22" * 32

        def anchored_record(merchant_id: str, record_id: str, version_hash: str) -> dict[str, object]:
            return {
                "merchant_id": merchant_id,
                "domain": f"{merchant_id}.example",
                "version_hash": version_hash,
                "onchain_identity": {
                    "chain_id": chain_id,
                    "registry_address": registry_address,
                    "record_id": record_id,
                },
            }

        active_first = anchored_record("active-first", first_id, first_hash)
        active_second = anchored_record("active-second", second_id, second_hash)
        mismatched_hosted = anchored_record("mismatched-hosted", first_id, second_hash)
        projected = registry_record_tool.agentcart.onchain_projection.overlay_records(
            [mismatched_hosted],
            {
                "chain_id": chain_id,
                "registry_address": registry_address,
                "records": [active_first, active_second],
                "revocations": [],
                "suspensions": [],
            },
            record_hash=lambda record: str(record["version_hash"]),
        )

        self.assertEqual(projected, [active_first, active_second])

    def test_auto_managed_shopbridge_registry_claim_verifies(self) -> None:
        manifest = shopbridge_manifest_with_published_claim()
        record = registry_record_tool.build_registry_record(manifest)
        proof = registry_record_tool.domain_proof_document(record)

        result = registry_record_tool.verify_registry_record(
            record,
            manifest_snapshot=manifest,
            proof_snapshot=proof,
            revocation_snapshot=revocation_document(record),
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["verification"]["state"], "verified")
        self.assertEqual(result["entry"]["registry_claim_hash"], record["registry_claim_hash"])

    def test_revoked_auto_managed_shopbridge_registry_record_is_rejected(self) -> None:
        manifest = shopbridge_manifest_with_published_claim()
        record = registry_record_tool.build_registry_record(manifest)
        proof = registry_record_tool.domain_proof_document(record)
        revocation = revocation_document(
            record,
            [
                {
                    "record_hash": registry_record_tool.agentcart.registry_record_hash(record),
                    "revoked_at": registry_record_tool.iso_now(),
                }
            ],
        )

        result = registry_record_tool.verify_registry_record(
            record,
            manifest_snapshot=manifest,
            proof_snapshot=proof,
            revocation_snapshot=revocation,
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("record_revoked_by_revocation_document", result["verification"]["errors"])

    def test_generated_domain_proof_record_verifies_with_snapshots(self) -> None:
        manifest = shopbridge_manifest()
        record = registry_record_tool.build_registry_record(
            manifest,
            updated_at=registry_record_tool.iso_now(),
        )
        proof = registry_record_tool.domain_proof_document(record)

        result = registry_record_tool.verify_registry_record(
            record,
            manifest_snapshot=manifest,
            proof_snapshot=proof,
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["verification"]["state"], "verified")
        self.assertEqual(result["verification"]["signature_alg"], "https-domain-proof")

    def test_builds_hmac_signed_record_for_private_local_feeds(self) -> None:
        manifest = shopbridge_manifest()
        record = registry_record_tool.build_registry_record(
            manifest,
            updated_at=registry_record_tool.iso_now(),
            signature_alg="hmac-sha256",
            hmac_secret="registry-secret",
        )

        result = registry_record_tool.verify_registry_record(
            record,
            manifest_snapshot=manifest,
            hmac_secret="registry-secret",
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(record["signature_alg"], "hmac-sha256")
        self.assertTrue(str(record["signature"]).startswith("hmac-sha256:"))


if __name__ == "__main__":
    unittest.main()
