"""Direct, dependency-free JSON-RPC discovery for ShopBridge registries.

The smart contract is the authority for candidate membership and lifecycle
commitments. V1 reads finalized lifecycle logs and retains its verified local
checkpoint path. V2 samples eligible-or-pending-prune indexed/category storage at one hash-pinned
finalized boundary, comparing every read with an independent witness. Both
paths load bounded committed documents; offchain trust decides full eligibility.
"""

from __future__ import annotations

import contextvars
import secrets
import datetime as dt
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import stat
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
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
    registry_version: int = 1
    runtime_code_hash: str = ""
    admission_witness_rpc_url: str = ""


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


keccak256 = registry_trust.keccak256


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

    def call_batch(self, calls: list[tuple[str, list[Any]]]) -> list[Any]:
        """Bound v2 batches to provider limits and validate independent ids."""
        if not calls or len(calls) > 300:
            raise OnchainRpcError("rpc_batch_size_invalid")
        try:
            size = int(os.environ.get("SHOPBRIDGE_ONCHAIN_RPC_BATCH_SIZE", "8"))
        except ValueError as exc:
            raise OnchainRpcError("rpc_batch_size_invalid") from exc
        if not 1 <= size <= 8:
            raise OnchainRpcError("rpc_batch_size_invalid")
        results = []
        for offset in range(0, len(calls), size):
            results.extend(self._call_batch_chunk(calls[offset:offset + size]))
        return results

    def _call_batch_chunk(self, calls: list[tuple[str, list[Any]]], attempt: int = 0) -> list[Any]:
        try:
            if len(calls) == 1:
                method, params = calls[0]
                return [self.call(method, params)]
            return self._request_batch(calls)
        except OnchainRpcError as exc:
            cause = exc.__cause__
            limited = isinstance(cause, safe_http.SafeHttpError) and cause.status == 429
            too_large = (isinstance(cause, safe_http.SafeHttpError)
                and (cause.status == 413 or "request too large" in cause.detail.lower()))
            too_large = too_large or "request too large" in str(exc).lower()
            if not (limited or too_large):
                raise
            if len(calls) == 1 and (not limited or attempt + 1 >= HISTORY_REQUEST_ATTEMPTS):
                raise
            if limited:
                # Match the history transport's bounded Retry-After cooldown.
                delay = min(30.0, max(0.5 * (2 ** attempt) + secrets.randbelow(501) / 1000,
                                     cause.retry_after))
                budget = safe_http.discovery_budget.get()
                if budget is not None:
                    remaining = budget.deadline - time.monotonic()
                    if remaining <= 0:
                        raise OnchainRpcError("rpc_transport_failed", "discovery_budget_exhausted") from exc
                    delay = min(delay, remaining)
                time.sleep(delay)
            if len(calls) == 1:
                return self._call_batch_chunk(calls, attempt + 1)
            middle = len(calls) // 2
            return (self._call_batch_chunk(calls[:middle], attempt + 1)
                    + self._call_batch_chunk(calls[middle:], attempt + 1))

    def _request_batch(self, calls: list[tuple[str, list[Any]]]) -> list[Any]:
        payload = []
        for method, params in calls:
            self.request_id += 1
            payload.append({"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params})
        try:
            response = self.request_json(self.url, method="POST", payload=payload,
                headers={"User-Agent": "AgentCart-ShopBridge-Direct/1"}, timeout_seconds=30,
                allow_private=self.allow_private, max_response_bytes=4 * 1024 * 1024)
        except safe_http.SafeHttpError as exc:
            raise OnchainRpcError("rpc_transport_failed", exc.code) from exc
        if not isinstance(response, list) or len(response) != len(payload):
            if isinstance(response, dict) and isinstance(response.get("error"), dict):
                raise OnchainRpcError("rpc_call_failed", str(response["error"]))
            raise OnchainRpcError("rpc_batch_response_invalid")
        expected = {item["id"] for item in payload}
        results = {}
        for item in response:
            if (not isinstance(item, dict) or item.get("jsonrpc") != "2.0"
                    or type(item.get("id")) is not int or item["id"] not in expected or item["id"] in results):
                raise OnchainRpcError("rpc_batch_response_invalid")
            if isinstance(item.get("error"), dict):
                raise OnchainRpcError("rpc_call_failed", str(item["error"]))
            if "result" not in item:
                raise OnchainRpcError("rpc_result_missing")
            results[item["id"]] = item["result"]
        return [results[item["id"]] for item in payload]


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
        for log in result:
            log = _rpc_log(log, registry_address)
            if not start <= _hex_int(log.get("blockNumber"), field="log.blockNumber") <= end:
                raise OnchainRpcError("rpc_log_block_out_of_range")
            logs.append(log)
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


CACHE_SCHEMA = "agentcart.onchain_verified_checkpoint.v2"
MAX_CACHE_BYTES = 16 * 1024 * 1024

# Detect once at import. CPython lists rename (not replace) in supports_dir_fd;
# replace uses the same native rename primitive with overwrite enabled.
_CACHE_PLATFORM_SUPPORTED = (
    all(hasattr(os, name) for name in (
        "geteuid", "O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "open", "replace",
        "unlink", "stat", "fstat", "fdopen", "fsync", "close", "supports_dir_fd", "supports_follow_symlinks",
    ))
    and os.open in os.supports_dir_fd
    and (os.replace in os.supports_dir_fd or getattr(os, "rename", None) in os.supports_dir_fd)
    and os.unlink in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
)


def _normalized_log(log: dict[str, Any]) -> dict[str, Any]:
    return {
        "address": _address(log["address"], field="log.address"),
        "blockNumber": hex(_hex_int(log["blockNumber"], field="log.blockNumber")),
        "blockHash": _fixed_hash(log["blockHash"], field="log.blockHash"),
        "transactionHash": _fixed_hash(log["transactionHash"], field="log.transactionHash"),
        "logIndex": hex(_hex_int(log["logIndex"], field="log.logIndex")),
        "topics": [_fixed_hash(topic, field="log.topic") for topic in log["topics"]],
        "data": "0x" + _hex_bytes(log["data"], field="log.data").hex(),
    }


def _cache_key(deployment: RegistryDeployment) -> dict[str, Any]:
    # v1 cache provenance is provider-bound trusted local state, not a proof.
    return {
        "chain_id": deployment.chain_id,
        "registry_address": deployment.registry_address.lower(),
        "registry_version": deployment.registry_version,
        "from_block": deployment.from_block,
        "deployment_block_hash": deployment.deployment_block_hash.lower(),
        "runtime_code_hash": deployment.runtime_code_hash.lower(),
        "primary_rpc": rpc_url_label(deployment.rpc_url),
        "facets_address": deployment.discovery_facets_address.lower(),
        "facets_from_block": deployment.discovery_facets_from_block,
        "facets_deployment_block_hash": deployment.discovery_facets_deployment_block_hash.lower(),
        "facets_runtime_code_hash": deployment.discovery_facets_runtime_code_hash.lower(),
    }


def _cache_path(key: dict[str, Any]) -> pathlib.Path:
    root = os.environ.get("SHOPBRIDGE_ONCHAIN_CACHE_DIR")
    if not root:
        root = str(pathlib.Path(os.environ.get("XDG_CACHE_HOME") or pathlib.Path.home() / ".cache") / "shopbridge-direct")
    name = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
    return pathlib.Path(root) / (name + ".json")


class _InsecureCacheDirectory(OSError):
    pass


def _cache_directory_fd(path: pathlib.Path, *, create: bool) -> int:
    root = path.parent
    directories = [root]
    if not os.environ.get("SHOPBRIDGE_ONCHAIN_CACHE_DIR"):
        directories.insert(0, root.parent)
    for directory in directories:
        if create:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        metadata = directory.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
            raise _InsecureCacheDirectory("cache_dir_insecure")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
        os.close(descriptor)
        raise _InsecureCacheDirectory("cache_dir_insecure")
    return descriptor


def _cache_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _read_checkpoint(client: JsonRpcClient, deployment: RegistryDeployment,
                     finalized_number: int, rpc_profile: str,
                     observed_code_hashes: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    diagnostics: dict[str, Any] = {"status": "miss", "scanned_ranges": []}
    if os.environ.get("SHOPBRIDGE_ONCHAIN_CACHE_DISABLED") == "1" or rpc_profile == RPC_PROFILE_MYOTIS or deployment.registry_version == 2:
        reason = "v2_full_two_rpc_scan" if deployment.registry_version == 2 else "myotis_full_verified_index_scan" if rpc_profile == RPC_PROFILE_MYOTIS else "environment"
        diagnostics.update(status="disabled", reason=reason)
        return None, diagnostics
    if not _CACHE_PLATFORM_SUPPORTED:
        diagnostics.update(status="disabled", reason="cache_unsupported_platform")
        return None, diagnostics
    key = _cache_key(deployment)
    try:
        path = _cache_path(key)
        directory_fd = _cache_directory_fd(path, create=False)
        try:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
            with os.fdopen(descriptor, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
                    raise ValueError("cache_file_insecure")
                raw = stream.read(MAX_CACHE_BYTES + 1)
        finally:
            os.close(directory_fd)
        if len(raw) > MAX_CACHE_BYTES:
            raise ValueError("checkpoint too large")
        envelope = json.loads(raw)
        cached = envelope["payload"]
        if not key["deployment_block_hash"]:
            # The filename indexes the configured descriptor; the stored key
            # also binds the independently verified, actual deployment hash.
            key["deployment_block_hash"] = cached["deployment_verification"]["block_hash"]
        if envelope["sha256"] != _cache_digest(cached) or cached["schema"] != CACHE_SCHEMA or cached["key"] != key:
            raise ValueError("checkpoint identity or digest mismatch")
        height = cached["block_number"]
        if type(height) is not int or not deployment.from_block <= height <= finalized_number:
            raise ValueError("checkpoint height invalid")
        if cached["observed_code_hashes"] != observed_code_hashes:
            raise ValueError("checkpoint runtime code changed")
        boundary = _block_header(client, hex(height), field="checkpoint", expected_number=height)
        if _fixed_hash(boundary["hash"], field="checkpoint.hash") != cached["block_hash"]:
            raise ValueError("checkpoint hash mismatch")
        if not isinstance(cached["logs"], list) or not isinstance(cached["category_logs"], list):
            raise ValueError("checkpoint logs invalid")
        seen_logs = set()
        registered_ids = set()
        previous_order = (-1, -1)
        for log in cached["logs"]:
            _rpc_log(log, deployment.registry_address.lower())
            spec, args = _decode_event(log)
            identity = (_fixed_hash(log["transactionHash"], field="checkpoint.tx"),
                        _hex_int(log["logIndex"], field="checkpoint.index"))
            order = (_hex_int(log["blockNumber"], field="checkpoint.number"), identity[1])
            record_id = args.get("recordId")
            if identity in seen_logs or order < previous_order:
                raise ValueError("checkpoint event order invalid")
            if spec.name != "MerchantRegistered" and record_id not in registered_ids:
                raise ValueError("checkpoint lifecycle incomplete")
            seen_logs.add(identity)
            registered_ids.add(record_id)
            previous_order = order
            number = _hex_int(log["blockNumber"], field="checkpoint.log.blockNumber")
            if not deployment.from_block <= number <= height:
                raise ValueError("checkpoint log outside history")
            header = cached["blocks"][str(number)]
            _hex_int(header["timestamp"], field="checkpoint.timestamp")
            if _hex_int(header["number"], field="checkpoint.header.number") != number:
                raise ValueError("checkpoint header height mismatch")
            if _fixed_hash(header["hash"], field="checkpoint.header.hash") != log["blockHash"]:
                raise ValueError("checkpoint header mismatch")
        if deployment.discovery_facets_address:
            _collect_category_declarations(client, facets_address=deployment.discovery_facets_address.lower(),
                from_block=deployment.discovery_facets_from_block or deployment.from_block,
                to_block=height, chunk_size=deployment.log_chunk_size, category_hashes=None,
                prepared_logs=cached["category_logs"])
            for log in cached["category_logs"]:
                _rpc_log(log, deployment.discovery_facets_address.lower())
                number = _hex_int(log["blockNumber"], field="checkpoint.category.blockNumber")
                header = cached["blocks"][str(number)]
                _hex_int(header["timestamp"], field="checkpoint.category.timestamp")
                if _fixed_hash(header["hash"], field="checkpoint.category.hash") != log["blockHash"]:
                    raise ValueError("checkpoint category header mismatch")
            if not isinstance(cached["facets_deployment_verification"], dict):
                raise ValueError("checkpoint facets deployment missing")
            facets_verification = cached["facets_deployment_verification"]
            _fixed_hash(facets_verification["runtime_code_hash"], field="checkpoint.facets.runtime")
            _fixed_hash(facets_verification["block_hash"], field="checkpoint.facets.deployment")
            if facets_verification["block_number"] != (deployment.discovery_facets_from_block or deployment.from_block):
                raise ValueError("checkpoint facets deployment height mismatch")
        verification = cached["deployment_verification"]
        if verification["block_number"] != deployment.from_block:
            raise ValueError("checkpoint deployment invalid")
        _fixed_hash(verification["block_hash"], field="checkpoint.deployment.hash")
        diagnostics.update(status="hit", checkpoint_block=height, checkpoint_hash=cached["block_hash"])
        return cached, diagnostics
    except FileNotFoundError:
        return None, diagnostics
    except _InsecureCacheDirectory:
        diagnostics.update(status="disabled", reason="cache_dir_insecure")
        return None, diagnostics
    except (OSError, ValueError, TypeError, KeyError, RecursionError, MemoryError, OverflowError, OnchainRpcError):
        diagnostics["status"] = "invalid"
        return None, diagnostics


def _write_checkpoint(deployment: RegistryDeployment, payload: dict[str, Any],
                      diagnostics: dict[str, Any]) -> None:
    if diagnostics["status"] == "disabled" or deployment.registry_version == 2:
        return
    if not _CACHE_PLATFORM_SUPPORTED:
        diagnostics.update(status="disabled", reason="cache_unsupported_platform")
        return
    temporary = None
    directory_fd = None
    try:
        encoded = json.dumps({"payload": payload, "sha256": _cache_digest(payload)}, separators=(",", ":")).encode()
        if len(encoded) > MAX_CACHE_BYTES:
            raise OSError("checkpoint exceeds size bound")
        path = _cache_path(_cache_key(deployment))
        directory_fd = _cache_directory_fd(path, create=True)
        temporary = ".checkpoint-" + secrets.token_hex(16)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory_fd)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        temporary = None
    except _InsecureCacheDirectory:
        diagnostics.update(status="disabled", reason="cache_dir_insecure")
    except (OSError, ValueError, RecursionError, MemoryError):
        diagnostics["status"] = "write_failed"
    finally:
        if temporary:
            try:
                if directory_fd is not None:
                    os.unlink(temporary, dir_fd=directory_fd)
            except OSError:
                pass
        if directory_fd is not None:
            os.close(directory_fd)


def _checkpoint_payload(deployment: RegistryDeployment, *, number: int, block_hash: str,
                        logs: list[dict[str, Any]], category_logs: list[dict[str, Any]],
                        blocks: dict[int, dict[str, Any]], deployment_verification: dict[str, Any],
                        facets_verification: dict[str, Any] | None, observed_code_hashes: dict[str, str],
                        complete: bool) -> dict[str, Any]:
    return {
        "schema": CACHE_SCHEMA,
        "key": {**_cache_key(deployment), "deployment_block_hash": deployment_verification["block_hash"]},
        "block_number": number, "block_hash": block_hash,
        "logs": [_normalized_log(log) for log in logs],
        "category_logs": [_normalized_log(log) for log in category_logs],
        "blocks": {str(height): {key: header[key] for key in ("number", "hash", "timestamp")}
                   for height, header in blocks.items() if height <= number},
        "deployment_verification": deployment_verification,
        "facets_deployment_verification": facets_verification,
        "observed_code_hashes": observed_code_hashes, "history_complete": complete,
    }


MAX_HISTORY_LOG_PAGES = 2000
HISTORY_REQUEST_ATTEMPTS = 4


def _history_workers() -> int:
    try:
        value = int(os.environ.get("SHOPBRIDGE_ONCHAIN_LOG_WORKERS", "2"))
    except ValueError as exc:
        raise OnchainRpcError("history_log_workers_invalid") from exc
    if not 1 <= value <= 8:
        raise OnchainRpcError("history_log_workers_invalid")
    return value


def _history_call(client: JsonRpcClient, method: str, params: list[Any],
                  diagnostics: dict[str, Any], lock: threading.Lock) -> Any:
    for attempt in range(HISTORY_REQUEST_ATTEMPTS):
        budget = safe_http.discovery_budget.get()
        while True:
            with lock:
                remaining = diagnostics.get("_cooldown_until", 0) - time.monotonic()
            if remaining <= 0:
                break
            if budget is not None:
                remaining = min(remaining, budget.deadline - time.monotonic())
            if remaining <= 0:
                raise OnchainRpcError("history_sync_incomplete")
            time.sleep(remaining)
        if budget is not None and time.monotonic() >= budget.deadline:
            raise OnchainRpcError("history_sync_incomplete")
        try:
            return client.call(method, params)
        except OnchainRpcError as exc:
            cause = exc.__cause__
            retryable = isinstance(cause, safe_http.SafeHttpError) and (
                cause.status in {429, 502, 503, 504} or cause.code == "request_timeout"
            )
            if isinstance(cause, safe_http.SafeHttpError) and cause.status == 429:
                with lock:
                    diagnostics["http_429_count"] += 1
            if budget is not None and time.monotonic() >= budget.deadline:
                raise OnchainRpcError("history_sync_incomplete") from exc
            if not retryable or attempt + 1 == HISTORY_REQUEST_ATTEMPTS:
                raise
            delay = min(30.0, max(0.5 * (2 ** attempt) + secrets.randbelow(501) / 1000,
                                 cause.retry_after))
            if budget is not None:
                delay = min(delay, max(0, budget.deadline - time.monotonic()))
            with lock:
                diagnostics["retry_count"] += 1
                diagnostics["_cooldown_until"] = max(diagnostics.get("_cooldown_until", 0),
                                                       time.monotonic() + delay)
    raise AssertionError("unreachable history retry state")


def _scan_finalized_history(client: JsonRpcClient, *, deployment: RegistryDeployment,
                            from_block: int, to_block: int, chunk_size: int,
                            checkpoint: dict[str, Any] | None, witness: JsonRpcClient | None,
                            deployment_verification: dict[str, Any],
                            facets_verification: dict[str, Any] | None,
                            observed_code_hashes: dict[str, str],
                            diagnostics: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[int, dict[str, Any]]]:
    workers = _history_workers()
    registry = deployment.registry_address.lower()
    facets = deployment.discovery_facets_address.lower()
    facets_from = deployment.discovery_facets_from_block or deployment.from_block
    range_count = max(0, (to_block - from_block + chunk_size) // chunk_size)
    first_facet_range = max(0, (facets_from - from_block) // chunk_size)
    facet_pages = max(0, range_count - first_facet_range) if facets and facets_from <= to_block else 0
    page_count = (range_count + facet_pages) * (2 if witness is not None else 1)
    if page_count > MAX_HISTORY_LOG_PAGES:
        raise OnchainRpcError("history_scan_exceeds_limit", f"history exceeds {MAX_HISTORY_LOG_PAGES} log pages")
    # Allocate no RPC-sized sequence; reject with constant-time arithmetic first.
    ranges = range(range_count)
    def page_range(index: int) -> tuple[int, int]:
        start = from_block + index * chunk_size
        return start, min(to_block, start + chunk_size - 1)
    diagnostics.update(history_log_pages=page_count, history_workers=workers,
                       retry_count=0, http_429_count=0, completed_history_log_pages=0)
    logs = list(checkpoint["logs"] if checkpoint else [])
    categories = list(checkpoint["category_logs"] if checkpoint else [])
    blocks = {int(number): header for number, header in (checkpoint["blocks"] if checkpoint else {}).items()}
    lock = threading.Lock()

    def scan_page(start: int, end: int):
        # Each worker owns its clients/JSON-RPC IDs; only budget counters are shared.
        primary = JsonRpcClient(client.url, allow_private=client.allow_private, request_json=client.request_json)
        secondary = None if witness is None else JsonRpcClient(
            witness.url, allow_private=witness.allow_private, request_json=witness.request_json)
        page_blocks: dict[int, dict[str, Any]] = {}
        page_registry: list[dict[str, Any]] = []
        page_categories: list[dict[str, Any]] = []
        token = safe_http.history_request.set(True)
        try:
            for target, begin, topics, destination in (
                (registry, start, [list(EVENT_SPECS)], page_registry),
                (facets, max(start, facets_from), [DISCOVERY_CATEGORY_DECLARED_TOPIC], page_categories),
            ):
                if not target or begin > end:
                    continue
                params = [{"address": target, "fromBlock": hex(begin), "toBlock": hex(end), "topics": topics}]
                rows = _history_call(primary, "eth_getLogs", params, diagnostics, lock)
                if not isinstance(rows, list):
                    raise OnchainRpcError("rpc_logs_result_invalid")
                for row in rows:
                    row = _rpc_log(row, target)
                    number = _hex_int(row.get("blockNumber"), field="history.log.blockNumber")
                    if not begin <= number <= end:
                        raise OnchainRpcError("rpc_log_block_out_of_range")
                    if target == registry:
                        _decode_event(row)
                    destination.append(_normalized_log(row))
                destination.sort(key=lambda row: (int(row["blockNumber"], 16), int(row["logIndex"], 16)))
                if target == facets:
                    _collect_category_declarations(primary, facets_address=facets, from_block=begin,
                        to_block=end, chunk_size=chunk_size, category_hashes=None, prepared_logs=destination)
                if secondary is not None:
                    witnessed = _history_call(secondary, "eth_getLogs", params, diagnostics, lock)
                    if not isinstance(witnessed, list) or _log_fingerprint(witnessed) != _log_fingerprint(destination):
                        raise OnchainRpcError("registry_v2_witness_logs_mismatch" if target == registry
                                              else "registry_v2_witness_category_logs_mismatch")
            boundary = _history_call(primary, "eth_getBlockByNumber", [hex(end), False], diagnostics, lock)
            if not isinstance(boundary, dict) or _hex_int(boundary.get("number"), field="history.boundary.number") != end:
                raise OnchainRpcError("rpc_block_number_mismatch")
            boundary_hash = _fixed_hash(boundary.get("hash"), field="history.boundary.hash")
            _hex_int(boundary.get("timestamp"), field="history.boundary.timestamp")
            if secondary is not None:
                other = _history_call(secondary, "eth_getBlockByNumber", [hex(end), False], diagnostics, lock)
                if not isinstance(other, dict) or other.get("hash", "").lower() != boundary_hash:
                    raise OnchainRpcError("registry_v2_witness_boundary_mismatch")
            page_blocks[end] = boundary
            for row in page_registry + page_categories:
                number = int(row["blockNumber"], 16)
                if number in blocks:
                    page_blocks[number] = blocks[number]
                # Event volume is merchant-controlled: these headers retain the
                # GENERAL request allowance, deduplicated by block within a page.
                event_token = safe_http.history_request.set(False)
                try:
                    if number not in page_blocks:
                        header = _history_call(primary, "eth_getBlockByNumber", [hex(number), False], diagnostics, lock)
                        if not isinstance(header, dict) or _hex_int(header.get("number"), field="event.number") != number:
                            raise OnchainRpcError("rpc_block_number_mismatch")
                        page_blocks[number] = header
                    canonical_hash, _ = _block_time(primary, number, page_blocks)
                finally:
                    safe_http.history_request.reset(event_token)
                if canonical_hash != row["blockHash"]:
                    raise OnchainRpcError("rpc_log_block_hash_mismatch")
            return page_registry, page_categories, page_blocks
        finally:
            safe_http.history_request.reset(token)

    complete_pages: dict[int, Any] = {}
    contiguous = 0
    next_page = 0
    failure: OnchainRpcError | None = None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        seen_registry = {(row["transactionHash"], row["logIndex"]) for row in logs}
        seen_categories = {(row["transactionHash"], row["logIndex"]) for row in categories}
        pending = {}
        def submit():
            nonlocal next_page
            index = next_page
            next_page += 1
            pending[pool.submit(contextvars.copy_context().run, scan_page, *page_range(index))] = index
        while next_page < min(workers, len(ranges)):
            submit()
        while pending:
            ready, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in ready:
                index = pending.pop(future)
                if future.cancelled():
                    continue
                try:
                    complete_pages[index] = future.result()
                except OnchainRpcError as exc:
                    if failure is None or failure.code == "history_sync_incomplete":
                        failure = exc
            while contiguous in complete_pages:
                page_logs, page_categories, page_blocks = complete_pages.pop(contiguous)
                for rows, seen in ((page_logs, seen_registry), (page_categories, seen_categories)):
                    for row in rows:
                        identity = (row["transactionHash"], row["logIndex"])
                        if identity in seen:
                            raise OnchainRpcError("rpc_log_duplicate")
                        seen.add(identity)
                logs.extend(page_logs)
                categories.extend(page_categories)
                blocks.update(page_blocks)
                start, end = page_range(contiguous)
                diagnostics["scanned_ranges"].append({"contract": "registry", "from_block": start, "to_block": end})
                if facets and end >= facets_from:
                    diagnostics["scanned_ranges"].append({"contract": "facets", "from_block": max(start, facets_from), "to_block": end})
                diagnostics["completed_history_log_pages"] += (1 + int(bool(facets) and end >= facets_from)) * (2 if witness else 1)
                contiguous += 1
            if failure is not None:
                for future in pending:
                    future.cancel()
            else:
                while next_page < len(ranges) and len(pending) < workers:
                    submit()
    diagnostics.pop("_cooldown_until", None)
    if failure is not None:
        if failure.code == "history_sync_incomplete":
            end = page_range(contiguous - 1)[1] if contiguous else from_block - 1
            if contiguous and witness is None:
                _write_checkpoint(deployment, _checkpoint_payload(deployment, number=end,
                    block_hash=blocks[end]["hash"].lower(), logs=logs, category_logs=categories,
                    blocks=blocks, deployment_verification=deployment_verification,
                    facets_verification=facets_verification, observed_code_hashes=observed_code_hashes, complete=False),
                    diagnostics)
            failure.progress = {
                "blocks_done": max(0, end - deployment.from_block + 1),
                "blocks_total": max(0, to_block - deployment.from_block + 1),
                "verified_through_block": end, "target_finalized_block": to_block,
                "checkpoint": diagnostics,
            }
        raise failure
    return logs, categories, blocks

def _log_fingerprint(logs: list[dict[str, Any]]) -> str:
    # Ignore transport-only fields; compare every consensus-relevant log field.
    rows = [
        [_hex_int(log.get("blockNumber"), field="log.blockNumber"),
         _fixed_hash(log.get("blockHash"), field="log.blockHash"),
         _fixed_hash(log.get("transactionHash"), field="log.transactionHash"),
         _hex_int(log.get("logIndex"), field="log.logIndex"),
         [_fixed_hash(topic, field="log.topic") for topic in log.get("topics", [])],
         _hex_bytes(log.get("data"), field="log.data").hex()]
        for log in logs
    ]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def _block_headers_agree(primary: dict[str, Any], witness: dict[str, Any]) -> bool:
    # Client-specific fields (e.g. totalDifficulty) are not consensus evidence.
    for field in ("number", "hash", "parentHash", "timestamp", "stateRoot"):
        if field == "stateRoot" and (field not in primary or field not in witness):
            continue
        left, right = primary.get(field), witness.get(field)
        if field in {"number", "timestamp"}:
            left = _hex_int(left, field=f"primary.{field}")
            right = _hex_int(right, field=f"witness.{field}")
        elif left is not None or right is not None:
            left = _fixed_hash(left, field=f"primary.{field}")
            right = _fixed_hash(right, field=f"witness.{field}")
        if left != right:
            return False
    return True


def _v2_witness(deployment: RegistryDeployment, primary: JsonRpcClient, *,
                request_json: Callable[..., Any] | None,
                sleep: Callable[[float], None] | None = None
                ) -> tuple[JsonRpcClient, dict[str, Any], dict[str, Any]]:
    witness_url = deployment.admission_witness_rpc_url
    if not witness_url:
        raise OnchainRpcError("registry_v2_admission_witness_required")
    primary_host = urllib.parse.urlsplit(deployment.rpc_url).hostname
    witness_host = urllib.parse.urlsplit(witness_url).hostname
    if not witness_host or primary_host == witness_host:
        raise OnchainRpcError("registry_v2_distinct_witness_required")
    witness = JsonRpcClient(witness_url, allow_private=deployment.allow_private_rpc, request_json=request_json)
    if _hex_int(witness.call("eth_chainId", []), field="witness.chain_id") != deployment.chain_id:
        raise OnchainRpcError("registry_v2_witness_chain_mismatch")
    policy = os.environ.get("SHOPBRIDGE_ONCHAIN_WITNESS_FINALITY_POLICY", "exact")
    if policy not in {"exact", "bounded_lag"}:
        raise OnchainRpcError("registry_v2_witness_finality_policy_invalid")
    skew = 0
    if policy == "bounded_lag":
        try:
            skew = int(os.environ.get("SHOPBRIDGE_ONCHAIN_WITNESS_MAX_HEAD_SKEW_SECONDS", "12"))
        except ValueError as exc:
            raise OnchainRpcError("registry_v2_witness_head_skew_invalid") from exc
        if not 1 <= skew <= 60:
            raise OnchainRpcError("registry_v2_witness_head_skew_invalid")
    observed = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for attempt in range(6):
            futures = [pool.submit(contextvars.copy_context().run, _block_header, provider,
                "finalized", field=f"{label}.finalized") for provider, label in
                ((primary, "primary"), (witness, "witness"))]
            heads = [future.result() for future in futures]
            observed.append({label: {field: head[field] for field in ("number", "hash", "timestamp")}
                for label, head in zip(("primary", "witness"), heads)})
            boundary = None
            if _block_headers_agree(*heads):
                boundary = heads[0]
            elif policy == "bounded_lag":
                numbers = [_hex_int(head["number"], field="finalized.number") for head in heads]
                timestamps = [_hex_int(head["timestamp"], field="finalized.timestamp") for head in heads]
                if numbers[0] != numbers[1] and abs(timestamps[0] - timestamps[1]) <= skew:
                    lower = min(numbers)
                    confirmations = [pool.submit(contextvars.copy_context().run, _block_header, provider,
                        hex(lower), field="finalized.boundary", expected_number=lower)
                        for provider in (primary, witness)]
                    confirmed = [future.result() for future in confirmations]
                    if _block_headers_agree(*confirmed) and _block_headers_agree(
                            confirmed[0], heads[numbers.index(lower)]):
                        boundary = confirmed[0]
            if boundary is not None:
                return witness, boundary, {
                    "policy": "two_rpc_agreement", "witness_rpc": rpc_url_label(witness_url),
                    "finality_agreement": "exact" if policy == "exact" else "bounded_lag_noncanonical",
                    "max_head_skew_seconds": skew, "observed_heads": observed,
                    "block_number": _hex_int(boundary["number"], field="finalized.number"),
                    "block_hash": _fixed_hash(boundary["hash"], field="finalized.hash"),
                    "history_scope": "selected_finalized_storage_two_rpc_agreement",
                }
            budget = safe_http.discovery_budget.get()
            if attempt == 5 or (budget is not None and budget.deadline - time.monotonic() <= .2):
                break
            (sleep or time.sleep)(.2)
    error = OnchainRpcError("registry_v2_witness_finality_mismatch", "finalized heads did not agree")
    error.diagnostics = {"finality_policy": policy, "observed_heads": observed}
    raise error


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
    category_hashes: set[str] | None,
    prepared_logs: list[dict[str, Any]] | None = None,
    captured_logs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    requested = None if category_hashes is None else {_fixed_hash(value, field="category_hash") for value in category_hashes}
    if requested == set():
        return []
    logs: list[dict[str, Any]] = list(prepared_logs or [])
    start = to_block + 1 if prepared_logs is not None else from_block
    while start <= to_block:
        end = min(to_block, start + chunk_size - 1)
        result = client.call(
            "eth_getLogs",
            [
                {
                    "address": facets_address,
                    "fromBlock": hex(start),
                    "toBlock": hex(end),
                    "topics": [DISCOVERY_CATEGORY_DECLARED_TOPIC] if requested is None else [DISCOVERY_CATEGORY_DECLARED_TOPIC, sorted(requested)],
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
    if captured_logs is not None:
        captured_logs.extend(logs)
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
            or (requested is not None and category_hash not in requested)
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
    category_logs: list[dict[str, Any]] | None = None,
    cached_deployment_verification: dict[str, Any] | None = None,
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
    if not deployment.discovery_facets_address:
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
    if cached_deployment_verification is not None:
        deployment_verification = cached_deployment_verification
        actual_runtime = "0x" + keccak256(_hex_bytes(current_code, field="facets.runtime")).hex()
        if actual_runtime != deployment_verification["runtime_code_hash"]:
            raise OnchainRpcError("discovery_facets_runtime_code_hash_mismatch")
    elif rpc_profile != RPC_PROFILE_MYOTIS:
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
    diagnostics["deployment_verification"] = deployment_verification
    if not normalized_groups:
        return set(), {}, diagnostics
    declarations = _collect_category_declarations(
        client,
        facets_address=facets_address,
        from_block=from_block,
        to_block=finalized_number,
        chunk_size=chunk_size,
        category_hashes=None if category_logs is not None else set().union(*normalized_groups),
        prepared_logs=category_logs,
    )
    if category_logs is not None:
        requested = set().union(*normalized_groups)
        declarations = [row for row in declarations if row["category_hash"] in requested]
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


def _sample_storage_indices(count: int, limit: int, seed: str) -> list[int]:
    """Sparse Fisher-Yates with rejection sampling: uniform, O(k) space/time."""
    swaps: dict[int, int] = {}
    result = []
    counter = 0
    for remaining in range(count, max(0, count - limit), -1):
        ceiling = (1 << 256) - ((1 << 256) % remaining)
        while True:
            value = int.from_bytes(hashlib.sha256(f"{seed}\0{counter}".encode()).digest(), "big")
            counter += 1
            if value < ceiling:
                break
        index = value % remaining
        result.append(swaps.get(index, index))
        swaps[index] = swaps.get(remaining - 1, remaining - 1)
    return result


class _WitnessedStorageClient:
    """Compare every storage/deployment read before exposing it to the buyer."""
    def __init__(self, primary: JsonRpcClient, witness: JsonRpcClient, block_hash: str,
                 block_number: int) -> None:
        self.primary, self.witness = primary, witness
        self.block_hash, self.block_number = block_hash, block_number
        self.cache: dict[str, Any] = {}

    def _params(self, method: str, params: list[Any]) -> list[Any]:
        if method == "eth_getLogs":
            raise OnchainRpcError("registry_v2_history_scan_forbidden")
        params = list(params)
        if method in {"eth_call", "eth_getCode"} and params[-1] == hex(self.block_number):
            params[-1] = {"blockHash": self.block_hash, "requireCanonical": True}
        return params

    def prefetch(self, calls: list[tuple[str, list[Any]]]) -> None:
        pending = {}
        for method, params in calls:
            params = self._params(method, params)
            key = json.dumps([method, params], sort_keys=True)
            if key not in self.cache:
                pending[key] = (method, params)
        if not pending:
            return
        rows = list(pending.values())
        primary = self.primary.call_batch(rows)
        witness = self.witness.call_batch(rows)
        if primary != witness:
            raise OnchainRpcError("registry_v2_witness_storage_mismatch", "storage_batch")
        self.cache.update(zip(pending, primary))

    def call(self, method: str, params: list[Any]) -> Any:
        params = self._params(method, params)
        key = json.dumps([method, params], sort_keys=True)
        if key in self.cache:
            return self.cache[key]
        value = self.primary.call(method, params)
        witnessed = self.witness.call(method, params)
        agrees = (_block_headers_agree(value, witnessed) if method == "eth_getBlockByNumber"
                  and isinstance(value, dict) and isinstance(witnessed, dict) else value == witnessed)
        if not agrees:
            raise OnchainRpcError("registry_v2_witness_storage_mismatch", method)
        self.cache[key] = value
        return value


def _v2_storage_candidates(client: Any, *, deployment: RegistryDeployment, registry_address: str,
                           block_selector: str, finalized_number: int, finalized_hash: str,
                           finalized_timestamp: int, seed: str, limit: int,
                           preferred_ids: set[str], preferred_domains: set[str],
                           category_groups: list[set[str]]) -> tuple[list[dict[str, Any]], set[str], dict[str, Any], int]:
    def call(signature: str, arguments: str = "", address: str = registry_address) -> Any:
        selector = "0x" + keccak256(signature.encode()).hex()[:8]
        return client.call("eth_call", [{"to": address, "data": selector + arguments}, block_selector])

    def count(signature: str, arguments: str = "", address: str = registry_address) -> int:
        raw = _hex_bytes(call(signature, arguments, address), field=signature)
        if len(raw) != 32:
            raise OnchainRpcError("registry_enumeration_result_invalid", signature)
        return int.from_bytes(raw, "big")

    indexed_count = count("indexedRecordCount()")
    reserve_limit = min(MAX_RECORD_CANDIDATES, limit * 3)
    ids: list[str] = []
    category_entries: dict[str, list[tuple[str, int]]] = {}
    facets = deployment.discovery_facets_address.lower()
    if preferred_ids or preferred_domains:
        ids.extend(sorted({_fixed_hash(value, field="preferred_record_id") for value in preferred_ids}))
        for domain in sorted(preferred_domains):
            value = _fixed_hash(call("recordIdForDomain(bytes32)", domain[2:]), field="record_id_for_domain")
            if value != ZERO_ADDRESS_TOPIC and value not in ids:
                ids.append(value)
        ids = ids[:reserve_limit]
    else:
        categories = sorted(set().union(*category_groups)) if category_groups else []
        category_budget = max(1, (reserve_limit + min(8, len(categories)) - 1) // min(8, len(categories))) if categories else 0
        # Query text cannot amplify requests: at most eight routing buckets.
        for category in categories[:8] if facets else []:
            category = _fixed_hash(category, field="category_hash")
            size = count("categoryRecordCount(bytes32)", category[2:], facets)
            indices = _sample_storage_indices(size, category_budget, seed + "\0category\0" + category)
            client.prefetch([("eth_call", [{"to": facets, "data": "0x" + keccak256(
                b"categoryRecordAt(bytes32,uint256)").hex()[:8] + category[2:] + index.to_bytes(32, "big").hex()},
                block_selector]) for index in indices])
            for index in indices:
                raw = _hex_bytes(call("categoryRecordAt(bytes32,uint256)",
                    category[2:] + index.to_bytes(32, "big").hex(), facets), field="category_record")
                if len(raw) != 64 or int.from_bytes(raw[32:], "big") >= 2**64:
                    raise OnchainRpcError("registry_enumeration_result_invalid", "category_record")
                record_id = "0x" + raw[:32].hex()
                category_entries.setdefault(record_id, []).append((category, int.from_bytes(raw[32:], "big")))
                if record_id not in ids:
                    ids.append(record_id)
        neutral_indices = _sample_storage_indices(indexed_count, reserve_limit, seed + "\0active")
        client.prefetch([("eth_call", [{"to": registry_address, "data": "0x" + keccak256(
            b"indexedRecordIdAt(uint256)").hex()[:8] + index.to_bytes(32, "big").hex()},
            block_selector]) for index in neutral_indices])
        neutral = [_fixed_hash(call("indexedRecordIdAt(uint256)", index.to_bytes(32, "big").hex()),
                    field="indexed_record_id") for index in neutral_indices]
        # Preserve a neutral slot even when all category buckets are populated.
        hint_budget = max(0, reserve_limit - max(1, reserve_limit // 3))
        ids = ids[:hint_budget] + [value for value in neutral if value not in ids[:hint_budget]]
        ids = ids[:reserve_limit]
    reads = []
    for record_id in ids:
        for signature, target in [("record(bytes32)", registry_address), ("recordURI(bytes32)", registry_address),
                ("eligibility(bytes32)", registry_address)] + (
                [("facetState(bytes32)", facets), ("isCurrent(bytes32)", facets)] if facets else []):
            reads.append(("eth_call", [{"to": target, "data": "0x" + keccak256(signature.encode()).hex()[:8]
                + record_id[2:]}, block_selector]))
    if reads:
        client.prefetch(reads)
    verification_reads = []
    logs, hints, states = [], set(), {}
    for record_id in ids:
        stored = _decode_record_call(call("record(bytes32)", record_id[2:]))
        if stored["status"] != 1:
            continue
        for signature, argument in [("recordIdForDomain(bytes32)", stored["domain_hash"]),
                ("revokedRecordHashes(bytes32)", stored["record_hash"])]:
            verification_reads.append(("eth_call", [{"to": registry_address,
                "data": "0x" + keccak256(signature.encode()).hex()[:8] + argument[2:]}, block_selector]))
        if facets:
            state = _decode_facet_state_call(call("facetState(bytes32)", record_id[2:], facets))
            current = count("isCurrent(bytes32)", record_id[2:], facets)
            if current not in {0, 1}:
                raise OnchainRpcError("discovery_facet_state_call_result_invalid")
            if current and state["record_hash"] == stored["record_hash"]:
                # Facets are routing hints, not mandatory fallback commitments.
                entries = category_entries.get(record_id, [])
                matched = {category for category, generation in entries if generation == state["generation"]}
                if matched and all(matched & group for group in category_groups):
                    hints.add(record_id)
                    if state["category_set_hash"] != "0x" + "0" * 64 and state["category_count"] >= 1:
                        states[record_id] = state
        raw_uri = _hex_bytes(call("recordURI(bytes32)", record_id[2:]), field="record_uri")
        if len(raw_uri) < 64 or int.from_bytes(raw_uri[:32], "big") != 32:
            raise OnchainRpcError("registry_record_uri_invalid")
        length = int.from_bytes(raw_uri[32:64], "big")
        if length > MAX_RECORD_URI_BYTES or len(raw_uri) != 64 + ((length + 31) // 32) * 32:
            raise OnchainRpcError("registry_record_uri_invalid")
        try:
            uri = raw_uri[64:64 + length].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise OnchainRpcError("registry_record_uri_invalid") from exc
        # Adapter rows represent current storage, not historical transactions.
        logs.append({"address": registry_address, "blockNumber": hex(finalized_number),
            "blockHash": finalized_hash, "transactionHash": ZERO_ADDRESS_TOPIC,
            "logIndex": hex(len(logs)), "removed": False,
            "topics": [next(topic for topic, spec in EVENT_SPECS.items() if spec.name == "MerchantRegistered"),
                       record_id, "0x" + "0" * 24 + stored["controller"][2:], stored["domain_hash"]],
            "data": "0x" + (bytes.fromhex(stored["record_hash"][2:]) + (64).to_bytes(32, "big")
                + length.to_bytes(32, "big") + raw_uri[64:]).hex()})
    if verification_reads:
        client.prefetch(verification_reads)
    return logs, hints, states, indexed_count


@safe_http.budgeted_discovery
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
    witness_client = None
    admission_verification = {}
    if rpc_profile == RPC_PROFILE_MYOTIS:
        finalized, profile_details = _myotis_finalized_header(
            client,
            monotonic=monotonic,
            sleep=sleep,
            timeout_seconds=myotis_ready_timeout_seconds,
        )
    elif deployment.registry_version == 2 and rpc_profile == RPC_PROFILE_STANDARD:
        witness_client, finalized, admission_verification = _v2_witness(
            deployment, client, request_json=request_json, sleep=sleep)
        profile_details = {"finality_source": "eth_getBlockByNumber(finalized)",
            "finality_agreement": admission_verification["finality_agreement"]}
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
    current_code = client.call("eth_getCode", [registry_address, state_selector])
    if not _has_contract_code(current_code):
        raise OnchainRpcError("registry_contract_code_missing")
    observed_code_hashes = {
        "registry": "0x" + keccak256(_hex_bytes(current_code, field="registry_code")).hex(),
        "facets": "",
    }
    if deployment.discovery_facets_address and rpc_profile != RPC_PROFILE_MYOTIS:
        facets_code = client.call("eth_getCode", [deployment.discovery_facets_address.lower(), state_selector])
        if not _has_contract_code(facets_code):
            raise OnchainRpcError("discovery_facets_contract_code_missing")
        observed_code_hashes["facets"] = "0x" + keccak256(_hex_bytes(facets_code, field="facets_code")).hex()
    if deployment.registry_version not in {1, 2}:
        raise OnchainRpcError("registry_version_unsupported")
    if deployment.registry_version == 2:
        if storage_scope != "same_finalized_block":
            raise OnchainRpcError("registry_v2_finalized_state_required")
        if not deployment.runtime_code_hash or not deployment.deployment_block_hash:
            raise OnchainRpcError("registry_v2_deployment_pins_required")
        actual_hash = observed_code_hashes["registry"]
        if actual_hash != deployment.runtime_code_hash.lower():
            raise OnchainRpcError("registry_runtime_code_hash_mismatch")
        client = _WitnessedStorageClient(client, witness_client, finalized_hash, finalized_number)
        # Recheck all current code through hash-pinned two-provider reads.
        pinned_code = _hex_bytes(client.call("eth_getCode", [registry_address, state_selector]), field="registry_code")
        if "0x" + keccak256(pinned_code).hex() != deployment.runtime_code_hash.lower():
            raise OnchainRpcError("registry_runtime_code_hash_mismatch")
        if deployment.discovery_facets_address:
            client.call("eth_getCode", [deployment.discovery_facets_address.lower(), state_selector])
    checkpoint, cache_diagnostics = _read_checkpoint(client, deployment, finalized_number, rpc_profile, observed_code_hashes)
    deployment_verification = checkpoint["deployment_verification"] if checkpoint else _verify_deployment_boundary(
        client,
        deployment=deployment,
        registry_address=registry_address,
        rpc_profile=rpc_profile,
    )
    scan_start = checkpoint["block_number"] + 1 if checkpoint else from_block

    facets_verification = checkpoint.get("facets_deployment_verification") if checkpoint else None
    category_logs: list[dict[str, Any]] | None = None
    v2_hints, v2_facets, v2_active_count = set(), {}, 0
    if deployment.registry_version == 2:
        seed = str(record_candidate_seed or secrets.token_hex(32))
        record_candidate_seed = seed
        limit = MAX_RECORD_CANDIDATES if record_candidate_limit is None else int(record_candidate_limit)
        if not 1 <= limit <= MAX_RECORD_CANDIDATES:
            raise OnchainRpcError("record_candidate_limit_invalid")
        if deployment.discovery_facets_address:
            _, _, descriptor = _onchain_category_hints(client, deployment=deployment,
                registry_address=registry_address, block_selector=state_selector,
                finalized_number=finalized_number, chunk_size=chunk_size, rpc_profile=rpc_profile,
                lifecycle={}, category_hash_groups=[], category_logs=[])
            facets_verification = descriptor["deployment_verification"]
        logs, v2_hints, v2_facets, v2_active_count = _v2_storage_candidates(client,
            deployment=deployment, registry_address=registry_address, block_selector=state_selector,
            finalized_number=finalized_number, finalized_hash=finalized_hash,
            finalized_timestamp=finalized_timestamp, seed=seed, limit=limit,
            preferred_ids=preferred_record_ids or set(), preferred_domains=preferred_domain_hashes or set(),
            category_groups=category_hash_groups or [])
        blocks = {finalized_number: finalized}
        category_logs = []
        cache_diagnostics = {"status": "disabled", "reason": "v2_storage_enumeration", "scanned_ranges": []}
    elif rpc_profile == RPC_PROFILE_MYOTIS:
        # Preserve the receipt-root-verified Myotis full-index path.
        logs = _collect_logs(client, registry_address=registry_address, from_block=scan_start,
                             to_block=finalized_number, chunk_size=chunk_size)
        blocks: dict[int, dict[str, Any]] = {}
        cache_diagnostics["scanned_ranges"].append({"contract": "registry", "from_block": scan_start,
                                                   "to_block": finalized_number})
    else:
        # V1 keeps its finalized-history/checkpoint path unchanged.
        if deployment.discovery_facets_address:
            _, _, descriptor = _onchain_category_hints(client, deployment=deployment,
                registry_address=registry_address, block_selector=state_selector,
                finalized_number=finalized_number, chunk_size=chunk_size, rpc_profile=rpc_profile,
                lifecycle={}, category_hash_groups=[], category_logs=[],
                cached_deployment_verification=facets_verification)
            facets_verification = descriptor["deployment_verification"]
        logs, category_logs, blocks = _scan_finalized_history(client, deployment=deployment,
            from_block=scan_start, to_block=finalized_number, chunk_size=chunk_size,
            checkpoint=checkpoint, witness=witness_client, deployment_verification=deployment_verification,
            facets_verification=facets_verification, observed_code_hashes=observed_code_hashes, diagnostics=cache_diagnostics)
        if finalized_number in blocks and blocks[finalized_number]["hash"].lower() != finalized_hash:
            raise OnchainRpcError("rpc_finalized_block_hash_mismatch")
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
            **({"projection_origin": "finalized_storage"} if deployment.registry_version == 2 else {}),
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
            category_logs=category_logs,
            cached_deployment_verification=facets_verification,
        )
    ) if deployment.registry_version == 1 else (v2_hints, v2_facets, {
        "schema": "agentcart.onchain_category_routing.v1",
        "query_group_count": len(category_hash_groups or []),
        "enumeration_scope": "sampled_finalized_storage",
        "configured": bool(deployment.discovery_facets_address), "used": bool(v2_hints),
        "authority": "smart_contract_routing_hint", "fallback_required": True,
        "matched_record_count": len(v2_hints), "deployment_verification": facets_verification})
    preferred_ids = {str(value).lower() for value in (preferred_record_ids or set())}
    preferred_domains = {
        str(value).lower() for value in (preferred_domain_hashes or set())
    }
    hinted_ids = {
        *(str(value).lower() for value in (hinted_record_ids or set())),
        *onchain_hinted_ids,
    }
    scoped_pool = active_pool
    admissions: dict[str, dict[str, Any]] = {}
    if deployment.registry_version == 2:
        selector = "0x" + keccak256(b"eligibility(bytes32)").hex()[:8]
        for record_id, _state in active_pool:
            admission_call = [{"to": registry_address, "data": _encode_call(selector, record_id)}, state_selector]
            raw = _hex_bytes(client.call("eth_call", admission_call), field="admission")
            # The v2 client witnesses every read, including admission.
            if len(raw) != 128 or int.from_bytes(raw[:32], "big") not in {0, 1}:
                raise OnchainRpcError("registry_admission_invalid")
            admitted = raw[:32] == bytes(31) + b"\x01"
            entity = "0x" + raw[32:64].hex()
            expiry = int.from_bytes(raw[64:96], "big")
            bond = int.from_bytes(raw[96:128], "big")
            if admitted and (entity == "0x" + "0" * 64 or expiry <= finalized_timestamp or bond == 0):
                raise OnchainRpcError("registry_admission_invalid")
            admissions[record_id] = {"eligible": admitted, "entity_id": entity, "expires_at": expiry,
                "bond_base_units": str(bond), "registry_version": 2, "block_number": state_block,
                "registry_address": registry_address, "runtime_code_hash": deployment.runtime_code_hash}
        # Indexed records may expire without a transaction. Exclude them before
        # selection so eligible reserve draws backfill within the same budget;
        # exhausted samples require keeper pruning, never an unbounded scan.
        scoped_pool = [item for item in active_pool if admissions[item[0]]["eligible"]]
    selection_mode = "query_seeded_sample"
    if preferred_ids or preferred_domains:
        scoped_pool = [
            (record_id, state)
            for record_id, state in scoped_pool
            if record_id in preferred_ids
            or str(state.get("domain_hash") or "").lower() in preferred_domains
        ]
        selection_mode = "exact_record_or_domain"
    seed = str(record_candidate_seed or secrets.token_hex(32))
    def query_seeded_order(pool: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
        return sorted(
            pool,
            key=lambda item: hashlib.sha256(f"{seed}\0{admissions.get(item[0], {}).get('entity_id') or item[0]}".encode("utf-8")).digest(),
        )

    if admissions:
        seen_entities = set()
        grouped_pool = []
        for item in sorted(scoped_pool, key=lambda item: hashlib.sha256(f"{seed}\0brand\0{item[0]}".encode()).digest()):
            entity = admissions[item[0]]["entity_id"]
            if entity not in seen_entities:
                seen_entities.add(entity)
                grouped_pool.append(item)
        scoped_pool = grouped_pool

    if record_candidate_limit is None:
        candidate_limit = len(scoped_pool)
    else:
        candidate_limit = int(record_candidate_limit)
        if candidate_limit < 1 or candidate_limit > MAX_RECORD_CANDIDATES:
            raise OnchainRpcError(
                "record_candidate_limit_invalid",
                f"must be 1..{MAX_RECORD_CANDIDATES}",
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

    # Backfill only failed documents, at the same finalized snapshot. Each wave
    # is bounded by missing slots; never fetch the entire public registry.
    target_count = min(candidate_limit, MAX_RECORD_CANDIDATES)
    attempt_limit = min(MAX_RECORD_CANDIDATES, target_count * 3)
    active_candidates = active_candidates[:target_count]
    chosen_ids = {record_id for record_id, _ in active_candidates}
    reserves = [item for item in query_seeded_order(scoped_pool) if item[0] not in chosen_ids]
    attempted = []
    wave = active_candidates
    resolved_count = 0
    storage_verification = {
        "status": "matched", "checked_record_count": 0, "block_number": state_block,
        "finalized_block_number": finalized_number, "scope": storage_scope, "rpc_profile": rpc_profile,
        "finalized_block_hash": finalized_hash, "matched_record_ids": [], "excluded_record_ids": [],
    }
    storage_mismatch = False
    while wave and len(attempted) < attempt_limit:
        verified_wave = []
        for record_id, state in wave:
            storage_verification["checked_record_count"] += 1
            try:
                _verify_contract_storage(client, registry_address=registry_address,
                    block_selector=state_selector, state_block=state_block,
                    finalized_block=finalized_number, scope=storage_scope, rpc_profile=rpc_profile,
                    lifecycle={record_id: state})
            except OnchainRpcError as exc:
                if rpc_profile == RPC_PROFILE_MYOTIS or exc.code.startswith("registry_v2_witness_"):
                    raise
                storage_mismatch = True
                storage_verification["excluded_record_ids"].append(record_id)
                record_errors.append(_record_resolution_error(record_id, str(state["record_hash"]), exc.code))
            else:
                storage_verification["matched_record_ids"].append(record_id)
                verified_wave.append((record_id, state))
        with ThreadPoolExecutor(max_workers=max(1, min(MAX_RECORD_FETCH_WORKERS, len(verified_wave)))) as pool:
            pending = {
                pool.submit(contextvars.copy_context().run, resolve_record, record_id, state): (record_id, state)
                for record_id, state in verified_wave
            }
            for future in as_completed(pending):
                record_id, state = pending[future]
                try:
                    record = future.result()
                except (Exception, SystemExit) as exc:
                    code = exc.code if isinstance(exc, OnchainRpcError) else "registry_record_fetch_failed"
                    record_errors.append(_record_resolution_error(record_id, str(state["record_hash"]), str(code)))
                    continue
                events[int(state["document_event_index"])]["registry_record"] = record
                resolved_count += 1
        attempted.extend(wave)
        count = min(target_count - resolved_count, attempt_limit - len(attempted))
        wave, reserves = reserves[:count], reserves[count:]
    active_candidates = attempted
    selected_record_ids = [record_id for record_id, _ in attempted]
    if selection_mode.startswith("discovery_facets"):
        selected_hint_count = sum(record_id in hinted_ids for record_id in selected_record_ids)
        selected_fallback_count = len(selected_record_ids) - selected_hint_count
    record_errors.sort(key=lambda value: value["record_id"])
    if storage_mismatch:
        storage_verification["status"] = "excluded_mismatched_records"
    elif cache_diagnostics["status"] != "disabled":
        _write_checkpoint(deployment, _checkpoint_payload(deployment, number=finalized_number,
            block_hash=finalized_hash, logs=logs, category_logs=category_logs or [],
            blocks=blocks, deployment_verification=deployment_verification,
            facets_verification=onchain_facet_diagnostics.get("deployment_verification"),
            observed_code_hashes=observed_code_hashes, complete=True), cache_diagnostics)
    budget = safe_http.discovery_budget.get()
    if budget is not None:
        cache_diagnostics["general_requests"] = budget.general_requests_used
        cache_diagnostics["history_transport_requests"] = budget.history_requests_used
    return {
        **({"projection_origin": "finalized_storage"} if deployment.registry_version == 2 else {}),
        "schema": CONTRACT_EVENTS_SCHEMA,
        "implementation": DIRECT_RPC_IMPLEMENTATION,
        "completeness_authority": "rpc_asserted_complete",
        "source": "myotis_verified_json_rpc" if rpc_profile == RPC_PROFILE_MYOTIS else "direct_json_rpc",
        "rpc": {
            "profile": rpc_profile,
            "client_version": client_version,
            **profile_details,
            "checkpoint": cache_diagnostics,
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
        "admissions": admissions,
        "admission_verification": admission_verification,
        "record_selection": {
            "schema": "agentcart.onchain_registry_candidate_selection.v1",
            "algorithm": "sha256-rejection-sparse-fisher-yates" if deployment.registry_version == 2 else "sha256-query-seeded-record-id-sample",
            "seed_sha256": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            "active_candidate_count": v2_active_count if deployment.registry_version == 2 else len(active_pool),
            "selection_scope_count": len(scoped_pool),
            "selection_mode": selection_mode,
            "candidate_limit": attempt_limit,
            "target_candidate_count": target_count,
            "selection_nonce": seed,
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
    document: dict[str, Any] = {"error": error.code if error.code == "history_sync_incomplete" else "onchain_registry_rpc_failed",
                                "code": error.code, "detail": error.detail}
    if hasattr(error, "diagnostics"):
        document["diagnostics"] = error.diagnostics
    if hasattr(error, "progress"):
        document["authority"] = "smart_contract"
        document["progress"] = error.progress
    return json.dumps(document, sort_keys=True)
