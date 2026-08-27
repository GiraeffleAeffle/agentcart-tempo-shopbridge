from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import json
import sys
import unittest
from pathlib import Path


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
        self.logs = [self.registered_log()]
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
        elif method == "eth_getBlockByNumber" and params[0] in {"finalized", hex(120)}:
            self.block_calls.append(params[0])
            result = {
                "number": hex(120),
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
            selector = params[1]
            result = (
                "0x"
                if selector not in {"latest", "finalized"} and int(selector, 16) < 100
                else "0x60016000"
            )
        elif method == "eth_getLogs":
            query = params[0]
            self.log_calls.append(query)
            start = int(query["fromBlock"], 16)
            end = int(query["toBlock"], 16)
            if query.get("topics", [None])[0] == onchain_rpc.OWNERSHIP_TRANSFERRED_TOPIC:
                result = [self.ownership_transferred_log()] if start <= 100 <= end else []
            else:
                result = [
                    log
                    for log in self.logs
                    if start <= int(log["blockNumber"], 16) <= end
                ]
        elif method == "eth_call":
            data = params[0]["data"]
            if data.startswith(onchain_rpc.RECORD_SELECTOR):
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
        self.assertEqual(document["contract_storage_verification"]["checked_record_count"], 2)
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


if __name__ == "__main__":
    unittest.main()
