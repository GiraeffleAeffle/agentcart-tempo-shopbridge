from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import json
import os
import tempfile
import sys
import stat
from dataclasses import replace
import threading
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "shopbridge-direct-skill"
    / "scripts"
    / "shopbridge_onchain_rpc.py"
)
SPEC = importlib.util.spec_from_file_location("shopbridge_onchain_rpc_test", SCRIPT_PATH)
assert SPEC and SPEC.loader
onchain_rpc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = onchain_rpc
SPEC.loader.exec_module(onchain_rpc)

PROJECTION_PATH = SCRIPT_PATH.with_name("shopbridge_onchain_projection.py")
PROJECTION_SPEC = importlib.util.spec_from_file_location(
    "shopbridge_onchain_projection_rpc_test", PROJECTION_PATH
)
assert PROJECTION_SPEC and PROJECTION_SPEC.loader
onchain_projection = importlib.util.module_from_spec(PROJECTION_SPEC)
sys.modules[PROJECTION_SPEC.name] = onchain_projection
PROJECTION_SPEC.loader.exec_module(onchain_projection)
IDENTITY_FIXTURE_PATH = (
    SCRIPT_PATH.parents[3]
    / "docs"
    / "fixtures"
    / "registry"
    / "onchain-identity-aliases.json"
)


def word(value: int) -> bytes:
    return value.to_bytes(32, "big")


def bytes32(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("0x"))


def address_word(value: str) -> bytes:
    return b"\x00" * 12 + bytes.fromhex(value.removeprefix("0x"))


def encode_registered_data(record_hash: str, record_uri: str) -> str:
    raw_uri = record_uri.encode()
    padded = raw_uri + b"\x00" * ((32 - len(raw_uri) % 32) % 32)
    return "0x" + (bytes32(record_hash) + word(64) + word(len(raw_uri)) + padded).hex()


def encode_record_call(controller: str, record_hash: str, domain_hash: str, status: int) -> str:
    values = [
        address_word(controller),
        bytes32(record_hash),
        bytes32(domain_hash),
        word(1),
        word(0),
        word(0),
        word(0),
        word(0),
        word(status),
    ]
    return "0x" + b"".join(values).hex()


def registered_log_for(
    rpc: "FakeRpc",
    *,
    record_id: str,
    controller: str,
    domain_hash_value: str,
    record_hash: str,
    record_uri: str,
    log_index: int,
) -> dict:
    log = rpc.registered_log()
    log.update(
        {
            "transactionHash": "0x" + f"{1000 + log_index:064x}",
            "logIndex": hex(log_index),
            "topics": [
                next(
                    topic
                    for topic, spec in onchain_rpc.EVENT_SPECS.items()
                    if spec.name == "MerchantRegistered"
                ),
                record_id,
                "0x" + address_word(controller).hex(),
                domain_hash_value,
            ],
            "data": encode_registered_data(record_hash, record_uri),
        }
    )
    return log


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


class FakeRpc:
    def __init__(
        self,
        *,
        supplied_chain_id: int = 42431,
        record_domain: str = "merchant.example",
        client_version: str = "FakeRpc/1.0",
        myotis_beacon_state: str = "SYNCED",
        myotis_finalized_block: int = 120,
        finalized_timestamp: int | None = None,
        myotis_status_states: list[str] | None = None,
        myotis_wakeup_ok: bool = True,
        myotis_snap_peers: list[int] | None = None,
        myotis_beacon_states: list[str] | None = None,
        myotis_finalized_blocks: list[int] | None = None,
    ) -> None:
        self.chain_id = supplied_chain_id
        self.client_version = client_version
        self.myotis_beacon_state = myotis_beacon_state
        self.myotis_finalized_block = myotis_finalized_block
        self.finalized_timestamp = finalized_timestamp or int(
            dt.datetime.now(dt.timezone.utc).timestamp()
        )
        self.myotis_status_states = list(myotis_status_states or ["RUNNING"])
        self.myotis_snap_peers = list(myotis_snap_peers or [2])
        self.myotis_beacon_states = list(myotis_beacon_states or [myotis_beacon_state])
        self.myotis_finalized_blocks = list(
            myotis_finalized_blocks or [myotis_finalized_block]
        )
        self.myotis_wakeup_ok = myotis_wakeup_ok
        self.myotis_wakeup_calls = 0
        self.registry = onchain_rpc.DEFAULT_REGISTRY_ADDRESS.lower()
        self.facets_address = "0x7777777777777777777777777777777777777777"
        self.registry_code = "0x60016000"
        self.facets_code = "0x60026000"
        self.controller = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        self.record_id = "0x" + "4" * 64
        self.record_hash = "0x" + "5" * 64
        self.domain = record_domain
        self.registered_domain_hash = onchain_rpc.domain_hash("merchant.example")
        self.record_uri = "https://merchant.example/.well-known/agentcart-registry-record.json"
        self.block_hash = "0x" + "b" * 64
        self.transaction_hash = "0x" + "c" * 64
        self.log_calls: list[dict] = []
        self.block_calls: list[str] = []
        self.finalized_number = 120
        self.call_calls: list[dict] = []
        self.logs = [self.registered_log()]
        self.facet_logs: list[dict] = []
        self.facet_states: dict[str, dict] = {}
        self.states = {
            self.record_id: {
                "controller": self.controller,
                "record_hash": self.record_hash,
                "domain_hash": self.registered_domain_hash,
                "status": 1,
            }
        }

    def record(self) -> dict:
        return {
            "merchant_id": "merchant-example",
            "domain": self.domain,
            "manifest_url": "https://merchant.example/.well-known/agentcart.json",
            "onchain_identity": {
                "standard": "agentcart-onchain-registry-v1",
                "chain_id": f"eip155:{self.chain_id}",
                "registry_address": onchain_rpc.DEFAULT_REGISTRY_ADDRESS,
                "record_id": self.record_id,
                "controller": self.controller,
            },
        }

    def record_with_facets(self, categories: list[str]) -> dict:
        value = self.record()
        value["discovery_facets"] = {
            "schema": onchain_rpc.discovery_facets.FACETS_SCHEMA,
            "taxonomy": onchain_rpc.discovery_facets.TAXONOMY,
            "source": onchain_rpc.discovery_facets.SOURCE_EXPOSED_CATALOG,
            "categories": sorted(categories),
            "category_count_total": len(categories),
            "coverage": "complete",
            "truncated": False,
        }
        return value

    def enable_facets(self, categories: list[str], *, generation: int = 1) -> set[str]:
        category_hashes = sorted(
            "0x" + onchain_rpc.keccak256(category.encode()).hex()
            for category in categories
        )
        set_hash = "0x" + onchain_rpc.keccak256(
            b"".join(bytes32(value) for value in category_hashes)
        ).hex()
        self.facet_states[self.record_id] = {
            "record_hash": self.record_hash,
            "category_set_hash": set_hash,
            "generation": generation,
            "category_count": len(category_hashes),
        }
        self.facet_logs = [
            {
                "address": self.facets_address,
                "blockNumber": hex(110),
                "blockHash": self.block_hash,
                "transactionHash": "0x" + f"{2000 + index:064x}",
                "logIndex": hex(index),
                "removed": False,
                "topics": [
                    onchain_rpc.DISCOVERY_CATEGORY_DECLARED_TOPIC,
                    category_hash,
                    self.record_id,
                    "0x" + word(generation).hex(),
                ],
                "data": "0x",
            }
            for index, category_hash in enumerate(category_hashes)
        ]
        return set(category_hashes)

    def registered_log(self) -> dict:
        return {
            "address": self.registry,
            "blockNumber": hex(100),
            "blockHash": self.block_hash,
            "transactionHash": self.transaction_hash,
            "logIndex": "0x0",
            "removed": False,
            "topics": [
                next(topic for topic, spec in onchain_rpc.EVENT_SPECS.items() if spec.name == "MerchantRegistered"),
                self.record_id,
                "0x" + address_word(self.controller).hex(),
                self.registered_domain_hash,
            ],
            "data": encode_registered_data(self.record_hash, self.record_uri),
        }

    def updated_log(
        self,
        *,
        record_id: str,
        record_hash: str,
        record_uri: str,
        block_number: int = 110,
        log_index: int = 0,
    ) -> dict:
        return {
            "address": self.registry,
            "blockNumber": hex(block_number),
            "blockHash": self.block_hash,
            "transactionHash": "0x" + f"{block_number + log_index:064x}",
            "logIndex": hex(log_index),
            "removed": False,
            "topics": [
                next(
                    topic
                    for topic, spec in onchain_rpc.EVENT_SPECS.items()
                    if spec.name == "MerchantUpdated"
                ),
                record_id,
            ],
            "data": encode_registered_data(record_hash, record_uri),
        }

    def controller_changed_log(
        self,
        *,
        record_id: str,
        controller: str,
        record_hash: str,
        record_uri: str,
        block_number: int = 111,
        log_index: int = 0,
    ) -> dict:
        return {
            "address": self.registry,
            "blockNumber": hex(block_number),
            "blockHash": self.block_hash,
            "transactionHash": "0x" + f"{block_number + log_index:064x}",
            "logIndex": hex(log_index),
            "removed": False,
            "topics": [
                next(
                    topic
                    for topic, spec in onchain_rpc.EVENT_SPECS.items()
                    if spec.name == "ControllerChanged"
                ),
                record_id,
                "0x" + address_word(controller).hex(),
            ],
            "data": encode_registered_data(record_hash, record_uri),
        }

    def status_log(
        self,
        event_name: str,
        *,
        record_id: str,
        block_number: int,
        log_index: int = 0,
    ) -> dict:
        data = "0x" if event_name == "MerchantUnsuspended" else "0x" + (b"\x11" * 32).hex()
        return {
            "address": self.registry,
            "blockNumber": hex(block_number),
            "blockHash": self.block_hash,
            "transactionHash": "0x" + f"{block_number + log_index:064x}",
            "logIndex": hex(log_index),
            "removed": False,
            "topics": [
                next(
                    topic
                    for topic, spec in onchain_rpc.EVENT_SPECS.items()
                    if spec.name == event_name
                ),
                record_id,
            ],
            "data": data,
        }

    def ownership_transferred_log(self) -> dict:
        return {
            "address": self.registry,
            "blockNumber": hex(100),
            "blockHash": self.block_hash,
            "transactionHash": "0x" + "9" * 64,
            "logIndex": "0x0",
            "removed": False,
            "topics": [
                onchain_rpc.OWNERSHIP_TRANSFERRED_TOPIC,
                onchain_rpc.ZERO_ADDRESS_TOPIC,
                "0x" + address_word(self.controller).hex(),
            ],
            "data": "0x",
        }

    def request(self, _url: str, **kwargs):
        payload = kwargs["payload"]
        method = payload["method"]
        params = payload["params"]
        if method == "eth_chainId":
            result = hex(self.chain_id)
        elif method == "web3_clientVersion":
            result = self.client_version
        elif method == "myotis_status":
            state = self.myotis_status_states[0]
            if len(self.myotis_status_states) > 1:
                self.myotis_status_states.pop(0)
            peers = self.myotis_snap_peers[0]
            if len(self.myotis_snap_peers) > 1:
                self.myotis_snap_peers.pop(0)
            result = {"ok": True, "state": state, "snapPeers": peers if state == "RUNNING" else 0}
        elif method == "myotis_wakeup":
            self.myotis_wakeup_calls += 1
            result = {
                "ok": self.myotis_wakeup_ok,
                "lifecycle": "RUNNING" if self.myotis_wakeup_ok else "PAUSED",
            }
        elif method == "myotis_beaconStatus":
            beacon_state = self.myotis_beacon_states[0]
            if len(self.myotis_beacon_states) > 1:
                self.myotis_beacon_states.pop(0)
            finalized_block = self.myotis_finalized_blocks[0]
            if len(self.myotis_finalized_blocks) > 1:
                self.myotis_finalized_blocks.pop(0)
            result = {
                "ok": True,
                "state": beacon_state,
                "executionBlockNumber": finalized_block,
            }
        elif method == "eth_blockNumber":
            result = hex(125)
        elif method == "eth_getBlockByNumber" and params[0] in {"finalized", hex(120), hex(self.finalized_number)}:
            self.block_calls.append(params[0])
            result = {
                "number": hex(self.finalized_number) if params[0] == "finalized" else params[0],
                "hash": "0x" + "d" * 64,
                "timestamp": hex(self.finalized_timestamp),
            }
        elif method == "eth_getBlockByNumber":
            self.block_calls.append(params[0])
            result = {
                "number": params[0],
                "hash": self.block_hash,
                "timestamp": hex(self.finalized_timestamp - 100),
            }
        elif method == "eth_getCode":
            target = params[0].lower()
            selector = params[1]
            deployment_block = 105 if target == self.facets_address else 100
            code = self.facets_code if target == self.facets_address else self.registry_code
            result = "0x" if selector not in {"latest", "finalized"} and int(selector, 16) < deployment_block else code
        elif method == "eth_getLogs":
            query = params[0]
            self.log_calls.append(query)
            start = int(query["fromBlock"], 16)
            end = int(query["toBlock"], 16)
            if query.get("topics", [None])[0] == onchain_rpc.OWNERSHIP_TRANSFERRED_TOPIC:
                result = [self.ownership_transferred_log()] if start <= 100 <= end else []
            elif query.get("address") == self.facets_address:
                requested = set(query["topics"][1]) if len(query["topics"]) > 1 else None
                result = [
                    log
                    for log in self.facet_logs
                    if start <= int(log["blockNumber"], 16) <= end
                    and (requested is None or log["topics"][1] in requested)
                ]
            else:
                result = [
                    log
                    for log in self.logs
                    if start <= int(log["blockNumber"], 16) <= end
                ]
        elif method == "eth_call":
            self.call_calls.append(params)
            data = params[0]["data"]
            target = params[0]["to"].lower()
            if target == self.facets_address and data == onchain_rpc.DISCOVERY_FACETS_REGISTRY_SELECTOR:
                result = "0x" + address_word(self.registry).hex()
            elif target == self.facets_address and data.startswith(onchain_rpc.DISCOVERY_FACET_STATE_SELECTOR):
                state = self.facet_states["0x" + data[-64:]]
                result = "0x" + b"".join(
                    [
                        bytes32(state["record_hash"]),
                        bytes32(state["category_set_hash"]),
                        word(state["generation"]),
                        word(state["category_count"]),
                    ]
                ).hex()
            elif data.startswith(onchain_rpc.RECORD_SELECTOR):
                state = self.states["0x" + data[-64:]]
                result = encode_record_call(
                    state["controller"],
                    state["record_hash"],
                    state["domain_hash"],
                    state["status"],
                )
            elif data.startswith(onchain_rpc.REVOKED_RECORD_HASHES_SELECTOR):
                supplied_hash = "0x" + data[-64:]
                revoked = any(
                    state["record_hash"] == supplied_hash and state["status"] == 2
                    for state in self.states.values()
                )
                result = "0x" + word(1 if revoked else 0).hex()
            elif data.startswith(onchain_rpc.RECORD_ID_FOR_DOMAIN_SELECTOR):
                supplied_domain = "0x" + data[-64:]
                result = next(
                    (
                        record_id
                        for record_id, state in self.states.items()
                        if state["domain_hash"] == supplied_domain and state["status"] in {1, 3}
                    ),
                    "0x" + "0" * 64,
                )
            else:
                raise AssertionError(f"unexpected eth_call: {data}")
        else:
            raise AssertionError(f"unexpected RPC method: {method}")
        return {"jsonrpc": "2.0", "id": payload["id"], "result": result}


class ShopBridgeOnchainRpcTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_CACHE_DISABLED": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def project_direct(self, document: dict, expected_hash: str) -> dict:
        return onchain_projection.index_contract_document(
            document,
            record_hash=lambda _record: expected_hash.removeprefix("0x"),
            require_finality=True,
            expected_chain_id=str(document["chain_id"]),
            expected_registry_address=str(document["registry_address"]),
            max_age_seconds=600,
            now=dt.datetime.fromisoformat(document["indexed_at"].replace("Z", "+00:00")),
            expected_implementation=onchain_projection.DIRECT_RPC_IMPLEMENTATION,
        )

    def test_keccak_matches_ethereum_vectors(self) -> None:
        self.assertEqual(
            onchain_rpc.keccak256(b"").hex(),
            "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470",
        )
        self.assertEqual(
            onchain_rpc.domain_hash("fixture-shop.example"),
            "0x8af7dc83ed9e74917f9d4d7d2143dc3371749c67d9b5cd70b4cc117a5a11da29",
        )

    def test_event_topics_and_call_selectors_match_contract_abi(self) -> None:
        signatures = {
            "MerchantRegistered": "MerchantRegistered(bytes32,address,bytes32,bytes32,string)",
            "MerchantUpdated": "MerchantUpdated(bytes32,bytes32,string)",
            "ControllerChanged": "ControllerChanged(bytes32,address,bytes32,string)",
            "MerchantRevoked": "MerchantRevoked(bytes32,bytes32)",
            "MerchantSuspended": "MerchantSuspended(bytes32,bytes32)",
            "MerchantUnsuspended": "MerchantUnsuspended(bytes32)",
        }
        actual_topics = {spec.name: topic for topic, spec in onchain_rpc.EVENT_SPECS.items()}
        expected_topics = {
            name: "0x" + onchain_rpc.keccak256(signature.encode()).hex()
            for name, signature in signatures.items()
        }
        self.assertEqual(actual_topics, expected_topics)
        self.assertEqual(
            onchain_rpc.RECORD_SELECTOR,
            "0x" + onchain_rpc.keccak256(b"record(bytes32)")[:4].hex(),
        )
        self.assertEqual(
            onchain_rpc.RECORD_ID_FOR_DOMAIN_SELECTOR,
            "0x" + onchain_rpc.keccak256(b"recordIdForDomain(bytes32)")[:4].hex(),
        )
        self.assertEqual(
            onchain_rpc.REVOKED_RECORD_HASHES_SELECTOR,
            "0x" + onchain_rpc.keccak256(b"revokedRecordHashes(bytes32)")[:4].hex(),
        )
        self.assertEqual(
            onchain_rpc.DISCOVERY_FACETS_REGISTRY_SELECTOR,
            "0x" + onchain_rpc.keccak256(b"registry()")[:4].hex(),
        )
        self.assertEqual(
            onchain_rpc.DISCOVERY_FACET_STATE_SELECTOR,
            "0x" + onchain_rpc.keccak256(b"facetState(bytes32)")[:4].hex(),
        )
        self.assertEqual(
            onchain_rpc.DISCOVERY_CATEGORY_DECLARED_TOPIC,
            "0x"
            + onchain_rpc.keccak256(b"CategoryDeclared(bytes32,bytes32,uint64)").hex(),
        )
        self.assertEqual(
            onchain_rpc.OWNERSHIP_TRANSFERRED_TOPIC,
            "0x"
            + onchain_rpc.keccak256(b"OwnershipTransferred(address,address)").hex(),
        )

    def test_collects_committed_record_directly_from_finalized_rpc(self) -> None:
        rpc = FakeRpc()
        loader_calls = []

        def load_record(uri: str, record_hash: str):
            loader_calls.append((uri, record_hash))
            return rpc.record()

        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(
                rpc_url="https://rpc.example",
                from_block=100,
                log_chunk_size=10,
            ),
            record_loader=load_record,
            request_json=rpc.request,
            now=lambda: dt.datetime.fromtimestamp(rpc.finalized_timestamp, tz=dt.timezone.utc),
        )

        self.assertEqual(document["implementation"], onchain_rpc.DIRECT_RPC_IMPLEMENTATION)
        self.assertEqual(document["source"], "direct_json_rpc")
        self.assertEqual(document["rpc"]["profile"], "standard")
        self.assertEqual(document["chain_id"], "eip155:42431")
        self.assertEqual(document["registry_address"], onchain_rpc.DEFAULT_REGISTRY_ADDRESS.lower())
        self.assertEqual(document["finality"]["block_number"], 120)
        self.assertEqual(document["contract_storage_verification"]["status"], "matched")
        self.assertEqual(document["contract_storage_verification"]["checked_record_count"], 1)
        self.assertEqual(document["events"][0]["event"], "MerchantRegistered")
        self.assertEqual(document["events"][0]["registry_record"]["merchant_id"], "merchant-example")
        self.assertEqual(loader_calls, [(rpc.record_uri, rpc.record_hash)])
        self.assertEqual(len(rpc.log_calls), 3)
        self.assertEqual(rpc.log_calls[0]["topics"], [list(onchain_rpc.EVENT_SPECS)])

    def test_onchain_category_declaration_routes_and_verifies_committed_facets(self) -> None:
        rpc = FakeRpc()
        category_hashes = rpc.enable_facets(["coffee", "tea"])
        tea_hash = "0x" + onchain_rpc.keccak256(b"tea").hex()

        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(
                rpc_url="https://rpc.example",
                from_block=100,
                log_chunk_size=10,
                discovery_facets_address=rpc.facets_address,
                discovery_facets_from_block=105,
            ),
            record_loader=lambda _uri, _record_hash: rpc.record_with_facets(["coffee", "tea"]),
            request_json=rpc.request,
            now=lambda: dt.datetime.fromtimestamp(rpc.finalized_timestamp, tz=dt.timezone.utc),
            record_candidate_limit=1,
            record_candidate_seed="tea",
            category_hash_groups=[{tea_hash}],
        )

        self.assertIn(tea_hash, category_hashes)
        self.assertEqual(
            document["record_selection"]["selection_mode"],
            "discovery_facets_with_neutral_fallback",
        )
        self.assertEqual(document["record_selection"]["selected_record_ids"], [rpc.record_id])
        self.assertTrue(document["onchain_discovery_facets"]["used"])
        self.assertEqual(document["onchain_discovery_facets"]["matched_record_count"], 1)
        self.assertEqual(document["record_errors"], [])

    def test_stale_or_record_mismatched_category_declaration_fails_closed(self) -> None:
        rpc = FakeRpc()
        rpc.enable_facets(["tea"], generation=1)
        tea_hash = "0x" + onchain_rpc.keccak256(b"tea").hex()
        rpc.facet_states[rpc.record_id]["generation"] = 2
        stale = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(
                rpc_url="https://rpc.example",
                from_block=100,
                discovery_facets_address=rpc.facets_address,
                discovery_facets_from_block=105,
            ),
            record_loader=lambda _uri, _record_hash: rpc.record(),
            request_json=rpc.request,
            now=lambda: dt.datetime.fromtimestamp(rpc.finalized_timestamp, tz=dt.timezone.utc),
            record_candidate_limit=1,
            record_candidate_seed="tea",
            category_hash_groups=[{tea_hash}],
        )
        self.assertFalse(stale["onchain_discovery_facets"]["used"])
        self.assertEqual(stale["record_selection"]["selection_mode"], "query_seeded_sample")

        rpc = FakeRpc()
        rpc.enable_facets(["tea"])
        mismatched = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(
                rpc_url="https://rpc.example",
                from_block=100,
                discovery_facets_address=rpc.facets_address,
                discovery_facets_from_block=105,
            ),
            record_loader=lambda _uri, _record_hash: rpc.record_with_facets(["coffee"]),
            request_json=rpc.request,
            now=lambda: dt.datetime.fromtimestamp(rpc.finalized_timestamp, tz=dt.timezone.utc),
            record_candidate_limit=1,
            record_candidate_seed="tea",
            category_hash_groups=[{tea_hash}],
        )
        self.assertEqual(
            mismatched["record_errors"][0]["code"],
            "registry_record_discovery_facet_commitment_mismatch",
        )

    def test_onchain_category_routing_pins_facets_deployment_and_runtime(self) -> None:
        rpc = FakeRpc()
        rpc.enable_facets(["tea"])
        tea_hash = "0x" + onchain_rpc.keccak256(b"tea").hex()
        runtime_hash = "0x" + onchain_rpc.keccak256(
            bytes.fromhex(rpc.facets_code.removeprefix("0x"))
        ).hex()

        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(
                rpc_url="https://rpc.example",
                from_block=100,
                discovery_facets_address=rpc.facets_address,
                discovery_facets_from_block=105,
                discovery_facets_deployment_block_hash=rpc.block_hash,
                discovery_facets_runtime_code_hash=runtime_hash,
            ),
            record_loader=lambda _uri, _record_hash: rpc.record_with_facets(["tea"]),
            request_json=rpc.request,
            category_hash_groups=[{tea_hash}],
        )
        verification = document["onchain_discovery_facets"]["deployment_verification"]
        self.assertTrue(verification["pinned_block_hash"])
        self.assertTrue(verification["pinned_runtime_code_hash"])

        for field, value, error in (
            (
                "discovery_facets_deployment_block_hash",
                "0x" + "a" * 64,
                "discovery_facets_deployment_block_hash_mismatch",
            ),
            (
                "discovery_facets_runtime_code_hash",
                "0x" + "a" * 64,
                "discovery_facets_runtime_code_hash_mismatch",
            ),
        ):
            with self.subTest(field=field):
                descriptor = {
                    "rpc_url": "https://rpc.example",
                    "from_block": 100,
                    "discovery_facets_address": rpc.facets_address,
                    "discovery_facets_from_block": 105,
                    "discovery_facets_deployment_block_hash": rpc.block_hash,
                    "discovery_facets_runtime_code_hash": runtime_hash,
                    field: value,
                }
                with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
                    onchain_rpc.collect_finalized_events(
                        onchain_rpc.RegistryDeployment(**descriptor),
                        record_loader=lambda _uri, _record_hash: rpc.record_with_facets(["tea"]),
                        request_json=rpc.request,
                        category_hash_groups=[{tea_hash}],
                    )
                self.assertEqual(raised.exception.code, error)

    def test_uses_myotis_verified_finality_and_skips_historical_block_reads(self) -> None:
        rpc = FakeRpc(client_version="Myotis/verified-light-client")

        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(
                rpc_url="http://127.0.0.1:8546",
                from_block=100,
                log_chunk_size=10,
                allow_private_rpc=True,
                deployment_block_hash=rpc.block_hash,
            ),
            record_loader=lambda _uri, _record_hash: rpc.record(),
            request_json=rpc.request,
        )

        self.assertEqual(document["source"], "myotis_verified_json_rpc")
        self.assertEqual(document["rpc"]["profile"], "myotis")
        self.assertEqual(
            document["rpc"]["finality_source"],
            "myotis_beaconStatus.executionBlockNumber",
        )
        self.assertEqual(document["finality"]["block_number"], 120)
        self.assertEqual(
            document["contract_storage_verification"]["scope"],
            "myotis_verified_head_conservative_cross_check",
        )
        self.assertEqual(document["contract_storage_verification"]["block_number"], 125)
        self.assertEqual(
            document["events"][0]["block_verification"],
            "myotis_receipt_root_log_index",
        )
        self.assertNotIn(hex(100), rpc.block_calls)

    def test_rejects_myotis_before_beacon_sync(self) -> None:
        rpc = FakeRpc(
            client_version="Myotis/verified-light-client",
            myotis_beacon_state="CATCHING_UP",
        )
        clock = FakeClock()
        with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
            onchain_rpc.collect_finalized_events(
                onchain_rpc.RegistryDeployment(
                    rpc_url="http://127.0.0.1:8546",
                    from_block=100,
                    allow_private_rpc=True,
                ),
                record_loader=lambda _uri, _record_hash: rpc.record(),
                request_json=rpc.request,
                monotonic=clock,
                sleep=clock.sleep,
                myotis_ready_timeout_seconds=1,
            )
        self.assertEqual(raised.exception.code, "myotis_beacon_not_synced")

    def test_wakes_paused_myotis_before_verified_reads(self) -> None:
        rpc = FakeRpc(
            client_version="Myotis/verified-light-client",
            myotis_status_states=["PAUSED", "RUNNING"],
        )
        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(
                rpc_url="http://127.0.0.1:8546",
                from_block=100,
                allow_private_rpc=True,
                deployment_block_hash=rpc.block_hash,
            ),
            record_loader=lambda _uri, _record_hash: rpc.record(),
            request_json=rpc.request,
        )
        self.assertEqual(document["rpc"]["profile"], "myotis")
        self.assertEqual(rpc.myotis_wakeup_calls, 1)

    def test_waits_for_myotis_peers_and_beacon_readiness_within_deadline(self) -> None:
        rpc = FakeRpc(
            client_version="Myotis/verified-light-client",
            myotis_status_states=["RUNNING", "RUNNING"],
            myotis_snap_peers=[0, 2],
            myotis_beacon_states=["CATCHING_UP", "SYNCED"],
            myotis_finalized_blocks=[0, 120],
        )
        clock = FakeClock()
        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(
                rpc_url="http://127.0.0.1:8546",
                from_block=100,
                allow_private_rpc=True,
                deployment_block_hash=rpc.block_hash,
            ),
            record_loader=lambda _uri, _record_hash: rpc.record(),
            request_json=rpc.request,
            monotonic=clock,
            sleep=clock.sleep,
            myotis_ready_timeout_seconds=2,
        )
        self.assertEqual(document["finality"]["block_number"], 120)
        self.assertEqual(clock.sleeps, [0.5, 0.5])

    def test_rejects_myotis_that_does_not_resume_after_wakeup(self) -> None:
        rpc = FakeRpc(
            client_version="Myotis/verified-light-client",
            myotis_status_states=["PAUSED", "PAUSED", "PAUSED", "PAUSED"],
        )
        clock = FakeClock()
        with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
            onchain_rpc.collect_finalized_events(
                onchain_rpc.RegistryDeployment(
                    rpc_url="http://127.0.0.1:8546",
                    from_block=100,
                    allow_private_rpc=True,
                    deployment_block_hash=rpc.block_hash,
                ),
                record_loader=lambda _uri, _record_hash: rpc.record(),
                request_json=rpc.request,
                monotonic=clock,
                sleep=clock.sleep,
                myotis_ready_timeout_seconds=1,
            )
        self.assertEqual(raised.exception.code, "myotis_wakeup_timeout")

    def test_rejects_myotis_adapter_that_does_not_expose_finalized_block(self) -> None:
        rpc = FakeRpc(
            client_version="Myotis/verified-light-client",
            myotis_finalized_block=0,
        )
        clock = FakeClock()
        with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
            onchain_rpc.collect_finalized_events(
                onchain_rpc.RegistryDeployment(
                    rpc_url="http://127.0.0.1:8546",
                    from_block=100,
                    allow_private_rpc=True,
                ),
                record_loader=lambda _uri, _record_hash: rpc.record(),
                request_json=rpc.request,
                monotonic=clock,
                sleep=clock.sleep,
                myotis_ready_timeout_seconds=1,
            )
        self.assertEqual(raised.exception.code, "myotis_finalized_block_unavailable")

    def test_rejects_forcing_standard_semantics_on_myotis(self) -> None:
        rpc = FakeRpc(client_version="Myotis/verified-light-client")
        with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
            onchain_rpc.collect_finalized_events(
                onchain_rpc.RegistryDeployment(
                    rpc_url="http://127.0.0.1:8546",
                    from_block=100,
                    allow_private_rpc=True,
                    rpc_profile="standard",
                ),
                record_loader=lambda _uri, _record_hash: rpc.record(),
                request_json=rpc.request,
            )
        self.assertEqual(raised.exception.code, "rpc_profile_mismatch")

    def test_rejects_rpc_on_the_wrong_chain(self) -> None:
        rpc = FakeRpc(supplied_chain_id=1)
        with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
            onchain_rpc.collect_finalized_events(
                onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
                record_loader=lambda _uri, _record_hash: rpc.record(),
                request_json=rpc.request,
            )
        self.assertEqual(raised.exception.code, "rpc_chain_id_mismatch")

    def test_isolates_record_whose_domain_does_not_match_contract_hash(self) -> None:
        rpc = FakeRpc(record_domain="attacker.example")
        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
            record_loader=lambda _uri, _record_hash: rpc.record(),
            request_json=rpc.request,
        )
        self.assertEqual(
            document["record_errors"],
            [
                {
                    "record_id": rpc.record_id,
                    "record_hash": rpc.record_hash,
                    "code": "registry_record_domain_hash_mismatch",
                }
            ],
        )
        self.assertNotIn("registry_record", document["events"][0])

    def test_one_broken_permissionless_record_does_not_hide_valid_merchant(self) -> None:
        rpc = FakeRpc()
        broken_id = "0x" + "6" * 64
        broken_controller = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        broken_hash = "0x" + "7" * 64
        broken_domain_hash = onchain_rpc.domain_hash("broken.example")
        broken_uri = "https://broken.example/record.json"
        rpc.logs.append(
            registered_log_for(
                rpc,
                record_id=broken_id,
                controller=broken_controller,
                domain_hash_value=broken_domain_hash,
                record_hash=broken_hash,
                record_uri=broken_uri,
                log_index=1,
            )
        )
        rpc.states[broken_id] = {
            "controller": broken_controller,
            "record_hash": broken_hash,
            "domain_hash": broken_domain_hash,
            "status": 1,
        }

        def load_record(uri: str, _record_hash: str) -> dict:
            if uri == broken_uri:
                raise RuntimeError("unreachable")
            return rpc.record()

        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
            record_loader=load_record,
            request_json=rpc.request,
        )
        self.assertEqual(document["lifecycle_record_count"], 2)
        self.assertEqual(document["resolved_record_count"], 1)
        self.assertEqual(document["record_errors"][0]["record_id"], broken_id)
        index = self.project_direct(document, rpc.record_hash)
        self.assertTrue(index["verification"]["chain_valid"], index["verification"])
        self.assertEqual(
            [record["merchant_id"] for record in index["records"]],
            ["merchant-example"],
        )

        # Force the broken record into the only primary slot; a valid reserve
        # must still be fetched and included in the verifiable projection.
        seed = next(str(i) for i in range(100) if onchain_rpc.hashlib.sha256(f"{i}\0{broken_id}".encode()).digest()
                    < onchain_rpc.hashlib.sha256(f"{i}\0{rpc.record_id}".encode()).digest())
        backfilled = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
            record_loader=load_record, request_json=rpc.request, record_candidate_limit=1, record_candidate_seed=seed,
        )
        self.assertEqual(backfilled["record_selection"]["selected_record_ids"], [broken_id, rpc.record_id])
        self.assertEqual(backfilled["resolved_record_count"], 1)
        self.assertTrue(self.project_direct(backfilled, rpc.record_hash)["verification"]["chain_valid"])

    def test_v2_admission_requires_pins_and_filters_before_document_fetch(self) -> None:
        rpc = EnumerableV2Rpc()
        selector = "0x" + onchain_rpc.keccak256(b"eligibility(bytes32)").hex()[:8]
        checked_blocks = []
        eligible = True

        def request(url, **kwargs):
            payload = kwargs["payload"]
            if isinstance(payload, list):
                return [request(url, **{**kwargs, "payload": item}) for item in payload]
            if payload["method"] == "eth_call" and payload["params"][0]["data"].startswith(selector):
                checked_blocks.append(payload["params"][1])
                raw = word(int(eligible)) + bytes32("0x" + "e" * 64) + word(rpc.finalized_timestamp + 1000) + word(100)
                return {"jsonrpc": "2.0", "id": payload["id"], "result": "0x" + raw.hex()}
            return rpc.request(url, **kwargs)

        fields = dict(rpc_url="https://rpc.example", from_block=100, registry_version=2,
                      admission_witness_rpc_url="https://witness.example",
                      deployment_block_hash=rpc.block_hash,
                      runtime_code_hash="0x" + onchain_rpc.keccak256(bytes.fromhex(rpc.registry_code[2:])).hex())
        document = onchain_rpc.collect_finalized_events(onchain_rpc.RegistryDeployment(**fields),
            record_loader=lambda *_: rpc.record(), request_json=request)
        self.assertEqual(document["admission_verification"]["policy"], "two_rpc_agreement")
        self.assertTrue(document["admissions"][rpc.record_id]["eligible"])
        eligible = False
        document = onchain_rpc.collect_finalized_events(onchain_rpc.RegistryDeployment(**fields),
            record_loader=lambda *_: self.fail("ineligible shop document was fetched"), request_json=request)
        self.assertEqual(document["resolved_record_count"], 0)
        for changed in ({"runtime_code_hash": "0x" + "0" * 64}, {"deployment_block_hash": ""}):
            with self.assertRaises(onchain_rpc.OnchainRpcError):
                onchain_rpc.collect_finalized_events(onchain_rpc.RegistryDeployment(**{**fields, **changed}),
                    record_loader=lambda *_: self.fail("untrusted deployment was fetched"), request_json=request)

    def test_v2_rejects_witness_disagreement_before_loading_shops(self) -> None:
        rpc = EnumerableV2Rpc()
        selector = "0x" + onchain_rpc.keccak256(b"eligibility(bytes32)").hex()[:8]
        fields = dict(rpc_url="https://rpc.example", from_block=100, registry_version=2,
                      admission_witness_rpc_url="https://witness.example", deployment_block_hash=rpc.block_hash,
                      runtime_code_hash="0x" + onchain_rpc.keccak256(bytes.fromhex(rpc.registry_code[2:])).hex())
        for disagreement in ("admission", "boundary", "code"):
            def request(url, **kwargs):
                payload = kwargs["payload"]
                if isinstance(payload, list):
                    return [request(url, **{**kwargs, "payload": item}) for item in payload]
                witness = "witness.example" in url
                method, params = payload["method"], payload["params"]
                if method == "eth_call" and params[0]["data"].startswith(selector):
                    admitted = not (witness and disagreement == "admission")
                    raw = word(int(admitted)) + bytes32("0x" + "e" * 64) + word(rpc.finalized_timestamp + 1000) + word(100)
                    return {"jsonrpc": "2.0", "id": payload["id"], "result": "0x" + raw.hex()}
                result = rpc.request(url, **kwargs)
                if witness and disagreement == "boundary" and method == "eth_getBlockByNumber" and params[0] == "finalized":
                    result = {**result, "result": {**result["result"], "hash": "0x" + "e" * 64}}
                elif witness and disagreement == "code" and method == "eth_getCode" and isinstance(params[1], dict):
                    result = {**result, "result": "0x6000"}
                return result
            with self.subTest(disagreement=disagreement), self.assertRaisesRegex(onchain_rpc.OnchainRpcError, "witness_.*mismatch"):
                onchain_rpc.collect_finalized_events(onchain_rpc.RegistryDeployment(**fields),
                    record_loader=lambda *_: self.fail("shop fetched before witness agreement"), request_json=request)
        for witness_url in ("", "https://rpc.example/another-key"):
            with self.assertRaisesRegex(onchain_rpc.OnchainRpcError, "witness_required"):
                onchain_rpc.collect_finalized_events(onchain_rpc.RegistryDeployment(**{**fields, "admission_witness_rpc_url": witness_url}),
                    record_loader=lambda *_: self.fail("shop fetched without distinct witness"), request_json=rpc.request)

    def test_onchain_candidate_sample_bounds_record_fetch_and_projection(self) -> None:
        rpc = FakeRpc()
        documents: dict[str, dict] = {}
        base_record = rpc.record()
        base_record["_expected_hash"] = rpc.record_hash
        documents[rpc.record_uri] = base_record
        for index, digit in enumerate(("6", "8"), start=1):
            record_id = "0x" + digit * 64
            controller = "0x" + ("b" if index == 1 else "c") * 40
            record_hash = "0x" + ("7" if index == 1 else "9") * 64
            domain = f"sample-{index}.example"
            domain_hash_value = onchain_rpc.domain_hash(domain)
            record_uri = f"https://{domain}/record.json"
            rpc.logs.append(
                registered_log_for(
                    rpc,
                    record_id=record_id,
                    controller=controller,
                    domain_hash_value=domain_hash_value,
                    record_hash=record_hash,
                    record_uri=record_uri,
                    log_index=index,
                )
            )
            rpc.states[record_id] = {
                "controller": controller,
                "record_hash": record_hash,
                "domain_hash": domain_hash_value,
                "status": 1,
            }
            documents[record_uri] = {
                "merchant_id": f"sample-{index}",
                "domain": domain,
                "manifest_url": f"https://{domain}/.well-known/agentcart.json",
                "_expected_hash": record_hash,
                "onchain_identity": {
                    "standard": "agentcart-onchain-registry-v1",
                    "chain_id": "eip155:42431",
                    "registry_address": onchain_rpc.DEFAULT_REGISTRY_ADDRESS,
                    "record_id": record_id,
                    "controller": controller,
                },
            }
        seed = "deterministic buyer query"
        loader_calls: list[str] = []

        def load_record(uri: str, _record_hash: str) -> dict:
            loader_calls.append(uri)
            return documents[uri]

        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
            record_loader=load_record,
            request_json=rpc.request,
            record_candidate_limit=1,
            record_candidate_seed=seed,
        )
        expected_id = min(
            rpc.states,
            key=lambda record_id: onchain_rpc.hashlib.sha256(
                f"{seed}\0{record_id}".encode()
            ).digest(),
        )
        self.assertEqual(len(loader_calls), 1)
        self.assertEqual(document["record_selection"]["selected_record_ids"], [expected_id])
        hinted_id = "0x" + "8" * 64
        hinted_document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
            record_loader=load_record,
            request_json=rpc.request,
            record_candidate_limit=2,
            record_candidate_seed=seed,
            hinted_record_ids={hinted_id},
        )
        hinted_selection = hinted_document["record_selection"]
        self.assertEqual(
            hinted_selection["selection_mode"],
            "discovery_facets_with_neutral_fallback",
        )
        self.assertEqual(hinted_selection["selected_record_ids"][0], hinted_id)
        self.assertEqual(hinted_selection["selected_hint_count"], 1)
        self.assertEqual(hinted_selection["selected_neutral_fallback_count"], 1)
        hinted_index = onchain_projection.index_contract_document(
            hinted_document,
            record_hash=lambda record: str(record["_expected_hash"]).removeprefix("0x"),
            require_finality=True,
            expected_chain_id="eip155:42431",
            expected_registry_address=onchain_rpc.DEFAULT_REGISTRY_ADDRESS,
            max_age_seconds=600,
            now=dt.datetime.fromisoformat(
                hinted_document["indexed_at"].replace("Z", "+00:00")
            ),
            expected_implementation=onchain_projection.DIRECT_RPC_IMPLEMENTATION,
        )
        self.assertTrue(
            hinted_index["verification"]["chain_valid"],
            hinted_index["verification"],
        )
        self.assertEqual(len(hinted_index["records"]), 2)

        invalid_hint_counts = copy.deepcopy(hinted_document)
        invalid_hint_counts["record_selection"]["selected_hint_count"] = 0
        rejected_hint_counts = onchain_projection.index_contract_document(
            invalid_hint_counts,
            record_hash=lambda record: str(record["_expected_hash"]).removeprefix("0x"),
            require_finality=True,
            expected_chain_id="eip155:42431",
            expected_registry_address=onchain_rpc.DEFAULT_REGISTRY_ADDRESS,
            max_age_seconds=600,
            now=dt.datetime.fromisoformat(
                hinted_document["indexed_at"].replace("Z", "+00:00")
            ),
            expected_implementation=onchain_projection.DIRECT_RPC_IMPLEMENTATION,
        )
        self.assertFalse(rejected_hint_counts["verification"]["chain_valid"])

        unmatched_hint_document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
            record_loader=load_record,
            request_json=rpc.request,
            record_candidate_limit=1,
            record_candidate_seed=seed,
            hinted_record_ids={"0x" + "f" * 64},
        )
        self.assertEqual(
            unmatched_hint_document["record_selection"]["selection_mode"],
            "discovery_facets_no_match_fallback",
        )
        unmatched_hint_index = onchain_projection.index_contract_document(
            unmatched_hint_document,
            record_hash=lambda record: str(record["_expected_hash"]).removeprefix("0x"),
            require_finality=True,
            expected_chain_id="eip155:42431",
            expected_registry_address=onchain_rpc.DEFAULT_REGISTRY_ADDRESS,
            max_age_seconds=600,
            now=dt.datetime.fromisoformat(
                unmatched_hint_document["indexed_at"].replace("Z", "+00:00")
            ),
            expected_implementation=onchain_projection.DIRECT_RPC_IMPLEMENTATION,
        )
        self.assertTrue(
            unmatched_hint_index["verification"]["chain_valid"],
            unmatched_hint_index["verification"],
        )
        index = onchain_projection.index_contract_document(
            document,
            record_hash=lambda record: str(record["_expected_hash"]).removeprefix("0x"),
            require_finality=True,
            expected_chain_id="eip155:42431",
            expected_registry_address=onchain_rpc.DEFAULT_REGISTRY_ADDRESS,
            max_age_seconds=600,
            now=dt.datetime.fromisoformat(document["indexed_at"].replace("Z", "+00:00")),
            expected_implementation=onchain_projection.DIRECT_RPC_IMPLEMENTATION,
        )
        self.assertTrue(index["verification"]["chain_valid"], index["verification"])
        self.assertEqual(len(index["records"]), 1)
        self.assertIn("merchant_id", index["records"][0])
        storage = document["contract_storage_verification"]
        self.assertEqual(storage["matched_record_ids"], document["record_selection"]["selected_record_ids"])
        self.assertEqual(storage["finalized_block_hash"], document["finality"]["block_hash"])
        self.assertEqual(storage["excluded_record_ids"], [])

        tampered_documents = []
        unknown = copy.deepcopy(document)
        unknown["record_selection"]["selected_record_ids"] = ["0x" + "f" * 64]
        tampered_documents.append(unknown)
        wrong_count = copy.deepcopy(document)
        wrong_count["record_selection"]["selected_record_count"] = 2
        tampered_documents.append(wrong_count)
        wrong_pool = copy.deepcopy(document)
        wrong_pool["record_selection"]["active_candidate_count"] = 2
        tampered_documents.append(wrong_pool)
        missing_check = copy.deepcopy(document)
        missing_check["contract_storage_verification"]["matched_record_ids"] = []
        tampered_documents.append(missing_check)
        wrong_hash = copy.deepcopy(document)
        wrong_hash["contract_storage_verification"]["finalized_block_hash"] = "0x" + "a" * 64
        tampered_documents.append(wrong_hash)
        excluded_without_error = copy.deepcopy(document)
        excluded_without_error["contract_storage_verification"].update(
            status="excluded_mismatched_records", matched_record_ids=[],
            excluded_record_ids=document["record_selection"]["selected_record_ids"])
        tampered_documents.append(excluded_without_error)
        for tampered in tampered_documents:
            rejected = onchain_projection.index_contract_document(
                tampered,
                record_hash=lambda record: str(record["_expected_hash"]).removeprefix("0x"),
                require_finality=True,
                expected_chain_id="eip155:42431",
                expected_registry_address=onchain_rpc.DEFAULT_REGISTRY_ADDRESS,
                max_age_seconds=600,
                now=dt.datetime.fromisoformat(document["indexed_at"].replace("Z", "+00:00")),
                expected_implementation=onchain_projection.DIRECT_RPC_IMPLEMENTATION,
            )
            self.assertFalse(rejected["verification"]["chain_valid"])

        loader_calls.clear()
        exact_document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
            record_loader=load_record,
            request_json=rpc.request,
            record_candidate_limit=1,
            record_candidate_seed="unrelated seed",
            preferred_domain_hashes={onchain_rpc.domain_hash("sample-2.example")},
        )
        self.assertEqual(exact_document["record_selection"]["selection_mode"], "exact_record_or_domain")
        self.assertEqual(
            exact_document["record_selection"]["selected_record_ids"],
            ["0x" + "8" * 64],
        )
        self.assertEqual(loader_calls, ["https://sample-2.example/record.json"])

    def test_fetches_only_current_record_version_not_broken_history(self) -> None:
        rpc = FakeRpc()
        historical_hash = "0x" + "6" * 64
        historical_uri = "https://merchant.example/missing-old-record.json"
        rpc.logs = [
            registered_log_for(
                rpc,
                record_id=rpc.record_id,
                controller=rpc.controller,
                domain_hash_value=rpc.registered_domain_hash,
                record_hash=historical_hash,
                record_uri=historical_uri,
                log_index=0,
            ),
            rpc.updated_log(
                record_id=rpc.record_id,
                record_hash=rpc.record_hash,
                record_uri=rpc.record_uri,
            ),
        ]
        loaded_uris: list[str] = []

        def load_record(uri: str, _record_hash: str) -> dict:
            loaded_uris.append(uri)
            if uri == historical_uri:
                raise RuntimeError("historical document disappeared")
            return rpc.record()

        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
            record_loader=load_record,
            request_json=rpc.request,
        )
        self.assertEqual(loaded_uris, [rpc.record_uri])
        self.assertEqual(document["record_errors"], [])
        index = self.project_direct(document, rpc.record_hash)
        self.assertEqual([record["merchant_id"] for record in index["records"]], ["merchant-example"])

    def test_replays_update_controller_suspend_and_unsuspend_into_current_record(self) -> None:
        rpc = FakeRpc()
        updated_hash = "0x" + "6" * 64
        updated_uri = "https://merchant.example/updated-record.json"
        final_hash = "0x" + "7" * 64
        final_uri = "https://merchant.example/final-record.json"
        final_controller = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        rpc.logs.extend(
            [
                rpc.updated_log(
                    record_id=rpc.record_id,
                    record_hash=updated_hash,
                    record_uri=updated_uri,
                    block_number=105,
                ),
                rpc.controller_changed_log(
                    record_id=rpc.record_id,
                    controller=final_controller,
                    record_hash=final_hash,
                    record_uri=final_uri,
                    block_number=106,
                ),
                rpc.status_log(
                    "MerchantSuspended",
                    record_id=rpc.record_id,
                    block_number=107,
                ),
                rpc.status_log(
                    "MerchantUnsuspended",
                    record_id=rpc.record_id,
                    block_number=108,
                ),
            ]
        )
        rpc.controller = final_controller
        rpc.record_hash = final_hash
        rpc.record_uri = final_uri
        rpc.states[rpc.record_id].update(
            {
                "controller": final_controller,
                "record_hash": final_hash,
                "status": 1,
            }
        )
        loaded: list[tuple[str, str]] = []

        def load_record(uri: str, record_hash: str) -> dict:
            loaded.append((uri, record_hash))
            return rpc.record()

        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
            record_loader=load_record,
            request_json=rpc.request,
        )

        self.assertEqual(
            [event["event"] for event in document["events"]],
            [
                "MerchantRegistered",
                "MerchantUpdated",
                "ControllerChanged",
                "MerchantSuspended",
                "MerchantUnsuspended",
            ],
        )
        self.assertEqual(loaded, [(final_uri, final_hash)])
        index = self.project_direct(document, final_hash)
        self.assertTrue(index["verification"]["chain_valid"], index["verification"])
        self.assertEqual([record["merchant_id"] for record in index["records"]], ["merchant-example"])
        self.assertEqual(
            index["records"][0]["onchain_identity"]["controller"],
            final_controller,
        )

    def test_replays_revoke_and_supersession_base_events_without_fetching_old_record(self) -> None:
        rpc = FakeRpc()
        new_record_id = "0x" + "6" * 64
        new_controller = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        new_hash = "0x" + "7" * 64
        new_uri = "https://merchant.example/superseding-record.json"
        rpc.logs.extend(
            [
                rpc.status_log(
                    "MerchantRevoked",
                    record_id=rpc.record_id,
                    block_number=110,
                    log_index=0,
                ),
                registered_log_for(
                    rpc,
                    record_id=new_record_id,
                    controller=new_controller,
                    domain_hash_value=rpc.registered_domain_hash,
                    record_hash=new_hash,
                    record_uri=new_uri,
                    log_index=2,
                )
                | {"blockNumber": hex(110)},
            ]
        )
        rpc.states[rpc.record_id]["status"] = 2
        rpc.states[new_record_id] = {
            "controller": new_controller,
            "record_hash": new_hash,
            "domain_hash": rpc.registered_domain_hash,
            "status": 1,
        }
        loaded: list[str] = []

        def load_record(uri: str, _record_hash: str) -> dict:
            loaded.append(uri)
            self.assertEqual(uri, new_uri)
            record = rpc.record()
            record["merchant_id"] = "merchant-superseding"
            record["onchain_identity"].update(
                {
                    "record_id": new_record_id,
                    "controller": new_controller,
                }
            )
            return record

        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
            record_loader=load_record,
            request_json=rpc.request,
        )

        self.assertEqual(loaded, [new_uri])
        self.assertEqual(document["contract_storage_verification"]["checked_record_count"], 1)
        self.assertEqual(document["contract_storage_verification"]["matched_record_ids"],
            document["record_selection"]["selected_record_ids"])
        self.assertEqual(document["contract_storage_verification"]["finalized_block_hash"],
            document["finality"]["block_hash"])
        index = self.project_direct(document, new_hash)
        self.assertTrue(index["verification"]["chain_valid"], index["verification"])
        self.assertEqual([record["merchant_id"] for record in index["records"]], ["merchant-superseding"])
        self.assertEqual(len(index["revocations"]), 1)

    def test_identity_chain_alias_is_consistent_across_collector_and_projection(self) -> None:
        rpc = FakeRpc()

        def load_record(_uri: str, _record_hash: str) -> dict:
            record = rpc.record()
            identity = record["onchain_identity"]
            identity["chain"] = identity.pop("chain_id")
            return record

        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
            record_loader=load_record,
            request_json=rpc.request,
        )
        index = self.project_direct(document, rpc.record_hash)
        self.assertTrue(index["verification"]["chain_valid"], index["verification"])

    def test_shared_onchain_identity_alias_contract(self) -> None:
        fixture = json.loads(IDENTITY_FIXTURE_PATH.read_text(encoding="utf-8"))
        expected = {
            **fixture["expected"],
            "domain_hash": onchain_rpc.domain_hash("merchant.example"),
        }
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                record = {"domain": "merchant.example"}
                if case["container"] == "top_level":
                    record.update(case["identity"])
                else:
                    record[case["container"]] = case["identity"]
                if case["valid"]:
                    onchain_rpc._assert_record_identity(record, expected)
                else:
                    with self.assertRaises(onchain_rpc.OnchainRpcError):
                        onchain_rpc._assert_record_identity(record, expected)

    def test_myotis_head_state_mismatch_fails_closed(self) -> None:
        rpc = FakeRpc(client_version="Myotis/verified-light-client")
        rpc.states[rpc.record_id]["status"] = 2
        with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
            onchain_rpc.collect_finalized_events(
                onchain_rpc.RegistryDeployment(
                    rpc_url="http://127.0.0.1:8546",
                    from_block=100,
                    allow_private_rpc=True,
                    deployment_block_hash=rpc.block_hash,
                ),
                record_loader=lambda _uri, _record_hash: rpc.record(),
                request_json=rpc.request,
            )
        self.assertEqual(raised.exception.code, "contract_record_status_mismatch")

    def test_current_broken_record_is_ineligible_without_fetching_history(self) -> None:
        rpc = FakeRpc()
        historical_hash = "0x" + "6" * 64
        historical_uri = "https://merchant.example/old-record.json"
        broken_uri = "https://merchant.example/current-broken.json"
        rpc.logs = [
            registered_log_for(
                rpc,
                record_id=rpc.record_id,
                controller=rpc.controller,
                domain_hash_value=rpc.registered_domain_hash,
                record_hash=historical_hash,
                record_uri=historical_uri,
                log_index=0,
            ),
            rpc.updated_log(
                record_id=rpc.record_id,
                record_hash=rpc.record_hash,
                record_uri=broken_uri,
            ),
        ]
        loaded_uris: list[str] = []

        def load_record(uri: str, _record_hash: str) -> dict:
            loaded_uris.append(uri)
            raise RuntimeError("current document unavailable")

        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100),
            record_loader=load_record,
            request_json=rpc.request,
        )
        self.assertEqual(loaded_uris, [broken_uri])
        self.assertEqual(document["record_errors"][0]["record_id"], rpc.record_id)
        index = self.project_direct(document, rpc.record_hash)
        self.assertEqual(index["records"], [])

    def test_rejects_more_than_provider_safe_log_range(self) -> None:
        with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
            onchain_rpc.collect_finalized_events(
                onchain_rpc.RegistryDeployment(
                    rpc_url="https://rpc.example",
                    from_block=100,
                    log_chunk_size=100_001,
                ),
                record_loader=lambda _uri, _record_hash: {},
                request_json=FakeRpc().request,
            )
        self.assertEqual(raised.exception.code, "log_chunk_size_invalid")

    def test_rejects_late_from_block_that_would_omit_existing_records(self) -> None:
        rpc = FakeRpc()
        with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
            onchain_rpc.collect_finalized_events(
                onchain_rpc.RegistryDeployment(
                    rpc_url="https://rpc.example",
                    from_block=101,
                ),
                record_loader=lambda _uri, _record_hash: rpc.record(),
                request_json=rpc.request,
            )
        self.assertEqual(
            raised.exception.code,
            "deployment_block_not_contract_creation_boundary",
        )

    def test_myotis_requires_independently_pinned_deployment_block_hash(self) -> None:
        rpc = FakeRpc(client_version="Myotis/verified-light-client")
        with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
            onchain_rpc.collect_finalized_events(
                onchain_rpc.RegistryDeployment(
                    rpc_url="http://127.0.0.1:8546",
                    from_block=100,
                    allow_private_rpc=True,
                ),
                record_loader=lambda _uri, _record_hash: rpc.record(),
                request_json=rpc.request,
            )
        self.assertEqual(raised.exception.code, "myotis_deployment_block_hash_required")

    def test_rejects_stale_finalized_head_for_standard_and_myotis(self) -> None:
        reference = dt.datetime(2026, 8, 23, 12, tzinfo=dt.timezone.utc)
        for client_version, rpc_url, allow_private in (
            ("FakeRpc/1.0", "https://rpc.example", False),
            ("Myotis/verified-light-client", "http://127.0.0.1:8546", True),
        ):
            with self.subTest(client_version=client_version):
                rpc = FakeRpc(
                    client_version=client_version,
                    finalized_timestamp=int(reference.timestamp()) - 601,
                )
                with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
                    onchain_rpc.collect_finalized_events(
                        onchain_rpc.RegistryDeployment(
                            rpc_url=rpc_url,
                            from_block=100,
                            allow_private_rpc=allow_private,
                        ),
                        record_loader=lambda _uri, _record_hash: rpc.record(),
                        request_json=rpc.request,
                        now=lambda: reference,
                    )
                self.assertEqual(raised.exception.code, "finalized_block_time_stale")

    def test_rejects_future_finalized_head_for_standard_and_myotis(self) -> None:
        reference = dt.datetime(2026, 8, 23, 12, tzinfo=dt.timezone.utc)
        for client_version, rpc_url, allow_private in (
            ("FakeRpc/1.0", "https://rpc.example", False),
            ("Myotis/verified-light-client", "http://127.0.0.1:8546", True),
        ):
            with self.subTest(client_version=client_version):
                rpc = FakeRpc(
                    client_version=client_version,
                    finalized_timestamp=int(reference.timestamp()) + 301,
                )
                with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
                    onchain_rpc.collect_finalized_events(
                        onchain_rpc.RegistryDeployment(
                            rpc_url=rpc_url,
                            from_block=100,
                            allow_private_rpc=allow_private,
                        ),
                        record_loader=lambda _uri, _record_hash: rpc.record(),
                        request_json=rpc.request,
                        now=lambda: reference,
                    )
                self.assertEqual(raised.exception.code, "finalized_block_time_future")

    def test_ethereum_uses_chain_specific_finality_age_policy(self) -> None:
        reference = dt.datetime(2026, 8, 23, 12, tzinfo=dt.timezone.utc)
        rpc = FakeRpc(
            supplied_chain_id=1,
            finalized_timestamp=int(reference.timestamp()) - 1200,
        )
        document = onchain_rpc.collect_finalized_events(
            onchain_rpc.RegistryDeployment(
                rpc_url="https://ethereum-rpc.example",
                chain_id=1,
                from_block=100,
            ),
            record_loader=lambda _uri, _record_hash: rpc.record(),
            request_json=rpc.request,
            now=lambda: reference,
        )
        self.assertEqual(document["finality"]["max_age_seconds"], 1800)

        with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
            onchain_rpc.collect_finalized_events(
                onchain_rpc.RegistryDeployment(
                    rpc_url="https://ethereum-rpc.example",
                    chain_id=1,
                    from_block=100,
                    max_finality_age_seconds=600,
                ),
                record_loader=lambda _uri, _record_hash: rpc.record(),
                request_json=rpc.request,
                now=lambda: reference,
            )
        self.assertEqual(raised.exception.code, "finalized_block_time_stale")

    def test_rpc_url_label_redacts_path_query_and_userinfo_credentials(self) -> None:
        self.assertEqual(
            onchain_rpc.rpc_url_label("https://user:secret@rpc.example:8545/v3/api-key?token=secret"),
            "https://rpc.example:8545",
        )


class VerifiedCheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cache_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.cache_dir.cleanup)
        patcher = mock.patch.dict(os.environ, {
            "SHOPBRIDGE_ONCHAIN_CACHE_DIR": self.cache_dir.name,
            "SHOPBRIDGE_ONCHAIN_CACHE_DISABLED": "0",
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rpc = FakeRpc()
        self.deployment = onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100,
            discovery_facets_address=self.rpc.facets_address, discovery_facets_from_block=105)

    def collect(self, **kwargs):
        return onchain_rpc.collect_finalized_events(self.deployment,
            record_loader=kwargs.pop("record_loader", lambda *_: self.rpc.record()),
            request_json=kwargs.pop("request_json", self.rpc.request), **kwargs)

    def test_cold_checkpoint_is_private_and_warm_revoke_uses_only_incremental_logs(self):
        cold = self.collect()
        self.assertEqual(cold["rpc"]["checkpoint"]["status"], "miss")
        path = onchain_rpc._cache_path(onchain_rpc._cache_key(self.deployment))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.rpc.finalized_number = 130
        self.rpc.logs.append(self.rpc.status_log(event_name="MerchantRevoked",
            record_id=self.rpc.record_id, block_number=125))
        self.rpc.states[self.rpc.record_id]["status"] = 2
        self.rpc.log_calls.clear()
        warm = self.collect(record_loader=lambda *_: self.fail("revoked record fetched"))
        self.assertEqual(warm["rpc"]["checkpoint"]["status"], "hit")
        self.assertEqual([(int(row["fromBlock"], 16), int(row["toBlock"], 16))
            for row in self.rpc.log_calls], [(121, 130), (121, 130)])
        self.assertEqual(warm["events"][-1]["event"], "MerchantRevoked")
        self.assertEqual(warm["resolved_record_count"], 0)

    def test_warm_update_loads_only_new_document_and_all_cached_category_topics(self):
        self.rpc.enable_facets(["tea", "coffee"])
        tea_hash = "0x" + onchain_rpc.keccak256(b"tea").hex()
        coffee_hash = "0x" + onchain_rpc.keccak256(b"coffee").hex()
        self.collect(record_loader=lambda *_: self.rpc.record_with_facets(["tea", "coffee"]),
            category_hash_groups=[{tea_hash}])
        self.rpc.finalized_number = 130
        new_hash = "0x" + "a" * 64
        new_uri = "https://merchant.example/new-record.json"
        self.rpc.logs.append(self.rpc.updated_log(record_id=self.rpc.record_id, record_hash=new_hash,
            record_uri=new_uri, block_number=125))
        self.rpc.states[self.rpc.record_id]["record_hash"] = new_hash
        self.rpc.facet_states[self.rpc.record_id]["record_hash"] = new_hash
        loaded = []
        self.rpc.log_calls.clear()
        def loader(uri, record_hash):
            loaded.append((uri, record_hash))
            return self.rpc.record_with_facets(["tea", "coffee"])
        warm = self.collect(record_loader=loader, category_hash_groups=[{coffee_hash}])
        self.assertEqual(loaded, [(new_uri, new_hash)])
        self.assertEqual(warm["rpc"]["checkpoint"]["status"], "hit")
        self.assertTrue(all(int(row["fromBlock"], 16) == 121 for row in self.rpc.log_calls))
        self.assertEqual(warm["onchain_discovery_facets"]["matched_record_count"], 1)

    def test_invalid_checkpoint_falls_back_to_full_verified_scan(self):
        for defect in ("hash", "chain", "registry", "corrupt", "log_tamper"):
            with self.subTest(defect=defect):
                self.collect()
                path = onchain_rpc._cache_path(onchain_rpc._cache_key(self.deployment))
                envelope = json.loads(path.read_text())
                payload = envelope["payload"]
                if defect == "hash":
                    payload["block_hash"] = "0x" + "a" * 64
                elif defect == "chain":
                    payload["key"]["chain_id"] = 1
                elif defect == "registry":
                    payload["key"]["registry_address"] = "0x" + "a" * 40
                elif defect == "log_tamper":
                    payload["logs"][0]["data"] = "0x"
                envelope["sha256"] = onchain_rpc._cache_digest(payload)
                path.write_text("{" if defect == "corrupt" else json.dumps(envelope))
                self.rpc.log_calls.clear()
                document = self.collect()
                self.assertEqual(document["rpc"]["checkpoint"]["status"], "invalid")
                self.assertEqual(int(self.rpc.log_calls[0]["fromBlock"], 16), 100)
                self.assertEqual(document["resolved_record_count"], 1)

    def test_unreadable_checkpoint_falls_back_to_full_scan(self):
        self.collect()
        self.rpc.log_calls.clear()
        original_open = onchain_rpc.os.open
        def restricted_open(path, flags, *args, **kwargs):
            if str(path).endswith(".json"):
                raise PermissionError("unreadable")
            return original_open(path, flags, *args, **kwargs)
        with mock.patch.object(onchain_rpc.os, "open", side_effect=restricted_open):
            document = self.collect()
        self.assertEqual(document["rpc"]["checkpoint"]["status"], "invalid")
        self.assertEqual(int(self.rpc.log_calls[0]["fromBlock"], 16), 100)
        self.assertEqual(document["resolved_record_count"], 1)

    def test_read_only_cache_directory_is_nonfatal(self):
        original_open = onchain_rpc.os.open
        def read_only_open(path, flags, *args, **kwargs):
            if flags & os.O_CREAT:
                raise PermissionError("read-only directory")
            return original_open(path, flags, *args, **kwargs)
        with mock.patch.object(onchain_rpc.os, "open", side_effect=read_only_open):
            document = self.collect()
        self.assertEqual(document["rpc"]["checkpoint"]["status"], "write_failed")
        self.assertEqual(document["resolved_record_count"], 1)
        self.assertEqual(list(Path(self.cache_dir.name).iterdir()), [])

    def test_unwritable_checkpoint_is_nonfatal(self):
        with mock.patch.object(onchain_rpc.os, "replace", side_effect=PermissionError("read-only")):
            document = self.collect()
        self.assertEqual(document["rpc"]["checkpoint"]["status"], "write_failed")
        self.assertEqual(document["resolved_record_count"], 1)
        self.assertEqual(list(Path(self.cache_dir.name).iterdir()), [])

    def test_projection_rejects_selected_document_without_matching_storage_check(self):
        document = self.collect()
        document["contract_storage_verification"]["matched_record_ids"] = []
        index = onchain_projection.index_contract_document(document,
            record_hash=lambda _: self.rpc.record_hash.removeprefix("0x"), require_finality=True,
            expected_chain_id=document["chain_id"], expected_registry_address=document["registry_address"],
            expected_implementation=onchain_projection.DIRECT_RPC_IMPLEMENTATION)
        self.assertFalse(index["verification"]["chain_valid"])
        self.assertEqual(index["records"], [])
        self.assertIn("contract_events_selected_storage_coverage_invalid",
            {error["error"] for error in index["verification"]["errors"]})

    def test_storage_checks_only_selected_and_backfill_and_excludes_mismatch(self):
        records = {}
        for index in range(6):
            record_id = "0x" + f"{index + 1:064x}"
            domain = f"shop-{index}.example"
            hash_value = onchain_rpc.domain_hash(domain)
            uri = f"https://{domain}/record.json"
            record_hash = "0x" + f"{index + 100:064x}"
            self.rpc.logs.append(registered_log_for(self.rpc, record_id=record_id,
                controller=self.rpc.controller, domain_hash_value=hash_value,
                record_hash=record_hash, record_uri=uri, log_index=index + 1))
            self.rpc.states[record_id] = dict(self.rpc.states[self.rpc.record_id],
                domain_hash=hash_value, record_hash=record_hash)
            record = self.rpc.record()
            record.update(domain=domain, merchant_id=f"shop-{index}")
            record["onchain_identity"]["record_id"] = record_id
            records[uri] = record
        seed = "bounded-storage"
        ordered = sorted(self.rpc.states, key=lambda record_id: __import__("hashlib").sha256(f"{seed}\0{record_id}".encode()).digest())
        self.rpc.states[ordered[0]]["status"] = 2
        loaded = []
        def loader(uri, _hash):
            loaded.append(uri)
            return records.get(uri, self.rpc.record())
        document = self.collect(record_candidate_limit=1, record_candidate_seed=seed, record_loader=loader)
        checks = [params for params in self.rpc.call_calls if params[0]["data"].startswith(onchain_rpc.RECORD_SELECTOR)]
        self.assertEqual(len(checks), 2)
        self.assertEqual(document["contract_storage_verification"]["checked_record_count"], 2)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(document["record_errors"][0]["code"], "contract_record_status_mismatch")
        self.assertEqual(document["resolved_record_count"], 1)
        self.assertTrue(all(params[1] == hex(120) for params in checks))
        self.assertFalse(onchain_rpc._cache_path(onchain_rpc._cache_key(self.deployment)).exists())
        index = onchain_projection.index_contract_document(document,
            record_hash=lambda record: self.rpc.states[record["onchain_identity"]["record_id"]]["record_hash"].removeprefix("0x"),
            require_finality=True, expected_chain_id=document["chain_id"],
            expected_registry_address=document["registry_address"],
            expected_implementation=onchain_projection.DIRECT_RPC_IMPLEMENTATION)
        self.assertTrue(index["verification"]["chain_valid"], index["verification"])
        self.assertEqual(len(index["records"]), 1)
        self.assertNotEqual(index["records"][0]["onchain_identity"]["record_id"], ordered[0])

    def test_cache_provider_change_forces_full_rescan(self):
        self.collect()
        old_path = onchain_rpc._cache_path(onchain_rpc._cache_key(self.deployment))
        self.deployment = replace(self.deployment, rpc_url="https://another-provider.example/v3/key")
        new_path = onchain_rpc._cache_path(onchain_rpc._cache_key(self.deployment))
        new_path.write_bytes(old_path.read_bytes())
        new_path.chmod(0o600)
        self.rpc.log_calls.clear()
        document = self.collect()
        self.assertEqual(document["rpc"]["checkpoint"]["status"], "invalid")
        self.assertEqual(int(self.rpc.log_calls[0]["fromBlock"], 16), 100)
        self.assertEqual(document["resolved_record_count"], 1)

    def test_unpinned_observed_runtime_change_invalidates_checkpoint(self):
        for contract in ("registry", "facets"):
            with self.subTest(contract=contract):
                self.collect()
                if contract == "registry":
                    self.rpc.registry_code += "00"
                else:
                    self.rpc.facets_code += "00"
                self.rpc.log_calls.clear()
                document = self.collect()
                self.assertEqual(document["rpc"]["checkpoint"]["status"], "invalid")
                self.assertEqual(int(self.rpc.log_calls[0]["fromBlock"], 16), 100)
                self.assertEqual(document["resolved_record_count"], 1)

    def test_semantic_owner_rewrite_is_trusted_local_state_not_authenticated(self):
        self.collect()
        path = onchain_rpc._cache_path(onchain_rpc._cache_key(self.deployment))
        envelope = json.loads(path.read_text())
        envelope["payload"]["logs"] = []
        envelope["sha256"] = onchain_rpc._cache_digest(envelope["payload"])
        path.write_text(json.dumps(envelope))
        # Same-euid, owner-only state is intentionally trusted: the digest
        # detects corruption, NOT authenticated log completeness.
        rewritten = self.collect()
        self.assertEqual(rewritten["rpc"]["checkpoint"]["status"], "hit")
        self.assertEqual(rewritten["resolved_record_count"], 0)
        path.chmod(0o644)
        self.rpc.log_calls.clear()
        rejected = self.collect()
        self.assertEqual(rejected["rpc"]["checkpoint"]["status"], "invalid")
        self.assertEqual(rejected["resolved_record_count"], 1)
        self.assertEqual(int(self.rpc.log_calls[0]["fromBlock"], 16), 100)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_symlinked_checkpoint_is_not_followed(self):
        self.collect()
        path = onchain_rpc._cache_path(onchain_rpc._cache_key(self.deployment))
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "external.json"
            original = path.read_bytes()
            path.rename(target)
            path.symlink_to(target)
            self.rpc.log_calls.clear()
            document = self.collect()
            self.assertEqual(document["rpc"]["checkpoint"]["status"], "invalid")
            self.assertEqual(document["resolved_record_count"], 1)
            self.assertEqual(target.read_bytes(), original)
            self.assertFalse(path.is_symlink())

    def test_symlinked_or_shared_cache_directory_is_disabled(self):
        root = Path(self.cache_dir.name)
        actual = root / "real"
        actual.mkdir(mode=0o700)
        link = root / "link"
        link.symlink_to(actual, target_is_directory=True)
        shared = root / "shared"
        shared.mkdir()
        shared.chmod(0o777)
        for directory in (link, shared):
            with self.subTest(directory=directory), mock.patch.dict(os.environ,
                    {"SHOPBRIDGE_ONCHAIN_CACHE_DIR": str(directory)}):
                document = self.collect()
                self.assertEqual(document["rpc"]["checkpoint"]["status"], "disabled")
                self.assertEqual(document["rpc"]["checkpoint"]["reason"], "cache_dir_insecure")
                self.assertEqual(document["resolved_record_count"], 1)
        self.assertEqual(list(actual.iterdir()), [])
        self.assertEqual(list(shared.iterdir()), [])
        self.assertEqual(shared.stat().st_mode & 0o777, 0o777)
        with mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_CACHE_DIR": "", "XDG_CACHE_HOME": str(shared)}):
            document = self.collect()
            self.assertEqual(document["rpc"]["checkpoint"]["reason"], "cache_dir_insecure")
            self.assertFalse((shared / "shopbridge-direct").exists())

    def test_wrong_cache_owner_is_rejected(self):
        original_lstat = Path.lstat
        def foreign_directory(path):
            result = original_lstat(path)
            if path == Path(self.cache_dir.name):
                fields = list(result)
                fields[4] = os.geteuid() + 1
                return os.stat_result(fields)
            return result
        with mock.patch.object(Path, "lstat", foreign_directory):
            document = self.collect()
        self.assertEqual(document["rpc"]["checkpoint"]["reason"], "cache_dir_insecure")
        self.collect()
        original_fstat = os.fstat
        def foreign_file(descriptor):
            result = original_fstat(descriptor)
            if stat.S_ISREG(result.st_mode):
                fields = list(result)
                fields[4] = os.geteuid() + 1
                return os.stat_result(fields)
            return result
        with mock.patch.object(onchain_rpc.os, "fstat", side_effect=foreign_file):
            document = self.collect()
        self.assertEqual(document["rpc"]["checkpoint"]["status"], "invalid")
        self.assertEqual(document["resolved_record_count"], 1)

    def test_deeply_nested_checkpoint_is_invalid_not_uncaught(self):
        self.collect()
        path = onchain_rpc._cache_path(onchain_rpc._cache_key(self.deployment))
        path.write_text("[" * 2000 + "0" + "]" * 2000)
        self.rpc.log_calls.clear()
        document = self.collect()
        self.assertEqual(document["rpc"]["checkpoint"]["status"], "invalid")
        self.assertEqual(int(self.rpc.log_calls[0]["fromBlock"], 16), 100)
        self.assertEqual(document["resolved_record_count"], 1)

    def test_unsupported_cache_platform_disables_persistence_without_weak_fallback(self):
        unsupported = ("geteuid", "O_DIRECTORY", "O_NOFOLLOW", "open_dir_fd",
                       "replace_dir_fd", "unlink_dir_fd", "stat_nofollow")
        for missing in unsupported:
            with self.subTest(missing=missing), mock.patch.dict(os.__dict__):
                if missing.endswith("_dir_fd"):
                    names = ("replace", "rename") if missing == "replace_dir_fd" else (missing.removesuffix("_dir_fd"),)
                    os.supports_dir_fd = os.supports_dir_fd.difference(getattr(os, name) for name in names)
                elif missing == "stat_nofollow":
                    os.supports_follow_symlinks = os.supports_follow_symlinks.difference({os.stat})
                else:
                    delattr(os, missing)
                name = "shopbridge_rpc_unsupported_" + missing
                spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
                runtime = importlib.util.module_from_spec(spec)
                sys.modules[name] = runtime
                try:
                    spec.loader.exec_module(runtime)
                    self.rpc.log_calls.clear()
                    document = runtime.collect_finalized_events(
                        runtime.RegistryDeployment(rpc_url="https://rpc.example", from_block=100,
                            discovery_facets_address=self.rpc.facets_address, discovery_facets_from_block=105),
                        request_json=self.rpc.request, record_loader=lambda *_: self.rpc.record())
                    self.assertEqual(document["rpc"]["checkpoint"]["status"], "disabled")
                    self.assertEqual(document["rpc"]["checkpoint"]["reason"], "cache_unsupported_platform")
                    self.assertEqual(document["resolved_record_count"], 1)
                    self.assertEqual(document["contract_storage_verification"]["status"], "matched")
                    self.assertEqual(int(self.rpc.log_calls[0]["fromBlock"], 16), 100)
                    self.assertEqual(list(Path(self.cache_dir.name).iterdir()), [])
                finally:
                    sys.modules.pop(name, None)

    def test_myotis_bypasses_checkpoint_and_scans_full_history_each_time(self):
        self.rpc.client_version = "Myotis/verified-light-client"
        self.deployment = onchain_rpc.RegistryDeployment(rpc_url="http://127.0.0.1:8546",
            from_block=100, allow_private_rpc=True, deployment_block_hash=self.rpc.block_hash)
        for _ in range(2):
            self.rpc.log_calls.clear()
            document = self.collect()
            self.assertEqual(document["rpc"]["checkpoint"]["status"], "disabled")
            self.assertEqual(int(self.rpc.log_calls[-1]["fromBlock"], 16), 100)
        self.assertEqual(list(Path(self.cache_dir.name).iterdir()), [])



class FinalizedHistoryPagingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patcher = mock.patch.dict(os.environ, {
            "SHOPBRIDGE_ONCHAIN_CACHE_DIR": self.directory.name,
            "SHOPBRIDGE_ONCHAIN_CACHE_DISABLED": "0",
            "SHOPBRIDGE_ONCHAIN_LOG_WORKERS": "4",
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rpc = FakeRpc()
        self.deployment = onchain_rpc.RegistryDeployment(rpc_url="https://rpc.example", from_block=100,
            log_chunk_size=10, discovery_facets_address=self.rpc.facets_address,
            discovery_facets_from_block=105)

    def collect(self, request=None):
        return onchain_rpc.collect_finalized_events(self.deployment,
            record_loader=lambda *_: self.rpc.record(), request_json=request or self.rpc.request,
            record_candidate_seed="history-regression")

    def test_out_of_order_pages_merge_deterministically(self):
        gate = threading.Event()
        completed = []
        def request(url, **kwargs):
            payload = kwargs["payload"]
            if payload["method"] == "eth_getLogs" and payload["params"][0]["address"] == self.rpc.registry:
                start = int(payload["params"][0]["fromBlock"], 16)
                if start == 100:
                    self.assertTrue(gate.wait(2))
                else:
                    completed.append(start)
                    gate.set()
            return self.rpc.request(url, **kwargs)
        self.rpc.logs.extend([
            self.rpc.status_log(event_name="MerchantSuspended", record_id=self.rpc.record_id, block_number=110),
            self.rpc.status_log(event_name="MerchantUnsuspended", record_id=self.rpc.record_id, block_number=115),
        ])
        document = self.collect(request)
        self.assertNotEqual(completed[0], 100)
        self.assertEqual([event["event"] for event in document["events"]],
            ["MerchantRegistered", "MerchantSuspended", "MerchantUnsuspended"])
        self.assertEqual([event["block_number"] for event in document["events"]], [100, 110, 115])
        with tempfile.TemporaryDirectory() as other, mock.patch.dict(os.environ,
                {"SHOPBRIDGE_ONCHAIN_CACHE_DIR": other, "SHOPBRIDGE_ONCHAIN_LOG_WORKERS": "1"}):
            sequential = self.collect()
        self.assertEqual(document["events"], sequential["events"])
        self.assertEqual(document["record_selection"], sequential["record_selection"])

    def test_http_429_retries_then_succeeds(self):
        attempts = 0
        lock = threading.Lock()
        def request(url, **kwargs):
            nonlocal attempts
            if kwargs["payload"]["method"] == "eth_getLogs":
                with lock:
                    attempts += 1
                    fail = attempts == 1
                if fail:
                    raise onchain_rpc.safe_http.SafeHttpError("upstream_http_error", status=429, retry_after=2)
            return self.rpc.request(url, **kwargs)
        clock = FakeClock()
        with mock.patch.object(onchain_rpc.time, "sleep", side_effect=clock.sleep), mock.patch.object(onchain_rpc.time, "monotonic", side_effect=clock):
            document = self.collect(request)
        self.assertEqual(document["resolved_record_count"], 1)
        self.assertEqual(document["rpc"]["checkpoint"]["http_429_count"], 1)
        self.assertEqual(document["rpc"]["checkpoint"]["retry_count"], 1)
        self.assertEqual(attempts, 7)
        self.assertGreaterEqual(sum(clock.sleeps), 2)

    def test_persistent_transient_failure_is_bounded_and_surfaces_error(self):
        attempts = []
        def request(url, **kwargs):
            payload = kwargs["payload"]
            if payload["method"] == "eth_getLogs":
                attempts.append(payload["params"][0]["fromBlock"])
                raise onchain_rpc.safe_http.SafeHttpError("upstream_http_error", status=503)
            return self.rpc.request(url, **kwargs)
        clock = FakeClock()
        with (
            mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_LOG_WORKERS": "1"}),
            mock.patch.object(onchain_rpc.time, "sleep", side_effect=clock.sleep),
            mock.patch.object(onchain_rpc.time, "monotonic", side_effect=clock),
        ):
            with self.assertRaisesRegex(onchain_rpc.OnchainRpcError, "rpc_transport_failed"):
                self.collect(request)
        self.assertEqual(attempts, [hex(100)] * 4)
        self.assertFalse(onchain_rpc._cache_path(onchain_rpc._cache_key(self.deployment)).exists())

    def test_history_pages_preserve_general_allowance_but_event_headers_consume_it(self):
        budget = onchain_rpc.safe_http.DiscoveryBudget(requests=256)
        classifications = []
        def request(url, **kwargs):
            history = onchain_rpc.safe_http.history_request.get()
            classifications.append((kwargs["payload"]["method"], kwargs["payload"]["params"], history))
            _, allocation = budget.reserve(30, 1024, history=history)
            try:
                return self.rpc.request(url, **kwargs)
            finally:
                budget.finish(allocation, 0)
        token = onchain_rpc.safe_http.discovery_budget.set(budget)
        try:
            document = self.collect(request)
        finally:
            onchain_rpc.safe_http.discovery_budget.reset(token)
        self.assertEqual(document["rpc"]["checkpoint"]["history_log_pages"], 6)
        self.assertTrue(all(history for method, _, history in classifications if method == "eth_getLogs"))
        self.assertEqual(budget.history_requests_used, 9)
        self.assertEqual(budget.requests_remaining, 256 - sum(not row[2] for row in classifications))
        event_headers = [history for method, params, history in classifications
                         if method == "eth_getBlockByNumber" and params[0] == hex(100)]
        self.assertEqual(event_headers, [False, False])
        exhausted = onchain_rpc.safe_http.DiscoveryBudget(requests=0)
        exhausted.reserve(1, 10, history=True)
        with self.assertRaisesRegex(onchain_rpc.safe_http.SafeHttpError, "discovery_budget_exhausted"):
            exhausted.reserve(1, 10)

    def test_history_page_limit_is_enforced_before_log_requests(self):
        with mock.patch.object(onchain_rpc, "MAX_HISTORY_LOG_PAGES", 5):
            with self.assertRaisesRegex(onchain_rpc.OnchainRpcError, "history_scan_exceeds_limit"):
                self.collect()
        self.assertEqual(self.rpc.log_calls, [])

    def test_deadline_persists_only_verified_prefix_then_resumes_full_projection(self):
        budget = onchain_rpc.safe_http.DiscoveryBudget()
        def request(url, **kwargs):
            payload = kwargs["payload"]
            if payload["method"] == "eth_getLogs" and int(payload["params"][0]["fromBlock"], 16) >= 110:
                budget.deadline = 0
                raise onchain_rpc.safe_http.SafeHttpError("discovery_budget_exhausted")
            return self.rpc.request(url, **kwargs)
        with mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_LOG_WORKERS": "1"}):
            token = onchain_rpc.safe_http.discovery_budget.set(budget)
            try:
                with self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
                    self.collect(request)
            finally:
                onchain_rpc.safe_http.discovery_budget.reset(token)
        self.assertEqual(raised.exception.code, "history_sync_incomplete")
        error = json.loads(onchain_rpc.error_document(raised.exception))
        self.assertEqual(error["progress"]["blocks_done"], 10)
        self.assertEqual(error["progress"]["blocks_total"], 21)
        path = onchain_rpc._cache_path(onchain_rpc._cache_key(self.deployment))
        prefix = json.loads(path.read_text())["payload"]
        self.assertEqual(prefix["block_number"], 109)
        self.assertFalse(prefix["history_complete"])
        self.assertTrue(all("registry_record" not in row for row in prefix["logs"]))
        self.rpc.log_calls.clear()
        resumed = self.collect()
        self.assertEqual(resumed["rpc"]["checkpoint"]["status"], "hit")
        self.assertTrue(all(int(query["fromBlock"], 16) >= 110 for query in self.rpc.log_calls))
        with tempfile.TemporaryDirectory() as other, mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_CACHE_DIR": other}):
            full = self.collect()
        def project(document):
            return onchain_projection.index_contract_document(document, record_hash=lambda _: self.rpc.record_hash[2:],
                require_finality=True, expected_chain_id=document["chain_id"],
                expected_registry_address=document["registry_address"],
                expected_implementation=onchain_projection.DIRECT_RPC_IMPLEMENTATION)
        self.assertEqual(resumed["events"], full["events"])
        resumed_index, full_index = project(resumed), project(full)
        self.assertTrue(resumed_index["verification"]["chain_valid"], resumed_index["verification"])
        self.assertEqual(resumed_index["records"], full_index["records"])
        self.assertEqual(resumed_index["revocations"], full_index["revocations"])


    def test_astronomical_height_is_rejected_before_range_materialization(self):
        client = onchain_rpc.JsonRpcClient(self.deployment.rpc_url, request_json=self.rpc.request)
        with mock.patch.object(onchain_rpc, "range",
                side_effect=AssertionError("range constructed before cap"), create=True):
            with self.assertRaisesRegex(onchain_rpc.OnchainRpcError, "history_scan_exceeds_limit"):
                onchain_rpc._scan_finalized_history(client, deployment=self.deployment,
                    from_block=100, to_block=10 ** 10000, chunk_size=10, checkpoint=None,
                    witness=None, deployment_verification={}, facets_verification=None,
                    observed_code_hashes={}, diagnostics={"scanned_ranges": []})
        self.assertEqual(self.rpc.log_calls, [])

    def test_huge_retry_after_is_clamped_without_an_outer_budget(self):
        clock = FakeClock()
        attempts = 0
        def request(url, **kwargs):
            nonlocal attempts
            budget = onchain_rpc.safe_http.discovery_budget.get()
            _, allocation = budget.reserve(30, 1024, history=onchain_rpc.safe_http.history_request.get())
            try:
                if kwargs["payload"]["method"] == "eth_getLogs":
                    attempts += 1
                    if attempts == 1:
                        raise onchain_rpc.safe_http.SafeHttpError("upstream_http_error", status=429, retry_after=3600)
                return self.rpc.request(url, **kwargs)
            finally:
                budget.finish(allocation, 0)
        with (
            mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_LOG_WORKERS": "1"}),
            mock.patch.object(onchain_rpc.time, "monotonic", side_effect=clock),
            mock.patch.object(onchain_rpc.time, "sleep", side_effect=clock.sleep),
        ):
            document = self.collect(request)
        self.assertEqual(document["resolved_record_count"], 1)
        self.assertEqual(max(clock.sleeps), 30)
        self.assertIsNone(onchain_rpc.safe_http.discovery_budget.get())


    def test_workers_configuration_is_bounded(self):
        for value in ("0", "9", "many"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_LOG_WORKERS": value}):
                with self.assertRaisesRegex(onchain_rpc.OnchainRpcError, "history_log_workers_invalid"):
                    self.collect()


class ExactOnchainResolutionBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("onchain_resolution_security_command",
            SCRIPT_PATH.with_name("shopbridge-command.py"))
        cls.command = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.command
        spec.loader.exec_module(cls.command)

    def setUp(self):
        self.rpc = FakeRpc()
        self.args = {"onchain_rpc_url": "https://rpc.example", "onchain_from_block": 100,
            "onchain_discovery_facets_address": self.rpc.facets_address,
            "onchain_discovery_facets_from_block": 105, "record_id": self.rpc.record_id}
        patcher = mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_CACHE_DISABLED": "1",
            "SHOPBRIDGE_ONCHAIN_LOG_WORKERS": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_exact_resolution_honors_request_and_response_byte_limits(self):
        transport = self.command.safe_http
        for limit in ("requests", "bytes"):
            with self.subTest(limit=limit):
                budget = transport.DiscoveryBudget(requests=0 if limit == "requests" else 256,
                    response_bytes=1 if limit == "bytes" else 64 * 1024 * 1024)
                requests = []
                def request(url, **kwargs):
                    _, allocation = transport.discovery_budget.get().reserve(30, 1024,
                        history=transport.history_request.get())
                    requests.append(kwargs["payload"])
                    transport.discovery_budget.get().finish(allocation, 0)
                    return self.rpc.request(url, **kwargs)
                with (
                    mock.patch.object(transport, "DiscoveryBudget", return_value=budget),
                    mock.patch.object(transport, "request_json", side_effect=request),
                ):
                    with self.assertRaises(SystemExit) as raised:
                        self.command.command_resolve_merchant(dict(self.args))
                error = json.loads(str(raised.exception))
                self.assertEqual(error["detail"], "discovery_budget_exhausted")
                self.assertEqual(requests, [])
                self.assertIsNone(transport.discovery_budget.get())

    def test_exact_domain_resolution_honors_deadline_and_retry_after_clamp(self):
        transport = self.command.safe_http
        original_budget = transport.DiscoveryBudget
        clock = FakeClock()
        completed_rpc = []
        def request(url, **kwargs):
            budget = transport.discovery_budget.get()
            _, allocation = budget.reserve(30, 1024, history=transport.history_request.get())
            try:
                if kwargs["payload"]["method"] == "eth_getLogs":
                    raise transport.SafeHttpError("upstream_http_error", status=429, retry_after=3600)
                completed_rpc.append(kwargs["payload"]["method"])
                return self.rpc.request(url, **kwargs)
            finally:
                budget.finish(allocation, 0)
        args = {key: value for key, value in self.args.items() if key != "record_id"}
        args["merchant_domain"] = self.rpc.domain
        with (
            mock.patch.object(transport.time, "monotonic", side_effect=clock),
            mock.patch.object(transport.time, "sleep", side_effect=clock.sleep),
            mock.patch.object(transport, "DiscoveryBudget", side_effect=lambda: original_budget(seconds=1)),
            mock.patch.object(transport, "request_json", side_effect=request),
        ):
            with self.assertRaises(SystemExit) as raised:
                self.command.command_resolve_merchant(args)
        error = json.loads(str(raised.exception))
        self.assertEqual(error["code"], "history_sync_incomplete")
        self.assertEqual(error["progress"]["blocks_done"], 0)
        self.assertEqual(sum(clock.sleeps), 1)
        self.assertIn("eth_chainId", completed_rpc)
        self.assertIsNone(transport.discovery_budget.get())

    def test_nested_exact_resolution_keeps_outer_request_allowance(self):
        transport = self.command.safe_http
        budget = transport.DiscoveryBudget(requests=1)
        requests = []
        def request(url, **kwargs):
            _, allocation = transport.discovery_budget.get().reserve(30, 1024)
            requests.append(kwargs["payload"]["method"])
            budget.finish(allocation, 0)
            return self.rpc.request(url, **kwargs)
        token = transport.discovery_budget.set(budget)
        try:
            with mock.patch.object(transport, "request_json", side_effect=request):
                with self.assertRaises(SystemExit) as raised:
                    self.command.command_resolve_merchant(dict(self.args))
            self.assertEqual(json.loads(str(raised.exception))["detail"], "discovery_budget_exhausted")
            self.assertIs(transport.discovery_budget.get(), budget)
            self.assertEqual(requests, ["eth_chainId"])
            self.assertEqual(budget.requests_remaining, 0)
        finally:
            transport.discovery_budget.reset(token)


class EnumerableV2Rpc(FakeRpc):
    def __init__(self):
        super().__init__()
        self.requests = []
        self.disagree = ""
        self.category = "0x" + "1" * 64
        self.category_generation = 1
        self.current = True
        self.ineligible_ids = set()
        self.pruned_ids = set()
        self.category = next(iter(self.enable_facets(["tea"])))

    def request(self, url, **kwargs):
        payload = kwargs["payload"]
        if isinstance(payload, list):
            return [self.request(url, **{**kwargs, "payload": item}) for item in payload]
        method, params = payload["method"], payload["params"]
        self.requests.append((url, method, params))
        if method == "eth_getLogs":
            raise AssertionError("v2 must not scan history")
        signatures = {name: "0x" + onchain_rpc.keccak256(name.encode()).hex()[:8] for name in (
            "indexedRecordCount()", "indexedRecordIdAt(uint256)", "recordURI(bytes32)",
            "eligibility(bytes32)", "categoryRecordCount(bytes32)", "categoryRecordAt(bytes32,uint256)",
            "isCurrent(bytes32)")}
        result = None
        if method == "eth_call":
            self.assert_hash_selector(params[-1])
            data = params[0]["data"]
            selector = data[:10]
            indexed_ids = [record_id for record_id in self.states if record_id not in self.pruned_ids]
            if selector in {signatures["indexedRecordCount()"], signatures["categoryRecordCount(bytes32)"]}:
                result = "0x" + word(len(indexed_ids)).hex()
            elif selector == signatures["indexedRecordIdAt(uint256)"]:
                result = indexed_ids[int(data[10:], 16)]
            elif selector == signatures["categoryRecordAt(bytes32,uint256)"]:
                result = "0x" + (bytes32(indexed_ids[int(data[-64:], 16)]) + word(self.category_generation)).hex()
            elif selector == signatures["isCurrent(bytes32)"]:
                result = "0x" + word(int(self.current and "0x" + data[-64:] not in self.ineligible_ids)).hex()
            elif selector == signatures["recordURI(bytes32)"]:
                raw = self.record_uri.encode()
                result = "0x" + (word(32) + word(len(raw)) + raw + bytes((-len(raw)) % 32)).hex()
            elif selector == signatures["eligibility(bytes32)"]:
                eligible = "0x" + data[-64:] not in self.ineligible_ids
                expiry = self.finalized_timestamp + 3600 if eligible else self.finalized_timestamp - 1
                result = "0x" + (word(int(eligible)) + bytes32("0x" + data[-64:]) + word(expiry) + word(10)).hex()
            if "witness" in url and selector == self.disagree:
                if result is None:
                    result = super().request(url, **kwargs)["result"]
                result = "0x" + f"{int(result[2:], 16) ^ 1:0{len(result) - 2}x}"
        if result is not None:
            return {"jsonrpc": "2.0", "id": payload["id"], "result": result}
        if method == "eth_getCode" and isinstance(params[-1], dict):
            self.assert_hash_selector(params[-1])
            return {"jsonrpc": "2.0", "id": payload["id"],
                "result": self.facets_code if params[0] == self.facets_address else self.registry_code}
        if method == "eth_call":
            self.assert_hash_selector(params[-1])
        return super().request(url, **kwargs)

    def assert_hash_selector(self, selector):
        assert selector == {"blockHash": "0x" + "d" * 64, "requireCanonical": True}


class EnumerableV2Tests(unittest.TestCase):
    def collect(self, rpc, categories=False):
        deployment = onchain_rpc.RegistryDeployment(rpc_url="https://primary.example",
            admission_witness_rpc_url="https://witness.example", registry_version=2,
            from_block=100, deployment_block_hash=rpc.block_hash,
            runtime_code_hash="0x" + onchain_rpc.keccak256(bytes.fromhex(rpc.registry_code[2:])).hex(),
            discovery_facets_address=rpc.facets_address if categories else "",
            discovery_facets_from_block=105)
        with mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_CACHE_DISABLED": "1"}):
            return onchain_rpc.collect_finalized_events(deployment, record_loader=lambda uri, digest: rpc.record_with_facets(["tea"]),
                request_json=rpc.request, record_candidate_limit=2, record_candidate_seed="buyer-seed",
                category_hash_groups=[{rpc.category}] if categories else [])

    def test_exact_finality_rejects_persistently_ahead_witness_before_documents(self):
        rpc = EnumerableV2Rpc()
        original = rpc.request
        loaded = []
        def request(url, **kwargs):
            response = original(url, **kwargs)
            payload = kwargs["payload"]
            if isinstance(payload, dict) and payload["method"] == "eth_getBlockByNumber" and payload["params"][0] == "finalized" and "witness" in url:
                response = {**response, "result": {**response["result"],
                    "number": hex(rpc.finalized_number + 1),
                    "timestamp": hex(rpc.finalized_timestamp + 1), "hash": "0x" + "e" * 64}}
            return response
        rpc.request = request
        with mock.patch.object(rpc, "record_with_facets", side_effect=lambda *_: loaded.append(True)), \
                mock.patch.object(onchain_rpc.time, "sleep"), \
                self.assertRaisesRegex(onchain_rpc.OnchainRpcError, "registry_v2_witness_finality_mismatch"):
            self.collect(rpc)
        self.assertEqual(loaded, [])

    def test_exact_finality_converges_on_retry(self):
        rpc = EnumerableV2Rpc()
        original = rpc.request
        witness_heads = []
        def request(url, **kwargs):
            response = original(url, **kwargs)
            payload = kwargs["payload"]
            if isinstance(payload, dict) and payload["method"] == "eth_getBlockByNumber" and payload["params"][0] == "finalized" and "witness" in url:
                witness_heads.append(True)
                if len(witness_heads) == 1:
                    response = {**response, "result": {**response["result"],
                        "number": hex(rpc.finalized_number + 1), "hash": "0x" + "e" * 64}}
            return response
        rpc.request = request
        with mock.patch.object(onchain_rpc.time, "sleep") as backoff:
            document = self.collect(rpc)
        self.assertEqual(document["resolved_record_count"], 1)
        self.assertEqual(len(witness_heads), 2)
        self.assertGreaterEqual(backoff.call_args.args[0], .2)

    def test_bounded_lag_uses_lower_boundary_and_labels_weaker_agreement(self):
        rpc = EnumerableV2Rpc()
        original = rpc.request
        def request(url, **kwargs):
            response = original(url, **kwargs)
            payload = kwargs["payload"]
            if isinstance(payload, dict) and payload["method"] == "eth_getBlockByNumber" and payload["params"][0] == "finalized" and "witness" in url:
                response = {**response, "result": {**response["result"],
                    "number": hex(rpc.finalized_number + 1),
                    "timestamp": hex(rpc.finalized_timestamp + 6), "hash": "0x" + "e" * 64}}
            return response
        rpc.request = request
        with mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_WITNESS_FINALITY_POLICY": "bounded_lag",
                "SHOPBRIDGE_ONCHAIN_WITNESS_MAX_HEAD_SKEW_SECONDS": "12"}):
            document = self.collect(rpc)
        self.assertEqual(document["finality"]["block_number"], rpc.finalized_number)
        self.assertEqual(document["admission_verification"]["finality_agreement"], "bounded_lag_noncanonical")

    def test_bounded_lag_rejects_large_skew_before_documents(self):
        rpc = EnumerableV2Rpc()
        original = rpc.request
        def request(url, **kwargs):
            response = original(url, **kwargs)
            payload = kwargs["payload"]
            if isinstance(payload, dict) and payload["method"] == "eth_getBlockByNumber" and payload["params"][0] == "finalized" and "witness" in url:
                response = {**response, "result": {**response["result"],
                    "number": hex(rpc.finalized_number + 20),
                    "timestamp": hex(rpc.finalized_timestamp + 240), "hash": "0x" + "e" * 64}}
            return response
        rpc.request = request
        with mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_WITNESS_FINALITY_POLICY": "bounded_lag",
                "SHOPBRIDGE_ONCHAIN_WITNESS_MAX_HEAD_SKEW_SECONDS": "12"}), \
                mock.patch.object(rpc, "record_with_facets", side_effect=AssertionError("document loaded")), \
                mock.patch.object(onchain_rpc.time, "sleep"), \
                self.assertRaisesRegex(onchain_rpc.OnchainRpcError, "registry_v2_witness_finality_mismatch"):
            self.collect(rpc)

    def test_nonconsensus_provider_header_fields_do_not_break_discovery(self):
        rpc = EnumerableV2Rpc()
        original = rpc.request
        def request(url, **kwargs):
            response = original(url, **kwargs)
            payload = kwargs["payload"]
            if isinstance(payload, dict) and payload["method"] == "eth_getBlockByNumber":
                response = {**response, "result": {**response["result"],
                    "totalDifficulty": "0x1" if "witness" in url else "0x2",
                    "providerExtra": url}}
            return response
        rpc.request = request
        self.assertEqual(self.collect(rpc)["resolved_record_count"], 1)

    def test_cleared_facets_preserve_neutral_fallback_with_and_without_query(self):
        for categories in (False, True):
            with self.subTest(categories=categories):
                rpc = EnumerableV2Rpc()
                original = rpc.request
                facet_selector = "0x" + onchain_rpc.keccak256(b"facetState(bytes32)").hex()[:8]
                category_selector = "0x" + onchain_rpc.keccak256(b"categoryRecordCount(bytes32)").hex()[:8]
                def request(url, **kwargs):
                    payload = kwargs["payload"]
                    if isinstance(payload, list):
                        return [request(url, **{**kwargs, "payload": item}) for item in payload]
                    if payload["method"] == "eth_call":
                        selector = payload["params"][0]["data"][:10]
                        if selector == facet_selector:
                            return {"jsonrpc": "2.0", "id": payload["id"], "result":
                                "0x" + (bytes32(rpc.record_hash) + word(0) + word(2) + word(0)).hex()}
                        if selector == category_selector:
                            return {"jsonrpc": "2.0", "id": payload["id"], "result": "0x" + word(0).hex()}
                    return original(url, **kwargs)
                rpc.request = request
                document = self.collect(rpc, categories=True) if categories else self.collect_with_facets_without_query(rpc)
                self.assertEqual(document["resolved_record_count"], 1)

    def collect_with_facets_without_query(self, rpc):
        deployment = onchain_rpc.RegistryDeployment(rpc_url="https://primary.example",
            admission_witness_rpc_url="https://witness.example", registry_version=2,
            from_block=100, deployment_block_hash=rpc.block_hash,
            runtime_code_hash="0x" + onchain_rpc.keccak256(bytes.fromhex(rpc.registry_code[2:])).hex(),
            discovery_facets_address=rpc.facets_address, discovery_facets_from_block=105)
        return onchain_rpc.collect_finalized_events(deployment, record_loader=lambda *_: rpc.record_with_facets(["tea"]),
            request_json=rpc.request, record_candidate_limit=2, record_candidate_seed="buyer-seed")

    def test_storage_discovery_and_projection_without_history(self):
        rpc = EnumerableV2Rpc()
        document = self.collect(rpc)
        self.assertEqual(document["resolved_record_count"], 1)
        self.assertTrue(document["admissions"][rpc.record_id]["eligible"])
        index = onchain_projection.index_contract_document(document,
            record_hash=lambda record: rpc.record_hash[2:], require_finality=True,
            expected_implementation=onchain_projection.DIRECT_RPC_IMPLEMENTATION)
        self.assertTrue(index["complete"], index["verification"])
        self.assertEqual(index["records"][0]["merchant_id"], rpc.record()["merchant_id"])
        self.assertFalse(any(method == "eth_getLogs" for _, method, _ in rpc.requests))

    def test_expired_dominated_draws_need_pruning_and_recover_at_any_chain_age(self):
        counts = []
        for height in (120, 1000000000):
            rpc = EnumerableV2Rpc()
            rpc.finalized_number = height
            for index in range(100):
                record_id = "0x" + f"{index + 1:064x}"
                rpc.states[record_id] = {**rpc.states[rpc.record_id],
                    "domain_hash": onchain_rpc.domain_hash(f"expired-{index}.example")}
                rpc.ineligible_ids.add(record_id)
            # This replayable draw never reaches the sole valid index (zero).
            draws = onchain_rpc._sample_storage_indices(101, 6, "buyer-seed\0active")
            self.assertNotIn(0, draws)
            with mock.patch.object(rpc, "record_with_facets",
                    side_effect=AssertionError("expired draw fetched a merchant document")):
                exhausted = self.collect(rpc)
            self.assertEqual(exhausted["resolved_record_count"], 0)
            self.assertEqual(exhausted["record_selection"]["selected_record_ids"], [])
            self.assertTrue(all(not item["eligible"] for item in exhausted["admissions"].values()))
            index = onchain_projection.index_contract_document(exhausted,
                record_hash=lambda record: rpc.record_hash[2:], require_finality=True,
                expected_implementation=onchain_projection.DIRECT_RPC_IMPLEMENTATION)
            self.assertTrue(index["complete"], index["verification"])
            self.assertEqual(index["records"], [])
            unpruned_requests = len(rpc.requests)
            # Model permissionless keeper pruning: lifecycle records remain,
            # but expired ids no longer occupy the enumerable set.
            rpc.pruned_ids.update(rpc.ineligible_ids)
            rpc.requests.clear()
            restored = self.collect(rpc)
            self.assertEqual(restored["record_selection"]["selected_record_ids"], [rpc.record_id])
            self.assertEqual(restored["resolved_record_count"], 1)
            self.assertEqual(restored["record_selection"]["active_candidate_count"], 1)
            self.assertFalse(any(method == "eth_getLogs" for _, method, _ in rpc.requests))
            counts.append((unpruned_requests, len(rpc.requests)))
        self.assertEqual(counts[0], counts[1])

    def test_ineligible_initial_draw_backfills_from_same_bounded_reserve(self):
        rpc = EnumerableV2Rpc()
        # Put the valid merchant after an expired initial draw in the seeded
        # index order. A target of one still samples only three reserve indices.
        expired_id = "0x" + "2" * 64
        rpc.states[expired_id] = {**rpc.states[rpc.record_id],
            "domain_hash": onchain_rpc.domain_hash("expired.example")}
        rpc.ineligible_ids.add(expired_id)
        seed = "buyer-seed"
        self.assertEqual(onchain_rpc._sample_storage_indices(2, 3, seed + "\0active"), [1, 0])
        deployment = onchain_rpc.RegistryDeployment(rpc_url="https://primary.example",
            admission_witness_rpc_url="https://witness.example", registry_version=2,
            from_block=100, deployment_block_hash=rpc.block_hash,
            runtime_code_hash="0x" + onchain_rpc.keccak256(bytes.fromhex(rpc.registry_code[2:])).hex())
        loaded = []
        budget = onchain_rpc.safe_http.DiscoveryBudget()
        def transport(url, **kwargs):
            _, allocation = budget.reserve(30, 100000)
            try:
                return rpc.request(url, **kwargs)
            finally:
                budget.finish(allocation, 1000)
        def loader(uri, digest):
            _, allocation = budget.reserve(5, 10000)
            budget.finish(allocation, 1000)
            loaded.append(digest)
            return rpc.record()
        token = onchain_rpc.safe_http.discovery_budget.set(budget)
        try:
            document = onchain_rpc.collect_finalized_events(deployment, request_json=transport,
                record_loader=loader, record_candidate_limit=1, record_candidate_seed=seed)
        finally:
            onchain_rpc.safe_http.discovery_budget.reset(token)
        self.assertFalse(document["admissions"][expired_id]["eligible"])
        self.assertEqual(document["record_selection"]["selected_record_ids"], [rpc.record_id])
        self.assertEqual(document["resolved_record_count"], 1)
        self.assertEqual(loaded, [rpc.record_hash])
        self.assertLessEqual(budget.general_requests_used, 256)

    def test_deterministic_unique_and_uniform_index_sample(self):
        sample = onchain_rpc._sample_storage_indices
        self.assertEqual(sample(1000000000000, 12, "buyer"), sample(1000000000000, 12, "buyer"))
        self.assertEqual(len(set(sample(7, 20, "buyer"))), 7)
        counts = [0] * 7
        for seed in range(7000):
            counts[sample(7, 1, str(seed))[0]] += 1
        self.assertTrue(all(850 < count < 1150 for count in counts), counts)

    def test_witness_disagreement_fails_before_document_loading(self):
        for signature in ("indexedRecordCount()", "indexedRecordIdAt(uint256)", "record(bytes32)",
                "recordURI(bytes32)", "eligibility(bytes32)", "categoryRecordCount(bytes32)",
                "categoryRecordAt(bytes32,uint256)", "facetState(bytes32)", "isCurrent(bytes32)",
                "recordIdForDomain(bytes32)", "revokedRecordHashes(bytes32)"):
            rpc = EnumerableV2Rpc()
            rpc.disagree = "0x" + onchain_rpc.keccak256(signature.encode()).hex()[:8]
            with self.subTest(signature=signature), self.assertRaises(onchain_rpc.OnchainRpcError) as raised:
                self.collect(rpc, categories=True)
            self.assertEqual(raised.exception.code, "registry_v2_witness_storage_mismatch")


    def test_batched_storage_rejects_duplicate_response_ids(self):
        rpc = EnumerableV2Rpc()
        def request(url, **kwargs):
            result = rpc.request(url, **kwargs)
            if isinstance(result, list) and len(result) > 1:
                result[1] = {**result[1], "id": result[0]["id"]}
            return result
        deployment = onchain_rpc.RegistryDeployment(rpc_url="https://primary.example",
            admission_witness_rpc_url="https://witness.example", registry_version=2,
            from_block=100, deployment_block_hash=rpc.block_hash,
            runtime_code_hash="0x" + onchain_rpc.keccak256(bytes.fromhex(rpc.registry_code[2:])).hex())
        with self.assertRaisesRegex(onchain_rpc.OnchainRpcError, "rpc_batch_response_invalid"):
            onchain_rpc.collect_finalized_events(deployment, request_json=request,
                record_loader=lambda *_: self.fail("invalid batch reached document loading"))


    def test_batch_413_splits_with_provider_limit_eight_and_counts_attempts(self):
        attempts = []
        budget = onchain_rpc.safe_http.DiscoveryBudget()
        reject_next_eight = True

        def request(_url, **kwargs):
            nonlocal reject_next_eight
            _, allocation = budget.reserve(30, 10000)
            budget.finish(allocation, 100)
            payload = kwargs["payload"]
            size = len(payload) if isinstance(payload, list) else 1
            attempts.append(size)
            # The provider rejects every batch >8. Even a supported-size batch
            # can exceed its byte limit, exercising the actual 413 split path.
            if size > 8 or (size == 8 and reject_next_eight):
                reject_next_eight = False
                raise onchain_rpc.safe_http.SafeHttpError("upstream_http_error",
                    status=413, detail="request too large")
            rows = payload if isinstance(payload, list) else [payload]
            responses = [{"jsonrpc": "2.0", "id": row["id"], "result": row["params"][0]} for row in rows]
            return list(reversed(responses)) if isinstance(payload, list) else responses[0]

        client = onchain_rpc.JsonRpcClient("https://primary.example", request_json=request)
        calls = [("eth_call", [index]) for index in range(24)]
        with mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_RPC_BATCH_SIZE": "8"}):
            self.assertEqual(client.call_batch(calls), list(range(24)))
        self.assertEqual(attempts, [8, 4, 4, 8, 8])
        self.assertEqual(budget.general_requests_used, 5)
        attempts.clear()
        # Also prove the splitter rejects >8 rather than accepting 12/16.
        self.assertEqual(client._call_batch_chunk(calls[:16]), list(range(16)))
        self.assertEqual(attempts, [16, 8, 8])

    def test_batch_429_honors_cooldown_and_splits_to_single_requests(self):
        attempts = []
        def request(_url, **kwargs):
            payload = kwargs["payload"]
            size = len(payload) if isinstance(payload, list) else 1
            attempts.append(size)
            if isinstance(payload, list):
                raise onchain_rpc.safe_http.SafeHttpError("upstream_http_error",
                    status=429, retry_after=7)
            return {"jsonrpc": "2.0", "id": payload["id"], "result": payload["params"][0]}
        client = onchain_rpc.JsonRpcClient("https://primary.example", request_json=request)
        with mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_RPC_BATCH_SIZE": "4"}), \
                mock.patch.object(onchain_rpc.time, "sleep") as sleep:
            self.assertEqual(client.call_batch([("eth_call", [index]) for index in range(4)]), list(range(4)))
        self.assertEqual(attempts, [4, 2, 1, 1, 2, 1, 1])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [7, 7, 7])

    def test_batch_size_can_only_be_configured_downward(self):
        calls = []
        def request(_url, **kwargs):
            row = kwargs["payload"]
            self.assertIsInstance(row, dict)
            calls.append(row)
            return {"jsonrpc": "2.0", "id": row["id"], "result": "0x1"}
        client = onchain_rpc.JsonRpcClient("https://primary.example", request_json=request)
        with mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_RPC_BATCH_SIZE": "1"}):
            self.assertEqual(client.call_batch([("eth_call", []), ("eth_call", [])]), ["0x1", "0x1"])
        self.assertEqual(len(calls), 2)
        for invalid in ("0", "9", "bogus"):
            with mock.patch.dict(os.environ, {"SHOPBRIDGE_ONCHAIN_RPC_BATCH_SIZE": invalid}), \
                    self.assertRaisesRegex(onchain_rpc.OnchainRpcError, "rpc_batch_size_invalid"):
                client.call_batch([("eth_call", [])])

    def test_exact_domain_lookup_bypasses_random_index_sampling(self):
        rpc = EnumerableV2Rpc()
        deployment = onchain_rpc.RegistryDeployment(rpc_url="https://primary.example",
            admission_witness_rpc_url="https://witness.example", registry_version=2,
            from_block=100, deployment_block_hash=rpc.block_hash,
            runtime_code_hash="0x" + onchain_rpc.keccak256(bytes.fromhex(rpc.registry_code[2:])).hex())
        document = onchain_rpc.collect_finalized_events(deployment, request_json=rpc.request,
            record_loader=lambda *_: rpc.record(), preferred_domain_hashes={rpc.registered_domain_hash},
            record_candidate_limit=1)
        self.assertEqual(document["record_selection"]["selected_record_ids"], [rpc.record_id])
        self.assertEqual(document["resolved_record_count"], 1)
        selector = "0x" + onchain_rpc.keccak256(b"indexedRecordIdAt(uint256)").hex()[:8]
        self.assertFalse(any(method == "eth_call" and params[0]["data"].startswith(selector)
            for _, method, params in rpc.requests))

    def test_stale_category_generation_and_current_binding_use_neutral_fallback(self):
        for generation, current in ((2, True), (1, False)):
            rpc = EnumerableV2Rpc()
            rpc.category_generation, rpc.current = generation, current
            document = self.collect(rpc, categories=True)
            self.assertEqual(document["record_selection"]["hinted_record_count"], 0)
            self.assertEqual(document["resolved_record_count"], 1)

    def test_request_count_is_independent_of_chain_age(self):
        counts = []
        for height in (120, 1000000000):
            rpc = EnumerableV2Rpc()
            rpc.finalized_number = height
            self.collect(rpc)
            counts.append(len(rpc.requests))
        self.assertEqual(counts[0], counts[1])
        self.assertLess(counts[0], 50)

    def test_default_target_and_reserve_fit_shared_transport_budget(self):
        rpc = EnumerableV2Rpc()
        documents = {}
        for index in range(1, 101):
            record_id = "0x" + f"{index:064x}"
            digest = "0x" + f"{index + 100:064x}"
            record = rpc.record_with_facets(["tea"])
            record["domain"] = f"shop-{index}.example"
            record["onchain_identity"]["record_id"] = record_id
            record["merchant_id"] = f"merchant-{index}"
            documents[digest] = record
            rpc.states[record_id] = {"controller": rpc.controller, "record_hash": digest,
                "domain_hash": onchain_rpc.domain_hash(record["domain"]), "status": 1}
            rpc.facet_states[record_id] = {**rpc.facet_states[rpc.record_id], "record_hash": digest}
        del rpc.states[rpc.record_id]
        budget = onchain_rpc.safe_http.DiscoveryBudget()
        def transport(url, **kwargs):
            timeout, allocation = budget.reserve(30, 100000)
            try:
                return rpc.request(url, **kwargs)
            finally:
                budget.finish(allocation, 1000)
        def loader(uri, digest):
            timeout, allocation = budget.reserve(5, 10000)
            budget.finish(allocation, 1000)
            return documents[digest]
        deployment = onchain_rpc.RegistryDeployment(rpc_url="https://primary.example",
            admission_witness_rpc_url="https://witness.example", registry_version=2,
            from_block=100, deployment_block_hash=rpc.block_hash,
            runtime_code_hash="0x" + onchain_rpc.keccak256(bytes.fromhex(rpc.registry_code[2:])).hex(),
            discovery_facets_address=rpc.facets_address, discovery_facets_from_block=105)
        token = onchain_rpc.safe_http.discovery_budget.set(budget)
        try:
            document = onchain_rpc.collect_finalized_events(deployment, record_loader=loader,
                request_json=transport, record_candidate_limit=12, record_candidate_seed="buyer",
                category_hash_groups=[{rpc.category}])
        finally:
            onchain_rpc.safe_http.discovery_budget.reset(token)
        self.assertEqual(document["resolved_record_count"], 12)


if __name__ == "__main__":
    unittest.main()
