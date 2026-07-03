#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import datetime as dt
import importlib.util
import json
import pathlib
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from typing import Any


GATEWAY_DIR = pathlib.Path(__file__).resolve().parents[1]
AGENTCART_PATH = GATEWAY_DIR / "agentcart.py"
SPEC = importlib.util.spec_from_file_location("agentcart", AGENTCART_PATH)
agentcart = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["agentcart"] = agentcart
SPEC.loader.exec_module(agentcart)


def load_json_file(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{url} did not return a JSON object")
    return data


def dump_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def iso_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def manifest_url_for(manifest: dict[str, Any], supplied_url: str = "") -> str:
    url = supplied_url or str(manifest.get("manifest_url") or "")
    if not url:
        endpoints = manifest.get("endpoints") if isinstance(manifest.get("endpoints"), dict) else {}
        url = str(endpoints.get("manifest") or "")
    if not url:
        raise ValueError("manifest URL is required; pass --manifest-url or publish manifest_url in the manifest")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"manifest URL is invalid: {url}")
    return url


def origin_for(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def proof_url_for(manifest: dict[str, Any], manifest_url: str, supplied_url: str = "") -> str:
    if supplied_url:
        return supplied_url
    discovery = manifest.get("discovery") if isinstance(manifest.get("discovery"), dict) else {}
    proof = discovery.get("registry_proof") if isinstance(discovery.get("registry_proof"), dict) else {}
    proof_url = str(proof.get("url") or "")
    if proof_url:
        return proof_url
    return origin_for(manifest_url) + "/.well-known/agentcart-registry-proof.json"


def revocation_url_for(manifest: dict[str, Any], manifest_url: str, supplied_url: str = "") -> str:
    if supplied_url:
        return supplied_url
    discovery = manifest_discovery(manifest)
    revocation_url = str(discovery.get("revocation_url") or "")
    if revocation_url:
        return revocation_url
    claim = discovery.get("registry_claim") if isinstance(discovery.get("registry_claim"), dict) else {}
    revocation_url = str(claim.get("revocation_url") or "")
    if revocation_url:
        return revocation_url
    return ""


def manifest_discovery(manifest: dict[str, Any]) -> dict[str, Any]:
    return manifest.get("discovery") if isinstance(manifest.get("discovery"), dict) else {}


def suggested_record_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    discovery = manifest_discovery(manifest)
    record = discovery.get("suggested_registry_record")
    return copy.deepcopy(record) if isinstance(record, dict) else {}


def protocol_ids(manifest: dict[str, Any]) -> list[str]:
    profile_ids = protocol_profile_ids(manifest)
    protocols = manifest.get("protocols") if isinstance(manifest.get("protocols"), list) else []
    ids: list[str] = []
    for profile in protocol_profiles(manifest):
        payment_protocol_id = str(profile.get("payment_protocol_id") or "").strip()
        profile_id = str(profile.get("id") or "").strip()
        for protocol_id in [payment_protocol_id, profile_id]:
            if protocol_id and protocol_id not in ids:
                ids.append(protocol_id)
    for protocol in protocols:
        if not isinstance(protocol, dict):
            continue
        protocol_id = str(protocol.get("id") or protocol.get("protocol") or protocol.get("method") or "").strip()
        if protocol_id and protocol_id not in ids:
            ids.append(protocol_id)
    for profile_id in profile_ids:
        if profile_id not in ids:
            ids.append(profile_id)
    if "agentcart-shopbridge" not in ids:
        ids.insert(0, "agentcart-shopbridge")
    return ids


def protocol_profiles(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = manifest.get("protocol_profiles") if isinstance(manifest.get("protocol_profiles"), list) else []
    return [profile for profile in profiles if isinstance(profile, dict) and profile.get("id")]


def protocol_profile_ids(manifest: dict[str, Any]) -> list[str]:
    return [str(profile.get("id")) for profile in protocol_profiles(manifest) if profile.get("id")]


def tempo_payment_binding(manifest: dict[str, Any]) -> tuple[str, str]:
    for profile in protocol_profiles(manifest):
        profile_id = str(profile.get("id") or "")
        payment_protocol_id = str(profile.get("payment_protocol_id") or "")
        if profile_id in {"mpp-http-auth", "tempo-mpp"} or payment_protocol_id == "tempo-mpp":
            network = str(profile.get("network") or "").strip()
            recipient = str(profile.get("recipient") or "").strip()
            if network or recipient:
                return network, recipient
    protocols = manifest.get("protocols") if isinstance(manifest.get("protocols"), list) else []
    for protocol in protocols:
        if not isinstance(protocol, dict) or str(protocol.get("id") or "") != "tempo-mpp":
            continue
        network = str(protocol.get("network") or "").strip()
        recipient = str(protocol.get("recipient") or "").strip()
        if network or recipient:
            return network, recipient
    payment = manifest.get("payment") if isinstance(manifest.get("payment"), dict) else {}
    return str(payment.get("network") or "").strip(), str(payment.get("recipient") or "").strip()


def stripe_profile_id(manifest: dict[str, Any]) -> str:
    for profile in protocol_profiles(manifest):
        profile_id = str(profile.get("id") or "")
        payment_protocol_id = str(profile.get("payment_protocol_id") or "")
        if profile_id == "stripe-card-mpp" or payment_protocol_id == "stripe-card-mpp":
            value = str(profile.get("network_id") or profile.get("stripe_profile_id") or "").strip()
            if value:
                return value
    for protocol in manifest.get("protocols", []) if isinstance(manifest.get("protocols"), list) else []:
        if isinstance(protocol, dict) and str(protocol.get("id") or "") == "stripe-card-mpp":
            return str(protocol.get("network_id") or protocol.get("stripe_profile_id") or "").strip()
    return ""


def shipping_countries(manifest: dict[str, Any]) -> list[str]:
    delivery = manifest.get("delivery") if isinstance(manifest.get("delivery"), dict) else {}
    countries = [
        str(country).upper()
        for country in delivery.get("ship_to_countries", [])
        if country
    ]
    return sorted(dict.fromkeys(countries))


def manifest_endpoints(manifest: dict[str, Any]) -> dict[str, str]:
    endpoints = manifest.get("endpoints") if isinstance(manifest.get("endpoints"), dict) else {}
    return {
        key: str(value)
        for key, value in endpoints.items()
        if key in {"catalog", "quote", "orders", "order_status", "refunds"} and value
    }


def merchant_block(manifest: dict[str, Any]) -> dict[str, Any]:
    merchant = manifest.get("merchant") if isinstance(manifest.get("merchant"), dict) else {}
    if not merchant.get("id"):
        raise ValueError("manifest merchant.id is required")
    return merchant


def registry_claim(
    manifest: dict[str, Any],
    *,
    manifest_url: str = "",
    proof_url: str = "",
    revocation_url: str = "",
) -> dict[str, Any]:
    discovery = manifest_discovery(manifest)
    published_claim = discovery.get("registry_claim")
    if isinstance(published_claim, dict):
        return copy.deepcopy(published_claim)
    merchant = merchant_block(manifest)
    final_manifest_url = manifest_url_for(manifest, manifest_url)
    parsed_manifest_url = urllib.parse.urlparse(final_manifest_url)
    payment_network, payment_recipient = tempo_payment_binding(manifest)
    claim: dict[str, Any] = {
        "merchant_id": str(merchant["id"]),
        "name": str(merchant.get("name") or merchant["id"]),
        "domain": parsed_manifest_url.netloc.lower(),
        "manifest_url": final_manifest_url,
        "endpoints": manifest_endpoints(manifest),
        "supported_protocols": protocol_ids(manifest),
        "protocol_profile_ids": protocol_profile_ids(manifest),
        "payment_network": payment_network,
        "payment_recipient": payment_recipient,
        "stripe_profile_id": stripe_profile_id(manifest),
        "ship_to_countries": shipping_countries(manifest),
        "proof_url": proof_url_for(manifest, final_manifest_url, proof_url),
        "revocation_url": revocation_url_for(manifest, final_manifest_url, revocation_url),
    }
    return claim


def build_registry_record(
    manifest: dict[str, Any],
    *,
    manifest_url: str = "",
    updated_at: str = "",
    proof_url: str = "",
    revocation_url: str = "",
    signature_alg: str = "https-domain-proof",
    hmac_secret: str = "",
    include_manifest_snapshot: bool = False,
) -> dict[str, Any]:
    record = suggested_record_from_manifest(manifest)
    if record:
        if updated_at:
            record["updated_at"] = updated_at
        if proof_url:
            record["proof"] = {"type": "https-well-known", "url": proof_url}
        if revocation_url:
            record["revocation_url"] = revocation_url
        record["signature_alg"] = signature_alg
        record["signature"] = ""
    else:
        merchant = merchant_block(manifest)
        discovery = manifest_discovery(manifest)
        if isinstance(discovery.get("registry_claim"), dict):
            claim = registry_claim(
                manifest,
                manifest_url=manifest_url,
                proof_url=proof_url,
                revocation_url=revocation_url,
            )
            record = {
                **claim,
                "registry_claim_hash_alg": "sha-256",
                "registry_claim_hash": agentcart.canonical_json_hash(claim),
                "updated_at": updated_at or iso_now(),
                "revoked_at": None,
                "signature_alg": signature_alg,
                "signature": "",
            }
        else:
            final_manifest_url = manifest_url_for(manifest, manifest_url)
            parsed_manifest_url = urllib.parse.urlparse(final_manifest_url)
            payment_network, payment_recipient = tempo_payment_binding(manifest)
            record = {
                "merchant_id": str(merchant["id"]),
                "name": str(merchant.get("name") or merchant["id"]),
                "domain": parsed_manifest_url.netloc.lower(),
                "manifest_url": final_manifest_url,
                "manifest_hash_alg": "sha-256",
                "manifest_hash": agentcart.canonical_json_hash(manifest),
                "supported_protocols": protocol_ids(manifest),
                "protocol_profile_ids": protocol_profile_ids(manifest),
                "payment_network": payment_network,
                "payment_recipient": payment_recipient,
                "stripe_profile_id": stripe_profile_id(manifest),
                "ship_to_countries": shipping_countries(manifest),
                "revocation_url": revocation_url_for(manifest, final_manifest_url, revocation_url),
                "updated_at": updated_at or iso_now(),
                "revoked_at": None,
                "signature_alg": signature_alg,
                "signature": "",
            }
        if merchant.get("terms_url"):
            record["terms_url"] = str(merchant["terms_url"])
        if merchant.get("returns_url"):
            record["returns_url"] = str(merchant["returns_url"])
    if signature_alg in {"https-domain-proof", "agentcart-domain-v1"}:
        existing_proof_url = ""
        if isinstance(record.get("proof"), dict):
            existing_proof_url = str(record["proof"].get("url") or "")
        default_manifest_url = str(record.get("manifest_url") or manifest_url_for(manifest, manifest_url))
        record["proof"] = {
            "type": "https-well-known",
            "url": proof_url or existing_proof_url or str(record.get("proof_url") or "") or proof_url_for(manifest, default_manifest_url),
        }
    elif signature_alg == "hmac-sha256":
        if not hmac_secret:
            raise ValueError("--hmac-secret is required for hmac-sha256 records")
        record["signature"] = agentcart.hmac_registry_signature(record, hmac_secret)
    else:
        raise ValueError(f"unsupported signature algorithm: {signature_alg}")
    if include_manifest_snapshot:
        record["manifest_snapshot"] = manifest
    return record


def domain_proof_document(record: dict[str, Any]) -> dict[str, Any]:
    proof = {
        "merchant_id": str(record.get("merchant_id") or ""),
        "domain": str(record.get("domain") or ""),
        "manifest_url": str(record.get("manifest_url") or ""),
        "payment_network": str(record.get("payment_network") or ""),
        "payment_recipient": str(record.get("payment_recipient") or ""),
        "updated_at": str(record.get("updated_at") or ""),
        "record_hash": agentcart.registry_record_hash(record),
    }
    if record.get("revocation_url"):
        proof["revocation_url"] = str(record.get("revocation_url") or "")
    if record.get("registry_claim_hash"):
        proof["registry_claim_hash"] = str(record.get("registry_claim_hash") or "")
    else:
        proof["manifest_hash"] = str(record.get("manifest_hash") or "")
    identity = onchain_identity_payload(record)
    for field in ("controller", "chain_id", "registry_address", "record_id"):
        value = identity.get(field, "")
        if value:
            proof[field] = value
    return proof


def onboarding_bundle(record: dict[str, Any]) -> dict[str, Any]:
    manifest_hash = str(record.get("manifest_hash") or "")
    updated_at = str(record.get("updated_at") or "")
    record_hash = agentcart.registry_record_hash(record)
    return {
        "registry_record": record,
        "record_hash": record_hash,
        "merchant_action": "none if the ShopBridge manifest already contains discovery.suggested_registry_record; the plugin auto-publishes the proof hash and updated_at",
        "legacy_merchant_settings": {
            "AGENTCART_REGISTRY_MANIFEST_HASH": manifest_hash,
            "AGENTCART_REGISTRY_UPDATED_AT": updated_at,
            "AGENTCART_REGISTRY_RECORD_HASH": record_hash,
        } if manifest_hash else {},
        "proof_document_expected": domain_proof_document(record)
        if str(record.get("signature_alg") or "") in {"https-domain-proof", "agentcart-domain-v1"}
        else None,
        "registry_feed": {
            "entries": [record],
        },
        "next_steps": [
            "Add registry_record to the public AgentCart registry feed.",
            "If this record came from ShopBridge discovery.suggested_registry_record, the plugin already publishes the matching proof.",
            "Only legacy/non-ShopBridge manifests need manual paste-back settings.",
            "Run verify against the registry record after the shop proof endpoint updates.",
        ],
    }


ONCHAIN_REQUIRED_FIELDS = (
    "record_hash",
    "record_hash_alg",
    "merchant_id",
    "domain",
    "manifest_url",
    "registry_claim_hash_alg",
    "registry_claim_hash",
    "payment_network",
    "payment_recipient",
    "updated_at",
    "revocation_url",
)

ONCHAIN_OPTIONAL_LIST_FIELDS = (
    "protocol_profile_ids",
    "supported_protocols",
    "ship_to_countries",
)

ONCHAIN_IDENTITY_FIELDS = (
    "controller",
    "chain_id",
    "registry_address",
    "record_id",
    "agent_id",
    "registration_uri",
    "registration_tx_hash",
    "attestation_hash",
)


ONCHAIN_LEDGER_EVENT_SCHEMA = "agentcart.onchain_registry_ledger_event.v1"
ONCHAIN_LEDGER_INDEX_SCHEMA = "agentcart.onchain_registry_ledger_index.v1"
ONCHAIN_LEDGER_PROOF_SCHEMA = "agentcart.onchain_registry_ledger_proof.v1"
ONCHAIN_CONTRACT_EVENTS_SCHEMA = "agentcart.onchain_registry_contract_events.v1"
ONCHAIN_CONTRACT_INDEX_SCHEMA = "agentcart.onchain_registry_contract_index.v1"


def raw_onchain_identity(record: dict[str, Any]) -> Any:
    if "onchain_identity" in record:
        return record.get("onchain_identity")
    return record.get("erc8004_identity")


def onchain_identity_payload(record: dict[str, Any]) -> dict[str, str]:
    raw = raw_onchain_identity(record)
    if not isinstance(raw, dict):
        return {}
    aliases = {
        "chain": "chain_id",
        "chainId": "chain_id",
        "controller_address": "controller",
        "merchant_controller": "controller",
        "registry": "registry_address",
        "registry_contract": "registry_address",
        "contract": "registry_address",
        "service_id": "agent_id",
        "id": "record_id",
        "tx_hash": "registration_tx_hash",
        "transaction_hash": "registration_tx_hash",
        "uri": "registration_uri",
    }
    payload: dict[str, str] = {}
    for source_key in (
        "chain_id",
        "chain",
        "chainId",
        "controller",
        "controller_address",
        "merchant_controller",
        "registry_address",
        "registry",
        "registry_contract",
        "contract",
        "record_id",
        "id",
        "agent_id",
        "service_id",
        "registration_uri",
        "uri",
        "registration_tx_hash",
        "tx_hash",
        "transaction_hash",
        "attestation_hash",
    ):
        target_key = aliases.get(source_key, source_key)
        if target_key in payload:
            continue
        text = str(raw.get(source_key) or "").strip()
        if text:
            payload[target_key] = text
    return payload


def non_empty_string(value: Any) -> str:
    return str(value or "").strip()


def is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value)


def strip_hex_prefix(value: Any) -> str:
    text = str(value or "").strip()
    return text[2:] if text.lower().startswith("0x") else text


def is_bytes32_hex(value: Any) -> bool:
    text = strip_hex_prefix(value)
    return len(text) == 64 and all(character in "0123456789abcdefABCDEF" for character in text)


def normalize_bytes32_hex(value: Any, *, with_prefix: bool = False) -> str:
    text = strip_hex_prefix(value).lower()
    return f"0x{text}" if with_prefix and text else text


def onchain_projection(record: dict[str, Any]) -> dict[str, Any]:
    projection: dict[str, Any] = {
        "record_hash": agentcart.registry_record_hash(record),
        "record_hash_alg": "sha-256",
    }
    scalar_fields = (
        "merchant_id",
        "domain",
        "manifest_url",
        "payment_network",
        "payment_recipient",
        "updated_at",
        "revocation_url",
    )
    for field in scalar_fields:
        value = non_empty_string(record.get(field))
        if value:
            projection[field] = value
    registry_claim_hash = non_empty_string(record.get("registry_claim_hash"))
    registry_claim_hash_alg = non_empty_string(record.get("registry_claim_hash_alg")) or "sha-256"
    if registry_claim_hash:
        projection["registry_claim_hash_alg"] = registry_claim_hash_alg
        projection["registry_claim_hash"] = registry_claim_hash

    identity = onchain_identity_payload(record)
    for field in ONCHAIN_IDENTITY_FIELDS:
        value = identity.get(field, "")
        if value:
            projection[field] = value

    for field in ONCHAIN_OPTIONAL_LIST_FIELDS:
        values = record.get(field)
        if isinstance(values, list):
            cleaned = [str(value).strip() for value in values if str(value).strip()]
            if cleaned:
                projection[field] = cleaned

    missing = [field for field in ONCHAIN_REQUIRED_FIELDS if not projection.get(field)]
    if missing:
        raise ValueError(f"onchain projection missing required fields: {', '.join(missing)}")
    if str(projection["registry_claim_hash_alg"]).lower() not in {"sha-256", "sha256"}:
        raise ValueError("onchain projection unsupported registry_claim_hash_alg")
    if not is_sha256_hex(str(projection["registry_claim_hash"])):
        raise ValueError("onchain projection registry_claim_hash must be a SHA-256 hex digest")
    return projection


def hash_without(value: dict[str, Any], field: str) -> str:
    return agentcart.canonical_json_hash({key: item for key, item in value.items() if key != field})


def onchain_ledger_event_hash(event: dict[str, Any]) -> str:
    return hash_without(event, "event_hash")


def load_onchain_ledger_events(path: pathlib.Path) -> list[dict[str, Any]]:
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw_lines, start=1):
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        events.append(event)
    return events


def verify_onchain_ledger_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    previous_hash = ""
    for index, event in enumerate(events, start=1):
        sequence = int(event.get("sequence") or 0)
        if sequence != index:
            errors.append({"sequence": index, "error": "sequence_mismatch", "actual": sequence})
        if str(event.get("schema") or "") != ONCHAIN_LEDGER_EVENT_SCHEMA:
            errors.append({"sequence": index, "error": "schema_mismatch"})
        supplied_previous = str(event.get("previous_event_hash") or "")
        if supplied_previous != previous_hash:
            errors.append({"sequence": index, "error": "previous_event_hash_mismatch"})
        supplied_hash = str(event.get("event_hash") or "")
        actual_hash = onchain_ledger_event_hash(event)
        if not supplied_hash or supplied_hash != actual_hash:
            errors.append({"sequence": index, "error": "event_hash_mismatch", "actual": actual_hash})
        operation = str(event.get("operation") or "")
        if operation not in {"upsert", "revoke"}:
            errors.append({"sequence": index, "error": "operation_mismatch"})
        record_hash = str(event.get("record_hash") or "")
        if not is_sha256_hex(record_hash):
            errors.append({"sequence": index, "error": "record_hash_invalid"})
        if operation == "upsert":
            onchain_record = event.get("onchain_record")
            if not isinstance(onchain_record, dict):
                errors.append({"sequence": index, "error": "onchain_record_missing"})
            elif str(onchain_record.get("record_hash") or "") != record_hash:
                errors.append({"sequence": index, "error": "onchain_record_hash_mismatch"})
        previous_hash = supplied_hash
    return {
        "chain_valid": not errors,
        "errors": errors,
        "event_count": len(events),
        "log_head_hash": previous_hash if events else "",
        "hash_alg": "sha-256",
    }


def onchain_ledger_event(
    events: list[dict[str, Any]],
    *,
    operation: str,
    record_hash: str,
    created_at: str,
    onchain_record: dict[str, Any] | None = None,
    merchant_id: str = "",
    domain: str = "",
    reason: str = "",
) -> dict[str, Any]:
    if operation not in {"upsert", "revoke"}:
        raise ValueError("operation must be upsert or revoke")
    if not is_sha256_hex(record_hash):
        raise ValueError("record_hash must be a SHA-256 hex digest")
    previous_hash = str(events[-1].get("event_hash") or "") if events else ""
    event: dict[str, Any] = {
        "schema": ONCHAIN_LEDGER_EVENT_SCHEMA,
        "sequence": len(events) + 1,
        "operation": operation,
        "created_at": created_at,
        "record_hash": record_hash,
        "record_hash_alg": "sha-256",
        "merchant_id": merchant_id,
        "domain": domain,
        "previous_event_hash": previous_hash,
        "hash_alg": "sha-256",
    }
    if operation == "upsert":
        if onchain_record is None:
            raise ValueError("onchain_record is required for upsert")
        event["onchain_record"] = onchain_record
        event["onchain_record_hash"] = agentcart.canonical_json_hash(onchain_record)
    if operation == "revoke":
        event["reason"] = reason or "merchant_admin_revoke"
    event["event_hash"] = onchain_ledger_event_hash(event)
    return event


def append_onchain_ledger_event(
    path: pathlib.Path,
    *,
    operation: str,
    record: dict[str, Any] | None = None,
    record_hash: str = "",
    created_at: str = "",
    reason: str = "",
) -> dict[str, Any]:
    events = load_onchain_ledger_events(path)
    verification = verify_onchain_ledger_events(events)
    if not verification["chain_valid"]:
        raise ValueError("onchain ledger chain is invalid")
    onchain_record = onchain_projection(record) if record is not None else None
    final_record_hash = record_hash or str((onchain_record or {}).get("record_hash") or "")
    event = onchain_ledger_event(
        events,
        operation=operation,
        record_hash=final_record_hash,
        created_at=created_at or iso_now(),
        onchain_record=onchain_record,
        merchant_id=str((onchain_record or record or {}).get("merchant_id") or ""),
        domain=str((onchain_record or record or {}).get("domain") or ""),
        reason=reason,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    return event


def onchain_ledger_proof(
    *,
    record_hashes: list[str],
    revocation_record_hashes: list[str],
    verification: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema": ONCHAIN_LEDGER_PROOF_SCHEMA,
        "record_hashes": record_hashes,
        "revocation_record_hashes": revocation_record_hashes,
        "records_hash": agentcart.canonical_json_hash(record_hashes),
        "revocations_hash": agentcart.canonical_json_hash(revocation_record_hashes),
        "log_head_hash": str(verification.get("log_head_hash") or ""),
        "event_count": int(verification.get("event_count") or 0),
        "hash_alg": "sha-256",
    }
    return {
        **payload,
        "payload_hash": agentcart.canonical_json_hash(payload),
    }


def index_onchain_ledger_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    verification = verify_onchain_ledger_events(events)
    if not verification["chain_valid"]:
        return {
            "schema": ONCHAIN_LEDGER_INDEX_SCHEMA,
            "generated_at": iso_now(),
            "source": "append_only_jsonl",
            "event_count": len(events),
            "log_head_hash": str(verification.get("log_head_hash") or ""),
            "verification": verification,
            "records": [],
            "revocations": [],
            "proof": onchain_ledger_proof(
                record_hashes=[],
                revocation_record_hashes=[],
                verification=verification,
            ),
        }
    active: dict[str, dict[str, Any]] = {}
    revocations: dict[str, dict[str, Any]] = {}
    for event in events:
        operation = str(event.get("operation") or "")
        record_hash = str(event.get("record_hash") or "")
        if not is_sha256_hex(record_hash):
            continue
        if operation == "upsert" and isinstance(event.get("onchain_record"), dict):
            active[record_hash] = copy.deepcopy(event["onchain_record"])
            revocations.pop(record_hash, None)
        elif operation == "revoke":
            active.pop(record_hash, None)
            revocations[record_hash] = {
                "record_hash": record_hash,
                "merchant_id": str(event.get("merchant_id") or ""),
                "domain": str(event.get("domain") or ""),
                "revoked_at": str(event.get("created_at") or ""),
                "reason": str(event.get("reason") or ""),
                "event_hash": str(event.get("event_hash") or ""),
            }
    records = sorted(active.values(), key=lambda item: (str(item.get("domain") or ""), str(item.get("merchant_id") or ""), str(item.get("record_hash") or "")))
    revocation_list = sorted(revocations.values(), key=lambda item: str(item.get("record_hash") or ""))
    record_hashes = [str(record.get("record_hash") or "") for record in records]
    revocation_record_hashes = [str(item.get("record_hash") or "") for item in revocation_list]
    return {
        "schema": ONCHAIN_LEDGER_INDEX_SCHEMA,
        "generated_at": iso_now(),
        "source": "append_only_jsonl",
        "event_count": len(events),
        "log_head_hash": str(verification.get("log_head_hash") or ""),
        "verification": verification,
        "records": records,
        "revocations": revocation_list,
        "proof": onchain_ledger_proof(
            record_hashes=record_hashes,
            revocation_record_hashes=revocation_record_hashes,
            verification=verification,
        ),
    }


def load_onchain_contract_events(path: pathlib.Path) -> list[dict[str, Any]]:
    document = load_json_file(path)
    if isinstance(document, dict):
        if str(document.get("schema") or "") != ONCHAIN_CONTRACT_EVENTS_SCHEMA:
            raise ValueError("contract events fixture schema mismatch")
        events = document.get("events")
    else:
        events = document
    if not isinstance(events, list):
        raise ValueError("contract events fixture must contain an events array")
    result: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise ValueError(f"contract event {index} must be an object")
        result.append(event)
    return result


def contract_event_args(event: dict[str, Any]) -> dict[str, Any]:
    args = event.get("args")
    return args if isinstance(args, dict) else {}


def contract_event_arg(args: dict[str, Any], *names: str) -> str:
    for name in names:
        value = args.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def contract_event_record_id(event: dict[str, Any]) -> str:
    args = contract_event_args(event)
    return normalize_bytes32_hex(contract_event_arg(args, "recordId", "record_id"), with_prefix=True)


def contract_event_record_hash(event: dict[str, Any]) -> str:
    args = contract_event_args(event)
    return normalize_bytes32_hex(contract_event_arg(args, "recordHash", "record_hash"), with_prefix=False)


def contract_event_stream_hash(events: list[dict[str, Any]]) -> str:
    return agentcart.canonical_json_hash(events) if events else ""


def verify_onchain_contract_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    allowed_events = {
        "MerchantRegistered",
        "MerchantUpdated",
        "ControllerChanged",
        "MerchantRevoked",
        "MerchantAttested",
        "MerchantSuspended",
        "MerchantUnsuspended",
        "MerchantFlagged",
    }
    for sequence, event in enumerate(events, start=1):
        event_name = str(event.get("event") or "")
        args = contract_event_args(event)
        if event_name not in allowed_events:
            errors.append({"sequence": sequence, "error": "event_name_unsupported", "event": event_name})
            continue
        if not args:
            errors.append({"sequence": sequence, "error": "event_args_missing", "event": event_name})
            continue
        record_id = contract_event_record_id(event)
        if not is_bytes32_hex(record_id):
            errors.append({"sequence": sequence, "error": "record_id_invalid", "event": event_name})
        if event_name in {"MerchantRegistered", "MerchantUpdated", "MerchantAttested"}:
            record_hash = contract_event_record_hash(event)
            if not is_sha256_hex(record_hash):
                errors.append({"sequence": sequence, "error": "record_hash_invalid", "event": event_name})
        if event_name in {"MerchantRegistered", "MerchantUpdated"}:
            onchain_record = event.get("onchain_record")
            if not isinstance(onchain_record, dict):
                errors.append({"sequence": sequence, "error": "onchain_record_missing", "event": event_name})
            elif str(onchain_record.get("record_hash") or "").lower() != contract_event_record_hash(event):
                errors.append({"sequence": sequence, "error": "onchain_record_hash_mismatch", "event": event_name})
        if event_name == "MerchantRegistered":
            controller = contract_event_arg(args, "controller")
            if controller and not re.fullmatch(r"0x[0-9a-fA-F]{40}", controller):
                errors.append({"sequence": sequence, "error": "controller_invalid", "event": event_name})
            domain_hash = contract_event_arg(args, "domainHash", "domain_hash")
            if domain_hash and not is_bytes32_hex(domain_hash):
                errors.append({"sequence": sequence, "error": "domain_hash_invalid", "event": event_name})
        if event_name == "MerchantAttested":
            validator = contract_event_arg(args, "validator")
            if validator and not re.fullmatch(r"0x[0-9a-fA-F]{40}", validator):
                errors.append({"sequence": sequence, "error": "validator_invalid", "event": event_name})
    return {
        "chain_valid": not errors,
        "errors": errors,
        "event_count": len(events),
        "log_head_hash": contract_event_stream_hash(events) if events else "",
        "hash_alg": "sha-256",
    }


def index_onchain_contract_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    verification = verify_onchain_contract_events(events)
    if not verification["chain_valid"]:
        return {
            "schema": ONCHAIN_CONTRACT_INDEX_SCHEMA,
            "generated_at": iso_now(),
            "source": "contract_events",
            "event_count": len(events),
            "log_head_hash": str(verification.get("log_head_hash") or ""),
            "verification": verification,
            "records": [],
            "revocations": [],
            "attestations": [],
            "suspensions": [],
            "flags": [],
            "proof": onchain_ledger_proof(
                record_hashes=[],
                revocation_record_hashes=[],
                verification=verification,
            ),
        }

    active_by_record_id: dict[str, dict[str, Any]] = {}
    revocations: dict[str, dict[str, Any]] = {}
    attestations: dict[str, dict[str, Any]] = {}
    suspensions: dict[str, dict[str, Any]] = {}
    flags: list[dict[str, Any]] = []
    for sequence, event in enumerate(events, start=1):
        event_name = str(event.get("event") or "")
        args = contract_event_args(event)
        record_id = contract_event_record_id(event)
        record_hash = contract_event_record_hash(event)
        event_ref = {
            "event": event_name,
            "sequence": sequence,
            "block_number": int(event.get("block_number") or 0),
            "transaction_hash": str(event.get("transaction_hash") or ""),
            "log_index": int(event.get("log_index") or 0),
        }
        if event_name in {"MerchantRegistered", "MerchantUpdated"} and isinstance(event.get("onchain_record"), dict):
            active_by_record_id[record_id] = copy.deepcopy(event["onchain_record"])
            active_by_record_id[record_id].setdefault("record_id", record_id)
            revocations.pop(record_hash, None)
            attestations.pop(record_id, None)
            suspensions.pop(record_id, None)
        elif event_name == "MerchantRevoked":
            current = active_by_record_id.pop(record_id, None)
            final_hash = str((current or {}).get("record_hash") or record_hash)
            if final_hash:
                revocations[final_hash] = {
                    "record_hash": final_hash,
                    "record_id": record_id,
                    "revoked_at": str(event.get("block_time") or event.get("created_at") or ""),
                    "reason_hash": contract_event_arg(args, "reasonHash", "reason_hash"),
                    **event_ref,
                }
            attestations.pop(record_id, None)
            suspensions.pop(record_id, None)
        elif event_name == "MerchantAttested":
            if record_id in active_by_record_id and active_by_record_id[record_id].get("record_hash") == record_hash:
                attestations[record_id] = {
                    "record_id": record_id,
                    "record_hash": record_hash,
                    "validator": contract_event_arg(args, "validator"),
                    "result_hash": contract_event_arg(args, "resultHash", "result_hash"),
                    "expires_at": str(contract_event_arg(args, "expiresAt", "expires_at")),
                    "evidence_uri": str(contract_event_arg(args, "evidenceURI", "evidence_uri")),
                    **event_ref,
                }
        elif event_name == "MerchantSuspended":
            suspensions[record_id] = {
                "record_id": record_id,
                "reason_hash": contract_event_arg(args, "reasonHash", "reason_hash"),
                **event_ref,
            }
        elif event_name == "MerchantUnsuspended":
            suspensions.pop(record_id, None)
        elif event_name == "MerchantFlagged":
            flags.append(
                {
                    "record_id": record_id,
                    "flagger": contract_event_arg(args, "flagger"),
                    "challenge_type": contract_event_arg(args, "challengeType", "challenge_type"),
                    "evidence_uri": contract_event_arg(args, "evidenceURI", "evidence_uri"),
                    **event_ref,
                }
            )

    active_records = [
        record
        for record_id, record in active_by_record_id.items()
        if record_id not in suspensions
    ]
    records = sorted(active_records, key=lambda item: (str(item.get("domain") or ""), str(item.get("merchant_id") or ""), str(item.get("record_hash") or "")))
    revocation_list = sorted(revocations.values(), key=lambda item: str(item.get("record_hash") or ""))
    attestation_list = sorted(attestations.values(), key=lambda item: str(item.get("record_id") or ""))
    suspension_list = sorted(suspensions.values(), key=lambda item: str(item.get("record_id") or ""))
    record_hashes = [str(record.get("record_hash") or "") for record in records]
    revocation_record_hashes = [str(item.get("record_hash") or "") for item in revocation_list]
    return {
        "schema": ONCHAIN_CONTRACT_INDEX_SCHEMA,
        "generated_at": iso_now(),
        "source": "contract_events",
        "event_count": len(events),
        "log_head_hash": str(verification.get("log_head_hash") or ""),
        "verification": verification,
        "records": records,
        "revocations": revocation_list,
        "attestations": attestation_list,
        "suspensions": suspension_list,
        "flags": flags,
        "proof": onchain_ledger_proof(
            record_hashes=record_hashes,
            revocation_record_hashes=revocation_record_hashes,
            verification=verification,
        ),
    }


def minimal_config(tmp: pathlib.Path, *, hmac_secret: str = "", max_age_days: int = 180) -> Any:
    return agentcart.Config(
        bind="127.0.0.1",
        port=8099,
        timezone="Europe/Berlin",
        public_url="http://agentcart.test",
        agentcart_token="",
        state_path=tmp / "state.json",
        audit_log_path=tmp / "audit.jsonl",
        policy_path=None,
        homeassistant_url="",
        homeassistant_token="",
        ha_notify_services=(),
        homeassistant_calendar_entity_id="",
        energy_solar_power_entity="sensor.solar_power",
        energy_battery_level_entity="sensor.battery_level",
        energy_battery_power_entity="sensor.battery_power",
        energy_grid_export_entity="sensor.grid_export",
        energy_grid_import_entity="sensor.grid_import",
        energy_house_output_entity="sensor.house_output",
        energy_min_export_w=100.0,
        energy_min_battery_percent=70.0,
        vikunja_api_url="",
        vikunja_web_url="",
        vikunja_token="",
        vikunja_project_id=None,
        default_ship_country="DE",
        default_ship_postal_code="10115",
        woocommerce_mode="disabled",
        woocommerce_base_url="",
        woocommerce_consumer_key="",
        woocommerce_consumer_secret="",
        woocommerce_agentcart_token="",
        woocommerce_signed_request_secret="",
        woocommerce_signed_request_private_key="",
        woocommerce_signed_request_signer="agentcart-service",
        woocommerce_merchant_id="woocommerce-demo-tea",
        woocommerce_merchant_name="Woo Demo Tea Shop",
        payment_provider="demo",
        agentcash_proof_url="",
        agentcash_command="",
        agentcash_proof_required=False,
        agentcash_timeout_seconds=5,
        tempo_mpp_endpoint="",
        tempo_mpp_proof_url="",
        tempo_mpp_command="npx mppx",
        tempo_mpp_network="testnet",
        tempo_mpp_account="agentcart-test",
        tempo_mpp_proof_required=False,
        tempo_mpp_timeout_seconds=5,
        tempo_mpp_recipient_address="",
        delivery_calendar_enabled=False,
        delivery_calendar_token="",
        merchant_registry_path=None,
        merchant_registry_url="",
        merchant_registry_hmac_secret=hmac_secret,
        require_verified_registry=True,
        merchant_registry_max_age_days=max_age_days,
        hosted_registry_enabled=False,
        hosted_registry_path=tmp / "hosted-registry.json",
        hosted_registry_submit_token="",
        registry_feed_proof_private_key="",
        registry_feed_proof_signer="agentcart-registry",
        registry_feed_proof_public_key_url="",
        registry_feed_proof_anchor_url="",
        registry_feed_proof_anchor_chain_id="",
        registry_feed_proof_retiring_signers=(),
        registry_feed_proof_rotation_due_at="",
        registry_monitor_interval_seconds=0,
        registry_monitor_history_limit=50,
        registry_alert_webhook_url="",
        registry_alert_webhook_token="",
        registry_alert_homeassistant_enabled=False,
        registry_alert_email_to=(),
        registry_alert_email_from="",
        registry_alert_smtp_host="",
        registry_alert_smtp_port=587,
        registry_alert_smtp_username="",
        registry_alert_smtp_password="",
        registry_alert_smtp_starttls=True,
        registry_alert_min_severity="warning",
        registry_alert_include_resolved=True,
        ops_event_webhook_url="",
        ops_event_webhook_token="",
        ops_event_homeassistant_enabled=False,
        ops_event_email_to=(),
        ops_event_email_from="",
        ops_event_smtp_host="",
        ops_event_smtp_port=587,
        ops_event_smtp_username="",
        ops_event_smtp_password="",
        ops_event_smtp_starttls=True,
        ops_event_min_severity="warning",
    )


def verify_registry_record(
    record: dict[str, Any],
    *,
    manifest_snapshot: dict[str, Any] | None = None,
    proof_snapshot: dict[str, Any] | None = None,
    revocation_snapshot: dict[str, Any] | None = None,
    hmac_secret: str = "",
    max_age_days: int = 180,
) -> dict[str, Any]:
    candidate = copy.deepcopy(record)
    if manifest_snapshot is not None:
        candidate["manifest_snapshot"] = manifest_snapshot
    if proof_snapshot is not None:
        candidate["proof_snapshot"] = proof_snapshot
    if revocation_snapshot is not None:
        candidate["revocation_snapshot"] = revocation_snapshot
    with tempfile.TemporaryDirectory() as raw_tmp:
        service = agentcart.AgentCartService(
            minimal_config(pathlib.Path(raw_tmp), hmac_secret=hmac_secret, max_age_days=max_age_days)
        )
        entry = service.verify_registry_record(candidate)
    verification = entry.get("verification") if isinstance(entry.get("verification"), dict) else {}
    return {
        "ok": verification.get("state") == "verified",
        "verification": verification,
        "entry": {key: value for key, value in entry.items() if not key.startswith("_")},
    }


def emit(value: Any, output_path: pathlib.Path | None = None) -> None:
    rendered = value if isinstance(value, str) else dump_json(value)
    if output_path:
        output_path.write_text(rendered)
    else:
        sys.stdout.write(rendered)


def build_command(args: argparse.Namespace) -> int:
    if args.manifest_file:
        manifest = load_json_file(args.manifest_file)
    else:
        manifest = fetch_json(args.manifest_url)
    record = build_registry_record(
        manifest,
        manifest_url=args.manifest_url,
        updated_at=args.updated_at,
        proof_url=args.proof_url,
        revocation_url=args.revocation_url,
        signature_alg=args.signature_alg,
        hmac_secret=args.hmac_secret,
        include_manifest_snapshot=args.include_manifest_snapshot,
    )
    bundle = onboarding_bundle(record)
    if args.format == "record":
        output: Any = record
    elif args.format == "feed":
        output = bundle["registry_feed"]
    elif args.format == "env":
        settings = bundle["legacy_merchant_settings"]
        output = (
            "".join(f"{key}={value}\n" for key, value in settings.items())
            if settings
            else "# no merchant env paste-back is required for this ShopBridge manifest\n"
        )
    elif args.format == "onchain":
        output = onchain_projection(record)
    else:
        output = bundle
    emit(output, args.output)
    return 0


def project_onchain_command(args: argparse.Namespace) -> int:
    record = load_json_file(args.record_file)
    emit(onchain_projection(record), args.output)
    return 0


def append_onchain_command(args: argparse.Namespace) -> int:
    record = load_json_file(args.record_file) if args.record_file else None
    event = append_onchain_ledger_event(
        args.ledger_file,
        operation=args.operation,
        record=record,
        record_hash=args.record_hash,
        created_at=args.created_at,
        reason=args.reason,
    )
    emit(event, args.output)
    return 0


def index_onchain_command(args: argparse.Namespace) -> int:
    events = load_onchain_ledger_events(args.ledger_file)
    index = index_onchain_ledger_events(events)
    emit(index, args.output)
    return 0 if index["verification"]["chain_valid"] else 1


def index_contract_events_command(args: argparse.Namespace) -> int:
    events = load_onchain_contract_events(args.events_file)
    index = index_onchain_contract_events(events)
    emit(index, args.output)
    return 0 if index["verification"]["chain_valid"] else 1


def verify_command(args: argparse.Namespace) -> int:
    record = load_json_file(args.record_file)
    manifest = load_json_file(args.manifest_file) if args.manifest_file else None
    proof = load_json_file(args.proof_file) if args.proof_file else None
    revocation = load_json_file(args.revocation_file) if args.revocation_file else None
    result = verify_registry_record(
        record,
        manifest_snapshot=manifest,
        proof_snapshot=proof,
        revocation_snapshot=revocation,
        hmac_secret=args.hmac_secret,
        max_age_days=args.max_age_days,
    )
    emit(result, args.output)
    return 0 if result["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and verify AgentCart merchant registry records from ShopBridge manifests."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a registry record from a ShopBridge manifest")
    manifest_source = build.add_mutually_exclusive_group(required=True)
    manifest_source.add_argument("--manifest-url", default="", help="Manifest URL to fetch and register")
    manifest_source.add_argument("--manifest-file", type=pathlib.Path, help="Local manifest JSON file")
    build.add_argument("--updated-at", default="", help="Registry record timestamp, for example 2026-06-22T10:00:00Z")
    build.add_argument("--proof-url", default="", help="Override the domain-proof URL")
    build.add_argument("--revocation-url", default="", help="Override the registry revocation URL")
    build.add_argument(
        "--signature-alg",
        default="https-domain-proof",
        choices=["https-domain-proof", "agentcart-domain-v1", "hmac-sha256"],
    )
    build.add_argument("--hmac-secret", default="", help="Shared secret for hmac-sha256 private feeds")
    build.add_argument("--include-manifest-snapshot", action="store_true", help="Embed manifest_snapshot for local tests")
    build.add_argument("--format", choices=["bundle", "record", "feed", "env", "onchain"], default="bundle")
    build.add_argument("--output", type=pathlib.Path, help="Write output to a file instead of stdout")
    build.set_defaults(func=build_command)

    project_onchain = subparsers.add_parser(
        "project-onchain",
        help="Project an existing registry record to the smart-contract-facing adapter shape",
    )
    project_onchain.add_argument("--record-file", type=pathlib.Path, required=True)
    project_onchain.add_argument("--output", type=pathlib.Path, help="Write output to a file instead of stdout")
    project_onchain.set_defaults(func=project_onchain_command)

    append_onchain = subparsers.add_parser(
        "append-onchain",
        help="Append an upsert or revoke event to an append-only onchain registry ledger",
    )
    append_onchain.add_argument("--ledger-file", type=pathlib.Path, required=True)
    append_onchain.add_argument("--operation", choices=["upsert", "revoke"], required=True)
    append_onchain.add_argument("--record-file", type=pathlib.Path, help="Registry record JSON file for upsert or revoke metadata")
    append_onchain.add_argument("--record-hash", default="", help="Record hash to revoke when --record-file is omitted")
    append_onchain.add_argument("--created-at", default="", help="Event timestamp, for example 2026-06-22T10:00:00Z")
    append_onchain.add_argument("--reason", default="", help="Revocation reason for revoke events")
    append_onchain.add_argument("--output", type=pathlib.Path, help="Write appended event to a file instead of stdout")
    append_onchain.set_defaults(func=append_onchain_command)

    index_onchain = subparsers.add_parser(
        "index-onchain",
        help="Verify and index an append-only onchain registry ledger",
    )
    index_onchain.add_argument("--ledger-file", type=pathlib.Path, required=True)
    index_onchain.add_argument("--output", type=pathlib.Path, help="Write output to a file instead of stdout")
    index_onchain.set_defaults(func=index_onchain_command)

    index_contract_events = subparsers.add_parser(
        "index-contract-events",
        help="Verify and index smart-contract registry events into the onchain adapter shape",
    )
    index_contract_events.add_argument("--events-file", type=pathlib.Path, required=True)
    index_contract_events.add_argument("--output", type=pathlib.Path, help="Write output to a file instead of stdout")
    index_contract_events.set_defaults(func=index_contract_events_command)

    verify = subparsers.add_parser("verify", help="Verify a registry record using the gateway verifier")
    verify.add_argument("--record-file", type=pathlib.Path, required=True)
    verify.add_argument("--manifest-file", type=pathlib.Path, help="Use a local manifest snapshot instead of fetching")
    verify.add_argument("--proof-file", type=pathlib.Path, help="Use a local domain-proof snapshot instead of fetching")
    verify.add_argument("--revocation-file", type=pathlib.Path, help="Use a local revocation snapshot instead of fetching")
    verify.add_argument("--hmac-secret", default="", help="Shared secret for hmac-sha256 private feeds")
    verify.add_argument("--max-age-days", type=int, default=180)
    verify.add_argument("--output", type=pathlib.Path, help="Write output to a file instead of stdout")
    verify.set_defaults(func=verify_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"registry-record: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
