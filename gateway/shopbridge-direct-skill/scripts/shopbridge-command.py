#!/usr/bin/env python3
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


DEFAULT_BASE_URL = "http://127.0.0.1:8098"
BASE_URL = os.getenv("SHOPBRIDGE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
ALLOW_PRIVATE_ORIGIN = env_bool(
    "SHOPBRIDGE_ALLOW_PRIVATE_ORIGIN",
    env_bool("AGENTCART_ALLOW_PRIVATE_ORIGIN", False),
)
MPP_PROOF_URL = os.getenv("SHOPBRIDGE_MPP_PROOF_URL", "").strip()
MPP_COMMAND = os.getenv("SHOPBRIDGE_MPP_COMMAND", "npx mppx").strip()
MPP_NETWORK = os.getenv("SHOPBRIDGE_MPP_NETWORK", "testnet").strip()
MPP_ACCOUNT = os.getenv("SHOPBRIDGE_MPP_ACCOUNT", "agentcart-test").strip()
REGISTRY_URL = (
    os.getenv("SHOPBRIDGE_REGISTRY_URL")
    or os.getenv("AGENTCART_MERCHANT_REGISTRY_URL")
    or ""
).strip()
REGISTRY_MAX_AGE_DAYS = env_int(
    "SHOPBRIDGE_REGISTRY_MAX_AGE_DAYS",
    env_int("AGENTCART_MERCHANT_REGISTRY_MAX_AGE_DAYS", 180),
)
REGISTRY_PATH = (
    os.getenv("SHOPBRIDGE_REGISTRY_PATH")
    or os.getenv("AGENTCART_MERCHANT_REGISTRY_PATH")
    or ""
).strip()
AGENTCART_SERVICE_URL = (
    os.getenv("SHOPBRIDGE_AGENTCART_URL")
    or os.getenv("AGENTCART_URL")
    or ""
).strip()
AGENTCART_SERVICE_TOKEN = (
    os.getenv("SHOPBRIDGE_AGENTCART_TOKEN")
    or os.getenv("AGENTCART_TOKEN")
    or ""
).strip()
SIGNED_REQUEST_SECRET = (
    os.getenv("SHOPBRIDGE_SIGNED_REQUEST_SECRET")
    or os.getenv("AGENTCART_SIGNED_REQUEST_SECRET")
    or ""
).strip()
SIGNED_REQUEST_PRIVATE_KEY = (
    os.getenv("SHOPBRIDGE_SIGNED_REQUEST_PRIVATE_KEY")
    or os.getenv("AGENTCART_SIGNED_REQUEST_PRIVATE_KEY")
    or ""
).strip()
SIGNED_REQUEST_SIGNER = (
    os.getenv("SHOPBRIDGE_SIGNED_REQUEST_SIGNER")
    or os.getenv("AGENTCART_SIGNED_REQUEST_SIGNER")
    or "agentcart-direct-skill"
).strip()


def boolish(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def private_or_local_host(host: str) -> bool:
    host = host.lower().strip("[]")
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return True
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(parsed.is_private or parsed.is_loopback or parsed.is_link_local)


def allow_private_merchant_origin(args: dict[str, Any] | None = None) -> bool:
    args = args or {}
    return boolish(
        args.get("allow_private_origin", args.get("allow_local_origin", args.get("local_demo"))),
        ALLOW_PRIVATE_ORIGIN,
    )


def require_trusted_merchant_origin(base_url: str, args: dict[str, Any] | None = None, *, field: str = "base_url") -> None:
    parsed = urllib.parse.urlparse(str(base_url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit(f"{field}_invalid")
    private_host = private_or_local_host(parsed.hostname or "")
    allow_private = allow_private_merchant_origin(args)
    if parsed.scheme != "https":
        if allow_private and private_host:
            return
        raise SystemExit(f"{field}_requires_https_public_origin")
    if private_host and not allow_private:
        raise SystemExit(f"{field}_requires_public_origin")


def require_trusted_agentcart_origin(base_url: str) -> None:
    parsed = urllib.parse.urlparse(str(base_url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit("agentcart_url_invalid")
    if parsed.scheme == "https":
        return
    if private_or_local_host(parsed.hostname or ""):
        return
    raise SystemExit("agentcart_url_requires_https_public_origin")


def base_url_from_args(args: dict[str, Any] | None = None) -> str:
    args = args or {}
    raw = args.get("base_url") or args.get("shopbridge_base_url") or args.get("merchant_base_url") or BASE_URL
    base_url = str(raw).rstrip("/")
    require_trusted_merchant_origin(base_url, args)
    return base_url


def configured_base_url(args: dict[str, Any] | None = None) -> dict[str, Any]:
    args = args or {}
    for key in ("base_url", "shopbridge_base_url", "merchant_base_url"):
        raw = str(args.get(key) or "").strip()
        if raw:
            return {
                "configured": True,
                "source": f"args.{key}",
                "effective": raw.rstrip("/"),
                "is_default": False,
            }
    raw_env = os.getenv("SHOPBRIDGE_BASE_URL", "").strip()
    if raw_env:
        return {
            "configured": True,
            "source": "SHOPBRIDGE_BASE_URL",
            "effective": raw_env.rstrip("/"),
            "is_default": False,
        }
    return {
        "configured": False,
        "source": "default",
        "effective": BASE_URL,
        "is_default": BASE_URL == DEFAULT_BASE_URL,
    }


def arg_bool(args: dict[str, Any], name: str, default: bool = False) -> bool:
    return boolish(args.get(name), default)


def request_json(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    origin = (base_url or BASE_URL).rstrip("/")
    url = f"{origin}{path}"
    request_headers.update(signed_request_headers(url, method=method, body=data or b""))
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            detail: Any = json.loads(body)
        except json.JSONDecodeError:
            detail = body
        raise SystemExit(json.dumps({"error": {"status": exc.code, "detail": detail}}, indent=2))


def agentcart_service_base_url(args: dict[str, Any]) -> str:
    raw = (
        args.get("agentcart_url")
        or args.get("agentcart_base_url")
        or args.get("agentcart_service_url")
        or AGENTCART_SERVICE_URL
    )
    base_url = str(raw or "").rstrip("/")
    if not base_url:
        raise SystemExit("agentcart_url or AGENTCART_URL is required")
    require_trusted_agentcart_origin(base_url)
    return base_url


def agentcart_service_token(args: dict[str, Any]) -> str:
    return str(
        args.get("agentcart_token")
        or args.get("agentcart_service_token")
        or AGENTCART_SERVICE_TOKEN
        or ""
    ).strip()


def agentcart_service_request_json(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    base_url: str,
    token: str = "",
) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            detail: Any = json.loads(body)
        except json.JSONDecodeError:
            detail = body
        raise SystemExit(json.dumps({"error": {"status": exc.code, "detail": detail}}, indent=2))


def signed_request_headers(url: str, *, method: str, body: bytes) -> dict[str, str]:
    if not SIGNED_REQUEST_SECRET and not SIGNED_REQUEST_PRIVATE_KEY:
        return {}
    parsed = urllib.parse.urlsplit(url)
    signed_path = parsed.path or "/"
    if parsed.query:
        signed_path += "?" + parsed.query
    signed_method = method.upper()
    digest = "sha-256=" + hashlib.sha256(body).hexdigest()
    nonce = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    expires_at = str(int(time.time()) + 300)
    signer = SIGNED_REQUEST_SIGNER or "agentcart-direct-skill"
    canonical_request = "\n".join(
        [
            "agentcart-signed-request-v1",
            signed_method,
            signed_path,
            digest,
            nonce,
            expires_at,
            signer,
        ]
    )
    headers = {
        "X-AgentCart-Signed-Method": signed_method,
        "X-AgentCart-Signed-Path": signed_path,
        "X-AgentCart-Content-Digest": digest,
        "X-AgentCart-Nonce": nonce,
        "X-AgentCart-Expires-At": expires_at,
        "X-AgentCart-Signer": signer,
    }
    if SIGNED_REQUEST_PRIVATE_KEY:
        signature = rsa_sha256_signature(canonical_request, SIGNED_REQUEST_PRIVATE_KEY)
        headers["X-AgentCart-Signature-Alg"] = "rsa-sha256"
        headers["X-AgentCart-Signature"] = "rsa-sha256=" + signature
        return headers
    signature = hmac.new(SIGNED_REQUEST_SECRET.encode(), canonical_request.encode(), hashlib.sha256).hexdigest()
    headers["X-AgentCart-Signature"] = "sha256=" + signature
    return headers


def rsa_sha256_signature(message: str, private_key_pem: str) -> str:
    if not shutil.which("openssl"):
        raise RuntimeError("openssl is required for rsa-sha256 signed requests")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(private_key_pem)
        handle.write("\n")
        key_path = handle.name
    try:
        os.chmod(key_path, 0o600)
        completed = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=message.encode(),
            capture_output=True,
            check=True,
            timeout=10,
        )
        return base64.b64encode(completed.stdout).decode()
    finally:
        try:
            os.unlink(key_path)
        except OSError:
            pass


def money(cents: int, currency: str) -> str:
    return f"{cents / 100:.2f} {currency}"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def hash_without(value: dict[str, Any], *excluded: str) -> str:
    excluded_set = set(excluded)
    return sha256_hex({key: child for key, child in value.items() if key not in excluded_set})


def ap2_style_mandate_mapping(material: dict[str, Any], approval_hash: str, *, mode: str) -> dict[str, Any]:
    destination = material.get("payment_destination") if isinstance(material.get("payment_destination"), dict) else {}
    merchant = material.get("merchant") if isinstance(material.get("merchant"), dict) else {}
    total_cents = int(material.get("total_cents") or 0)
    currency = str(material.get("currency") or "").upper()
    payment_contract_hash = str(destination.get("payment_contract_hash") or "")
    mapping = {
        "schema": "agentcart.ap2_style_mandate_mapping.v1",
        "mode": mode,
        "mapping_status": "unsigned_adapter_mapping",
        "compatibility_note": "AP2-style field mapping only; not an AP2 signed VDC or network assertion.",
        "requires_trusted_surface_signature": True,
        "checkout_mandate": {
            "vct": "mandate.checkout.1",
            "source": "agentcart.approval_material",
            "checkout_reference_hash": approval_hash,
            "merchant": merchant,
            "items": material.get("items") if isinstance(material.get("items"), list) else [],
            "subtotal_cents": int(material.get("subtotal_cents") or 0),
            "shipping_cents": int(material.get("shipping_cents") or 0),
            "total": {"amount_cents": total_cents, "currency": currency},
            "delivery": material.get("delivery") if isinstance(material.get("delivery"), dict) else {},
            "quote_id": str(material.get("quote_id") or ""),
            "quote_hash": str(material.get("quote_hash") or ""),
            "expires_at": str(material.get("expires_at") or ""),
            "data_trust": material.get("data_trust") if isinstance(material.get("data_trust"), dict) else {},
        },
        "payment_mandate": {
            "vct": "mandate.payment.1",
            "source": "agentcart.payment_handoff",
            "transaction_id": approval_hash,
            "checkout_reference_hash": approval_hash,
            "merchant": merchant,
            "amount": {"amount_cents": total_cents, "currency": currency},
            "payment_rail": str(material.get("payment_rail") or destination.get("rail") or ""),
            "payment_destination": destination,
            "payment_contract_hash": payment_contract_hash,
            "quote_hash": str(material.get("quote_hash") or ""),
            "quote_id": str(material.get("quote_id") or ""),
            "expires_at": str(material.get("expires_at") or ""),
        },
        "audit_bindings": {
            "approval_hash": approval_hash,
            "quote_hash": str(material.get("quote_hash") or ""),
            "payment_contract_hash": payment_contract_hash,
        },
        "safety": {
            "human_approval_required": True,
            "merchant_text_untrusted": True,
            "no_real_settlement_without_external_verifier": True,
            "approval_required_before_payment": True,
        },
    }
    mapping["mapping_hash"] = hash_without(mapping, "mapping_hash")
    return mapping


def iso_now() -> str:
    return utcnow().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def registry_signature_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key
        not in {
            "signature",
            "verification",
            "manifest",
            "manifest_snapshot",
            "proof_snapshot",
            "revocation_snapshot",
        }
    }


def registry_record_hash(record: dict[str, Any]) -> str:
    return sha256_hex(registry_signature_payload(record))


def parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def fetch_json_url(url: str) -> dict[str, Any]:
    parsed = parsed_url(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit(f"{url} must be an HTTP(S) JSON URL")
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise SystemExit(json.dumps({"error": {"status": exc.code, "detail": body}}, indent=2))
    except urllib.error.URLError as exc:
        raise SystemExit(json.dumps({"error": {"url": url, "detail": str(exc.reason)}}, indent=2))
    except json.JSONDecodeError as exc:
        raise SystemExit(json.dumps({"error": {"url": url, "detail": f"invalid JSON: {exc}"}}, indent=2))
    if not isinstance(data, dict):
        raise SystemExit(f"{url} did not return a JSON object")
    return data


def load_json_path(path: str) -> Any:
    if not path:
        raise SystemExit("registry path is required")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise SystemExit(json.dumps({"error": {"path": path, "detail": str(exc)}}, indent=2))
    except json.JSONDecodeError as exc:
        raise SystemExit(json.dumps({"error": {"path": path, "detail": f"invalid JSON: {exc}"}}, indent=2))


def parsed_url(value: str) -> urllib.parse.ParseResult:
    return urllib.parse.urlparse(str(value or ""))


def origin_for_url(value: str) -> str:
    parsed = parsed_url(value)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")


def local_registry_host(host: str) -> bool:
    return private_or_local_host(host)


def validate_registry_source_url(url: str, *, field: str = "registry_url") -> None:
    parsed = parsed_url(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit(f"{field}_invalid")
    if parsed.scheme != "https" and not local_registry_host(parsed.hostname or ""):
        raise SystemExit(f"{field}_requires_https")


def domain_matches(domain: str, parsed: urllib.parse.ParseResult) -> bool:
    domain = str(domain or "").lower().strip()
    host = (parsed.hostname or "").lower()
    netloc = parsed.netloc.lower()
    return bool(domain and domain in {host, netloc})


def endpoint_host_errors(record: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    domain = str(record.get("domain") or "")
    endpoints = manifest.get("endpoints") if isinstance(manifest.get("endpoints"), dict) else {}
    for required in ("catalog", "quote"):
        if not endpoints.get(required):
            errors.append(f"endpoint_{required}_missing")
    for name, endpoint in endpoints.items():
        endpoint_url = str(endpoint or "")
        if not endpoint_url or endpoint_url.startswith("/"):
            continue
        parsed = parsed_url(endpoint_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"endpoint_{name}_invalid")
            continue
        if parsed.scheme != "https" and not local_registry_host(parsed.hostname or ""):
            errors.append(f"endpoint_{name}_requires_https")
        if domain and not domain_matches(domain, parsed):
            errors.append(f"endpoint_{name}_domain_mismatch")
    return errors


def verify_registry_claim(record: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    expected_hash = str(record.get("registry_claim_hash") or "")
    if not expected_hash:
        expected_manifest_hash = str(record.get("manifest_hash") or "")
        if not expected_manifest_hash:
            return ["missing_registry_claim_hash"]
        actual_manifest_hash = sha256_hex(manifest)
        return [] if expected_manifest_hash == actual_manifest_hash else ["manifest_hash_mismatch"]
    discovery = manifest.get("discovery") if isinstance(manifest.get("discovery"), dict) else {}
    claim = discovery.get("registry_claim") if isinstance(discovery.get("registry_claim"), dict) else {}
    if not claim:
        return ["registry_claim_missing_in_manifest"]
    errors: list[str] = []
    actual_hash = sha256_hex(claim)
    if expected_hash != actual_hash:
        errors.append("registry_claim_hash_mismatch")
    for field in (
        "merchant_id",
        "name",
        "domain",
        "manifest_url",
        "payment_network",
        "payment_recipient",
        "stripe_profile_id",
        "proof_url",
        "revocation_url",
    ):
        expected = str(record.get(field) or "")
        supplied = str(claim.get(field) or "")
        if expected and supplied and expected != supplied:
            errors.append(f"registry_claim_{field}_mismatch")
        elif expected and not supplied:
            errors.append(f"registry_claim_{field}_missing")
    record_profile_ids = sorted(str(value) for value in record.get("protocol_profile_ids", []) if value)
    claim_profile_ids = sorted(str(value) for value in claim.get("protocol_profile_ids", []) if value)
    if record_profile_ids and record_profile_ids != claim_profile_ids:
        errors.append("registry_claim_protocol_profile_ids_mismatch")
    record_countries = sorted(str(value).upper() for value in record.get("ship_to_countries", []) if value)
    claim_countries = sorted(str(value).upper() for value in claim.get("ship_to_countries", []) if value)
    if record_countries and record_countries != claim_countries:
        errors.append("registry_claim_ship_to_countries_mismatch")
    record_protocols = sorted(str(value) for value in record.get("supported_protocols", []) if value)
    claim_protocols = sorted(str(value) for value in claim.get("supported_protocols", []) if value)
    if record_protocols and record_protocols != claim_protocols:
        errors.append("registry_claim_supported_protocols_mismatch")
    record_onchain_identity = registry_onchain_identity_payload(record)
    claim_onchain_identity = registry_onchain_identity_payload(claim)
    if record_onchain_identity and not claim_onchain_identity:
        errors.append("registry_claim_onchain_identity_missing")
    elif record_onchain_identity and sha256_hex(record_onchain_identity) != sha256_hex(claim_onchain_identity):
        errors.append("registry_claim_onchain_identity_mismatch")
    record_endpoints = record.get("endpoints") if isinstance(record.get("endpoints"), dict) else {}
    claim_endpoints = claim.get("endpoints") if isinstance(claim.get("endpoints"), dict) else {}
    for name, endpoint in record_endpoints.items():
        supplied = claim_endpoints.get(name)
        if endpoint and supplied and endpoint != supplied:
            errors.append(f"registry_claim_endpoint_{name}_mismatch")
        elif endpoint and not supplied:
            errors.append(f"registry_claim_endpoint_{name}_missing")
    return errors


def raw_registry_onchain_identity(value: dict[str, Any]) -> Any:
    if "onchain_identity" in value:
        return value.get("onchain_identity")
    return value.get("erc8004_identity")


def registry_onchain_identity_payload(value: dict[str, Any]) -> dict[str, str]:
    raw = raw_registry_onchain_identity(value)
    if not isinstance(raw, dict):
        return {}
    standard = str(raw.get("standard") or raw.get("type") or "").strip()
    if not standard and "erc8004_identity" in value:
        standard = "ERC-8004"
    aliases = {
        "chain": "chain_id",
        "chainId": "chain_id",
        "registry": "registry_address",
        "registry_contract": "registry_address",
        "contract": "registry_address",
        "tx_hash": "registration_tx_hash",
        "transaction_hash": "registration_tx_hash",
        "uri": "registration_uri",
    }
    payload: dict[str, str] = {}
    if standard:
        payload["standard"] = standard
    for source_key in (
        "chain_id",
        "chain",
        "chainId",
        "registry_address",
        "registry",
        "registry_contract",
        "contract",
        "service_id",
        "agent_id",
        "registration_uri",
        "uri",
        "registration_tx_hash",
        "tx_hash",
        "transaction_hash",
        "attestation_hash",
        "proof_url",
    ):
        target_key = aliases.get(source_key, source_key)
        if target_key in payload:
            continue
        text = str(raw.get(source_key) or "").strip()
        if text:
            payload[target_key] = text
    return payload


def verify_registry_onchain_identity(record: dict[str, Any]) -> list[str]:
    raw = raw_registry_onchain_identity(record)
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return ["onchain_identity_must_be_object"]
    errors: list[str] = []
    payload = registry_onchain_identity_payload(record)
    standard = payload.get("standard", "").lower().replace("_", "-")
    if standard not in {"erc-8004", "erc8004", "eip-8004", "eip8004"}:
        errors.append("onchain_identity_standard_unsupported")
    if not any(
        payload.get(field)
        for field in (
            "agent_id",
            "service_id",
            "registration_uri",
            "registration_tx_hash",
            "attestation_hash",
            "registry_address",
        )
    ):
        errors.append("onchain_identity_missing_anchor")
    chain_id = payload.get("chain_id", "")
    if chain_id and not re.fullmatch(r"(eip155:)?[0-9]{1,20}", chain_id):
        errors.append("onchain_identity_chain_id_invalid")
    registry_address = payload.get("registry_address", "")
    if registry_address and not re.fullmatch(r"0x[0-9a-fA-F]{40}", registry_address):
        errors.append("onchain_identity_registry_address_invalid")
    for hash_field in ("registration_tx_hash", "attestation_hash"):
        supplied_hash = payload.get(hash_field, "")
        if supplied_hash.startswith("0x") and not re.fullmatch(r"0x[0-9a-fA-F]{64}", supplied_hash):
            errors.append(f"onchain_identity_{hash_field}_invalid")
    proof_url = payload.get("proof_url", "")
    if proof_url:
        parsed = parsed_url(proof_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append("onchain_identity_proof_url_invalid")
        elif parsed.scheme != "https" and not local_registry_host(parsed.hostname or ""):
            errors.append("onchain_identity_proof_url_requires_https")
    return errors


def manifest_payment_binding(manifest: dict[str, Any]) -> tuple[str, str]:
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
        if isinstance(protocol, dict) and str(protocol.get("id") or "") == "tempo-mpp":
            network = str(protocol.get("network") or "").strip()
            recipient = str(protocol.get("recipient") or "").strip()
            if network or recipient:
                return network, recipient
    payment = manifest.get("payment") if isinstance(manifest.get("payment"), dict) else {}
    return str(payment.get("network") or "").strip(), str(payment.get("recipient") or "").strip()


def verify_registry_payment_binding(record: dict[str, Any], manifest: dict[str, Any]) -> str | None:
    manifest_network, manifest_recipient = manifest_payment_binding(manifest)
    record_recipient = str(record.get("payment_recipient") or "").lower()
    if record_recipient and not manifest_recipient:
        return "payment_recipient_missing_in_manifest"
    if record_recipient and manifest_recipient and record_recipient != manifest_recipient.lower():
        return "payment_recipient_mismatch"
    record_network = str(record.get("payment_network") or "").lower()
    if record_network and manifest_network and record_network != manifest_network.lower():
        return "payment_network_mismatch"
    return None


def verify_registry_shipping_scope(record: dict[str, Any], manifest: dict[str, Any]) -> str | None:
    record_countries = {str(value).upper() for value in record.get("ship_to_countries", []) if value}
    delivery = manifest.get("delivery") if isinstance(manifest.get("delivery"), dict) else {}
    manifest_countries = {str(value).upper() for value in delivery.get("ship_to_countries", []) if value}
    if record_countries and not manifest_countries:
        return "shipping_scope_missing_in_manifest"
    if record_countries and manifest_countries and not record_countries.issubset(manifest_countries):
        return "shipping_scope_mismatch"
    return None


def protocol_profiles(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    profiles = document.get("protocol_profiles") if isinstance(document.get("protocol_profiles"), list) else []
    return [profile for profile in profiles if isinstance(profile, dict) and profile.get("id")]


def protocol_profile_ids(document: dict[str, Any] | None) -> list[str]:
    return [str(profile.get("id")) for profile in protocol_profiles(document) if profile.get("id")]


def first_protocol_profiles(*documents: dict[str, Any] | None) -> list[dict[str, Any]]:
    for document in documents:
        profiles = protocol_profiles(document)
        if profiles:
            return profiles
    return []


def verify_domain_proof(record: dict[str, Any], proof: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_hash = registry_record_hash(record)
    supplied_hash = str(proof.get("record_hash") or "")
    if not supplied_hash:
        errors.append("domain_proof_record_hash_missing")
    elif supplied_hash != expected_hash:
        errors.append("domain_proof_record_hash_mismatch")
    fields = ["merchant_id", "domain", "manifest_url", "payment_network", "payment_recipient", "updated_at"]
    if record.get("revocation_url"):
        fields.append("revocation_url")
    fields.append("registry_claim_hash" if record.get("registry_claim_hash") else "manifest_hash")
    for field in fields:
        expected = str(record.get(field) or "")
        supplied = str(proof.get(field) or "")
        if expected and supplied and expected != supplied:
            errors.append(f"domain_proof_{field}_mismatch")
        elif expected and not supplied:
            errors.append(f"domain_proof_{field}_missing")
    return errors


def validate_revocation_document(record: dict[str, Any], document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_merchant_id = str(record.get("merchant_id") or "")
    supplied_merchant_id = str(document.get("merchant_id") or "")
    if supplied_merchant_id and expected_merchant_id and supplied_merchant_id != expected_merchant_id:
        errors.append("revocation_merchant_id_mismatch")
    expected_domain = str(record.get("domain") or "")
    supplied_domain = str(document.get("domain") or "")
    if supplied_domain and expected_domain and supplied_domain.lower() != expected_domain.lower():
        errors.append("revocation_domain_mismatch")
    return errors


def revocation_document_revokes_record(record: dict[str, Any], document: dict[str, Any]) -> bool:
    candidates: list[dict[str, Any]] = [document]
    for key in ("revocations", "revoked_records", "records"):
        value = document.get(key)
        if isinstance(value, list):
            candidates.extend(entry for entry in value if isinstance(entry, dict))

    expected_hash = registry_record_hash(record)
    merchant_id = str(record.get("merchant_id") or "")
    domain = str(record.get("domain") or "").lower()
    for candidate in candidates:
        revoked = bool(candidate.get("revoked")) or bool(candidate.get("revoked_at"))
        if not revoked:
            continue
        supplied_hash = str(candidate.get("record_hash") or candidate.get("registry_record_hash") or "")
        if supplied_hash:
            if supplied_hash == expected_hash:
                return True
            continue
        supplied_merchant_id = str(candidate.get("merchant_id") or "")
        supplied_domain = str(candidate.get("domain") or "").lower()
        applies_to = str(candidate.get("applies_to") or "").lower()
        if (
            applies_to in {"merchant", "all_records"}
            and merchant_id
            and supplied_merchant_id == merchant_id
            and (not supplied_domain or supplied_domain == domain)
        ):
            return True
    return False


def revocation_url_errors(record: dict[str, Any], revocation_url: str) -> list[str]:
    errors: list[str] = []
    domain = str(record.get("domain") or "")
    parsed_revocation = parsed_url(revocation_url)
    if parsed_revocation.scheme not in {"http", "https"} or not parsed_revocation.netloc:
        errors.append("revocation_url_invalid")
    else:
        if parsed_revocation.scheme != "https" and not local_registry_host(parsed_revocation.hostname or ""):
            errors.append("revocation_url_requires_https")
        if domain and not domain_matches(domain, parsed_revocation):
            errors.append("revocation_url_domain_mismatch")
        if not parsed_revocation.path.startswith("/.well-known/"):
            errors.append("revocation_url_requires_well_known_path")
    return errors


def verify_registry_revocation(
    record: dict[str, Any],
    revocation_document: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    revocation_url = str(record.get("revocation_url") or "")
    if not revocation_url:
        return errors
    errors.extend(revocation_url_errors(record, revocation_url))
    if errors:
        return errors

    if revocation_document is None and isinstance(record.get("revocation_snapshot"), dict):
        revocation_document = record["revocation_snapshot"]
    if revocation_document is None:
        try:
            revocation_document = fetch_json_url(revocation_url)
        except SystemExit:
            errors.append("revocation_fetch_failed")
            return errors
    if not isinstance(revocation_document, dict):
        errors.append("revocation_not_object")
        return errors

    errors.extend(validate_revocation_document(record, revocation_document))
    if revocation_document_revokes_record(record, revocation_document):
        errors.append("record_revoked_by_revocation_document")
    return errors


def registry_max_age_days(args: dict[str, Any]) -> int:
    raw = args.get("registry_max_age_days", args.get("max_age_days", REGISTRY_MAX_AGE_DAYS))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return REGISTRY_MAX_AGE_DAYS


def verify_registry_updated_at(record: dict[str, Any], args: dict[str, Any]) -> list[str]:
    updated_at = str(record.get("updated_at") or "")
    if not updated_at:
        return ["missing_updated_at"]
    parsed = parse_time(updated_at)
    if parsed is None:
        return ["updated_at_invalid"]

    errors: list[str] = []
    now = utcnow()
    if parsed > now + dt.timedelta(minutes=10):
        errors.append("updated_at_in_future")
    max_age_days = registry_max_age_days(args)
    if max_age_days > 0 and parsed < now - dt.timedelta(days=max_age_days):
        errors.append("record_stale")
    return errors


def registry_record_from_args(args: dict[str, Any]) -> dict[str, Any]:
    record = args.get("registry_record")
    if isinstance(record, dict):
        return record
    record_url = str(args.get("registry_record_url") or "")
    if record_url:
        validate_registry_source_url(record_url, field="registry_record_url")
        loaded = fetch_json_url(record_url)
        loaded_records = registry_records_from_document(loaded)
        merchant_id = str(args.get("merchant_id") or "")
        for entry in loaded_records:
            if not merchant_id or str(entry.get("merchant_id") or "") == merchant_id:
                return entry
        raise SystemExit("registry_record_url did not contain the requested merchant_id")
    records = registry_records_from_source(args)
    merchant_id = str(args.get("merchant_id") or "")
    if not records:
        raise SystemExit("configured registry source did not contain any records")
    if merchant_id:
        for entry in records:
            if str(entry.get("merchant_id") or "") == merchant_id:
                return entry
        raise SystemExit("configured registry source did not contain the requested merchant_id")
    if len(records) == 1:
        return records[0]
    raise SystemExit("merchant_id is required when the configured registry source has multiple records")


def registry_records_from_document(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [record for record in document if isinstance(record, dict)]
    if isinstance(document, dict):
        if isinstance(document.get("entries"), list):
            return [record for record in document["entries"] if isinstance(record, dict)]
        registry_feed = document.get("registry_feed")
        if isinstance(registry_feed, dict) and isinstance(registry_feed.get("entries"), list):
            return [record for record in registry_feed["entries"] if isinstance(record, dict)]
        registry_record = document.get("registry_record")
        if isinstance(registry_record, dict):
            return [registry_record]
        if document.get("merchant_id") and document.get("manifest_url"):
            return [document]
    raise SystemExit("registry source must be a record, a list of records, an object with entries[], or a ShopBridge registry bundle")


def configured_registry_url(args: dict[str, Any]) -> str:
    return str(
        args.get("registry_url")
        or args.get("registry_feed_url")
        or REGISTRY_URL
        or ""
    ).strip()


def configured_registry_path(args: dict[str, Any]) -> str:
    return str(
        args.get("registry_path")
        or args.get("registry_file")
        or REGISTRY_PATH
        or ""
    ).strip()


def registry_records_from_source(args: dict[str, Any]) -> list[dict[str, Any]]:
    registry_path = configured_registry_path(args)
    registry_url = configured_registry_url(args)
    if registry_path:
        return registry_records_from_document(load_json_path(registry_path))
    if registry_url:
        validate_registry_source_url(registry_url)
        return registry_records_from_document(fetch_json_url(registry_url))
    return []


def registry_records_from_args(args: dict[str, Any]) -> list[dict[str, Any]]:
    raw_records = args.get("registry_records")
    if isinstance(raw_records, list):
        records = registry_records_from_document(raw_records)
    elif isinstance(args.get("registry"), dict):
        records = registry_records_from_document(args["registry"])
    elif args.get("registry_record") or args.get("registry_record_url"):
        record_url = str(args.get("registry_record_url") or "")
        if record_url:
            validate_registry_source_url(record_url, field="registry_record_url")
            records = registry_records_from_document(fetch_json_url(record_url))
        else:
            records = [registry_record_from_args(args)]
    else:
        records = registry_records_from_source(args)
        if not records:
            raise SystemExit(
                "registry_records, registry.entries, registry_record, registry_record_url, "
                "registry_url, registry_path, SHOPBRIDGE_REGISTRY_URL, or SHOPBRIDGE_REGISTRY_PATH is required"
            )
    merchant_ids = {
        str(value)
        for value in args.get("merchant_ids", [])
        if value
    } if isinstance(args.get("merchant_ids"), list) else set()
    merchant_id = str(args.get("merchant_id") or "")
    if merchant_id:
        merchant_ids.add(merchant_id)
    if merchant_ids:
        records = [record for record in records if str(record.get("merchant_id") or "") in merchant_ids]
    return records


def command_resolve_merchant(args: dict[str, Any]) -> dict[str, Any]:
    record = registry_record_from_args(args)
    errors: list[str] = []
    manifest_url = str(record.get("manifest_url") or "")
    domain = str(record.get("domain") or "")
    parsed_manifest = parsed_url(manifest_url)
    if record.get("revoked_at"):
        errors.append("record_revoked")
    errors.extend(verify_registry_updated_at(record, args))
    errors.extend(verify_registry_onchain_identity(record))
    if parsed_manifest.scheme not in {"http", "https"} or not parsed_manifest.netloc:
        errors.append("manifest_url_invalid")
    elif parsed_manifest.scheme != "https" and not local_registry_host(parsed_manifest.hostname or ""):
        errors.append("manifest_url_requires_https")
    if parsed_manifest.netloc and domain and not domain_matches(domain, parsed_manifest):
        errors.append("manifest_domain_mismatch")

    proof = record.get("proof") if isinstance(record.get("proof"), dict) else {}
    proof_url = str(proof.get("url") or "")
    proof_type = str(proof.get("type") or "").lower()
    parsed_proof = parsed_url(proof_url)
    if proof_type not in {"https-well-known", "agentcart-domain-v1"}:
        errors.append("domain_proof_type_unsupported")
    if not proof_url:
        errors.append("domain_proof_url_missing")
    elif parsed_proof.scheme not in {"http", "https"} or not parsed_proof.netloc:
        errors.append("domain_proof_url_invalid")
    else:
        if parsed_proof.scheme != "https" and not local_registry_host(parsed_proof.hostname or ""):
            errors.append("domain_proof_url_requires_https")
        if domain and not domain_matches(domain, parsed_proof):
            errors.append("domain_proof_url_domain_mismatch")
        if not parsed_proof.path.startswith("/.well-known/"):
            errors.append("domain_proof_url_requires_well_known_path")

    manifest = args.get("manifest_snapshot") if isinstance(args.get("manifest_snapshot"), dict) else None
    proof_document = args.get("proof_snapshot") if isinstance(args.get("proof_snapshot"), dict) else None
    revocation_document = args.get("revocation_snapshot") if isinstance(args.get("revocation_snapshot"), dict) else None
    if manifest is None and isinstance(record.get("manifest_snapshot"), dict):
        manifest = record["manifest_snapshot"]
    if proof_document is None and isinstance(record.get("proof_snapshot"), dict):
        proof_document = record["proof_snapshot"]
    if revocation_document is None and isinstance(record.get("revocation_snapshot"), dict):
        revocation_document = record["revocation_snapshot"]
    if manifest is None and not any(error.startswith("manifest_") for error in errors):
        manifest = fetch_json_url(manifest_url)
    if proof_document is None and not any(error.startswith("domain_proof_url_") for error in errors):
        proof_document = fetch_json_url(proof_url)
    errors.extend(verify_registry_revocation(record, revocation_document))

    if isinstance(manifest, dict):
        errors.extend(verify_registry_claim(record, manifest))
        errors.extend(endpoint_host_errors(record, manifest))
        payment_error = verify_registry_payment_binding(record, manifest)
        if payment_error:
            errors.append(payment_error)
        shipping_error = verify_registry_shipping_scope(record, manifest)
        if shipping_error:
            errors.append(shipping_error)
        manifest_merchant = manifest.get("merchant") if isinstance(manifest.get("merchant"), dict) else {}
        if record.get("merchant_id") and manifest_merchant.get("id") and record.get("merchant_id") != manifest_merchant.get("id"):
            errors.append("merchant_id_mismatch")
    else:
        errors.append("manifest_fetch_failed")
    if isinstance(proof_document, dict):
        errors.extend(verify_domain_proof(record, proof_document))
    else:
        errors.append("domain_proof_fetch_failed")

    verification = {
        "state": "verified" if not errors else "rejected",
        "errors": errors,
        "signature_alg": str(record.get("signature_alg") or ""),
        "proof_type": proof_type,
    }
    merchant = (manifest or {}).get("merchant") if isinstance((manifest or {}).get("merchant"), dict) else {}
    return {
        "ok": not errors,
        "base_url": origin_for_url(manifest_url) if manifest_url else "",
        "merchant": {
            "id": str(record.get("merchant_id") or merchant.get("id") or ""),
            "name": str(record.get("name") or merchant.get("name") or ""),
        },
        "manifest_url": manifest_url,
        "registry_record_hash": registry_record_hash(record),
        "protocol_profile_ids": (
            record.get("protocol_profile_ids")
            if isinstance(record.get("protocol_profile_ids"), list)
            else protocol_profile_ids(manifest)
        ),
        "protocol_profiles": protocol_profiles(manifest),
        "verification": verification,
        "manifest": manifest if args.get("include_manifest") else None,
    }


def scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def toon_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if any(ch in text for ch in [",", "\n", "{", "}", "[", "]", ":"]):
        return json.dumps(text, ensure_ascii=False)
    return text


def to_toon(value: Any, *, name: str = "result", indent: int = 0) -> str:
    pad = "  " * indent
    if scalar(value):
        return f"{pad}{name}: {toon_value(value)}"
    if isinstance(value, dict):
        lines = [f"{pad}{name}:"]
        for key, child in value.items():
            lines.append(to_toon(child, name=str(key), indent=indent + 1))
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return f"{pad}{name}[0]:"
        if all(isinstance(item, dict) for item in value):
            keys = []
            for item in value:
                for key, child in item.items():
                    if key not in keys and scalar(child):
                        keys.append(key)
            if keys:
                rows = [f"{pad}{name}[{len(value)}]{{{','.join(keys)}}}:"]
                for item in value:
                    rows.append(f"{pad}{','.join(toon_value(item.get(key)) for key in keys)}")
                return "\n".join(rows)
        lines = [f"{pad}{name}[{len(value)}]:"]
        for index, child in enumerate(value, 1):
            lines.append(to_toon(child, name=str(index), indent=indent + 1))
        return "\n".join(lines)
    return f"{pad}{name}: {toon_value(value)}"


def compact_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    return {
        "merchant": (catalog.get("merchant") or {}).get("name"),
        "products": [
            {
                "id": product.get("id") or product.get("product_id"),
                "title": product.get("title"),
                "price": money(int(product.get("price_cents") or 0), product.get("currency", "EUR")),
                "unit_size": product.get("unit_size"),
                "package_size": product.get("package_size"),
                "tags": product.get("tags"),
                "dietary_tags": product.get("dietary_tags"),
                "allergens": product.get("allergens"),
                "stock": product.get("stock"),
                "eligible": product.get("eligible_for_agent_checkout"),
            }
            for product in catalog.get("products", [])
            if isinstance(product, dict)
        ],
    }


def compact_quote(quote: dict[str, Any]) -> dict[str, Any]:
    merchant = quote.get("merchant") or {}
    items = [item for item in quote.get("items", []) if isinstance(item, dict)]
    shipping = quote.get("shipping") or {}
    payment = quote.get("payment_requirements") or {}
    protocols = payment.get("protocols") if isinstance(payment.get("protocols"), list) else []
    merchant_policy = compact_merchant_policy(
        quote.get("merchant_policy") if isinstance(quote.get("merchant_policy"), dict) else merchant.get("merchant_policy")
    )
    return {
        "quote_id": quote.get("id"),
        "merchant": merchant.get("name"),
        "items": [
            {
                "product_id": item.get("product_id"),
                "title": item.get("title"),
                "quantity": item.get("quantity"),
                "line_total": money(int(item.get("line_total_cents") or 0), quote.get("currency", "EUR")),
            }
            for item in items
        ],
        "subtotal": money(int(quote.get("subtotal_cents") or 0), quote.get("currency", "EUR")),
        "shipping": money(int(shipping.get("amount_cents") or 0), quote.get("currency", "EUR")),
        "total": money(int(quote.get("total_cents") or 0), quote.get("currency", "EUR")),
        "delivery": (quote.get("delivery_estimate") or {}).get("label"),
        "quote_hash": quote.get("quote_hash"),
        "payment_methods": [protocol.get("id") for protocol in protocols if isinstance(protocol, dict)],
        "merchant_policy": merchant_policy,
        "data_trust": untrusted_merchant_text_metadata(),
    }


def bounded_display_text(value: object, max_length: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > max_length:
        return f"{text[: max_length - 1]}..."
    return text


def quoted_display_text(value: object) -> str:
    return json.dumps(bounded_display_text(value))


def untrusted_merchant_text_metadata() -> dict[str, Any]:
    return {
        "merchant_text": "untrusted",
        "instructions_allowed": False,
        "display_or_summarize_only": True,
        "untrusted_fields": [
            "merchant.name",
            "items[].title",
            "items[].description",
            "delivery",
            "merchant_policy",
        ],
    }


def compact_aftercare(order: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    fulfillment = order.get("fulfillment") if isinstance(order.get("fulfillment"), dict) else {}
    tracking = compact_tracking(fulfillment)
    refund_policy = order.get("refund_policy") if isinstance(order.get("refund_policy"), dict) else {}
    cancellation_policy = order.get("cancellation_policy") if isinstance(order.get("cancellation_policy"), dict) else {}
    aftercare_state = order.get("aftercare_state") if isinstance(order.get("aftercare_state"), dict) else {}
    payment = order.get("payment_verification") if isinstance(order.get("payment_verification"), dict) else {}
    refunds = order.get("refunds") if isinstance(order.get("refunds"), list) else []
    item_policy = aftercare_item_policy_summary(order, refund_policy)
    merchant_policy = aftercare_merchant_policy(order, refund_policy, args)
    cancellation = compact_cancellation_policy(cancellation_policy, merchant_policy)
    support = support_contact(order, args)
    if not support.get("returns_url") and merchant_policy.get("returns_url"):
        support["returns_url"] = str(merchant_policy["returns_url"])
    currency = str(refund_policy.get("currency") or args.get("currency") or "EUR")
    remaining_cents = int(refund_policy.get("remaining_refundable_cents") or 0)
    tracking_url = tracking["tracking_url"]
    tracking_number = tracking["tracking_number"]
    delivery = fulfillment.get("estimated_delivery_window") if isinstance(fulfillment.get("estimated_delivery_window"), dict) else {}
    delivery_exception = compact_delivery_exception(fulfillment, aftercare_state)
    next_actions = []
    if tracking_url:
        next_actions.append({"id": "open_tracking", "label": "Open carrier tracking", "url": tracking_url})
    elif tracking_number:
        next_actions.append({"id": "track_with_carrier", "label": f"Track shipment {tracking_number}"})
    else:
        next_actions.append({"id": "check_status_later", "label": "Check order status again later"})
    if delivery_exception["requires_attention"]:
        next_actions.append(
            {
                "id": "review_delivery_exception",
                "label": "Review carrier delivery exception",
                "state": delivery_exception["state"],
                "summary": delivery_exception["summary"],
            }
        )
    if cancellation.get("eligible"):
        next_actions.append(
            {
                "id": "request_cancellation",
                "label": "Ask merchant or trusted gateway to review cancellation",
                "window_minutes": cancellation.get("advertised_request_window_minutes"),
                "requires_merchant_token": cancellation.get("requires_merchant_token"),
            }
        )
    if item_policy.get("merchant_review_required"):
        next_actions.append({"id": "review_item_policy", "label": "Review item-level return and substitution policy"})
    if remaining_cents > 0:
        next_actions.append(
            {
                "id": "request_refund",
                "label": "Ask merchant or trusted gateway to review a refund",
                "requires_merchant_token": bool(refund_policy.get("requires_merchant_token", True)),
            }
        )
    if support.get("email"):
        next_actions.append({"id": "contact_support", "label": "Contact merchant support", "email": support["email"]})
    transaction_reference = str(payment.get("transaction_reference") or payment.get("reference") or "")
    if transaction_reference:
        next_actions.append({"id": "export_payment_proof", "label": "Export payment proof", "reference": transaction_reference})
    refund_request = refund_request_draft(order, args, support, remaining_cents, currency) if args.get("refund_reason") or args.get("refund_amount_cents") else None
    cancellation_request = cancellation_request_draft(order, args, support, cancellation) if args.get("cancellation_reason") else None
    compact_state = compact_aftercare_state(aftercare_state)
    messages = buyer_aftercare_messages(compact_state, refunds, currency)
    return {
        "order": {
            "id": str(order.get("id") or order.get("order_id") or ""),
            "number": str(order.get("number") or ""),
            "status": str(order.get("status") or ""),
            "payment_status": str(order.get("payment_status") or ("paid" if payment else "")),
            "status_url": str(order.get("status_url") or ""),
            "has_status_token": bool(order.get("status_token") or args.get("status_token") or args.get("token")),
        },
        "fulfillment": {
            "state": str(fulfillment.get("state") or ""),
            "carrier": tracking["carrier"],
            "tracking_number": tracking_number,
            "tracking_url": tracking_url,
            "tracking_status": tracking["tracking_status"],
            "tracking_source": tracking["source"],
            "tracking_confidence": tracking["confidence"],
            "tracking": tracking,
            "has_delivery_exception": delivery_exception["requires_attention"],
            "delivery_exception": delivery_exception if delivery_exception["requires_attention"] else None,
            "estimated_delivery": delivery.get("label") or delivery.get("latest_date") or "",
            "note": str(fulfillment.get("note") or ""),
        },
        "refund": {
            "available": remaining_cents > 0,
            "remaining": money(remaining_cents, currency),
            "requires_merchant_or_gateway": bool(refund_policy.get("requires_merchant_token", True)),
            "merchant_review_required": bool(refund_policy.get("merchant_review_required") or item_policy.get("merchant_review_required")),
            "endpoint_for_trusted_gateway": str(refund_policy.get("endpoint") or ""),
            "existing_refunds": len([refund for refund in refunds if isinstance(refund, dict)]),
        },
        "item_policy": item_policy,
        "merchant_policy": merchant_policy,
        "aftercare_state": compact_state,
        "buyer_aftercare_messages": messages,
        "cancellation": cancellation,
        "support": support,
        "payment_proof": {
            "rail": str(payment.get("rail") or ""),
            "transaction_reference": transaction_reference,
            "real_settlement_verified": bool(payment.get("real_settlement_verified")),
        },
        "refund_request_draft": refund_request,
        "cancellation_request_draft": cancellation_request,
        "next_actions": next_actions,
        "safety_note": "The direct buyer skill does not call merchant-token refund, cancellation, or order mutation endpoints. Ask the merchant or a trusted AgentCart gateway to submit approved aftercare requests, especially for perishable, deposit, restricted, or final-sale items.",
    }


def compact_tracking(fulfillment: dict[str, Any]) -> dict[str, Any]:
    nested = fulfillment.get("tracking") if isinstance(fulfillment.get("tracking"), dict) else {}
    return {
        "carrier": str(nested.get("carrier") or fulfillment.get("carrier") or ""),
        "tracking_number": str(nested.get("tracking_number") or fulfillment.get("tracking_number") or ""),
        "tracking_url": str(nested.get("tracking_url") or fulfillment.get("tracking_url") or ""),
        "tracking_status": str(nested.get("tracking_status") or fulfillment.get("tracking_status") or ""),
        "tracking_status_label": str(nested.get("tracking_status_label") or ""),
        "shipped_at": str(nested.get("shipped_at") or ""),
        "delivered_at": str(nested.get("delivered_at") or ""),
        "last_event_at": str(nested.get("last_event_at") or ""),
        "source": str(nested.get("source") or fulfillment.get("source") or ""),
        "adapter": str(nested.get("adapter") or ""),
        "confidence": str(nested.get("confidence") or ""),
        "is_real_carrier_tracking": bool(nested.get("is_real_carrier_tracking") or fulfillment.get("tracking_number") or fulfillment.get("tracking_url")),
    }


def compact_delivery_exception(fulfillment: dict[str, Any], aftercare_state: dict[str, Any]) -> dict[str, Any]:
    raw = fulfillment.get("delivery_exception") if isinstance(fulfillment.get("delivery_exception"), dict) else {}
    if not raw and isinstance(aftercare_state.get("delivery_exception"), dict):
        raw = aftercare_state["delivery_exception"]
    state = str(raw.get("state") or aftercare_state.get("delivery_exception_state") or "")
    requires_attention = bool(
        raw.get("requires_attention")
        or aftercare_state.get("delivery_exception_requires_attention")
        or (state and state != "none")
    )
    return {
        "state": state or ("exception" if requires_attention else "none"),
        "summary": str(raw.get("summary") or raw.get("tracking_status_label") or ""),
        "tracking_status": str(raw.get("tracking_status") or ""),
        "tracking_status_label": str(raw.get("tracking_status_label") or ""),
        "carrier": str(raw.get("carrier") or fulfillment.get("carrier") or ""),
        "tracking_number": str(raw.get("tracking_number") or fulfillment.get("tracking_number") or ""),
        "tracking_url": str(raw.get("tracking_url") or fulfillment.get("tracking_url") or ""),
        "source": str(raw.get("source") or fulfillment.get("source") or ""),
        "last_event_at": str(raw.get("last_event_at") or ""),
        "requires_attention": requires_attention,
    }


def compact_aftercare_state(aftercare_state: dict[str, Any]) -> dict[str, Any]:
    state = aftercare_state if isinstance(aftercare_state, dict) else {}
    next_actions = state.get("next_actions") if isinstance(state.get("next_actions"), list) else []
    blocking_reasons = state.get("blocking_reasons") if isinstance(state.get("blocking_reasons"), list) else []
    refund_progress = state.get("refund_progress") if isinstance(state.get("refund_progress"), dict) else {}
    return {
        "order_lifecycle_state": str(state.get("order_lifecycle_state") or ""),
        "fulfillment_phase": str(state.get("fulfillment_phase") or ""),
        "cancellation_state": str(state.get("cancellation_state") or ""),
        "refund_state": str(state.get("refund_state") or ""),
        "remaining_refundable_cents": bounded_int(state.get("remaining_refundable_cents"), default=0, minimum=0, maximum=999999999),
        "refund_progress": {
            "total_order_cents": bounded_int(refund_progress.get("total_order_cents"), default=0, minimum=0, maximum=999999999),
            "refunded_cents": bounded_int(refund_progress.get("refunded_cents"), default=0, minimum=0, maximum=999999999),
            "remaining_refundable_cents": bounded_int(refund_progress.get("remaining_refundable_cents"), default=0, minimum=0, maximum=999999999),
            "partially_refunded": bool(refund_progress.get("partially_refunded")),
            "fully_refunded": bool(refund_progress.get("fully_refunded")),
            "refund_required_after_cancellation": bool(refund_progress.get("refund_required_after_cancellation") or state.get("refund_required_after_cancellation")),
        },
        "fulfillment_locked": bool(state.get("fulfillment_locked")),
        "refund_required_if_cancelled": bool(state.get("refund_required_if_cancelled")),
        "refund_required_after_cancellation": bool(state.get("refund_required_after_cancellation")),
        "cancellation_does_not_execute_refund": bool(state.get("cancellation_does_not_execute_refund", True)),
        "rail_refund_requires_verifier": bool(state.get("rail_refund_requires_verifier", True)),
        "delivery_exception_state": str(state.get("delivery_exception_state") or "none"),
        "delivery_exception_requires_attention": bool(state.get("delivery_exception_requires_attention")),
        "delivery_exception": state.get("delivery_exception") if isinstance(state.get("delivery_exception"), dict) else None,
        "blocking_reasons": [str(reason) for reason in blocking_reasons],
        "next_actions": [str(action) for action in next_actions],
    }


def buyer_aftercare_messages(aftercare_state: dict[str, Any], refunds: list[Any], currency: str) -> dict[str, Any]:
    state = aftercare_state if isinstance(aftercare_state, dict) else {}
    refund_progress = state.get("refund_progress") if isinstance(state.get("refund_progress"), dict) else {}
    refunded_cents = bounded_int(refund_progress.get("refunded_cents"), default=0, minimum=0, maximum=999999999)
    remaining_cents = bounded_int(state.get("remaining_refundable_cents"), default=0, minimum=0, maximum=999999999)
    refund_records = [refund for refund in refunds if isinstance(refund, dict)]
    latest_refund = refund_records[-1] if refund_records else {}
    latest_refund_verified = bool(latest_refund.get("real_refund_verified"))
    any_real_refund_verified = any(bool(refund.get("real_refund_verified")) for refund in refund_records)
    refund_reference = str(latest_refund.get("refund_reference") or latest_refund.get("merchant_refund_id") or latest_refund.get("id") or "")
    provider = str(latest_refund.get("provider") or latest_refund.get("rail") or "")
    refund_state = str(state.get("refund_state") or "")
    cancellation_state = str(state.get("cancellation_state") or "")
    lifecycle_state = str(state.get("order_lifecycle_state") or "")
    delivery_exception = state.get("delivery_exception") if isinstance(state.get("delivery_exception"), dict) else {}
    messages: dict[str, Any] = {
        "summary": "Order aftercare is active.",
        "refund": "No refund has been recorded.",
        "cancellation": "Order cancellation is not currently available.",
        "delivery": "Check merchant status for delivery updates.",
        "allowed_claims": {
            "order_cancelled": lifecycle_state.startswith("cancelled"),
            "refund_recorded": refunded_cents > 0,
            "refund_executed": any_real_refund_verified,
            "money_returned": any_real_refund_verified,
            "refund_still_required": bool(state.get("refund_required_after_cancellation")),
            "carrier_exception": bool(state.get("delivery_exception_requires_attention")),
        },
    }

    if lifecycle_state == "cancelled_refund_required":
        messages["summary"] = "Order is cancelled, but a verified refund is still required."
        messages["cancellation"] = "Order is cancelled. Cancellation does not prove money was returned."
    elif lifecycle_state == "cancelled_refunded":
        messages["summary"] = "Order is cancelled and the refundable amount is closed."
        messages["cancellation"] = "Order is cancelled and no refundable amount remains."
    elif lifecycle_state == "cancelled_no_refund_due":
        messages["summary"] = "Order is cancelled and no refund is due."
        messages["cancellation"] = "Order is cancelled. No paid refundable amount remains."
    elif cancellation_state == "cancellable_before_fulfillment":
        messages["summary"] = "Order can still be sent for merchant cancellation review."
        messages["cancellation"] = "A trusted gateway or merchant can review cancellation before fulfillment locks."
    elif cancellation_state == "fulfillment_locked":
        messages["cancellation"] = "Cancellation is locked because fulfillment or tracking has started."

    if refund_state == "refund_required_after_cancellation":
        messages["refund"] = f"A verified refund is still required for {money(remaining_cents, currency)}."
    elif refund_state == "partially_refunded":
        messages["refund"] = (
            f"A partial refund of {money(refunded_cents, currency)} is recorded; "
            f"{money(remaining_cents, currency)} remains refundable."
        )
    elif refund_state == "refunded":
        if any_real_refund_verified:
            reference = f" Reference: {refund_reference}." if refund_reference else ""
            via = f" via {provider}" if provider else ""
            messages["refund"] = f"Refund executed and verified{via}.{reference}"
        else:
            messages["refund"] = "Refund recorded by the merchant system. No real rail refund verification is attached."
    elif refund_state == "refund_available":
        messages["refund"] = f"{money(remaining_cents, currency)} remains refundable pending merchant or verifier review."
    elif refund_state == "unpaid_no_refund_due":
        messages["refund"] = "Order is unpaid, so no refund is due."
    elif refund_state == "no_refund_remaining":
        messages["refund"] = "No refundable amount remains."

    if state.get("delivery_exception_requires_attention"):
        summary = str(delivery_exception.get("summary") or delivery_exception.get("state") or "Carrier reported a delivery exception.")
        messages["delivery"] = f"Carrier delivery exception requires attention: {summary}"

    if latest_refund and latest_refund_verified:
        messages["allowed_claims"]["latest_refund_verified"] = True
        messages["allowed_claims"]["latest_refund_reference"] = refund_reference
    return messages


def aftercare_item_policy_summary(order: dict[str, Any], refund_policy: dict[str, Any]) -> dict[str, Any]:
    policy_summary = refund_policy.get("item_policy_summary") if isinstance(refund_policy.get("item_policy_summary"), dict) else {}
    codes = set(str(code) for code in policy_summary.get("commerce_policy_codes", []) if str(code))
    restricted = set(str(code) for code in policy_summary.get("restricted_goods_codes", []) if str(code))
    item_notes = []
    order_items = order.get("items") if isinstance(order.get("items"), list) else []
    for item in order_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("product_id") or "item")
        commerce_policy = item.get("commerce_policy") if isinstance(item.get("commerce_policy"), dict) else {}
        commerce_flags = commerce_policy.get("flags") if isinstance(commerce_policy.get("flags"), list) else []
        for flag in commerce_flags:
            if not isinstance(flag, dict):
                continue
            code = str(flag.get("code") or "")
            if code:
                codes.add(code)
                item_notes.append({"product": title, "code": code, "summary": str(flag.get("summary") or "")})
        restricted_goods = item.get("restricted_goods") if isinstance(item.get("restricted_goods"), list) else []
        for flag in restricted_goods:
            if not isinstance(flag, dict):
                continue
            code = str(flag.get("code") or "")
            if code:
                restricted.add(code)
                item_notes.append({"product": title, "code": code, "summary": str(flag.get("summary") or "")})
    merchant_review = bool(policy_summary.get("merchant_review_required") or codes or restricted)
    return {
        "merchant_review_required": merchant_review,
        "commerce_policy_codes": sorted(codes),
        "restricted_goods_codes": sorted(restricted),
        "perishable_item_count": bounded_int(policy_summary.get("perishable_item_count"), default=0, minimum=0, maximum=999),
        "deposit_item_count": bounded_int(policy_summary.get("deposit_item_count"), default=0, minimum=0, maximum=999),
        "non_returnable_item_count": bounded_int(policy_summary.get("non_returnable_item_count"), default=0, minimum=0, maximum=999),
        "item_notes": item_notes[:8],
        "buyer_agent_note": str(
            policy_summary.get("buyer_agent_note")
            or (
                "Review item-level policy before refund, return, cancellation, or substitution."
                if merchant_review
                else "Standard merchant refund policy applies."
            )
        ),
    }


def aftercare_merchant_policy(order: dict[str, Any], refund_policy: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        refund_policy.get("merchant_policy"),
        order.get("merchant_policy"),
        order.get("merchant", {}).get("merchant_policy") if isinstance(order.get("merchant"), dict) else None,
        args.get("merchant", {}).get("merchant_policy") if isinstance(args.get("merchant"), dict) else None,
        args.get("merchant_policy"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return compact_merchant_policy(candidate)
    return compact_merchant_policy({})


def compact_merchant_policy(policy: dict[str, Any]) -> dict[str, Any]:
    policy = policy if isinstance(policy, dict) else {}
    substitutions = policy.get("substitutions") if isinstance(policy.get("substitutions"), dict) else {}
    cancellations = policy.get("cancellations") if isinstance(policy.get("cancellations"), dict) else {}
    refunds = policy.get("refunds") if isinstance(policy.get("refunds"), dict) else {}
    return {
        "returns_url": str(policy.get("returns_url") or refunds.get("policy_url") or cancellations.get("policy_url") or ""),
        "substitution_policy": str(substitutions.get("policy") or ""),
        "substitution_label": str(substitutions.get("label") or ""),
        "substitution_requires_buyer_approval": bool(substitutions.get("requires_buyer_approval")),
        "substitutions_not_allowed": bool(substitutions.get("not_allowed")),
        "cancellation_request_allowed": bool(cancellations.get("buyer_request_allowed")),
        "cancellation_window_minutes": bounded_int(cancellations.get("request_window_minutes"), default=0, minimum=0, maximum=10080),
        "refund_requires_merchant_review": bool(refunds.get("requires_merchant_review", True)),
        "rail_refund_requires_verifier": bool(refunds.get("rail_refund_requires_verifier", True)),
    }


def compact_cancellation_policy(policy: dict[str, Any], merchant_policy: dict[str, Any]) -> dict[str, Any]:
    policy = policy if isinstance(policy, dict) else {}
    eligibility = policy.get("eligibility") if isinstance(policy.get("eligibility"), dict) else {}
    eligible = bool(policy.get("eligible", merchant_policy.get("cancellation_request_allowed")))
    blocking_reasons = eligibility.get("blocking_reasons") if isinstance(eligibility.get("blocking_reasons"), list) else []
    return {
        "eligible": eligible,
        "endpoint_for_trusted_gateway": str(policy.get("endpoint") or ""),
        "requires_merchant_token": bool(policy.get("requires_merchant_token", True)),
        "idempotency_required": bool(policy.get("idempotency_required", True)),
        "does_not_execute_refund": bool(policy.get("does_not_execute_refund", True)),
        "paid_order_requires_separate_refund": bool(policy.get("paid_order_requires_separate_refund")),
        "refund_endpoint": str(policy.get("refund_endpoint") or ""),
        "blocking_reasons": [str(reason) for reason in blocking_reasons],
        "within_advertised_buyer_request_window": bool(
            eligibility.get(
                "within_advertised_buyer_request_window",
                merchant_policy.get("cancellation_request_allowed"),
            )
        ),
        "advertised_request_window_minutes": bounded_int(
            eligibility.get(
                "advertised_request_window_minutes",
                merchant_policy.get("cancellation_window_minutes"),
            ),
            default=0,
            minimum=0,
            maximum=10080,
        ),
    }


def support_contact(order: dict[str, Any], args: dict[str, Any]) -> dict[str, str]:
    candidates = [
        args.get("merchant"),
        args.get("manifest", {}).get("merchant") if isinstance(args.get("manifest"), dict) else None,
        order.get("merchant"),
        order.get("merchant_of_record"),
    ]
    support_email = str(args.get("support_email") or "")
    returns_url = str(args.get("returns_url") or "")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        merchant_of_record = candidate.get("merchant_of_record") if isinstance(candidate.get("merchant_of_record"), dict) else {}
        support_email = support_email or str(candidate.get("support_email") or merchant_of_record.get("support_email") or "")
        returns_url = returns_url or str(candidate.get("returns_url") or "")
    return {"email": support_email, "returns_url": returns_url}


def refund_request_draft(
    order: dict[str, Any],
    args: dict[str, Any],
    support: dict[str, str],
    remaining_cents: int,
    currency: str,
) -> dict[str, Any]:
    requested_cents = int(args.get("refund_amount_cents") or remaining_cents or 0)
    if remaining_cents > 0:
        requested_cents = min(requested_cents, remaining_cents)
    reason = str(args.get("refund_reason") or "Buyer requested refund review")
    return {
        "to": support.get("email") or "merchant support",
        "subject": f"Refund request for AgentCart order {order.get('number') or order.get('id') or ''}".strip(),
        "amount": money(max(0, requested_cents), currency),
        "reason": reason,
        "order_id": str(order.get("id") or order.get("order_id") or ""),
        "trusted_gateway_payload_hint": {
            "order_id": str(order.get("id") or order.get("order_id") or ""),
            "amount_cents": max(0, requested_cents),
            "currency": currency,
            "reason": reason,
            "requested_reference": args.get("requested_reference") or f"buyer_refund_{order.get('id') or 'order'}",
            "item_policy_summary": aftercare_item_policy_summary(order, order.get("refund_policy") if isinstance(order.get("refund_policy"), dict) else {}),
            "merchant_policy": aftercare_merchant_policy(order, order.get("refund_policy") if isinstance(order.get("refund_policy"), dict) else {}, args),
        },
    }


def cancellation_request_draft(
    order: dict[str, Any],
    args: dict[str, Any],
    support: dict[str, str],
    cancellation: dict[str, Any],
) -> dict[str, Any]:
    reason = str(args.get("cancellation_reason") or "Buyer requested cancellation review")
    order_id = str(order.get("id") or order.get("order_id") or "")
    requested_reference = str(args.get("cancellation_requested_reference") or f"buyer_cancel_{order_id or 'order'}")
    return {
        "to": support.get("email") or "merchant support",
        "subject": f"Cancellation request for AgentCart order {order.get('number') or order_id}".strip(),
        "reason": reason,
        "order_id": order_id,
        "eligible": bool(cancellation.get("eligible")),
        "blocking_reasons": cancellation.get("blocking_reasons") or [],
        "trusted_gateway_payload_hint": {
            "endpoint": cancellation.get("endpoint_for_trusted_gateway"),
            "order_id": order_id,
            "cancellation_idempotency_key": requested_reference,
            "requested_reference": requested_reference,
            "reason": reason,
            "does_not_execute_refund": True,
            "refund_required_after_cancellation": bool(cancellation.get("paid_order_requires_separate_refund")),
        },
    }


def payment_protocols(quote: dict[str, Any]) -> list[dict[str, Any]]:
    payment = quote.get("payment_requirements") if isinstance(quote.get("payment_requirements"), dict) else {}
    protocols = payment.get("protocols") if isinstance(payment.get("protocols"), list) else []
    return [protocol for protocol in protocols if isinstance(protocol, dict)]


def normalize_payment_rail(value: Any) -> str:
    rail = str(value or "").strip().lower().replace("_", "-")
    if rail in {"stripe", "stripe-card", "stripe-card-mpp"}:
        return "stripe-card-mpp"
    if rail in {"tempo", "tempo-mpp", "mpp", "mpp-shaped-demo", "demo-payment-proof"}:
        return "tempo-mpp"
    if rail in {"x402", "x402-exact", "x402-compatible"}:
        return "x402-compatible"
    return rail


def selected_payment_protocol(quote: dict[str, Any], payment_rail: str | None = None) -> dict[str, Any]:
    protocols = payment_protocols(quote)
    requested = normalize_payment_rail(payment_rail)
    if requested:
        for protocol in protocols:
            if normalize_payment_rail(protocol.get("id")) == requested:
                return protocol
        return {"id": requested, "available": False}
    for protocol in protocols:
        if protocol.get("available", True) is not False and protocol.get("setup_required") is not True:
            return protocol
    return protocols[0] if protocols else {}


def payment_contract_hash_for_quote(quote: dict[str, Any], rail: str | None = None) -> str:
    payment = quote.get("payment_requirements") if isinstance(quote.get("payment_requirements"), dict) else {}
    normalized_rail = normalize_payment_rail(rail)
    contracts = payment.get("verification_contracts") if isinstance(payment.get("verification_contracts"), list) else []
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        if normalized_rail and normalize_payment_rail(contract.get("rail")) != normalized_rail:
            continue
        value = str(contract.get("payment_contract_hash") or "")
        if value:
            return value
    contract = payment.get("verification_contract") if isinstance(payment.get("verification_contract"), dict) else {}
    if contract and (not normalized_rail or normalize_payment_rail(contract.get("rail")) == normalized_rail):
        value = str(contract.get("payment_contract_hash") or "")
        if value:
            return value
    verification = payment.get("verification") if isinstance(payment.get("verification"), dict) else {}
    return str(payment.get("payment_contract_hash") or verification.get("payment_contract_hash") or "")


def payment_destination(quote: dict[str, Any], payment_rail: str | None = None) -> dict[str, Any]:
    protocol = selected_payment_protocol(quote, payment_rail)
    rail = normalize_payment_rail(protocol.get("id") or payment_rail)
    destination: dict[str, Any] = {
        "rail": rail,
        "method": rail,
        "protocol": str(protocol.get("protocol") or "mpp"),
        "available": protocol.get("available", True) is not False,
        "setup_required": protocol.get("setup_required") is True,
        "source": "quote.payment_requirements.protocols",
        "payment_contract_hash": payment_contract_hash_for_quote(quote, rail),
    }
    if rail == "stripe-card-mpp":
        profile_id = str(
            protocol.get("stripe_profile_id")
            or protocol.get("network_id")
            or protocol.get("profile_id")
            or ""
        )
        destination.update(
            {
                "stripe_profile_id": profile_id,
                "network_id": str(protocol.get("network_id") or profile_id),
            }
        )
    elif rail == "tempo-mpp":
        destination.update(
            {
                "network": str(protocol.get("network") or ""),
                "recipient": str(protocol.get("recipient") or protocol.get("recipient_address") or ""),
                "settlement_asset": str(protocol.get("settlement_asset") or ""),
            }
        )
    elif rail == "x402-compatible":
        destination.update(
            {
                "network": str(protocol.get("network") or ""),
                "asset": str(protocol.get("asset") or ""),
                "pay_to": str(protocol.get("pay_to") or protocol.get("payTo") or protocol.get("recipient") or ""),
                "max_amount_required": str(protocol.get("max_amount_required") or protocol.get("maxAmountRequired") or ""),
                "payment_required_header": str(protocol.get("payment_required_header") or "PAYMENT-REQUIRED"),
                "payment_signature_header": str(protocol.get("payment_signature_header") or "PAYMENT-SIGNATURE"),
                "payment_response_header": str(protocol.get("payment_response_header") or "PAYMENT-RESPONSE"),
            }
        )
        payment = quote.get("payment_requirements") if isinstance(quote.get("payment_requirements"), dict) else {}
        x402 = payment.get("x402") if isinstance(payment.get("x402"), dict) else {}
        if isinstance(x402.get("payment_required"), dict):
            destination["payment_required"] = x402["payment_required"]
        if x402.get("payment_required_header_value"):
            destination["payment_required_header_value"] = str(x402["payment_required_header_value"])
    return destination


def payment_destination_label(destination: dict[str, Any]) -> str:
    rail = destination.get("rail")
    if rail == "stripe-card-mpp":
        profile = destination.get("stripe_profile_id") or destination.get("network_id") or "unconfigured"
        return f"Stripe/card MPP to seller profile {profile}"
    if rail == "tempo-mpp":
        recipient = destination.get("recipient") or "unconfigured recipient"
        network = destination.get("network") or "unknown network"
        return f"Tempo MPP to {recipient} on {network}"
    if rail == "x402-compatible":
        pay_to = destination.get("pay_to") or "unconfigured payTo"
        network = destination.get("network") or "unknown network"
        return f"x402 exact payment to {pay_to} on {network}"
    return str(rail or "unknown payment rail")


QUOTE_TRUST_KEY = "agentcart_direct_skill"


def normalized_origin(value: str) -> str:
    parsed = urllib.parse.urlparse(str(value or ""))
    if parsed.scheme and parsed.netloc:
        return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), "", "", "")).rstrip("/")
    return str(value or "").rstrip("/")


def quote_trust_metadata(quote: dict[str, Any]) -> dict[str, Any]:
    metadata = quote.get(QUOTE_TRUST_KEY)
    return metadata if isinstance(metadata, dict) else {}


def annotate_quote_trust(
    quote: dict[str, Any],
    *,
    merchant_origin: str,
    registry_record_hash: str = "",
    manifest_url: str = "",
) -> dict[str, Any]:
    copied = json.loads(json.dumps(quote, ensure_ascii=False))
    trust = {
        "schema": "agentcart.direct_skill_quote_trust.v1",
        "merchant_origin": normalized_origin(merchant_origin),
        "registry_record_hash": str(registry_record_hash or ""),
        "manifest_url": str(manifest_url or ""),
        "source": "verified_registry_record" if registry_record_hash else "single_merchant_base_url",
        "created_at": iso_now(),
    }
    trust["trust_hash"] = hash_without(trust, "trust_hash")
    copied[QUOTE_TRUST_KEY] = trust
    return copied


def checkout_base_url_for_quote(args: dict[str, Any], quote: dict[str, Any]) -> str:
    base_url = base_url_from_args(args)
    trust = quote_trust_metadata(quote)
    approved_origin = str(trust.get("merchant_origin") or "")
    if approved_origin and normalized_origin(base_url) != normalized_origin(approved_origin):
        raise SystemExit("checkout_base_url does not match approved quote merchant_origin")
    return base_url


def approval_material(quote: dict[str, Any], *, payment_rail: str | None = None) -> dict[str, Any]:
    merchant = quote.get("merchant") or {}
    shipping = quote.get("shipping") or {}
    delivery = quote.get("delivery_window") or quote.get("delivery_estimate") or {}
    destination = payment_destination(quote, payment_rail)
    trust = quote_trust_metadata(quote)
    merchant_material = {
        "id": quote.get("merchant_id") or merchant.get("id"),
        "name": merchant.get("name"),
    }
    if "merchant_of_record" in quote:
        merchant_material["merchant_of_record"] = quote.get("merchant_of_record")
    material = {
        "quote_id": quote.get("id"),
        "merchant": merchant_material,
        "items": [
            {
                "product_id": item.get("product_id"),
                "title": item.get("title"),
                "quantity": item.get("quantity"),
                "line_total_cents": item.get("line_total_cents"),
            }
            for item in quote.get("items", [])
            if isinstance(item, dict)
        ],
        "subtotal_cents": quote.get("subtotal_cents"),
        "shipping_cents": shipping.get("amount_cents"),
        "total_cents": quote.get("total_cents"),
        "currency": quote.get("currency"),
        "ship_to": quote.get("ship_to"),
        "delivery": delivery,
        "quote_hash": quote.get("quote_hash"),
        "expires_at": quote.get("expires_at"),
        "payment_destination": destination,
        "data_trust": untrusted_merchant_text_metadata(),
    }
    if trust:
        material["merchant_origin"] = trust.get("merchant_origin")
        material["registry_record_hash"] = trust.get("registry_record_hash")
        material["quote_trust"] = trust
    return material


def approval_record_from_material(
    material: dict[str, Any],
    *,
    approval_id: str | None = None,
    mode: str = "skill_only",
) -> dict[str, Any]:
    approval_hash = sha256_hex(material)
    record = {
        "schema": "agentcart.approval_record.v1",
        "approval_id": approval_id or f"skill_approval_{approval_hash[:24]}",
        "mode": mode,
        "approval_hash": approval_hash,
        "approval_material": material,
        "human_approval_required": True,
        "record_role": "approval_contract",
        "safety_boundaries": [
            "merchant",
            "merchant_origin",
            "registry_record_hash",
            "items",
            "total_cents",
            "currency",
            "delivery",
            "quote_hash",
            "expires_at",
            "payment_rail",
            "payment_destination",
        ],
    }
    record["ap2_style_mandate_mapping"] = ap2_style_mandate_mapping(material, approval_hash, mode=mode)
    record["approval_record_hash"] = hash_without(record, "approval_record_hash")
    return record


def approval_packet(quote: dict[str, Any], *, payment_rail: str | None = None) -> dict[str, Any]:
    material = approval_material(quote, payment_rail=payment_rail)
    record = approval_record_from_material(material)
    compact = compact_quote(quote)
    summary = (
        f"Approve merchant-provided item {quoted_display_text(quote_title(quote))} "
        f"from merchant {quoted_display_text(compact['merchant'])} for {compact['total']} "
        f"via {payment_destination_label(material['payment_destination'])}?"
    )
    record["summary"] = summary
    record["quote_summary"] = compact
    record["approval_record_hash"] = hash_without(record, "approval_record_hash")
    return {
        "approval_hash": record["approval_hash"],
        "approval_record_hash": record["approval_record_hash"],
        "approval_material": material,
        "summary": summary,
        "quote": compact,
        "approval_record": record,
        "ap2_style_mandate_mapping": record["ap2_style_mandate_mapping"],
        "approval_in_skill_only_mode": "Human approval happens in the agent chat; this portable approval_record can be stored by the agent or exported into an AgentCart service audit trail.",
    }


def quote_title(quote: dict[str, Any]) -> str:
    items = [item for item in quote.get("items", []) if isinstance(item, dict)]
    if not items:
        return "the quote"
    if len(items) == 1:
        return str(items[0].get("title") or items[0].get("product_id") or "the item")
    first = str(items[0].get("title") or items[0].get("product_id") or "item")
    return f"{len(items)} items including {first}"


def proof_url_for_quote(quote: dict[str, Any]) -> str:
    if not MPP_PROOF_URL:
        raise SystemExit("SHOPBRIDGE_MPP_PROOF_URL is required for demo checkout")
    amount = f"{int(quote['total_cents']) // 100}.{int(quote['total_cents']) % 100:02d}"
    parts = urllib.parse.urlsplit(MPP_PROOF_URL)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "amount"]
    query.append(("amount", amount))
    query.append(("currency", str(quote.get("currency") or "")))
    query.append(("quote_hash", str(quote.get("quote_hash") or "")))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment))


def b64url_json(value: str) -> Any:
    padding = "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode((value + padding).encode())
    return json.loads(decoded)


def parse_mppx_output(output: str) -> dict[str, Any]:
    body_match = re.search(r'\n(\{\s*"ok"\s*:\s*true.*\})\s*$', output, flags=re.S)
    body = json.loads(body_match.group(1)) if body_match else {}
    receipt_match = re.search(r"(?im)^payment-receipt:\s*(.+)$", output)
    receipt_header = receipt_match.group(1).strip() if receipt_match else ""
    receipt: dict[str, Any] = {}
    if receipt_header:
        try:
            decoded = b64url_json(receipt_header)
            receipt = decoded if isinstance(decoded, dict) else {}
        except (ValueError, json.JSONDecodeError):
            receipt = {}
    reference_match = re.search(r'"reference"\s*:\s*"([^"]+)"', output)
    reference = str(receipt.get("reference") or (reference_match.group(1) if reference_match else ""))
    if not receipt_header or not reference:
        raise SystemExit(
            json.dumps(
                {
                    "error": "mppx payment did not return a usable Payment-Receipt reference",
                    "has_payment_receipt_header": bool(receipt_header),
                    "raw_tail": output[-3000:],
                },
                indent=2,
            )
        )
    return {
        "body": body,
        "payment_receipt_header": receipt_header,
        "payment_receipt": receipt,
        "reference": reference,
        "raw_tail": output[-3000:],
    }


def create_tempo_demo_proof(quote: dict[str, Any]) -> dict[str, Any]:
    command = shlex.split(MPP_COMMAND)
    full_command = [*command, proof_url_for_quote(quote)]
    if MPP_NETWORK:
        full_command.extend(["--network", MPP_NETWORK])
    if MPP_ACCOUNT:
        full_command.extend(["--account", MPP_ACCOUNT])
    if "--include" not in full_command and "-i" not in full_command:
        full_command.append("--include")
    completed = subprocess.run(full_command, check=False, capture_output=True, text=True, timeout=90)
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
    if completed.returncode != 0:
        raise SystemExit(json.dumps({"error": "mppx payment failed", "output": output[-3000:]}, indent=2))
    parsed = parse_mppx_output(output)
    return {
        "state": "succeeded",
        "provider": "tempo_mpp",
        "mode": "mppx-cli",
        "network": MPP_NETWORK,
        "quote_currency": quote.get("currency"),
        "quote_total_cents": quote.get("total_cents"),
        "body": parsed["body"],
        "payment_receipt": {
            "method": "tempo",
            "status": "success",
            "reference": parsed["reference"],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "payment_receipt_header": parsed["payment_receipt_header"],
        "transaction_reference": parsed["reference"],
        "real_settlement": False,
        "value_transfer": True,
        "raw_tail": parsed["raw_tail"],
    }


def quote_items_from_args(args: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = args.get("items")
    if isinstance(raw_items, list) and raw_items:
        items = raw_items
    else:
        items = [{"product_id": args["product_id"], "quantity": args.get("quantity") or 1}]
    normalized = []
    for item in items:
        if not isinstance(item, dict) or not item.get("product_id"):
            raise SystemExit("Each quote item must include product_id")
        normalized.append({"product_id": item["product_id"], "quantity": int(item.get("quantity") or 1)})
    return normalized


def bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def quote_ship_to_from_args(args: dict[str, Any]) -> dict[str, Any]:
    ship_to = args.get("ship_to") if isinstance(args.get("ship_to"), dict) else {}
    normalized = dict(ship_to)
    normalized.update(
        {
        "country": ship_to.get("country") or args.get("country") or "DE",
        "postal_code": (
            ship_to.get("postal_code")
            or ship_to.get("postcode")
            or args.get("postal_code")
            or args.get("postcode")
            or "10115"
        ),
        }
    )
    return normalized


def command_catalog(args: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "search": args.get("search") or args.get("q") or "",
            "limit": args.get("limit") or 12,
        }
    )
    return request_json(f"/wp-json/agentcart/v1/catalog?{query}", base_url=base_url_from_args(args))


def command_manifest(args: dict[str, Any]) -> dict[str, Any]:
    return request_json("/.well-known/agentcart.json", base_url=base_url_from_args(args))


def command_capability(args: dict[str, Any]) -> dict[str, Any]:
    return request_json("/wp-json/agentcart/v1/capability", base_url=base_url_from_args(args))


def command_readiness(args: dict[str, Any]) -> dict[str, Any]:
    manifest: dict[str, Any] | None = None
    capability: dict[str, Any] | None = None
    errors: list[dict[str, Any]] = []
    for name, fn in [("manifest", command_manifest), ("capability", command_capability)]:
        try:
            result = fn(args)
            if name == "manifest":
                manifest = result
            else:
                capability = result
        except SystemExit as exc:
            errors.append({"check": name, "error": str(exc)})
    payment = capability.get("payment") if isinstance(capability, dict) else {}
    verification = (
        capability.get("payment_verification")
        if isinstance(capability, dict) and isinstance(capability.get("payment_verification"), dict)
        else payment.get("verification")
        if isinstance(payment, dict)
        else {}
    )
    protocols = (
        capability.get("protocols")
        if isinstance(capability, dict) and isinstance(capability.get("protocols"), list)
        else payment.get("protocols")
        if isinstance(payment, dict)
        else None
    )
    profiles = first_protocol_profiles(capability, manifest)
    return {
        "base_url": base_url_from_args(args),
        "merchant": (manifest or {}).get("merchant") or (capability or {}).get("merchant"),
        "manifest_ok": manifest is not None,
        "capability_ok": capability is not None,
        "external_verifier_configured": bool(
            verification.get("external_verifier_configured") if isinstance(verification, dict) else False
        ),
        "payment_rails": protocols,
        "protocol_profiles": profiles,
        "protocol_profile_ids": [str(profile.get("id")) for profile in profiles if profile.get("id")],
        "errors": errors,
    }


def registry_source_configured(args: dict[str, Any]) -> bool:
    return bool(
        args.get("registry_records")
        or args.get("registry")
        or args.get("registry_record")
        or args.get("registry_record_url")
        or configured_registry_url(args)
        or configured_registry_path(args)
    )


def doctor_next_commands(mode: str, base_url: str, has_registry: bool) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    if mode == "registry" or has_registry:
        commands.extend(
            [
                {
                    "command": "resolve_merchant",
                    "purpose": "verify one merchant record before catalog or quote calls",
                    "example_args": {"merchant_id": "<merchant-id>"},
                },
                {
                    "command": "discover_basket_quotes",
                    "purpose": "compare whole-basket quotes across verified merchants",
                    "example_args": {
                        "basket": [{"query": "tea", "quantity": 1}],
                        "country": "DE",
                        "postal_code": "10115",
                        "payment_rail": "stripe-card-mpp",
                        "format": "toon",
                    },
                },
            ]
        )
    if mode == "single_merchant":
        commands.extend(
            [
                {
                    "command": "readiness",
                    "purpose": "probe the merchant manifest and capability endpoint",
                    "example_args": {"base_url": base_url, "format": "toon"},
                },
                {
                    "command": "catalog",
                    "purpose": "read opt-in products from the known merchant",
                    "example_args": {"base_url": base_url, "search": "tea", "format": "toon"},
                },
            ]
        )
    if mode == "unconfigured":
        commands.append(
            {
                "command": "doctor",
                "purpose": "rerun after configuring a registry or explicit merchant base URL",
                "example_args": {
                    "registry_path": "/path/to/merchant-registry.json",
                    "format": "toon",
                },
            }
        )
    return commands


def command_doctor(args: dict[str, Any]) -> dict[str, Any]:
    base = configured_base_url(args)
    registry_configured = registry_source_configured(args)
    mode = "registry" if registry_configured else "single_merchant" if base["configured"] else "unconfigured"
    checks: list[dict[str, Any]] = [
        {
            "id": "python_runtime",
            "ok": True,
            "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }
    ]
    records: list[dict[str, Any]] = []

    if registry_configured:
        try:
            records = registry_records_from_args(args)
            checks.append(
                {
                    "id": "registry_source",
                    "ok": bool(records),
                    "record_count": len(records),
                    "source": configured_registry_path(args) or configured_registry_url(args) or "inline",
                }
            )
        except SystemExit as exc:
            checks.append({"id": "registry_source", "ok": False, "error": str(exc)})

        if records and arg_bool(args, "verify_merchants", arg_bool(args, "probe", False)):
            limit = bounded_int(args.get("verify_limit"), default=5, minimum=1, maximum=25)
            resolved = []
            for record in records[:limit]:
                try:
                    result = resolve_record_for_discovery(record, args)
                    resolved.append(
                        {
                            "merchant_id": result.get("merchant", {}).get("id") if isinstance(result.get("merchant"), dict) else "",
                            "ok": bool(result.get("ok")),
                            "verification": result.get("verification"),
                            "base_url": result.get("base_url"),
                        }
                    )
                except SystemExit as exc:
                    resolved.append(
                        {
                            "merchant_id": str(record.get("merchant_id") or ""),
                            "ok": False,
                            "error": str(exc),
                        }
                    )
            checks.append(
                {
                    "id": "registry_record_verification",
                    "ok": all(entry["ok"] for entry in resolved),
                    "checked": len(resolved),
                    "records": resolved,
                }
            )
    elif base["configured"]:
        origin_error = ""
        try:
            require_trusted_merchant_origin(str(base["effective"]), args)
        except SystemExit as exc:
            origin_error = str(exc)
        checks.append(
            {
                "id": "single_merchant_override",
                "ok": not origin_error,
                "base_url": base["effective"],
                "source": base["source"],
                "error": origin_error,
                "note": "single-merchant mode is for local tests or user-specified shops; production discovery should use verified registry records",
            }
        )
        if not origin_error and arg_bool(args, "probe", False):
            readiness = command_readiness(
                {"base_url": base["effective"], "allow_private_origin": allow_private_merchant_origin(args)}
            )
            checks.append(
                {
                    "id": "merchant_readiness_probe",
                    "ok": bool(readiness.get("manifest_ok") and readiness.get("capability_ok")),
                    "readiness": readiness,
                }
            )
    else:
        checks.append(
            {
                "id": "buyer_configuration",
                "ok": False,
                "issue": "configure SHOPBRIDGE_REGISTRY_URL, SHOPBRIDGE_REGISTRY_PATH, registry args, or an explicit SHOPBRIDGE_BASE_URL",
            }
        )

    issues = [check for check in checks if check.get("ok") is False]
    return {
        "ok": not issues,
        "mode": mode,
        "configuration": {
            "base_url": base,
            "registry_url_configured": bool(configured_registry_url(args)),
            "registry_path_configured": bool(configured_registry_path(args)),
            "registry_max_age_days": registry_max_age_days(args),
            "allow_private_origin": allow_private_merchant_origin(args),
            "signed_requests_configured": bool(SIGNED_REQUEST_SECRET or SIGNED_REQUEST_PRIVATE_KEY),
            "signed_request_alg": "rsa-sha256" if SIGNED_REQUEST_PRIVATE_KEY else ("hmac-sha256" if SIGNED_REQUEST_SECRET else ""),
            "signed_request_signer": SIGNED_REQUEST_SIGNER if (SIGNED_REQUEST_SECRET or SIGNED_REQUEST_PRIVATE_KEY) else "",
            "tempo_demo_proof_url_configured": bool(MPP_PROOF_URL),
            "tempo_demo_command": MPP_COMMAND,
        },
        "checks": checks,
        "issues": issues,
        "next_commands": doctor_next_commands(mode, str(base["effective"]), registry_configured),
        "available_commands": [
            "doctor",
            "resolve_merchant",
            "readiness",
            "catalog",
            "product",
            "quote",
            "discover_quotes",
            "discover_basket_quotes",
            "approval_packet",
            "checkout_preflight",
            "payment_handoff",
            "checkout",
            "order_status",
            "aftercare_summary",
        ],
        "safety_notes": [
            "Use verified registry records for multi-merchant discovery before catalog or quote calls.",
            "Use SHOPBRIDGE_BASE_URL only as a local or human-specified single-shop override.",
            "Do not call checkout until a human approves the approval_packet hash and an external payment receipt satisfies payment_handoff receipt requirements.",
        ],
    }


def command_product(args: dict[str, Any]) -> dict[str, Any]:
    product_id = str(args.get("product_id") or args.get("id") or "").removeprefix("woo_")
    if not product_id:
        raise SystemExit("product_id is required")
    return request_json(
        f"/wp-json/agentcart/v1/products/{urllib.parse.quote(product_id)}",
        base_url=base_url_from_args(args),
    )


def command_quote(args: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "items": quote_items_from_args(args),
        "ship_to": quote_ship_to_from_args(args),
    }
    base_url = base_url_from_args(args)
    quote = request_json("/wp-json/agentcart/v1/quote", method="POST", payload=payload, base_url=base_url)
    return annotate_quote_trust(
        quote,
        merchant_origin=base_url,
        registry_record_hash=str(args.get("registry_record_hash") or ""),
        manifest_url=str(args.get("manifest_url") or ""),
    )


def product_id_for_quote(product: dict[str, Any]) -> str:
    return str(product.get("id") or product.get("product_id") or "").strip()


def product_ships_to_country(product: dict[str, Any], country: str) -> bool:
    raw_regions = product.get("shipping_regions") or product.get("ship_to_countries") or []
    regions = [str(region).upper() for region in raw_regions if region] if isinstance(raw_regions, list) else []
    return not regions or country.upper() in regions


def format_quantity(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def normalize_package_quantity(quantity: float, unit: str) -> tuple[float, str]:
    normalized_unit = unit.strip().lower().replace(".", "")
    aliases = {
        "kilogram": "kg",
        "kilograms": "kg",
        "gram": "g",
        "grams": "g",
        "liter": "l",
        "litre": "l",
        "liters": "l",
        "litres": "l",
        "milliliter": "ml",
        "millilitre": "ml",
        "milliliters": "ml",
        "millilitres": "ml",
        "centiliter": "cl",
        "centilitre": "cl",
        "centiliters": "cl",
        "centilitres": "cl",
        "pound": "lb",
        "pounds": "lb",
        "ounce": "oz",
        "ounces": "oz",
        "item": "unit",
        "items": "unit",
        "piece": "unit",
        "pieces": "unit",
        "pcs": "unit",
        "pc": "unit",
        "ea": "unit",
        "each": "unit",
        "count": "unit",
        "units": "unit",
    }
    normalized_unit = aliases.get(normalized_unit, normalized_unit)
    if normalized_unit == "kg":
        return quantity * 1000, "g"
    if normalized_unit == "g":
        return quantity, "g"
    if normalized_unit == "lb":
        return quantity * 453.59237, "g"
    if normalized_unit == "oz":
        return quantity * 28.349523125, "g"
    if normalized_unit == "l":
        return quantity * 1000, "ml"
    if normalized_unit == "cl":
        return quantity * 10, "ml"
    if normalized_unit == "ml":
        return quantity, "ml"
    return max(1.0, quantity), "unit"


def package_size_from_product(product: dict[str, Any]) -> dict[str, Any]:
    package = product.get("package_size") if isinstance(product.get("package_size"), dict) else {}
    label = str(package.get("label") or product.get("unit_size") or "").strip()
    normalized_quantity = package.get("normalized_quantity")
    normalized_unit = str(package.get("normalized_unit") or "").strip().lower()
    if normalized_quantity is not None and normalized_unit:
        try:
            quantity = float(normalized_quantity)
        except (TypeError, ValueError):
            quantity = 0
        if quantity > 0:
            return {
                "available": True,
                "label": label or f"{format_quantity(quantity)} {normalized_unit}",
                "normalized_quantity": quantity,
                "normalized_unit": normalized_unit,
                "source": str(package.get("source") or "package_size"),
            }
    quantity = package.get("quantity")
    unit = str(package.get("unit") or "").strip()
    if quantity is not None and unit:
        try:
            normalized_quantity, normalized_unit = normalize_package_quantity(float(quantity), unit)
        except (TypeError, ValueError):
            normalized_quantity, normalized_unit = 0, ""
        if normalized_quantity > 0:
            return {
                "available": True,
                "label": label or f"{format_quantity(float(quantity))} {unit}",
                "normalized_quantity": normalized_quantity,
                "normalized_unit": normalized_unit,
                "source": str(package.get("source") or "package_size"),
            }
    text = str(product.get("unit_size") or "").strip()
    match = re.search(r"(?i)(\d+(?:[.,]\d+)?)\s*(kg|g|grams?|l|liters?|litres?|ml|cl|lbs?|pounds?|oz|ounces?|units?|items?|pieces?|pcs|ea|each|count)\b", text)
    if match:
        quantity = float(match.group(1).replace(",", "."))
        normalized_quantity, normalized_unit = normalize_package_quantity(quantity, match.group(2))
        if normalized_quantity > 0:
            return {
                "available": True,
                "label": text,
                "normalized_quantity": normalized_quantity,
                "normalized_unit": normalized_unit,
                "source": "unit_size",
            }
    return {
        "available": False,
        "label": text or "unknown",
        "normalized_quantity": 0,
        "normalized_unit": "",
        "source": "unavailable",
    }


def quote_line_for_product(quote: dict[str, Any], product_id: str) -> dict[str, Any]:
    items = [item for item in quote.get("items", []) if isinstance(item, dict)]
    for item in items:
        if str(item.get("product_id") or "") == product_id:
            return item
    return items[0] if items else {}


def unit_value_for_candidate(product: dict[str, Any], quote: dict[str, Any], product_id: str) -> dict[str, Any]:
    package = package_size_from_product(product)
    if not package.get("available"):
        return {"available": False, "package": package, "label": "unit value unavailable"}
    line = quote_line_for_product(quote, product_id)
    quantity = bounded_int(line.get("quantity"), default=1, minimum=1, maximum=999)
    line_total_cents = int(line.get("line_total_cents") or product.get("price_cents") or quote.get("subtotal_cents") or quote.get("total_cents") or 0)
    total_normalized_quantity = float(package["normalized_quantity"]) * quantity
    if total_normalized_quantity <= 0 or line_total_cents <= 0:
        return {"available": False, "package": package, "label": "unit value unavailable"}
    normalized_unit = str(package["normalized_unit"])
    basis_quantity = 100 if normalized_unit in {"g", "ml"} else 1
    basis_label = f"100 {normalized_unit}" if normalized_unit in {"g", "ml"} else normalized_unit
    cents_per_basis = int(round((line_total_cents / total_normalized_quantity) * basis_quantity))
    currency = str(quote.get("currency") or product.get("currency") or "EUR")
    return {
        "available": True,
        "package": package,
        "line_total": money(line_total_cents, currency),
        "normalized_total_quantity": total_normalized_quantity,
        "normalized_unit": normalized_unit,
        "cents_per_basis": cents_per_basis,
        "basis": basis_label,
        "label": f"{money(cents_per_basis, currency)} per {basis_label}",
    }


def basket_items_from_args(args: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = args.get("basket") or args.get("shopping_list") or args.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise SystemExit("basket, shopping_list, or items must contain at least one item")
    normalized = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"basket item {index} must be an object")
        query = str(item.get("query") or item.get("q") or item.get("search") or item.get("name") or item.get("title") or "").strip()
        product_id = str(item.get("product_id") or item.get("id") or "").strip()
        if not query and not product_id:
            raise SystemExit(f"basket item {index} must include query or product_id")
        constraints = item.get("constraints") if isinstance(item.get("constraints"), dict) else {}
        normalized.append(
            {
                "query": query or product_id,
                "product_id": product_id,
                "quantity": bounded_int(item.get("quantity"), default=1, minimum=1, maximum=20),
                "required": item.get("required", True) is not False,
                "constraints": constraints,
                "alternatives": basket_item_alternatives(item, parent_constraints=constraints),
            }
        )
    return normalized


def merge_basket_constraints(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    merged = dict(parent)
    for field in ("exclude_terms", "required_tags", "exclude_tags", "exclude_allergens"):
        values: list[str] = []
        for source in (parent, child):
            raw_values = source.get(field)
            if isinstance(raw_values, list):
                for value in raw_values:
                    text = str(value).strip()
                    if text and text not in values:
                        values.append(text)
        if values:
            merged[field] = values
        elif field in merged:
            merged.pop(field)
    for key, value in child.items():
        if key not in {"exclude_terms", "required_tags"}:
            merged[key] = value
    return merged


def basket_item_alternatives(item: dict[str, Any], *, parent_constraints: dict[str, Any]) -> list[dict[str, Any]]:
    raw_alternatives = item.get("alternatives") or item.get("substitutions") or []
    if not isinstance(raw_alternatives, list):
        return []
    alternatives = []
    for index, alternative in enumerate(raw_alternatives, start=1):
        if isinstance(alternative, str):
            alternative = {"query": alternative}
        if not isinstance(alternative, dict):
            raise SystemExit(f"basket alternative {index} must be a string or object")
        query = str(
            alternative.get("query")
            or alternative.get("q")
            or alternative.get("search")
            or alternative.get("name")
            or alternative.get("title")
            or ""
        ).strip()
        product_id = str(alternative.get("product_id") or alternative.get("id") or "").strip()
        if not query and not product_id:
            raise SystemExit(f"basket alternative {index} must include query or product_id")
        alt_constraints = alternative.get("constraints") if isinstance(alternative.get("constraints"), dict) else {}
        alternatives.append(
            {
                "query": query or product_id,
                "product_id": product_id,
                "constraints": merge_basket_constraints(parent_constraints, alt_constraints),
                "label": str(alternative.get("label") or query or product_id),
            }
        )
    return alternatives


def normalized_product_values(product: dict[str, Any], fields: tuple[str, ...]) -> set[str]:
    values: set[str] = set()
    for field in fields:
        value = product.get(field)
        if isinstance(value, list):
            for item in value:
                text = str(item).strip().lower()
                if text:
                    values.add(text)
                    values.add(text.replace(" ", "-"))
                    if text.endswith("s"):
                        values.add(text[:-1])
                        values.add(text[:-1].replace(" ", "-"))
        else:
            text = str(value or "").strip().lower()
            if text:
                values.add(text)
                values.add(text.replace(" ", "-"))
                if text.endswith("s"):
                    values.add(text[:-1])
                    values.add(text[:-1].replace(" ", "-"))
    return values


def constraint_values(constraints: dict[str, Any], field: str) -> set[str]:
    raw_values = constraints.get(field)
    if not isinstance(raw_values, list):
        return set()
    values = set()
    for value in raw_values:
        text = str(value).strip().lower()
        if text:
            values.add(text)
            values.add(text.replace(" ", "-"))
            if text.endswith("s"):
                values.add(text[:-1])
                values.add(text[:-1].replace(" ", "-"))
    return values


def basket_item_candidates(item: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        {
            "query": item["query"],
            "product_id": item.get("product_id") or "",
            "constraints": item.get("constraints") if isinstance(item.get("constraints"), dict) else {},
            "substitution": False,
            "requested_query": item["query"],
        }
    ]
    for alternative in item.get("alternatives", []):
        if not isinstance(alternative, dict):
            continue
        candidates.append(
            {
                "query": alternative["query"],
                "product_id": alternative.get("product_id") or "",
                "constraints": alternative.get("constraints") if isinstance(alternative.get("constraints"), dict) else {},
                "substitution": True,
                "requested_query": item["query"],
            }
        )
    return candidates


def product_matches_basket_item(product: dict[str, Any], item: dict[str, Any]) -> bool:
    product_id = item.get("product_id")
    if product_id and product_id_for_quote(product).removeprefix("woo_") != str(product_id).removeprefix("woo_"):
        return False
    constraints = item.get("constraints") if isinstance(item.get("constraints"), dict) else {}
    label_values = normalized_product_values(product, ("tags", "dietary_tags", "labels", "allergens"))
    excluded_terms = constraint_values(constraints, "exclude_terms")
    if excluded_terms:
        haystack = " ".join(
            [
                *[
                    str(product.get(field) or "")
                    for field in ("title", "description", "category", "brand")
                ],
                *sorted(label_values),
            ]
        ).lower()
        if any(term in haystack for term in excluded_terms):
            return False
    excluded_tags = constraint_values(constraints, "exclude_tags")
    if excluded_tags and excluded_tags.intersection(label_values):
        return False
    excluded_allergens = constraint_values(constraints, "exclude_allergens")
    allergen_values = normalized_product_values(product, ("allergens",))
    if excluded_allergens and excluded_allergens.intersection(allergen_values):
        return False
    required_tags = constraint_values(constraints, "required_tags")
    if required_tags:
        if not required_tags.issubset(label_values):
            return False
    return True


def best_catalog_product_for_basket_item(
    catalog: dict[str, Any],
    item: dict[str, Any],
    country: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    rejected = []
    products = catalog.get("products") if isinstance(catalog.get("products"), list) else []
    for product in products:
        if not isinstance(product, dict):
            continue
        product_id = product_id_for_quote(product)
        if not product_id:
            rejected.append({"reason": "catalog product missing product id"})
            continue
        if product.get("eligible_for_agent_checkout", True) is False:
            rejected.append({"product_id": product_id, "title": product.get("title"), "reason": "product is not eligible for agent checkout"})
            continue
        if not product_ships_to_country(product, country):
            rejected.append({"product_id": product_id, "title": product.get("title"), "reason": f"merchant does not ship to {country}"})
            continue
        if not product_matches_basket_item(product, item):
            rejected.append({"product_id": product_id, "title": product.get("title"), "reason": "product did not satisfy basket constraints"})
            continue
        return product, rejected
    return None, rejected


def basket_unit_values(products: list[dict[str, Any]], quote: dict[str, Any]) -> list[dict[str, Any]]:
    values = []
    for product in products:
        product_id = product_id_for_quote(product)
        values.append(
            {
                "product_id": product_id,
                "title": product.get("title"),
                "unit_value": unit_value_for_candidate(product, quote, product_id),
            }
        )
    return values


def merchant_snapshot_arg(args: dict[str, Any], name: str, merchant_id: str) -> dict[str, Any] | None:
    value = args.get(name)
    if isinstance(value, dict):
        if merchant_id and isinstance(value.get(merchant_id), dict):
            return value[merchant_id]
        if not merchant_id and value:
            return value
    return None


def resolve_record_for_discovery(record: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    merchant_id = str(record.get("merchant_id") or "")
    resolve_args: dict[str, Any] = {
        "registry_record": record,
        "include_manifest": bool(args.get("include_manifest")),
    }
    manifest_snapshot = merchant_snapshot_arg(args, "manifest_snapshots", merchant_id)
    proof_snapshot = merchant_snapshot_arg(args, "proof_snapshots", merchant_id)
    revocation_snapshot = merchant_snapshot_arg(args, "revocation_snapshots", merchant_id)
    if manifest_snapshot:
        resolve_args["manifest_snapshot"] = manifest_snapshot
    if proof_snapshot:
        resolve_args["proof_snapshot"] = proof_snapshot
    if revocation_snapshot:
        resolve_args["revocation_snapshot"] = revocation_snapshot
    return command_resolve_merchant(resolve_args)


def quote_latest_delivery_key(quote: dict[str, Any]) -> str:
    delivery = quote.get("delivery_window") or quote.get("delivery_estimate") or {}
    if isinstance(delivery, dict):
        return str(delivery.get("latest_date") or delivery.get("label") or "9999-12-31")
    return "9999-12-31"


def quote_rank_reasons(
    quote: dict[str, Any],
    resolved: dict[str, Any],
    preflight: dict[str, Any],
    unit_value: dict[str, Any] | None = None,
) -> list[str]:
    reasons = [
        f"final total {money(int(quote.get('total_cents') or 0), str(quote.get('currency') or 'EUR'))}",
    ]
    if isinstance(unit_value, dict) and unit_value.get("available") and unit_value.get("label"):
        reasons.append(f"unit value {unit_value['label']}")
    delivery = quote.get("delivery_window") or quote.get("delivery_estimate") or {}
    if isinstance(delivery, dict) and (delivery.get("latest_date") or delivery.get("label")):
        reasons.append(f"delivery {delivery.get('latest_date') or delivery.get('label')}")
    verification = resolved.get("verification") if isinstance(resolved.get("verification"), dict) else {}
    if verification.get("state") == "verified":
        reasons.append("merchant registry verification passed")
    destination = preflight.get("payment_destination") if isinstance(preflight.get("payment_destination"), dict) else {}
    if destination.get("rail"):
        reasons.append(f"payment rail ready: {payment_destination_label(destination)}")
    reasons.append("no paid ranking signal used")
    return reasons


def command_discover_quotes(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or args.get("q") or args.get("search") or "").strip()
    if not query:
        raise SystemExit("query, q, or search is required")
    ship_to = quote_ship_to_from_args(args)
    country = str(ship_to.get("country") or "DE").upper()
    quantity = bounded_int(args.get("quantity"), default=1, minimum=1, maximum=20)
    max_candidates = bounded_int(args.get("max_candidates"), default=6, minimum=1, maximum=12)
    products_per_merchant = bounded_int(args.get("products_per_merchant"), default=2, minimum=1, maximum=6)
    catalog_limit = max(products_per_merchant, bounded_int(args.get("catalog_limit"), default=8, minimum=1, maximum=24))
    rank_by = str(args.get("rank_by") or args.get("ranking") or "total").strip().lower().replace("-", "_")
    rank_by_unit_price = rank_by in {"unit_price", "unit_value", "package_value", "value"}
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_quotes: set[str] = set()

    for record in registry_records_from_args(args):
        merchant_id = str(record.get("merchant_id") or "")
        try:
            resolved = resolve_record_for_discovery(record, args)
        except SystemExit as exc:
            rejected.append({"merchant_id": merchant_id, "reason": "registry verification failed", "detail": str(exc)})
            continue
        verification = resolved.get("verification") if isinstance(resolved.get("verification"), dict) else {}
        if not resolved.get("ok") or verification.get("state") != "verified":
            rejected.append(
                {
                    "merchant_id": merchant_id or resolved.get("merchant", {}).get("id"),
                    "merchant_name": resolved.get("merchant", {}).get("name"),
                    "reason": "merchant registry verification failed",
                    "detail": verification,
                }
            )
            continue
        base_url = str(resolved.get("base_url") or "")
        try:
            catalog = command_catalog({"base_url": base_url, "search": query, "limit": catalog_limit})
        except SystemExit as exc:
            rejected.append({"merchant_id": merchant_id, "reason": "catalog request failed", "detail": str(exc)})
            continue
        products = catalog.get("products") if isinstance(catalog.get("products"), list) else []
        merchant_products = 0
        for product in products:
            if not isinstance(product, dict):
                continue
            if merchant_products >= products_per_merchant:
                break
            product_id = product_id_for_quote(product)
            if not product_id:
                rejected.append({"merchant_id": merchant_id, "reason": "catalog product missing product id"})
                continue
            if product.get("eligible_for_agent_checkout", True) is False:
                rejected.append(
                    {
                        "merchant_id": merchant_id,
                        "product_id": product_id,
                        "title": product.get("title"),
                        "reason": "product is not eligible for agent checkout",
                    }
                )
                continue
            if not product_ships_to_country(product, country):
                rejected.append(
                    {
                        "merchant_id": merchant_id,
                        "product_id": product_id,
                        "title": product.get("title"),
                        "reason": f"merchant does not ship to {country}",
                    }
                )
                continue
            merchant_products += 1
            try:
                quote = command_quote(
                    {
                        "base_url": base_url,
                        "items": [{"product_id": product_id, "quantity": quantity}],
                        "ship_to": ship_to,
                        "registry_record_hash": resolved.get("registry_record_hash"),
                        "manifest_url": resolved.get("manifest_url"),
                    }
                )
                preflight = command_checkout_preflight(
                    {
                        "quote": quote,
                        "payment_rail": args.get("payment_rail"),
                        "max_total_cents": args.get("max_total_cents"),
                    }
                )
            except SystemExit as exc:
                rejected.append(
                    {
                        "merchant_id": merchant_id,
                        "product_id": product_id,
                        "title": product.get("title"),
                        "reason": "quote request failed",
                        "detail": str(exc),
                    }
                )
                continue
            if not preflight.get("ok") or not preflight.get("available_payment_methods"):
                rejected.append(
                    {
                        "merchant_id": merchant_id,
                        "product_id": product_id,
                        "title": product.get("title"),
                        "quote_id": quote.get("id"),
                        "reason": "merchant payment rail is unavailable",
                        "detail": preflight,
                    }
                )
                continue
            quote_id = str(quote.get("id") or "")
            quote_key = quote_id or sha256_hex(quote)
            if quote_key in seen_quotes:
                continue
            seen_quotes.add(quote_key)
            merchant = quote.get("merchant") if isinstance(quote.get("merchant"), dict) else {}
            unit_value = unit_value_for_candidate(product, quote, product_id)
            candidates.append(
                {
                    "_quote": quote,
                    "_preflight": preflight,
                    "_unit_value": unit_value,
                    "quote_id": quote_id,
                    "merchant_id": str(merchant.get("id") or merchant_id),
                    "merchant_name": str(merchant.get("name") or resolved.get("merchant", {}).get("name") or ""),
                    "product_id": product_id,
                    "product_title": str(product.get("title") or quote_title(quote)),
                    "quantity": quantity,
                    "total_cents": int(quote.get("total_cents") or 0),
                    "currency": str(quote.get("currency") or "EUR"),
                    "delivery": quote.get("delivery_window") or quote.get("delivery_estimate") or {},
                    "quote_hash": quote.get("quote_hash"),
                    "approval_hash": preflight.get("approval_hash"),
                    "payment_destination": preflight.get("payment_destination"),
                    "unit_value": unit_value,
                    "registry": {
                        "manifest_url": resolved.get("manifest_url"),
                        "registry_record_hash": resolved.get("registry_record_hash"),
                        "verification": verification,
                        "paid_placement": False,
                    },
                    "rank_reasons": quote_rank_reasons(quote, resolved, preflight, unit_value),
                }
            )

    if rank_by_unit_price:
        candidates.sort(
            key=lambda candidate: (
                not bool(candidate["_unit_value"].get("available")),
                int(candidate["_unit_value"].get("cents_per_basis") or 10**12),
                int(candidate["total_cents"]),
                quote_latest_delivery_key(candidate["_quote"]),
                str(candidate["merchant_name"]),
            )
        )
    else:
        candidates.sort(
            key=lambda candidate: (
                int(candidate["total_cents"]),
                quote_latest_delivery_key(candidate["_quote"]),
                str(candidate["merchant_name"]),
            )
        )
    public_candidates = []
    for index, candidate in enumerate(candidates[:max_candidates], start=1):
        public = {key: value for key, value in candidate.items() if not key.startswith("_")}
        public["rank"] = index
        public["winner"] = index == 1
        public["quote_summary"] = compact_quote(candidate["_quote"])
        public_candidates.append(public)
    winner = None
    if public_candidates:
        raw_winner = candidates[0]
        winner = {
            **public_candidates[0],
            "quote": raw_winner["_quote"],
            "approval_packet": approval_packet(raw_winner["_quote"], payment_rail=args.get("payment_rail")),
        }
    return {
        "query": query,
        "ship_to": ship_to,
        "quantity": quantity,
        "market_design": {
            "registry_role": "public identity and integrity anchor",
            "quote_request": "private RFQ to verified merchants",
            "ranking": "local agent ranking by unit value when requested, then final price, delivery, payment readiness, and policy; no paid placement",
            "rank_by": "unit_price" if rank_by_unit_price else "total",
        },
        "candidates": public_candidates,
        "winner": winner,
        "rejected": rejected,
        "next_step": "Ask the human to approve winner.approval_packet.summary, then call checkout with the winner.quote and a matching payment receipt.",
    }


def basket_quote_items(matched_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, int] = {}
    for item in matched_items:
        product = item.get("product") if isinstance(item.get("product"), dict) else {}
        product_id = product_id_for_quote(product)
        if not product_id:
            continue
        merged[product_id] = merged.get(product_id, 0) + int(item.get("quantity") or 1)
    return [{"product_id": product_id, "quantity": quantity} for product_id, quantity in merged.items()]


def catalog_product_for_basket_item(
    base_url: str,
    item: dict[str, Any],
    country: str,
    catalog_limit: int,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    product_id = str(item.get("product_id") or "")
    if product_id:
        try:
            product = command_product({"base_url": base_url, "product_id": product_id})
        except SystemExit as exc:
            return None, [{"product_id": product_id, "reason": "product request failed", "detail": str(exc)}]
        if not product_ships_to_country(product, country):
            return None, [{"product_id": product_id, "title": product.get("title"), "reason": f"merchant does not ship to {country}"}]
        if product.get("eligible_for_agent_checkout", True) is False:
            return None, [{"product_id": product_id, "title": product.get("title"), "reason": "product is not eligible for agent checkout"}]
        if not product_matches_basket_item(product, item):
            return None, [{"product_id": product_id, "title": product.get("title"), "reason": "product did not satisfy basket constraints"}]
        return product, []
    catalog = command_catalog({"base_url": base_url, "search": item["query"], "limit": catalog_limit})
    return best_catalog_product_for_basket_item(catalog, item, country)


def resolved_product_for_basket_item(
    base_url: str,
    item: dict[str, Any],
    country: str,
    catalog_limit: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    rejections = []
    for candidate in basket_item_candidates(item):
        try:
            product, candidate_rejections = catalog_product_for_basket_item(base_url, candidate, country, catalog_limit)
        except SystemExit as exc:
            product, candidate_rejections = None, [{"reason": "catalog request failed", "detail": str(exc)}]
        rejections.extend(
            {
                "requested_query": item["query"],
                "query": candidate["query"],
                "substitution": bool(candidate.get("substitution")),
                **rejection,
            }
            for rejection in candidate_rejections
        )
        if product is not None:
            return product, candidate, rejections
    return None, None, rejections


def command_discover_basket_quotes(args: dict[str, Any]) -> dict[str, Any]:
    basket = basket_items_from_args(args)
    ship_to = quote_ship_to_from_args(args)
    country = str(ship_to.get("country") or "DE").upper()
    max_candidates = bounded_int(args.get("max_candidates"), default=6, minimum=1, maximum=12)
    catalog_limit = bounded_int(args.get("catalog_limit"), default=6, minimum=1, maximum=24)
    allow_partial = args.get("allow_partial", False) is True
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for record in registry_records_from_args(args):
        merchant_id = str(record.get("merchant_id") or "")
        try:
            resolved = resolve_record_for_discovery(record, args)
        except SystemExit as exc:
            rejected.append({"merchant_id": merchant_id, "reason": "registry verification failed", "detail": str(exc)})
            continue
        verification = resolved.get("verification") if isinstance(resolved.get("verification"), dict) else {}
        if not resolved.get("ok") or verification.get("state") != "verified":
            rejected.append(
                {
                    "merchant_id": merchant_id or resolved.get("merchant", {}).get("id"),
                    "merchant_name": resolved.get("merchant", {}).get("name"),
                    "reason": "merchant registry verification failed",
                    "detail": verification,
                }
            )
            continue
        base_url = str(resolved.get("base_url") or "")
        matched_items: list[dict[str, Any]] = []
        missing_items: list[dict[str, Any]] = []
        item_rejections: list[dict[str, Any]] = []
        for item in basket:
            product, selected_candidate, product_rejections = resolved_product_for_basket_item(base_url, item, country, catalog_limit)
            item_rejections.extend(product_rejections)
            if product is None:
                missing_items.append(
                    {
                        "query": item["query"],
                        "quantity": item["quantity"],
                        "required": item["required"],
                        "alternatives": [
                            alternative["query"]
                            for alternative in item.get("alternatives", [])
                            if isinstance(alternative, dict)
                        ],
                    }
                )
                continue
            matched_items.append(
                {
                    "query": item["query"],
                    "matched_query": (selected_candidate or item)["query"],
                    "substitution": bool((selected_candidate or {}).get("substitution")),
                    "quantity": item["quantity"],
                    "required": item["required"],
                    "product": product,
                }
            )
        required_missing = [item for item in missing_items if item.get("required")]
        if required_missing and not allow_partial:
            rejected.append(
                {
                    "merchant_id": merchant_id,
                    "merchant_name": resolved.get("merchant", {}).get("name"),
                    "reason": "merchant could not satisfy required basket items",
                    "missing_items": required_missing,
                    "detail": item_rejections,
                }
            )
            continue
        quote_items = basket_quote_items(matched_items)
        if not quote_items:
            rejected.append(
                {
                    "merchant_id": merchant_id,
                    "merchant_name": resolved.get("merchant", {}).get("name"),
                    "reason": "merchant had no quotable basket items",
                    "missing_items": missing_items,
                    "detail": item_rejections,
                }
            )
            continue
        try:
            quote = command_quote(
                {
                    "base_url": base_url,
                    "items": quote_items,
                    "ship_to": ship_to,
                    "registry_record_hash": resolved.get("registry_record_hash"),
                    "manifest_url": resolved.get("manifest_url"),
                }
            )
            preflight = command_checkout_preflight(
                {
                    "quote": quote,
                    "payment_rail": args.get("payment_rail"),
                    "max_total_cents": args.get("max_total_cents"),
                }
            )
        except SystemExit as exc:
            rejected.append(
                {
                    "merchant_id": merchant_id,
                    "merchant_name": resolved.get("merchant", {}).get("name"),
                    "reason": "basket quote request failed",
                    "detail": str(exc),
                }
            )
            continue
        if not preflight.get("ok") or not preflight.get("available_payment_methods"):
            rejected.append(
                {
                    "merchant_id": merchant_id,
                    "merchant_name": resolved.get("merchant", {}).get("name"),
                    "quote_id": quote.get("id"),
                    "reason": "merchant payment rail is unavailable",
                    "detail": preflight,
                }
            )
            continue
        merchant = quote.get("merchant") if isinstance(quote.get("merchant"), dict) else {}
        matched_products = [item["product"] for item in matched_items if isinstance(item.get("product"), dict)]
        substitutions = [
            {
                "query": item["query"],
                "matched_query": item.get("matched_query") or item["query"],
                "product_id": product_id_for_quote(item["product"]),
                "title": item["product"].get("title"),
            }
            for item in matched_items
            if item.get("substitution") and isinstance(item.get("product"), dict)
        ]
        candidates.append(
            {
                "_quote": quote,
                "_preflight": preflight,
                "quote_id": str(quote.get("id") or ""),
                "merchant_id": str(merchant.get("id") or merchant_id),
                "merchant_name": str(merchant.get("name") or resolved.get("merchant", {}).get("name") or ""),
                "matched_items": [
                    {
                        "query": item["query"],
                        "matched_query": item.get("matched_query") or item["query"],
                        "substitution": bool(item.get("substitution")),
                        "quantity": item["quantity"],
                        "product_id": product_id_for_quote(item["product"]),
                        "title": item["product"].get("title"),
                    }
                    for item in matched_items
                ],
                "substitutions": substitutions,
                "missing_items": missing_items,
                "full_basket": not missing_items,
                "total_cents": int(quote.get("total_cents") or 0),
                "currency": str(quote.get("currency") or "EUR"),
                "delivery": quote.get("delivery_window") or quote.get("delivery_estimate") or {},
                "quote_hash": quote.get("quote_hash"),
                "approval_hash": preflight.get("approval_hash"),
                "payment_destination": preflight.get("payment_destination"),
                "unit_values": basket_unit_values(matched_products, quote),
                "registry": {
                    "manifest_url": resolved.get("manifest_url"),
                    "registry_record_hash": resolved.get("registry_record_hash"),
                    "verification": verification,
                    "paid_placement": False,
                },
                "rank_reasons": quote_rank_reasons(quote, resolved, preflight),
                "item_rejections": item_rejections,
            }
        )

    candidates.sort(
        key=lambda candidate: (
            not bool(candidate["full_basket"]),
            int(candidate["total_cents"]),
            quote_latest_delivery_key(candidate["_quote"]),
            str(candidate["merchant_name"]),
        )
    )
    public_candidates = []
    for index, candidate in enumerate(candidates[:max_candidates], start=1):
        public = {key: value for key, value in candidate.items() if not key.startswith("_")}
        public["rank"] = index
        public["winner"] = index == 1
        public["quote_summary"] = compact_quote(candidate["_quote"])
        public_candidates.append(public)
    winner = None
    if public_candidates:
        raw_winner = candidates[0]
        winner = {
            **public_candidates[0],
            "quote": raw_winner["_quote"],
            "approval_packet": approval_packet(raw_winner["_quote"], payment_rail=args.get("payment_rail")),
        }
    return {
        "basket": basket,
        "ship_to": ship_to,
        "market_design": {
            "registry_role": "public identity and integrity anchor",
            "quote_request": "private whole-basket RFQ to verified merchants",
            "ranking": "full baskets first, then final price, delivery, payment readiness, and policy; no paid placement",
            "allow_partial": allow_partial,
        },
        "candidates": public_candidates,
        "winner": winner,
        "rejected": rejected,
        "next_step": "Ask the human to approve winner.approval_packet.summary, then call checkout with the winner.quote and a matching payment receipt.",
    }


def command_approval_summary(args: dict[str, Any]) -> dict[str, Any]:
    packet = approval_packet(args["quote"], payment_rail=args.get("payment_rail"))
    return {"approval_required": True, **packet}


def command_checkout_preflight(args: dict[str, Any]) -> dict[str, Any]:
    quote = args["quote"]
    approval = approval_packet(quote, payment_rail=args.get("payment_rail"))
    expires_at = parse_time(quote.get("expires_at"))
    now = dt.datetime.now(dt.timezone.utc)
    payment = quote.get("payment_requirements") if isinstance(quote.get("payment_requirements"), dict) else {}
    verification = payment.get("verification") if isinstance(payment.get("verification"), dict) else {}
    protocols = payment_protocols(quote)
    destination = payment_destination(quote, args.get("payment_rail"))
    available_protocols = [
        protocol.get("id")
        for protocol in protocols
        if isinstance(protocol, dict) and protocol.get("available", True) is not False
    ]
    issues = []
    if expires_at and expires_at <= now:
        issues.append("quote_expired")
    if not quote.get("quote_hash"):
        issues.append("missing_quote_hash")
    if not verification.get("external_verifier_configured"):
        issues.append("external_verifier_required_for_public_checkout")
    payment_rail = normalize_payment_rail(args.get("payment_rail"))
    available_rails = {normalize_payment_rail(value) for value in available_protocols}
    if payment_rail and payment_rail not in available_rails:
        issues.append("payment_rail_unavailable")
    if destination.get("setup_required"):
        issues.append("payment_destination_setup_required")
    if destination.get("rail") == "stripe-card-mpp" and not destination.get("stripe_profile_id"):
        issues.append("missing_stripe_profile_id")
    if destination.get("rail") == "tempo-mpp" and not destination.get("recipient"):
        issues.append("missing_tempo_recipient")
    if destination.get("rail") == "x402-compatible":
        for key in ("network", "asset", "pay_to", "max_amount_required", "payment_required"):
            if not destination.get(key):
                issues.append(f"missing_x402_{key}")
    max_total_cents = args.get("max_total_cents")
    if max_total_cents is not None and int(quote.get("total_cents") or 0) > int(max_total_cents):
        issues.append("over_buyer_limit")
    return {
        "ok": not issues,
        "issues": issues,
        "approval_hash": approval["approval_hash"],
        "approval_summary": approval["summary"],
        "available_payment_methods": available_protocols,
        "payment_destination": destination,
        "quote_trust": quote_trust_metadata(quote),
        "external_verifier_configured": bool(verification.get("external_verifier_configured")),
    }


def payment_receipt_requirements(destination: dict[str, Any]) -> dict[str, Any]:
    rail = str(destination.get("rail") or "")
    fields = ["method", "status", "amount_cents", "currency", "quote_hash"]
    alternatives = ["transaction_reference", "authorization", "credential"]
    must_match_quote = ["amount_cents", "currency", "quote_hash"]
    if destination.get("payment_contract_hash"):
        fields.append("payment_contract_hash")
        must_match_quote.append("payment_contract_hash")
    if rail == "stripe-card-mpp":
        fields.extend(["stripe_profile_id"])
        alternatives = ["authorization", "credential", "transaction_reference"]
    elif rail == "tempo-mpp":
        fields.extend(["network", "recipient"])
        alternatives = ["transaction_reference", "explorer_url"]
    elif rail == "x402-compatible":
        fields.extend(["network", "asset", "pay_to", "max_amount_required"])
        alternatives = ["x402_payment_signature", "payment_signature", "payment_signature_header", "transaction_reference"]
    return {
        "required_fields": fields,
        "one_of": alternatives,
        "must_match_quote": must_match_quote,
        "must_match_payment_destination": [
            key
            for key in ("stripe_profile_id", "network_id", "network", "recipient", "payment_contract_hash")
            if destination.get(key)
        ],
    }


def receipt_field_present(receipt: dict[str, Any], field: str) -> bool:
    value = receipt.get(field)
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def require_supplied_receipt_contract(receipt: dict[str, Any], destination: dict[str, Any]) -> None:
    requirements = payment_receipt_requirements(destination)
    missing = [field for field in requirements["required_fields"] if not receipt_field_present(receipt, field)]
    if missing:
        raise SystemExit(f"payment_receipt missing required field(s): {', '.join(missing)}")
    alternatives = [field for field in requirements["one_of"] if receipt_field_present(receipt, field)]
    if not alternatives:
        raise SystemExit(f"payment_receipt must include one of: {', '.join(requirements['one_of'])}")
    status = str(receipt.get("status") or "").strip().lower()
    accepted_statuses = {"succeeded", "success", "authorized", "paid", "settled", "verified", "ok"}
    if status not in accepted_statuses:
        raise SystemExit("payment_receipt.status must be succeeded, authorized, paid, settled, verified, or ok")


def command_payment_handoff(args: dict[str, Any]) -> dict[str, Any]:
    if not args.get("approved"):
        raise SystemExit("approved=true is required before creating a payment handoff")
    quote = args["quote"]
    approval = approval_packet(quote, payment_rail=args.get("payment_rail"))
    supplied_approval_hash = str(args.get("approval_hash") or "")
    if supplied_approval_hash != approval["approval_hash"]:
        raise SystemExit("approval_hash does not match the current quote approval packet")

    preflight = command_checkout_preflight(args)
    if not preflight["ok"]:
        return {
            "ok": False,
            "issues": preflight["issues"],
            "approval_hash": approval["approval_hash"],
            "approval_record_hash": approval["approval_record_hash"],
            "approval_summary": approval["summary"],
            "payment_destination": preflight["payment_destination"],
            "next_step": "Resolve these issues before sending the buyer to a payment provider.",
        }

    merchant = quote.get("merchant") if isinstance(quote.get("merchant"), dict) else {}
    destination = preflight["payment_destination"]
    payment_request = {
        "rail": destination.get("rail"),
        "amount_cents": int(quote["total_cents"]),
        "currency": str(quote["currency"]).upper(),
        "quote_hash": str(quote["quote_hash"]),
        "payment_contract_hash": destination.get("payment_contract_hash"),
        "merchant_quote_id": str(quote["id"]),
        "approval_hash": approval["approval_hash"],
        "approval_record_hash": approval["approval_record_hash"],
        "ap2_style_payment_mandate": approval["ap2_style_mandate_mapping"]["payment_mandate"],
        "quote_trust": quote_trust_metadata(quote),
        "merchant": {
            "id": str(merchant.get("id") or ""),
            "name": str(merchant.get("name") or ""),
        },
        "payment_destination": destination,
        "description": f"Quote-bound AgentCart payment for {quote_title(quote)}",
        "receipt_requirements": payment_receipt_requirements(destination),
    }
    return {
        "ok": True,
        "approval_hash": approval["approval_hash"],
        "approval_record_hash": approval["approval_record_hash"],
        "approval_record": approval["approval_record"],
        "ap2_style_mandate_mapping": approval["ap2_style_mandate_mapping"],
        "approval_summary": approval["summary"],
        "payment_request": payment_request,
        "payment_handoff_hash": sha256_hex(payment_request),
        "checkout_contract": {
            "next_command": "checkout",
            "required_args": ["quote", "approved", "approval_hash", "payment_receipt"],
            "receipt_validation": "checkout requires the returned receipt to match amount, currency, quote_hash, and payment_destination",
        },
        "safety_note": "This handoff does not move money and does not contain secret keys. It is the structured instruction for a payment-capable agent or provider, and the resulting receipt is still verified by ShopBridge before WooCommerce creates a paid order.",
    }


def validate_receipt_destination(receipt: dict[str, Any], destination: dict[str, Any]) -> None:
    rail = destination.get("rail")
    if rail == "stripe-card-mpp":
        expected = str(destination.get("stripe_profile_id") or destination.get("network_id") or "")
        supplied = str(receipt.get("stripe_profile_id") or receipt.get("network_id") or receipt.get("seller_profile_id") or "")
        if expected and supplied and supplied != expected:
            raise SystemExit("payment_receipt.stripe_profile_id does not match quote payment destination")
        if expected and not supplied:
            raise SystemExit("payment_receipt.stripe_profile_id is required for stripe-card-mpp checkout")
    elif rail == "tempo-mpp":
        expected_recipient = str(destination.get("recipient") or "").lower()
        supplied_recipient = str(receipt.get("recipient") or receipt.get("payment_recipient") or "").lower()
        if expected_recipient and supplied_recipient and supplied_recipient != expected_recipient:
            raise SystemExit("payment_receipt.recipient does not match quote payment destination")
        expected_network = str(destination.get("network") or "").lower()
        supplied_network = str(receipt.get("network") or "").lower()
        if expected_network and supplied_network and supplied_network != expected_network:
            raise SystemExit("payment_receipt.network does not match quote payment destination")
    elif rail == "x402-compatible":
        expected_network = str(destination.get("network") or "").lower()
        supplied_network = str(receipt.get("network") or receipt.get("x402_network") or "").lower()
        if expected_network and supplied_network and supplied_network != expected_network:
            raise SystemExit("payment_receipt.network does not match quote payment destination")
        expected_asset = str(destination.get("asset") or "").lower()
        supplied_asset = str(receipt.get("asset") or receipt.get("x402_asset") or "").lower()
        if expected_asset and supplied_asset and supplied_asset != expected_asset:
            raise SystemExit("payment_receipt.asset does not match quote payment destination")
        expected_pay_to = str(destination.get("pay_to") or "").lower()
        supplied_pay_to = str(receipt.get("pay_to") or receipt.get("payTo") or receipt.get("recipient") or "").lower()
        if expected_pay_to and supplied_pay_to and supplied_pay_to != expected_pay_to:
            raise SystemExit("payment_receipt.pay_to does not match quote payment destination")
        expected_amount = str(destination.get("max_amount_required") or "")
        supplied_amount = str(receipt.get("max_amount_required") or receipt.get("maxAmountRequired") or "")
        if expected_amount and supplied_amount and supplied_amount != expected_amount:
            raise SystemExit("payment_receipt.max_amount_required does not match quote payment destination")


def supplied_payment_receipt(quote: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    receipt = args.get("payment_receipt")
    if not isinstance(receipt, dict):
        raise SystemExit("payment_receipt is required unless use_tempo_demo_proof=true")
    destination = payment_destination(quote, args.get("payment_rail"))
    require_supplied_receipt_contract(receipt, destination)
    expected_amount = int(quote["total_cents"])
    expected_currency = str(quote["currency"]).upper()
    supplied_amount = int(receipt["amount_cents"])
    supplied_currency = str(receipt["currency"]).upper()
    supplied_hash = str(receipt["quote_hash"])
    if supplied_amount != expected_amount:
        raise SystemExit("payment_receipt.amount_cents does not match quote.total_cents")
    if supplied_currency != expected_currency:
        raise SystemExit("payment_receipt.currency does not match quote.currency")
    if supplied_hash != str(quote["quote_hash"]):
        raise SystemExit("payment_receipt.quote_hash does not match quote.quote_hash")
    expected_contract_hash = str(destination.get("payment_contract_hash") or "")
    supplied_contract_hash = str(receipt.get("payment_contract_hash") or receipt.get("contract_hash") or "")
    if expected_contract_hash and supplied_contract_hash != expected_contract_hash:
        raise SystemExit("payment_receipt.payment_contract_hash does not match quote payment contract")
    validate_receipt_destination(receipt, destination)
    return {
        **receipt,
        "id": receipt.get("id") or f"skill_payrcpt_{uuid.uuid4().hex[:12]}",
        "status": receipt.get("status") or "succeeded",
        "amount_cents": expected_amount,
        "currency": expected_currency,
        "quote_hash": quote["quote_hash"],
        "payment_contract_hash": expected_contract_hash or receipt.get("payment_contract_hash"),
        "payment_destination": destination,
    }


def demo_payment_receipt(quote: dict[str, Any]) -> dict[str, Any]:
    proof = create_tempo_demo_proof(quote)
    return {
        "id": f"skill_demo_payrcpt_{uuid.uuid4().hex[:12]}",
        "protocol": "mpp-shaped-tempo-demo",
        "method": "demo",
        "status": "succeeded",
        "amount_cents": quote["total_cents"],
        "currency": quote["currency"],
        "quote_hash": quote["quote_hash"],
        "payment_contract_hash": payment_contract_hash_for_quote(quote, "tempo-mpp"),
        "real_settlement": False,
        "external_value_proof": proof,
    }


def validated_or_new_approval_record(args: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
    expected = approval_packet(quote, payment_rail=args.get("payment_rail"))["approval_record"]
    supplied = args.get("approval_record")
    if supplied is None:
        return expected
    if not isinstance(supplied, dict):
        raise SystemExit("approval_record must be an object when supplied")
    if str(supplied.get("approval_hash") or "") != expected["approval_hash"]:
        raise SystemExit("approval_record.approval_hash does not match the current quote approval packet")
    supplied_hash = str(supplied.get("approval_record_hash") or "")
    actual_hash = hash_without(supplied, "approval_record_hash")
    if supplied_hash and supplied_hash != actual_hash:
        raise SystemExit("approval_record.approval_record_hash is invalid")
    if supplied_hash and supplied_hash != expected["approval_record_hash"]:
        raise SystemExit("approval_record.approval_record_hash does not match the current quote approval packet")
    return supplied


def approval_decision_record(args: dict[str, Any], approval_record: dict[str, Any]) -> dict[str, Any]:
    decided_at = str(args.get("approved_at") or iso_now())
    record = {
        "schema": "agentcart.approval_decision_record.v1",
        "mode": "skill_only",
        "approval_id": str(approval_record.get("approval_id") or ""),
        "approval_hash": str(approval_record.get("approval_hash") or ""),
        "approval_record_hash": str(approval_record.get("approval_record_hash") or ""),
        "decision": "approved",
        "approver": str(args.get("approver") or "human"),
        "channel": str(args.get("approval_channel") or args.get("channel") or "agent_chat"),
        "decided_at": decided_at,
        "decision_basis": "human approved the portable approval_record in chat or local agent UI",
    }
    record["decision_record_hash"] = hash_without(record, "decision_record_hash")
    return record


def skill_audit_packet(
    *,
    order_id: str,
    quote: dict[str, Any],
    approval_record: dict[str, Any],
    decision_record: dict[str, Any],
    receipt: dict[str, Any],
    occurred_at: str | None = None,
) -> dict[str, Any]:
    now = occurred_at or iso_now()
    receipt_reference = str(
        receipt.get("transaction_reference")
        or receipt.get("reference")
        or receipt.get("authorization")
        or receipt.get("credential")
        or ""
    )
    packet = {
        "schema": "agentcart.skill_audit_packet.v1",
        "mode": "skill_only",
        "quote_id": str(quote.get("id") or ""),
        "quote_hash": str(quote.get("quote_hash") or ""),
        "approval_hash": approval_record["approval_hash"],
        "approval_record_hash": approval_record["approval_record_hash"],
        "approval_decision_hash": decision_record["decision_record_hash"],
        "events": [
            {
                "event_type": "approval.approved",
                "actor": decision_record["approver"],
                "timestamp": decision_record["decided_at"],
                "refs": {
                    "approval_id": approval_record.get("approval_id"),
                    "approval_hash": approval_record["approval_hash"],
                    "approval_record_hash": approval_record["approval_record_hash"],
                    "approval_decision_hash": decision_record["decision_record_hash"],
                },
            },
            {
                "event_type": "payment.receipt_supplied",
                "actor": "payment_capable_agent_or_provider",
                "timestamp": now,
                "refs": {
                    "payment_receipt_id": receipt.get("id"),
                    "method": receipt.get("method") or receipt.get("protocol"),
                    "amount_cents": receipt.get("amount_cents"),
                    "currency": receipt.get("currency"),
                    "payment_contract_hash": receipt.get("payment_contract_hash"),
                    "transaction_reference": receipt_reference,
                },
            },
            {
                "event_type": "checkout.payload_created",
                "actor": "shopbridge_direct_skill",
                "timestamp": now,
                "refs": {
                    "agentcart_order_id": order_id,
                    "merchant_quote_id": quote.get("id"),
                    "quote_hash": quote.get("quote_hash"),
                    "approval_record_hash": approval_record["approval_record_hash"],
                },
            },
        ],
    }
    packet["audit_packet_hash"] = hash_without(packet, "audit_packet_hash")
    return packet


def audit_packet_from_args(args: dict[str, Any]) -> dict[str, Any]:
    packet = args.get("audit_packet")
    if isinstance(packet, dict):
        return packet
    for key in ("checkout_payload", "checkout_result", "payload"):
        value = args.get(key)
        if isinstance(value, dict) and isinstance(value.get("audit_packet"), dict):
            return value["audit_packet"]
    raise SystemExit("audit_packet or checkout_payload.audit_packet is required")


def validate_audit_packet(packet: dict[str, Any]) -> str:
    if packet.get("schema") != "agentcart.skill_audit_packet.v1":
        raise SystemExit("unsupported audit packet schema")
    packet_hash = str(packet.get("audit_packet_hash") or "")
    if not packet_hash:
        raise SystemExit("audit_packet_hash is required")
    if not hmac.compare_digest(packet_hash, hash_without(packet, "audit_packet_hash")):
        raise SystemExit("audit_packet_hash is invalid")
    if not str(packet.get("quote_id") or "").strip():
        raise SystemExit("audit packet quote_id is required")
    for required in ("approval_hash", "approval_record_hash", "approval_decision_hash"):
        if not str(packet.get(required) or "").strip():
            raise SystemExit(f"audit packet {required} is required")
    events = packet.get("events")
    if not isinstance(events, list) or not events:
        raise SystemExit("audit packet events must be a non-empty list")
    return packet_hash


def command_audit_import(args: dict[str, Any]) -> dict[str, Any]:
    packet = audit_packet_from_args(args)
    packet_hash = validate_audit_packet(packet)
    base_url = agentcart_service_base_url(args)
    token = agentcart_service_token(args)
    source = str(args.get("source") or "shopbridge-direct-skill")
    request = {"audit_packet": packet, "source": source}
    purchase_id = str(args.get("purchase_id") or packet.get("quote_id") or "")
    if purchase_id:
        request["purchase_id"] = purchase_id
    result = agentcart_service_request_json(
        "/v1/audit/import",
        method="POST",
        payload=request,
        base_url=base_url,
        token=token,
    )
    return {
        "ok": True,
        "agentcart_url": base_url,
        "audit_packet_hash": packet_hash,
        "quote_id": purchase_id,
        "import": result,
        "audit_export_url": f"{base_url}/v1/audit/{urllib.parse.quote(purchase_id)}/export" if purchase_id else "",
        "dashboard_url": f"{base_url}/?purchase_id={urllib.parse.quote(purchase_id)}" if purchase_id else base_url,
    }


def checkout_payload(args: dict[str, Any]) -> dict[str, Any]:
    if not args.get("approved"):
        raise SystemExit("approved=true is required before checkout")
    quote = args["quote"]
    trust = quote_trust_metadata(quote)
    approval_record = validated_or_new_approval_record(args, quote)
    expected_approval_hash = approval_record["approval_hash"]
    supplied_approval_hash = str(args.get("approval_hash") or "")
    if supplied_approval_hash != expected_approval_hash:
        raise SystemExit("approval_hash does not match the current quote approval packet")
    if args.get("use_tempo_demo_proof"):
        receipt = demo_payment_receipt(quote)
    else:
        receipt = supplied_payment_receipt(quote, args)
    stable_order_id = f"skill_{expected_approval_hash[:24]}"
    destination = payment_destination(quote, args.get("payment_rail"))
    order_id = args.get("agentcart_order_id") or args.get("idempotency_key") or stable_order_id
    decision_record = approval_decision_record(args, approval_record)
    audit_packet = skill_audit_packet(
        order_id=str(order_id),
        quote=quote,
        approval_record=approval_record,
        decision_record=decision_record,
        receipt=receipt,
        occurred_at=str(args.get("audit_event_timestamp") or args.get("event_timestamp") or "") or None,
    )
    return {
        "agentcart_order_id": order_id,
        "merchant_quote_id": quote["id"],
        "quote_hash": quote["quote_hash"],
        "quote": quote,
        "rail": destination.get("rail"),
        "payment_destination": destination,
        "merchant_origin": trust.get("merchant_origin") or "",
        "registry_record_hash": trust.get("registry_record_hash") or "",
        "quote_trust": trust,
        "approval_hash": expected_approval_hash,
        "approval_record": approval_record,
        "approval_record_hash": approval_record["approval_record_hash"],
        "approval_decision_record": decision_record,
        "approval_decision_hash": decision_record["decision_record_hash"],
        "audit_packet": audit_packet,
        "audit_packet_hash": audit_packet["audit_packet_hash"],
        "reason": args.get("reason") or "Skill-only ShopBridge agent checkout",
        "payment_receipt": receipt,
    }


def command_checkout(args: dict[str, Any]) -> dict[str, Any]:
    payload = checkout_payload(args)
    base_url = checkout_base_url_for_quote(args, payload["quote"])
    return request_json("/wp-json/agentcart/v1/orders", method="POST", payload=payload, base_url=base_url)


def command_order_status(args: dict[str, Any]) -> dict[str, Any]:
    status_url = str(args.get("status_url") or "")
    if status_url:
        parsed = urllib.parse.urlsplit(status_url)
        path = parsed.path
        if parsed.query:
            path = f"{path}?{parsed.query}"
        token = args.get("status_token") or args.get("token")
        headers = {"X-AgentCart-Order-Token": str(token)} if token else None
        base_url = origin_for_url(status_url) if parsed.scheme and parsed.netloc else base_url_from_args(args)
        require_trusted_merchant_origin(base_url, args, field="status_url" if parsed.scheme and parsed.netloc else "base_url")
        return request_json(path, headers=headers, base_url=base_url)
    order_id = str(args.get("order_id") or args.get("id") or "")
    if not order_id:
        raise SystemExit("order_id or status_url is required")
    token = args.get("status_token") or args.get("token")
    headers = {"X-AgentCart-Order-Token": str(token)} if token else None
    return request_json(
        f"/wp-json/agentcart/v1/orders/{urllib.parse.quote(order_id)}/status",
        headers=headers,
        base_url=base_url_from_args(args),
    )


def command_aftercare_summary(args: dict[str, Any]) -> dict[str, Any]:
    order = args.get("order") or args.get("status") or args.get("order_status")
    if not isinstance(order, dict):
        order = command_order_status(args)
    return compact_aftercare(order, args)


def main() -> None:
    request = json.load(sys.stdin)
    command = request.get("command")
    args = request.get("args") or {}
    if command == "manifest":
        result = command_manifest(args)
        compact = result
    elif command == "capability":
        result = command_capability(args)
        compact = result
    elif command == "readiness":
        compact = command_readiness(args)
    elif command == "doctor":
        compact = command_doctor(args)
    elif command == "resolve_merchant":
        compact = command_resolve_merchant(args)
    elif command == "catalog":
        result = command_catalog(args)
        compact = compact_catalog(result) if args.get("compact", True) else result
    elif command == "product":
        result = command_product(args)
        compact = result
    elif command == "quote":
        result = command_quote(args)
        compact = compact_quote(result) if args.get("compact") or args.get("format") == "toon" else result
    elif command == "discover_quotes":
        compact = command_discover_quotes(args)
    elif command == "discover_basket_quotes":
        compact = command_discover_basket_quotes(args)
    elif command == "approval_summary":
        compact = command_approval_summary(args)
    elif command == "approval_packet":
        compact = approval_packet(args["quote"], payment_rail=args.get("payment_rail"))
    elif command == "checkout_preflight":
        compact = command_checkout_preflight(args)
    elif command == "payment_handoff":
        compact = command_payment_handoff(args)
    elif command == "checkout":
        result = command_checkout(args)
        compact = result
    elif command == "checkout_with_tempo_demo_proof":
        args["use_tempo_demo_proof"] = True
        result = command_checkout(args)
        compact = result
    elif command == "checkout_payload":
        compact = checkout_payload(args)
    elif command == "audit_import":
        compact = command_audit_import(args)
    elif command == "order_status":
        result = command_order_status(args)
        compact = result
    elif command == "aftercare_summary":
        compact = command_aftercare_summary(args)
    else:
        raise SystemExit(f"Unknown command: {command}")

    if args.get("format") == "toon":
        print(to_toon(compact, name=command or "result"))
    else:
        print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
