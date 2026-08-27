"""Direct, dependency-free JSON-RPC discovery for ShopBridge registries.

The smart contract is the authority for candidate membership and lifecycle
commitments. This client reads the finalized lifecycle logs, selects a bounded
active candidate set, fetches the selected current record documents, and checks
the projected state against contract storage at the verified boundary. Full
buyer eligibility is decided later by offchain trust verification.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import pathlib
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable


DIRECT_RPC_IMPLEMENTATION = "agentcart.onchain_registry_direct_rpc.v1"
CONTRACT_EVENTS_SCHEMA = "agentcart.onchain_registry_contract_events.v1"
DEFAULT_RPC_URL = "https://rpc.moderato.tempo.xyz"
DEFAULT_CHAIN_ID = 42431
DEFAULT_REGISTRY_ADDRESS = "0x0965961617c5B0898167AA4034C5511dB0EfcA07"
DEFAULT_FROM_BLOCK = 30_731_101
DEFAULT_LOG_CHUNK_SIZE = 100_000
MAX_LOG_CHUNK_SIZE = 100_000
DEFAULT_MAX_FINALITY_AGE_SECONDS_BY_CHAIN = {
    1: 1800,
    100: 600,
    42431: 600,
}
DEFAULT_UNKNOWN_CHAIN_MAX_FINALITY_AGE_SECONDS = 1800
MAX_FINALITY_FUTURE_SKEW_SECONDS = 300
MAX_RECORD_URI_BYTES = 4096
MAX_RECORD_FETCH_WORKERS = 8
MAX_RECORD_CANDIDATES = 50
MYOTIS_READY_TIMEOUT_SECONDS = 30.0
MYOTIS_READY_POLL_INTERVAL_SECONDS = 0.5
RPC_PROFILE_AUTO = "auto"
RPC_PROFILE_STANDARD = "standard"
RPC_PROFILE_MYOTIS = "myotis"
RPC_PROFILES = {RPC_PROFILE_AUTO, RPC_PROFILE_STANDARD, RPC_PROFILE_MYOTIS}

RECORD_SELECTOR = "0xb5c645bd"
RECORD_ID_FOR_DOMAIN_SELECTOR = "0x15daecde"
REVOKED_RECORD_HASHES_SELECTOR = "0xf30566db"
DISCOVERY_FACETS_REGISTRY_SELECTOR = "0x7b103999"
DISCOVERY_FACET_STATE_SELECTOR = "0x8e5f8614"
DISCOVERY_CATEGORY_DECLARED_TOPIC = "0x4551117e5d0504f18451c9c628ff65603a21ae2bea44f44b8487f56317ab579c"
OWNERSHIP_TRANSFERRED_TOPIC = "0x8be0079c531659141344cd1fd0a4f28419497f9722a3daafe3b4186f6b6457e0"
ZERO_ADDRESS_TOPIC = "0x" + "0" * 64


def _load_safe_http_module():
    existing = sys.modules.get("shopbridge_safe_http")
    if existing is not None:
        return existing
    path = pathlib.Path(__file__).resolve().with_name("shopbridge_safe_http.py")
    spec = importlib.util.spec_from_file_location("shopbridge_safe_http", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("portable ShopBridge safe HTTP module is missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


safe_http = _load_safe_http_module()


def _load_registry_trust_module():
    existing = sys.modules.get("shopbridge_registry_trust")
    if existing is not None:
        return existing
    path = pathlib.Path(__file__).resolve().with_name("shopbridge_registry_trust.py")
    spec = importlib.util.spec_from_file_location("shopbridge_registry_trust", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("portable ShopBridge registry trust module is missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


registry_trust = _load_registry_trust_module()


def _load_discovery_facets_module():
    existing = sys.modules.get("shopbridge_discovery_facets")
    if existing is not None:
        return existing
    path = pathlib.Path(__file__).resolve().with_name("shopbridge_discovery_facets.py")
    spec = importlib.util.spec_from_file_location("shopbridge_discovery_facets", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("portable ShopBridge discovery facets module is missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


discovery_facets = _load_discovery_facets_module()


class OnchainRpcError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class RegistryDeployment:
    rpc_url: str = DEFAULT_RPC_URL
    chain_id: int = DEFAULT_CHAIN_ID
    registry_address: str = DEFAULT_REGISTRY_ADDRESS
    from_block: int = DEFAULT_FROM_BLOCK
    log_chunk_size: int = DEFAULT_LOG_CHUNK_SIZE
    allow_private_rpc: bool = False
    rpc_profile: str = RPC_PROFILE_AUTO
    max_finality_age_seconds: int | None = None
    deployment_block_hash: str = ""
    discovery_facets_address: str = ""
    discovery_facets_from_block: int = 0
    discovery_facets_deployment_block_hash: str = ""
    discovery_facets_runtime_code_hash: str = ""


@dataclass(frozen=True)
class EventSpec:
    name: str
    indexed: tuple[tuple[str, str], ...]
    data: tuple[tuple[str, str], ...]


EVENT_SPECS = {
    "0x2eab427fde5740c204479da28a832063e14c3ac979e6fdf1d6c10cf9ba919b42": EventSpec(
        "MerchantRegistered",
        (("recordId", "bytes32"), ("controller", "address"), ("domainHash", "bytes32")),
        (("recordHash", "bytes32"), ("recordURI", "string")),
    ),
    "0x9abf1ff335c57e4da7bbb7f423725536cdc09a1dc366384e401857baf45fc95d": EventSpec(
        "MerchantUpdated",
        (("recordId", "bytes32"),),
        (("recordHash", "bytes32"), ("recordURI", "string")),
    ),
    "0x1eee1cbfa38aff18495c0a48c88aa825c42a74f26ea0cb84cfa8c5d9b290d803": EventSpec(
        "ControllerChanged",
        (("recordId", "bytes32"), ("newController", "address")),
        (("newRecordHash", "bytes32"), ("recordURI", "string")),
    ),
    "0x531b0591d0132124378f50b572ea6deb89438376b9ea5f7e866b68d4e780761c": EventSpec(
        "MerchantRevoked",
        (("recordId", "bytes32"),),
        (("reasonHash", "bytes32"),),
    ),
    "0x15e296d470996646eef7fe498c8cd6f3fde3c9f222c7366234c5d2edb858c1dd": EventSpec(
        "MerchantSuspended",
        (("recordId", "bytes32"),),
        (("reasonHash", "bytes32"),),
    ),
    "0xa15b03db75acdfb528115be15c2092823f0086f8ffd885c1cd0b1c62af5c27d2": EventSpec(
        "MerchantUnsuspended",
        (("recordId", "bytes32"),),
        (),
    ),
}


_MASK64 = (1 << 64) - 1
_KECCAK_ROUND_CONSTANTS = (
    0x0000000000000001,
    0x0000000000008082,
    0x800000000000808A,
    0x8000000080008000,
    0x000000000000808B,
    0x0000000080000001,
    0x8000000080008081,
    0x8000000000008009,
    0x000000000000008A,
    0x0000000000000088,
    0x0000000080008009,
    0x000000008000000A,
    0x000000008000808B,
    0x800000000000008B,
    0x8000000000008089,
    0x8000000000008003,
    0x8000000000008002,
    0x8000000000000080,
    0x000000000000800A,
    0x800000008000000A,
    0x8000000080008081,
    0x8000000000008080,
    0x0000000080000001,
    0x8000000080008008,
)
_KECCAK_ROTATIONS = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


def _rotate_left(value: int, shift: int) -> int:
    if not shift:
        return value & _MASK64
    return ((value << shift) | (value >> (64 - shift))) & _MASK64


def _keccak_f1600(state: list[int]) -> None:
    for round_constant in _KECCAK_ROUND_CONSTANTS:
        columns = [
            state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20]
            for x in range(5)
        ]
        deltas = [columns[(x - 1) % 5] ^ _rotate_left(columns[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] ^= deltas[x]

        moved = [0] * 25
        for x in range(5):
            for y in range(5):
                moved[y + 5 * ((2 * x + 3 * y) % 5)] = _rotate_left(
                    state[x + 5 * y], _KECCAK_ROTATIONS[x][y]
                )
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = (
                    moved[x + 5 * y]
                    ^ ((~moved[(x + 1) % 5 + 5 * y]) & moved[(x + 2) % 5 + 5 * y])
                ) & _MASK64
        state[0] ^= round_constant


def keccak256(value: bytes) -> bytes:
    rate = 136
    padded = bytearray(value)
    padded.append(0x01)
    padded.extend(b"\x00" * ((rate - 1 - len(padded)) % rate))
    padded.append(0x80)
    state = [0] * 25
    for offset in range(0, len(padded), rate):
        block = padded[offset : offset + rate]
        for lane in range(rate // 8):
            start = lane * 8
            state[lane] ^= int.from_bytes(block[start : start + 8], "little")
        _keccak_f1600(state)
    output = bytearray()
    while len(output) < 32:
        for lane in range(rate // 8):
            output.extend(state[lane].to_bytes(8, "little"))
            if len(output) >= 32:
                return bytes(output[:32])
        _keccak_f1600(state)
    return bytes(output[:32])


def domain_hash(domain: str) -> str:
    normalized = registry_trust.normalized_domain(domain)
    if not normalized:
        raise OnchainRpcError("registry_record_domain_missing")
    return "0x" + keccak256(normalized.encode("utf-8")).hex()


def _hex_bytes(value: Any, *, field: str) -> bytes:
    text = str(value or "")
    if not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", text):
        raise OnchainRpcError("rpc_hex_invalid", field)
    return bytes.fromhex(text[2:])


def _hex_int(value: Any, *, field: str) -> int:
    text = str(value or "")
    if not re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)", text):
        raise OnchainRpcError("rpc_quantity_invalid", field)
    return int(text, 16)


def _fixed_hash(value: Any, *, field: str) -> str:
    text = str(value or "").lower()
    if not re.fullmatch(r"0x[0-9a-f]{64}", text):
        raise OnchainRpcError("rpc_hash_invalid", field)
    return text


def _address(value: Any, *, field: str) -> str:
    text = str(value or "")
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", text):
        raise OnchainRpcError("rpc_address_invalid", field)
    return "0x" + text[2:].lower()


def _decode_word(word: bytes, abi_type: str, *, field: str) -> Any:
    if len(word) != 32:
        raise OnchainRpcError("event_word_invalid", field)
    if abi_type == "bytes32":
        return "0x" + word.hex()
    if abi_type == "address":
        if any(word[:12]):
            raise OnchainRpcError("event_address_padding_invalid", field)
        return "0x" + word[12:].hex()
    if abi_type.startswith("uint"):
        return str(int.from_bytes(word, "big"))
    if abi_type == "bool":
        value = int.from_bytes(word, "big")
        if value not in {0, 1}:
            raise OnchainRpcError("event_bool_invalid", field)
        return bool(value)
    raise OnchainRpcError("event_abi_type_unsupported", abi_type)


def _decode_event(log: dict[str, Any]) -> tuple[EventSpec, dict[str, Any]]:
    topics = log.get("topics")
    if not isinstance(topics, list) or not topics:
        raise OnchainRpcError("event_topics_missing")
    topic0 = _fixed_hash(topics[0], field="topics[0]")
    spec = EVENT_SPECS.get(topic0)
    if spec is None:
        raise OnchainRpcError("event_topic_unsupported", topic0)
    if len(topics) != len(spec.indexed) + 1:
        raise OnchainRpcError("event_topic_count_invalid", spec.name)
    args: dict[str, Any] = {}
    for index, (name, abi_type) in enumerate(spec.indexed, start=1):
        args[name] = _decode_word(_hex_bytes(topics[index], field=f"topics[{index}]"), abi_type, field=name)

    data = _hex_bytes(log.get("data"), field="data")
    head_size = 32 * len(spec.data)
    if len(data) < head_size or len(data) % 32:
        raise OnchainRpcError("event_data_length_invalid", spec.name)
    for index, (name, abi_type) in enumerate(spec.data):
        word = data[index * 32 : (index + 1) * 32]
        if abi_type != "string":
            args[name] = _decode_word(word, abi_type, field=name)
            continue
        dynamic_offset = int.from_bytes(word, "big")
        if dynamic_offset < head_size or dynamic_offset % 32 or dynamic_offset + 32 > len(data):
            raise OnchainRpcError("event_string_offset_invalid", name)
        length = int.from_bytes(data[dynamic_offset : dynamic_offset + 32], "big")
        start = dynamic_offset + 32
        end = start + length
        if end > len(data):
            raise OnchainRpcError("event_string_length_invalid", name)
        try:
            args[name] = data[start:end].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise OnchainRpcError("event_string_utf8_invalid", name) from exc
    return spec, args


class JsonRpcClient:
    def __init__(
        self,
        url: str,
        *,
        allow_private: bool = False,
        request_json: Callable[..., Any] | None = None,
    ) -> None:
        self.url = str(url or "").strip()
        self.allow_private = allow_private
        self.request_json = request_json or safe_http.request_json
        self.request_id = 0

    def call(self, method: str, params: list[Any]) -> Any:
        self.request_id += 1
        payload = {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params}
        try:
            response = self.request_json(
                self.url,
                method="POST",
                payload=payload,
                headers={"User-Agent": "AgentCart-ShopBridge-Direct/1"},
                timeout_seconds=30,
                allow_private=self.allow_private,
                max_response_bytes=4 * 1024 * 1024,
            )
        except safe_http.SafeHttpError as exc:
            raise OnchainRpcError("rpc_transport_failed", exc.code) from exc
        if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
            raise OnchainRpcError("rpc_response_invalid", method)
        if response.get("id") != self.request_id:
            raise OnchainRpcError("rpc_response_id_mismatch", method)
        if isinstance(response.get("error"), dict):
            error = response["error"]
            detail = f"{method} ({error.get('code')}): {error.get('message')}"
            raise OnchainRpcError("rpc_call_failed", detail)
        if "result" not in response:
            raise OnchainRpcError("rpc_result_missing", method)
        return response["result"]


def _validate_deployment(deployment: RegistryDeployment) -> tuple[str, int, int, str, int]:
    try:
        parsed = urllib.parse.urlsplit(deployment.rpc_url)
        parsed.hostname
    except ValueError as exc:
        raise OnchainRpcError("rpc_url_invalid") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OnchainRpcError("rpc_url_invalid")
    try:
        parsed.port
    except ValueError as exc:
        raise OnchainRpcError("rpc_url_invalid", "port") from exc
    if not deployment.allow_private_rpc and parsed.scheme != "https":
        raise OnchainRpcError("rpc_url_requires_https")
    registry_address = _address(deployment.registry_address, field="registry_address")
    if deployment.chain_id < 1:
        raise OnchainRpcError("chain_id_invalid")
    if deployment.from_block < 0:
        raise OnchainRpcError("from_block_invalid")
    chunk_size = int(deployment.log_chunk_size)
    if chunk_size < 1 or chunk_size > MAX_LOG_CHUNK_SIZE:
        raise OnchainRpcError("log_chunk_size_invalid", f"must be 1..{MAX_LOG_CHUNK_SIZE}")
    rpc_profile = str(deployment.rpc_profile or RPC_PROFILE_AUTO).strip().lower()
    if rpc_profile not in RPC_PROFILES:
        raise OnchainRpcError("rpc_profile_invalid", ", ".join(sorted(RPC_PROFILES)))
    max_finality_age_seconds = (
        default_max_finality_age_seconds(deployment.chain_id)
        if deployment.max_finality_age_seconds is None
        else int(deployment.max_finality_age_seconds)
    )
    if max_finality_age_seconds < 1:
        raise OnchainRpcError("max_finality_age_seconds_invalid")
    if deployment.deployment_block_hash:
        _fixed_hash(deployment.deployment_block_hash, field="deployment_block_hash")
    return registry_address, deployment.from_block, chunk_size, rpc_profile, max_finality_age_seconds


def default_max_finality_age_seconds(chain_id: int) -> int:
    return DEFAULT_MAX_FINALITY_AGE_SECONDS_BY_CHAIN.get(
        int(chain_id), DEFAULT_UNKNOWN_CHAIN_MAX_FINALITY_AGE_SECONDS
    )


def _utc_now(now: Callable[[], dt.datetime] | None) -> dt.datetime:
    value = (now or (lambda: dt.datetime.now(dt.timezone.utc)))()
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc).replace(microsecond=0)


def _assert_finalized_block_fresh(
    timestamp: int,
    *,
    reference: dt.datetime,
    max_age_seconds: int,
) -> None:
    block_time = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc)
    if block_time > reference + dt.timedelta(seconds=MAX_FINALITY_FUTURE_SKEW_SECONDS):
        raise OnchainRpcError("finalized_block_time_future")
    if block_time < reference - dt.timedelta(seconds=max_age_seconds):
        raise OnchainRpcError("finalized_block_time_stale")


def _has_contract_code(value: Any) -> bool:
    code = str(value or "").lower()
    return bool(re.fullmatch(r"0x[0-9a-f]*", code) and code not in {"0x", "0x0", "0x00"})


def _verify_deployment_boundary(
    client: JsonRpcClient,
    *,
    deployment: RegistryDeployment,
    registry_address: str,
    rpc_profile: str,
) -> dict[str, Any]:
    pinned_hash = str(deployment.deployment_block_hash or "").lower()
    if rpc_profile == RPC_PROFILE_MYOTIS:
        if not pinned_hash:
            raise OnchainRpcError(
                "myotis_deployment_block_hash_required",
                "pin the independently recorded deployment block hash",
            )
        constructor_logs = client.call(
            "eth_getLogs",
            [
                {
                    "address": registry_address,
                    "fromBlock": hex(deployment.from_block),
                    "toBlock": hex(deployment.from_block),
                    "topics": [OWNERSHIP_TRANSFERRED_TOPIC, ZERO_ADDRESS_TOPIC],
                }
            ],
        )
        if not isinstance(constructor_logs, list) or len(constructor_logs) != 1:
            raise OnchainRpcError("myotis_deployment_constructor_log_missing")
        constructor_log = _rpc_log(constructor_logs[0], registry_address)
        if (
            _hex_int(constructor_log.get("blockNumber"), field="deployment_log.blockNumber")
            != deployment.from_block
            or _fixed_hash(constructor_log.get("blockHash"), field="deployment_log.blockHash")
            != pinned_hash
        ):
            raise OnchainRpcError("deployment_block_hash_mismatch")
        constructor_topics = constructor_log.get("topics")
        if (
            not isinstance(constructor_topics, list)
            or len(constructor_topics) != 3
            or _fixed_hash(constructor_topics[0], field="deployment_log.topics[0]")
            != OWNERSHIP_TRANSFERRED_TOPIC
            or _fixed_hash(constructor_topics[1], field="deployment_log.topics[1]")
            != ZERO_ADDRESS_TOPIC
            or _decode_word(
                _hex_bytes(constructor_topics[2], field="deployment_log.topics[2]"),
                "address",
                field="deployment_owner",
            )
            == "0x" + "0" * 40
        ):
            raise OnchainRpcError("myotis_deployment_constructor_log_invalid")
        return {
            "status": "pinned",
            "block_number": deployment.from_block,
            "block_hash": pinned_hash,
            "transaction_hash": _fixed_hash(
                constructor_log.get("transactionHash"), field="deployment_log.transactionHash"
            ),
            "scope": "pinned_descriptor_constructor_log_and_verified_index_coverage",
            "pinned_block_hash": True,
        }
    block = _block_header(
        client,
        hex(deployment.from_block),
        field="deployment_block",
        expected_number=deployment.from_block,
    )
    block_hash = _fixed_hash(block.get("hash"), field="deployment_block.hash")
    if pinned_hash and block_hash != pinned_hash:
        raise OnchainRpcError("deployment_block_hash_mismatch")
    if not _has_contract_code(
        client.call("eth_getCode", [registry_address, hex(deployment.from_block)])
    ):
        raise OnchainRpcError("registry_code_missing_at_deployment_block")
    if deployment.from_block > 0 and _has_contract_code(
        client.call("eth_getCode", [registry_address, hex(deployment.from_block - 1)])
    ):
        raise OnchainRpcError("deployment_block_not_contract_creation_boundary")
    return {
        "status": "matched",
        "block_number": deployment.from_block,
        "block_hash": block_hash,
        "scope": "historical_code_creation_boundary",
        "pinned_block_hash": bool(pinned_hash),
    }


def _json_nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OnchainRpcError("rpc_integer_invalid", field)
    return value


def _detect_rpc_profile(client: JsonRpcClient, requested: str) -> tuple[str, str]:
    try:
        client_version = client.call("web3_clientVersion", [])
    except OnchainRpcError as exc:
        if requested == RPC_PROFILE_MYOTIS:
            raise OnchainRpcError("rpc_profile_mismatch", "Myotis client identity unavailable") from exc
        return RPC_PROFILE_STANDARD, ""
    version = str(client_version or "")
    detected = RPC_PROFILE_MYOTIS if version.lower().startswith("myotis/") else RPC_PROFILE_STANDARD
    if requested == RPC_PROFILE_MYOTIS and detected != RPC_PROFILE_MYOTIS:
        raise OnchainRpcError("rpc_profile_mismatch", f"expected Myotis, got {version or 'unknown'}")
    if requested == RPC_PROFILE_STANDARD and detected == RPC_PROFILE_MYOTIS:
        raise OnchainRpcError(
            "rpc_profile_mismatch",
            "Myotis must use the myotis profile because its finalized/state semantics differ",
        )
    return (detected if requested == RPC_PROFILE_AUTO else requested), version


def _block_header(
    client: JsonRpcClient,
    selector: str,
    *,
    field: str,
    expected_number: int | None = None,
) -> dict[str, Any]:
    block = client.call("eth_getBlockByNumber", [selector, False])
    if not isinstance(block, dict):
        raise OnchainRpcError("rpc_block_invalid", field)
    number = _hex_int(block.get("number"), field=f"{field}.number")
    if expected_number is not None and number != expected_number:
        raise OnchainRpcError(
            "rpc_block_number_mismatch",
            f"{field}: expected {expected_number}, got {number}",
        )
    _fixed_hash(block.get("hash"), field=f"{field}.hash")
    _hex_int(block.get("timestamp"), field=f"{field}.timestamp")
    return block


def _myotis_finalized_header(
    client: JsonRpcClient,
    *,
    monotonic: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    timeout_seconds: float = MYOTIS_READY_TIMEOUT_SECONDS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    clock = monotonic or time.monotonic
    sleeper = sleep or time.sleep
    deadline = clock() + max(0.0, float(timeout_seconds))

    def wait_or_timeout(code: str) -> None:
        remaining = deadline - clock()
        if remaining <= 0:
            raise OnchainRpcError(code)
        sleeper(min(MYOTIS_READY_POLL_INTERVAL_SECONDS, remaining))

    status = client.call("myotis_status", [])
    if not isinstance(status, dict) or status.get("ok") is not True:
        raise OnchainRpcError("myotis_status_invalid")
    woke = False
    if str(status.get("state") or "") == "PAUSED":
        wake = client.call("myotis_wakeup", [])
        if (
            not isinstance(wake, dict)
            or wake.get("ok") is not True
            or str(wake.get("lifecycle") or "") != "RUNNING"
        ):
            raise OnchainRpcError("myotis_wakeup_failed")
        woke = True
        status = client.call("myotis_status", [])

    snap_peers = 0
    while True:
        if not isinstance(status, dict) or status.get("ok") is not True:
            raise OnchainRpcError("myotis_status_invalid")
        state = str(status.get("state") or "")
        if state == "RUNNING":
            snap_peers = _json_nonnegative_int(
                status.get("snapPeers"), field="myotis_status.snapPeers"
            )
            if snap_peers >= 1:
                break
        elif state == "STOPPED":
            raise OnchainRpcError("myotis_not_running", state)
        wait_or_timeout("myotis_wakeup_timeout" if woke else "myotis_snap_peer_unavailable")
        status = client.call("myotis_status", [])

    beacon: Any = None
    while True:
        beacon = client.call("myotis_beaconStatus", [])
        if not isinstance(beacon, dict) or beacon.get("ok") is not True:
            raise OnchainRpcError("myotis_beacon_status_invalid")
        if str(beacon.get("state") or "") == "SYNCED":
            finalized_number = _json_nonnegative_int(
                beacon.get("executionBlockNumber"),
                field="myotis_beaconStatus.executionBlockNumber",
            )
            if finalized_number >= 1:
                break
        state = str(beacon.get("state") or "unknown")
        wait_or_timeout(
            "myotis_beacon_not_synced"
            if state != "SYNCED"
            else "myotis_finalized_block_unavailable"
        )
    block = _block_header(
        client,
        hex(finalized_number),
        field="finalized",
        expected_number=finalized_number,
    )
    return block, {
        "finality_source": "myotis_beaconStatus.executionBlockNumber",
        "beacon_state": "SYNCED",
        "snap_peers": snap_peers,
    }


def _assert_record_identity(record: dict[str, Any], expected: dict[str, str]) -> None:
    identity = registry_trust.onchain_identity_payload(record)
    checks = {
        "chain_id": str(identity.get("chain_id") or ""),
        "registry_address": str(identity.get("registry_address") or "").lower(),
        "record_id": str(identity.get("record_id") or "").lower(),
        "controller": str(identity.get("controller") or "").lower(),
    }
    for field, supplied in checks.items():
        if supplied != expected[field].lower():
            raise OnchainRpcError(f"registry_record_{field}_mismatch")
    if domain_hash(str(record.get("domain") or "")) != expected["domain_hash"].lower():
        raise OnchainRpcError("registry_record_domain_hash_mismatch")


def _rpc_log(log: Any, registry_address: str) -> dict[str, Any]:
    if not isinstance(log, dict):
        raise OnchainRpcError("rpc_log_invalid")
    if _address(log.get("address"), field="log.address") != registry_address:
        raise OnchainRpcError("rpc_log_address_mismatch")
    if log.get("removed") is True:
        raise OnchainRpcError("finalized_log_marked_removed")
    return log


def _collect_logs(
    client: JsonRpcClient,
    *,
    registry_address: str,
    from_block: int,
    to_block: int,
    chunk_size: int,
) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    topics = [list(EVENT_SPECS)]
    start = from_block
    while start <= to_block:
        end = min(to_block, start + chunk_size - 1)
        result = client.call(
            "eth_getLogs",
            [
                {
                    "address": registry_address,
                    "fromBlock": hex(start),
                    "toBlock": hex(end),
                    "topics": topics,
                }
            ],
        )
        if not isinstance(result, list):
            raise OnchainRpcError("rpc_logs_result_invalid")
        logs.extend(_rpc_log(log, registry_address) for log in result)
        start = end + 1
    logs.sort(key=lambda value: (_hex_int(value.get("blockNumber"), field="blockNumber"), _hex_int(value.get("logIndex"), field="logIndex")))
    seen: set[tuple[str, int]] = set()
    for log in logs:
        key = (
            _fixed_hash(log.get("transactionHash"), field="transactionHash"),
            _hex_int(log.get("logIndex"), field="logIndex"),
        )
        if key in seen:
            raise OnchainRpcError("rpc_log_duplicate")
        seen.add(key)
    return logs


def _decode_address_call(value: Any, *, field: str) -> str:
    data = _hex_bytes(value, field=field)
    if len(data) != 32 or any(data[:12]):
        raise OnchainRpcError("contract_address_call_result_invalid", field)
    return "0x" + data[12:].hex()


def _decode_facet_state_call(value: Any) -> dict[str, Any]:
    data = _hex_bytes(value, field="discovery_facet_state_call")
    if len(data) != 4 * 32:
        raise OnchainRpcError("discovery_facet_state_call_result_invalid")
    words = [data[index : index + 32] for index in range(0, len(data), 32)]
    generation = int.from_bytes(words[2], "big")
    category_count = int.from_bytes(words[3], "big")
    if generation >= 2**64 or category_count > discovery_facets.MAX_CATEGORIES:
        raise OnchainRpcError("discovery_facet_state_call_result_invalid")
    return {
        "record_hash": "0x" + words[0].hex(),
        "category_set_hash": "0x" + words[1].hex(),
        "generation": generation,
        "category_count": category_count,
    }


def _collect_category_declarations(
    client: JsonRpcClient,
    *,
    facets_address: str,
    from_block: int,
    to_block: int,
    chunk_size: int,
    category_hashes: set[str],
) -> list[dict[str, Any]]:
    requested = {_fixed_hash(value, field="category_hash") for value in category_hashes}
    if not requested:
        return []
    logs: list[dict[str, Any]] = []
    start = from_block
    while start <= to_block:
        end = min(to_block, start + chunk_size - 1)
        result = client.call(
            "eth_getLogs",
            [
                {
                    "address": facets_address,
                    "fromBlock": hex(start),
                    "toBlock": hex(end),
                    "topics": [DISCOVERY_CATEGORY_DECLARED_TOPIC, sorted(requested)],
                }
            ],
        )
        if not isinstance(result, list):
            raise OnchainRpcError("discovery_category_logs_result_invalid")
        logs.extend(_rpc_log(log, facets_address) for log in result)
        start = end + 1
    logs.sort(
        key=lambda value: (
            _hex_int(value.get("blockNumber"), field="blockNumber"),
            _hex_int(value.get("logIndex"), field="logIndex"),
        )
    )
    declarations: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for log in logs:
        block_number = _hex_int(log.get("blockNumber"), field="blockNumber")
        if block_number < from_block or block_number > to_block:
            raise OnchainRpcError("discovery_category_event_block_out_of_range")
        topics = log.get("topics")
        if not isinstance(topics, list) or len(topics) != 4:
            raise OnchainRpcError("discovery_category_event_topics_invalid")
        topic0 = _fixed_hash(topics[0], field="topics[0]")
        category_hash = _fixed_hash(topics[1], field="categoryHash")
        record_id = _fixed_hash(topics[2], field="recordId")
        generation_data = _hex_bytes(topics[3], field="generation")
        if (
            topic0 != DISCOVERY_CATEGORY_DECLARED_TOPIC
            or category_hash not in requested
            or len(generation_data) != 32
            or len(_hex_bytes(log.get("data"), field="data")) != 0
        ):
            raise OnchainRpcError("discovery_category_event_invalid")
        generation = int.from_bytes(generation_data, "big")
        if generation < 1 or generation >= 2**64:
            raise OnchainRpcError("discovery_category_event_generation_invalid")
        key = (
            _fixed_hash(log.get("transactionHash"), field="transactionHash"),
            _hex_int(log.get("logIndex"), field="logIndex"),
        )
        if key in seen:
            raise OnchainRpcError("discovery_category_log_duplicate")
        seen.add(key)
        declarations.append(
            {
                "category_hash": category_hash,
                "record_id": record_id,
                "generation": generation,
            }
        )
    return declarations


def _onchain_category_hints(
    client: JsonRpcClient,
    *,
    deployment: RegistryDeployment,
    registry_address: str,
    block_selector: str,
    finalized_number: int,
    chunk_size: int,
    rpc_profile: str,
    lifecycle: dict[str, dict[str, Any]],
    category_hash_groups: list[set[str]],
) -> tuple[set[str], dict[str, dict[str, Any]], dict[str, Any]]:
    diagnostics: dict[str, Any] = {
        "schema": "agentcart.onchain_category_routing.v1",
        "authority": "smart_contract_routing_hint",
        "configured": bool(deployment.discovery_facets_address),
        "used": False,
        "query_group_count": len(category_hash_groups),
        "matched_record_count": 0,
        "fallback_required": True,
    }
    if not deployment.discovery_facets_address or not category_hash_groups:
        return set(), {}, diagnostics
    facets_address = _address(
        deployment.discovery_facets_address,
        field="discovery_facets_address",
    )
    from_block = int(deployment.discovery_facets_from_block or deployment.from_block)
    if from_block < 0 or from_block > finalized_number:
        raise OnchainRpcError("discovery_facets_from_block_invalid")
    current_code = client.call("eth_getCode", [facets_address, block_selector])
    if not _has_contract_code(current_code):
        raise OnchainRpcError("discovery_facets_contract_code_missing")
    runtime_code_hash = str(deployment.discovery_facets_runtime_code_hash or "").lower()
    if runtime_code_hash:
        _fixed_hash(runtime_code_hash, field="discovery_facets_runtime_code_hash")
        actual_runtime_code_hash = "0x" + keccak256(
            _hex_bytes(current_code, field="discovery_facets_runtime_code")
        ).hex()
        if actual_runtime_code_hash != runtime_code_hash:
            raise OnchainRpcError("discovery_facets_runtime_code_hash_mismatch")
    deployment_block_hash = str(
        deployment.discovery_facets_deployment_block_hash or ""
    ).lower()
    if deployment_block_hash:
        _fixed_hash(
            deployment_block_hash,
            field="discovery_facets_deployment_block_hash",
        )
    if rpc_profile != RPC_PROFILE_MYOTIS:
        deployment_block = _block_header(
            client,
            hex(from_block),
            field="discovery_facets_deployment_block",
            expected_number=from_block,
        )
        actual_deployment_block_hash = _fixed_hash(
            deployment_block.get("hash"),
            field="discovery_facets_deployment_block.hash",
        )
        if deployment_block_hash and actual_deployment_block_hash != deployment_block_hash:
            raise OnchainRpcError("discovery_facets_deployment_block_hash_mismatch")
        if not _has_contract_code(
            client.call("eth_getCode", [facets_address, hex(from_block)])
        ):
            raise OnchainRpcError("discovery_facets_code_missing_at_deployment_block")
        if from_block > 0 and _has_contract_code(
            client.call("eth_getCode", [facets_address, hex(from_block - 1)])
        ):
            raise OnchainRpcError(
                "discovery_facets_block_not_contract_creation_boundary"
            )
        deployment_verification = {
            "status": "matched",
            "block_number": from_block,
            "block_hash": actual_deployment_block_hash,
            "runtime_code_hash": "0x" + keccak256(
                _hex_bytes(current_code, field="discovery_facets_runtime_code")
            ).hex(),
            "scope": "historical_code_creation_boundary_and_finalized_runtime",
            "pinned_block_hash": bool(deployment_block_hash),
            "pinned_runtime_code_hash": bool(runtime_code_hash),
        }
    else:
        if not deployment_block_hash or not runtime_code_hash:
            raise OnchainRpcError("myotis_discovery_facets_descriptor_incomplete")
        deployment_verification = {
            "status": "pinned",
            "block_number": from_block,
            "block_hash": deployment_block_hash,
            "runtime_code_hash": runtime_code_hash,
            "scope": "pinned_descriptor_verified_log_coverage_and_finalized_runtime",
            "pinned_block_hash": True,
            "pinned_runtime_code_hash": True,
        }
    linked_registry = _decode_address_call(
        client.call(
            "eth_call",
            [{"to": facets_address, "data": DISCOVERY_FACETS_REGISTRY_SELECTOR}, block_selector],
        ),
        field="discovery_facets_registry_call",
    )
    if linked_registry != registry_address:
        raise OnchainRpcError("discovery_facets_registry_mismatch")
    normalized_groups = [
        {_fixed_hash(value, field="category_hash") for value in group}
        for group in category_hash_groups
        if group
    ]
    if not normalized_groups:
        return set(), {}, diagnostics
    declarations = _collect_category_declarations(
        client,
        facets_address=facets_address,
        from_block=from_block,
        to_block=finalized_number,
        chunk_size=chunk_size,
        category_hashes=set().union(*normalized_groups),
    )
    by_record: dict[str, dict[int, set[str]]] = {}
    for declaration in declarations:
        record_id = declaration["record_id"]
        generation = declaration["generation"]
        by_record.setdefault(record_id, {}).setdefault(generation, set()).add(
            declaration["category_hash"]
        )
    hinted: set[str] = set()
    states: dict[str, dict[str, Any]] = {}
    for record_id, generations in sorted(by_record.items()):
        current = lifecycle.get(record_id)
        if current is None or int(current.get("status") or 0) != 1:
            continue
        state = _decode_facet_state_call(
            client.call(
                "eth_call",
                [
                    {
                        "to": facets_address,
                        "data": _encode_call(DISCOVERY_FACET_STATE_SELECTOR, record_id),
                    },
                    block_selector,
                ],
            )
        )
        declared = generations.get(state["generation"], set())
        if (
            state["record_hash"] != str(current.get("record_hash") or "").lower()
            or state["category_set_hash"] == ZERO_ADDRESS_TOPIC
            or state["category_count"] < 1
            or not all(group.intersection(declared) for group in normalized_groups)
        ):
            continue
        hinted.add(record_id)
        states[record_id] = state
    diagnostics.update(
        {
            "used": bool(hinted),
            "facets_address": facets_address,
            "from_block": from_block,
            "declaration_count": len(declarations),
            "matched_record_count": len(hinted),
            "deployment_verification": deployment_verification,
        }
    )
    return hinted, states, diagnostics


def _record_category_commitment(record: dict[str, Any]) -> tuple[str, int]:
    facets = record.get("discovery_facets")
    if discovery_facets.validate_discovery_facets(facets):
        raise OnchainRpcError("registry_record_discovery_facets_invalid")
    categories = facets.get("categories") if isinstance(facets, dict) else None
    if not isinstance(categories, list):
        raise OnchainRpcError("registry_record_discovery_facets_invalid")
    category_hashes = sorted(keccak256(category.encode("utf-8")) for category in categories)
    return "0x" + keccak256(b"".join(category_hashes)).hex(), len(category_hashes)


def _block_time(client: JsonRpcClient, block_number: int, cache: dict[int, dict[str, Any]]) -> tuple[str, str]:
    if block_number not in cache:
        cache[block_number] = _block_header(
            client,
            hex(block_number),
            field=f"event_block.{block_number}",
            expected_number=block_number,
        )
    block = cache[block_number]
    block_hash = _fixed_hash(block.get("hash"), field="block.hash")
    timestamp = _hex_int(block.get("timestamp"), field="block.timestamp")
    formatted = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return block_hash, formatted


def _encode_call(selector: str, value: str) -> str:
    return selector + _fixed_hash(value, field="call_argument")[2:]


def _decode_record_call(value: Any) -> dict[str, Any]:
    data = _hex_bytes(value, field="record_call")
    if len(data) != 9 * 32:
        raise OnchainRpcError("record_call_result_invalid")
    words = [data[index : index + 32] for index in range(0, len(data), 32)]
    return {
        "controller": _decode_word(words[0], "address", field="record.controller"),
        "record_hash": _decode_word(words[1], "bytes32", field="record.recordHash"),
        "domain_hash": _decode_word(words[2], "bytes32", field="record.domainHash"),
        "status": int.from_bytes(words[8], "big"),
    }


def _verify_contract_storage(
    client: JsonRpcClient,
    *,
    registry_address: str,
    block_selector: str,
    state_block: int,
    finalized_block: int,
    scope: str,
    rpc_profile: str,
    lifecycle: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    checked = 0
    for record_id, state in sorted(lifecycle.items()):
        expected_status = int(state["status"])
        expected_controller = str(state["controller"]).lower()
        expected_hash = str(state["record_hash"]).lower()
        expected_domain_hash = str(state["domain_hash"]).lower()
        call = {"to": registry_address, "data": _encode_call(RECORD_SELECTOR, record_id)}
        stored = _decode_record_call(client.call("eth_call", [call, block_selector]))
        if stored["controller"].lower() != expected_controller:
            raise OnchainRpcError("contract_record_controller_mismatch", record_id)
        if stored["record_hash"].lower() != expected_hash:
            raise OnchainRpcError("contract_record_hash_mismatch", record_id)
        if stored["domain_hash"].lower() != expected_domain_hash:
            raise OnchainRpcError("contract_record_domain_hash_mismatch", record_id)
        if stored["status"] != expected_status:
            raise OnchainRpcError("contract_record_status_mismatch", record_id)

        revoked_call = {"to": registry_address, "data": _encode_call(REVOKED_RECORD_HASHES_SELECTOR, expected_hash)}
        revoked_data = _hex_bytes(client.call("eth_call", [revoked_call, block_selector]), field="revoked_call")
        if len(revoked_data) != 32:
            raise OnchainRpcError("revoked_call_result_invalid")
        revoked = int.from_bytes(revoked_data, "big") == 1
        if revoked != (expected_status == 2):
            raise OnchainRpcError("contract_record_revocation_mismatch", record_id)

        if expected_status in {1, 3}:
            domain_call = {"to": registry_address, "data": _encode_call(RECORD_ID_FOR_DOMAIN_SELECTOR, expected_domain_hash)}
            mapped = _fixed_hash(client.call("eth_call", [domain_call, block_selector]), field="record_id_for_domain")
            if mapped != record_id:
                raise OnchainRpcError("contract_domain_record_id_mismatch", record_id)
        checked += 1
    return {
        "status": "matched",
        "checked_record_count": checked,
        "block_number": state_block,
        "finalized_block_number": finalized_block,
        "scope": scope,
        "rpc_profile": rpc_profile,
    }


def _onchain_record(
    *,
    chain_id: int,
    registry_address: str,
    record_id: str,
    controller: str,
    record_hash: str,
) -> dict[str, Any]:
    return {
        "record_hash": record_hash,
        "onchain_identity": {
            "standard": "agentcart-onchain-registry-v1",
            "chain_id": f"eip155:{chain_id}",
            "registry_address": registry_address,
            "record_id": record_id,
            "controller": controller,
        },
    }


def _record_resolution_error(record_id: str, record_hash: str, code: str) -> dict[str, str]:
    return {
        "record_id": record_id,
        "record_hash": record_hash,
        "code": code,
    }


def collect_finalized_events(
    deployment: RegistryDeployment,
    *,
    record_loader: Callable[[str, str], dict[str, Any]],
    request_json: Callable[..., Any] | None = None,
    now: Callable[[], dt.datetime] | None = None,
    record_candidate_limit: int | None = None,
    record_candidate_seed: str = "",
    monotonic: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    myotis_ready_timeout_seconds: float = MYOTIS_READY_TIMEOUT_SECONDS,
    preferred_record_ids: set[str] | None = None,
    preferred_domain_hashes: set[str] | None = None,
    hinted_record_ids: set[str] | None = None,
    category_hash_groups: list[set[str]] | None = None,
) -> dict[str, Any]:
    registry_address, from_block, chunk_size, requested_profile, max_finality_age_seconds = (
        _validate_deployment(deployment)
    )
    indexed_at = _utc_now(now)
    client = JsonRpcClient(
        deployment.rpc_url,
        allow_private=deployment.allow_private_rpc,
        request_json=request_json,
    )
    chain_id = _hex_int(client.call("eth_chainId", []), field="chain_id")
    if chain_id != deployment.chain_id:
        raise OnchainRpcError("rpc_chain_id_mismatch", f"expected {deployment.chain_id}, got {chain_id}")
    rpc_profile, client_version = _detect_rpc_profile(client, requested_profile)
    profile_details: dict[str, Any] = {}
    if rpc_profile == RPC_PROFILE_MYOTIS:
        finalized, profile_details = _myotis_finalized_header(
            client,
            monotonic=monotonic,
            sleep=sleep,
            timeout_seconds=myotis_ready_timeout_seconds,
        )
    else:
        finalized = _block_header(client, "finalized", field="finalized")
        profile_details = {"finality_source": "eth_getBlockByNumber(finalized)"}
    finalized_number = _hex_int(finalized.get("number"), field="finalized.number")
    finalized_hash = _fixed_hash(finalized.get("hash"), field="finalized.hash")
    finalized_timestamp = _hex_int(finalized.get("timestamp"), field="finalized.timestamp")
    _assert_finalized_block_fresh(
        finalized_timestamp,
        reference=indexed_at,
        max_age_seconds=max_finality_age_seconds,
    )
    if finalized_number < from_block:
        raise OnchainRpcError("deployment_block_not_finalized")
    if rpc_profile == RPC_PROFILE_MYOTIS:
        state_block = _hex_int(client.call("eth_blockNumber", []), field="myotis.head_block")
        if state_block < finalized_number:
            raise OnchainRpcError(
                "myotis_head_behind_finality",
                f"head {state_block}, finalized {finalized_number}",
            )
        state_selector = "latest"
        storage_scope = "myotis_verified_head_conservative_cross_check"
    else:
        state_block = finalized_number
        state_selector = hex(finalized_number)
        storage_scope = "same_finalized_block"
    if not _has_contract_code(client.call("eth_getCode", [registry_address, state_selector])):
        raise OnchainRpcError("registry_contract_code_missing")
    deployment_verification = _verify_deployment_boundary(
        client,
        deployment=deployment,
        registry_address=registry_address,
        rpc_profile=rpc_profile,
    )

    logs = _collect_logs(
        client,
        registry_address=registry_address,
        from_block=from_block,
        to_block=finalized_number,
        chunk_size=chunk_size,
    )
    blocks: dict[int, dict[str, Any]] = {}
    lifecycle: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    for log in logs:
        spec, args = _decode_event(log)
        block_number = _hex_int(log.get("blockNumber"), field="blockNumber")
        if block_number > finalized_number:
            raise OnchainRpcError("rpc_log_newer_than_finalized")
        log_block_hash = _fixed_hash(log.get("blockHash"), field="log.blockHash")
        if rpc_profile == RPC_PROFILE_MYOTIS:
            block_time = ""
            block_verification = "myotis_receipt_root_log_index"
        else:
            canonical_block_hash, block_time = _block_time(client, block_number, blocks)
            if log_block_hash != canonical_block_hash:
                raise OnchainRpcError("rpc_log_block_hash_mismatch")
            block_verification = "rpc_canonical_block_header"
        event = {
            "event": spec.name,
            "block_number": block_number,
            "block_hash": log_block_hash,
            "block_time": block_time,
            "transaction_hash": _fixed_hash(log.get("transactionHash"), field="transactionHash"),
            "log_index": _hex_int(log.get("logIndex"), field="logIndex"),
            "block_verification": block_verification,
            "args": args,
        }
        record_id = str(args.get("recordId") or "").lower()
        current = lifecycle.get(record_id)
        expected_controller = str(
            args.get("controller")
            or args.get("newController")
            or (current or {}).get("controller")
            or ""
        ).lower()
        expected_domain = str(
            args.get("domainHash") or (current or {}).get("domain_hash") or ""
        ).lower()
        record_hash = str(args.get("recordHash") or args.get("newRecordHash") or "").lower()
        record_uri = str(args.get("recordURI") or "")
        if spec.name == "MerchantRegistered":
            lifecycle[record_id] = {
                "controller": expected_controller,
                "domain_hash": expected_domain,
                "record_hash": record_hash,
                "record_uri": record_uri,
                "status": 1,
                "document_event_index": len(events),
            }
        elif spec.name == "MerchantUpdated":
            if current is None:
                raise OnchainRpcError("event_lifecycle_missing", record_id)
            current.update(
                {
                    "record_hash": record_hash,
                    "record_uri": record_uri,
                    "document_event_index": len(events),
                }
            )
        elif spec.name == "ControllerChanged":
            if current is None:
                raise OnchainRpcError("event_lifecycle_missing", record_id)
            current.update(
                {
                    "controller": expected_controller,
                    "record_hash": record_hash,
                    "record_uri": record_uri,
                    "document_event_index": len(events),
                }
            )
        elif spec.name == "MerchantRevoked":
            if current is None:
                raise OnchainRpcError("event_lifecycle_missing", record_id)
            current["status"] = 2
        elif spec.name == "MerchantSuspended":
            if current is None:
                raise OnchainRpcError("event_lifecycle_missing", record_id)
            current["status"] = 3
        elif spec.name == "MerchantUnsuspended":
            if current is None:
                raise OnchainRpcError("event_lifecycle_missing", record_id)
            current["status"] = 1
        state = lifecycle.get(record_id)
        if record_uri and record_hash and state is not None:
            event["onchain_record"] = _onchain_record(
                chain_id=chain_id,
                registry_address=registry_address,
                record_id=record_id,
                controller=expected_controller,
                record_hash=record_hash,
            )
        events.append(event)

    storage_verification = _verify_contract_storage(
        client,
        registry_address=registry_address,
        block_selector=state_selector,
        state_block=state_block,
        finalized_block=finalized_number,
        scope=storage_scope,
        rpc_profile=rpc_profile,
        lifecycle=lifecycle,
    )
    record_errors: list[dict[str, str]] = []
    active_pool = [
        (record_id, state)
        for record_id, state in sorted(lifecycle.items())
        if int(state["status"]) == 1
    ]
    onchain_hinted_ids, onchain_facet_states, onchain_facet_diagnostics = (
        _onchain_category_hints(
            client,
            deployment=deployment,
            registry_address=registry_address,
            block_selector=state_selector,
            finalized_number=finalized_number,
            chunk_size=chunk_size,
            rpc_profile=rpc_profile,
            lifecycle=lifecycle,
            category_hash_groups=category_hash_groups or [],
        )
    )
    preferred_ids = {str(value).lower() for value in (preferred_record_ids or set())}
    preferred_domains = {
        str(value).lower() for value in (preferred_domain_hashes or set())
    }
    hinted_ids = {
        *(str(value).lower() for value in (hinted_record_ids or set())),
        *onchain_hinted_ids,
    }
    scoped_pool = active_pool
    selection_mode = "query_seeded_sample"
    if preferred_ids or preferred_domains:
        scoped_pool = [
            (record_id, state)
            for record_id, state in active_pool
            if record_id in preferred_ids
            or str(state.get("domain_hash") or "").lower() in preferred_domains
        ]
        selection_mode = "exact_record_or_domain"
    if record_candidate_limit is None:
        candidate_limit = len(scoped_pool)
    else:
        candidate_limit = int(record_candidate_limit)
        if candidate_limit < 1 or candidate_limit > MAX_RECORD_CANDIDATES:
            raise OnchainRpcError(
                "record_candidate_limit_invalid",
                f"must be 1..{MAX_RECORD_CANDIDATES}",
            )
    seed = str(record_candidate_seed or "shopbridge-default-candidate-sample")
    def query_seeded_order(pool: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
        return sorted(
            pool,
            key=lambda item: hashlib.sha256(f"{seed}\0{item[0]}".encode("utf-8")).digest(),
        )

    selected_hint_count = 0
    selected_fallback_count = 0
    matched_hint_count = 0
    if hinted_ids and not preferred_ids and not preferred_domains:
        hinted_pool = [item for item in scoped_pool if item[0] in hinted_ids]
        neutral_pool = [item for item in scoped_pool if item[0] not in hinted_ids]
        matched_hint_count = len(hinted_pool)
        if hinted_pool:
            hint_budget = candidate_limit if candidate_limit == 1 else candidate_limit - 1
            active_candidates = query_seeded_order(hinted_pool)[:hint_budget]
            selected_hint_count = len(active_candidates)
            fallback = query_seeded_order(neutral_pool)[: candidate_limit - len(active_candidates)]
            active_candidates.extend(fallback)
            selected_fallback_count = len(fallback)
            if len(active_candidates) < candidate_limit:
                selected_ids = {record_id for record_id, _state in active_candidates}
                remainder = [item for item in query_seeded_order(hinted_pool) if item[0] not in selected_ids]
                active_candidates.extend(remainder[: candidate_limit - len(active_candidates)])
                selected_hint_count = len(active_candidates) - selected_fallback_count
            selection_mode = "discovery_facets_with_neutral_fallback"
        else:
            active_candidates = query_seeded_order(scoped_pool)[:candidate_limit]
            selected_fallback_count = len(active_candidates)
            selection_mode = "discovery_facets_no_match_fallback"
    else:
        active_candidates = query_seeded_order(scoped_pool)[:candidate_limit]
    selected_record_ids = [record_id for record_id, _state in active_candidates]

    def resolve_record(record_id: str, state: dict[str, Any]) -> dict[str, Any]:
        record_uri = str(state.get("record_uri") or "")
        record_hash = str(state.get("record_hash") or "").lower()
        if len(record_uri.encode("utf-8")) > MAX_RECORD_URI_BYTES:
            raise OnchainRpcError("registry_record_uri_too_long")
        loaded = record_loader(record_uri, record_hash)
        if not isinstance(loaded, dict):
            raise OnchainRpcError("registry_record_document_invalid")
        _assert_record_identity(
            loaded,
            {
                "chain_id": f"eip155:{chain_id}",
                "registry_address": registry_address,
                "record_id": record_id,
                "controller": str(state["controller"]),
                "domain_hash": str(state["domain_hash"]),
            },
        )
        facet_state = onchain_facet_states.get(record_id)
        if facet_state is not None:
            category_set_hash, category_count = _record_category_commitment(loaded)
            if (
                category_set_hash != facet_state["category_set_hash"]
                or category_count != facet_state["category_count"]
            ):
                raise OnchainRpcError("registry_record_discovery_facet_commitment_mismatch")
        return loaded

    if active_candidates:
        with ThreadPoolExecutor(max_workers=min(MAX_RECORD_FETCH_WORKERS, len(active_candidates))) as pool:
            pending = {
                pool.submit(resolve_record, record_id, state): (record_id, state)
                for record_id, state in active_candidates
            }
            for future in as_completed(pending):
                record_id, state = pending[future]
                try:
                    record = future.result()
                except (Exception, SystemExit) as exc:
                    code = exc.code if isinstance(exc, OnchainRpcError) else "registry_record_fetch_failed"
                    record_errors.append(
                        _record_resolution_error(record_id, str(state["record_hash"]), str(code))
                    )
                    continue
                events[int(state["document_event_index"])]["registry_record"] = record
    record_errors.sort(key=lambda value: value["record_id"])
    return {
        "schema": CONTRACT_EVENTS_SCHEMA,
        "implementation": DIRECT_RPC_IMPLEMENTATION,
        "source": "myotis_verified_json_rpc" if rpc_profile == RPC_PROFILE_MYOTIS else "direct_json_rpc",
        "rpc": {
            "profile": rpc_profile,
            "client_version": client_version,
            **profile_details,
        },
        "chain_id": f"eip155:{chain_id}",
        "registry_address": registry_address,
        "finality": {
            "block_tag": "finalized",
            "block_number": finalized_number,
            "block_hash": finalized_hash,
            "block_time": dt.datetime.fromtimestamp(finalized_timestamp, tz=dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "max_age_seconds": max_finality_age_seconds,
            "indexed_from_block": from_block,
            "indexed_to_block": finalized_number,
        },
        "indexed_at": indexed_at.isoformat().replace("+00:00", "Z"),
        "complete": True,
        "errors": [],
        "lifecycle_record_count": len(lifecycle),
        "resolved_record_count": len(active_candidates) - len(record_errors),
        "record_errors": record_errors,
        "record_selection": {
            "schema": "agentcart.onchain_registry_candidate_selection.v1",
            "algorithm": "sha256-query-seeded-record-id-sample",
            "seed_sha256": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            "active_candidate_count": len(active_pool),
            "selection_scope_count": len(scoped_pool),
            "selection_mode": selection_mode,
            "candidate_limit": candidate_limit,
            "selected_record_count": len(active_candidates),
            "selected_record_ids": selected_record_ids,
            "hinted_record_count": len(hinted_ids),
            "matched_hint_count": matched_hint_count,
            "selected_hint_count": selected_hint_count,
            "selected_neutral_fallback_count": selected_fallback_count,
            "before_record_fetch": True,
        },
        "onchain_discovery_facets": onchain_facet_diagnostics,
        "eligibility_event_topics": list(EVENT_SPECS),
        "contract_storage_verification": storage_verification,
        "deployment_verification": deployment_verification,
        "events": events,
    }


def rpc_url_label(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(str(value or ""))
        host = parsed.hostname or ""
    except ValueError:
        return ""
    try:
        parsed_port = parsed.port
    except ValueError:
        parsed_port = None
    port = f":{parsed_port}" if parsed_port else ""
    return urllib.parse.urlunsplit((parsed.scheme, host + port, "", "", ""))


def error_document(error: OnchainRpcError) -> str:
    return json.dumps({"error": "onchain_registry_rpc_failed", "code": error.code, "detail": error.detail}, sort_keys=True)
