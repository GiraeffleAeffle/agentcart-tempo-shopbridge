"""Canonical Merchant Registry Trust verification for every ShopBridge consumer.

The module owns the identity/integrity rules shared by the AgentCart service,
the portable Direct Skill, and registry tooling. Network I/O is deliberately
outside the module: callers inject a small JSON-document fetch adapter, while
tests pass snapshots or an in-memory adapter.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import importlib.util
import ipaddress
import json
import pathlib
import re
import sys
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable


TRUST_CONTRACT = "agentcart.registry_trust_contract.v1"
TRUST_IMPLEMENTATION = "shopbridge_registry_trust.v1"
JsonFetcher = Callable[[str], dict[str, Any]]


def _load_discovery_facets_module():
    loaded = sys.modules.get("shopbridge_discovery_facets")
    if loaded is not None:
        return loaded
    path = pathlib.Path(__file__).resolve().with_name("shopbridge_discovery_facets.py")
    spec = importlib.util.spec_from_file_location("shopbridge_discovery_facets", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Discovery Facets module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["shopbridge_discovery_facets"] = module
    spec.loader.exec_module(module)
    return module


discovery_facets = _load_discovery_facets_module()


@dataclass(frozen=True)
class TrustPolicy:
    max_age_days: int = 180
    hmac_secret: str = ""
    future_skew_seconds: int = 10 * 60
    now: dt.datetime | None = None

    def current_time(self) -> dt.datetime:
        value = self.now or dt.datetime.now(dt.timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)


def canonical_json(value: Any) -> str:
    """Match the ShopBridge plugin's stable JSON representation."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


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
    return canonical_json_hash(registry_signature_payload(record))


def parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def isoformat(value: dt.datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parsed_url(value: Any) -> urllib.parse.ParseResult:
    return urllib.parse.urlparse(str(value or ""))


def normalized_domain(value: Any) -> str:
    domain = str(value or "").strip().lower()
    if domain.endswith("."):
        domain = domain[:-1]
    if not domain:
        return ""
    try:
        domain.encode("ascii")
    except UnicodeEncodeError:
        return ""
    if len(domain) > 253:
        return ""
    labels = domain.split(".")
    for label in labels:
        if (
            not label
            or len(label) > 63
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
        ):
            return ""
        # Python's built-in IDNA 2003 mapping and Node's UTS-46 mapping are not
        # equivalent. Until the portable skill ships one shared UTS-46
        # implementation, rejecting IDN A-labels is safer than hashing them
        # differently in two verifier runtimes.
        if label.startswith("xn--"):
            return ""
    return domain


def domain_matches_url(domain: Any, url: urllib.parse.ParseResult | str) -> bool:
    parsed = parsed_url(url) if isinstance(url, str) else url
    return bool(normalized_domain(domain) and normalized_domain(domain) == normalized_domain(parsed.hostname))


def local_or_private_host(host: Any) -> bool:
    normalized = str(host or "").strip().strip("[]").rstrip(".").lower()
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith((".localhost", ".local")):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address.is_reserved
    )


def secure_url_errors(
    value: Any,
    *,
    field: str,
    domain: Any = "",
    well_known: bool = False,
) -> list[str]:
    url = str(value or "")
    parsed = parsed_url(url)
    errors: list[str] = []
    if not url:
        return [f"{field}_missing"]
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        return [f"{field}_invalid"]
    if parsed.username or parsed.password:
        errors.append(f"{field}_userinfo_forbidden")
    if parsed.scheme != "https" and not local_or_private_host(parsed.hostname):
        errors.append(f"{field}_requires_https")
    if domain and not domain_matches_url(domain, parsed):
        errors.append(f"{field}_domain_mismatch")
    if well_known and not parsed.path.startswith("/.well-known/"):
        errors.append(f"{field}_requires_well_known_path")
    return errors


def protocol_profiles(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    profiles = document.get("protocol_profiles") if isinstance(document.get("protocol_profiles"), list) else []
    return [profile for profile in profiles if isinstance(profile, dict) and profile.get("id")]


def protocol_profile_ids(document: dict[str, Any] | None) -> list[str]:
    return [str(profile["id"]) for profile in protocol_profiles(document)]


def raw_onchain_identity(value: dict[str, Any]) -> Any:
    if "onchain_identity" in value:
        return value.get("onchain_identity")
    return value.get("erc8004_identity")


def onchain_identity_payload(value: dict[str, Any]) -> dict[str, str]:
    raw = raw_onchain_identity(value)
    if not isinstance(raw, dict):
        return {}
    standard = str(raw.get("standard") or raw.get("type") or "").strip()
    if not standard and "erc8004_identity" in value:
        standard = "ERC-8004"
    aliases = {
        "chain": "chain_id",
        "chainId": "chain_id",
        "controller_address": "controller",
        "merchant_controller": "controller",
        "registry": "registry_address",
        "registry_contract": "registry_address",
        "contract": "registry_address",
        "id": "record_id",
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
        "controller",
        "controller_address",
        "merchant_controller",
        "registry_address",
        "registry",
        "registry_contract",
        "contract",
        "record_id",
        "id",
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
        supplied = str(raw.get(source_key) or "").strip()
        if supplied:
            payload[target_key] = supplied
    return payload


def onchain_identity_requires_controller_proof(payload: dict[str, str]) -> bool:
    return any(
        payload.get(field)
        for field in (
            "controller",
            "record_id",
            "chain_id",
            "registry_address",
            "registration_tx_hash",
            "attestation_hash",
        )
    )


def controller_proof_fields(record: dict[str, Any]) -> dict[str, str]:
    payload = onchain_identity_payload(record)
    if not onchain_identity_requires_controller_proof(payload):
        return {}
    return {field: payload.get(field, "") for field in ("controller", "chain_id", "registry_address", "record_id")}


def verify_onchain_identity(record: dict[str, Any]) -> list[str]:
    raw = raw_onchain_identity(record)
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return ["onchain_identity_must_be_object"]
    errors: list[str] = []
    payload = onchain_identity_payload(record)
    standard = payload.get("standard", "").lower().replace("_", "-")
    if standard not in {"erc-8004", "erc8004", "eip-8004", "eip8004", "agentcart-onchain-registry-v1"}:
        errors.append("onchain_identity_standard_unsupported")
    if not any(
        payload.get(field)
        for field in ("agent_id", "service_id", "registration_uri", "registration_tx_hash", "attestation_hash", "registry_address")
    ):
        errors.append("onchain_identity_missing_anchor")
    chain_id = payload.get("chain_id", "")
    if chain_id and not re.fullmatch(r"(eip155:)?[0-9]{1,20}", chain_id):
        errors.append("onchain_identity_chain_id_invalid")
    for field in ("controller", "registry_address"):
        supplied = payload.get(field, "")
        if supplied and not re.fullmatch(r"0x[0-9a-fA-F]{40}", supplied):
            errors.append(f"onchain_identity_{field}_invalid")
    record_id = payload.get("record_id", "")
    if record_id and not re.fullmatch(r"(0x)?[0-9a-fA-F]{64}", record_id):
        errors.append("onchain_identity_record_id_invalid")
    for field in ("registration_tx_hash", "attestation_hash"):
        supplied = payload.get(field, "")
        if supplied.startswith("0x") and not re.fullmatch(r"0x[0-9a-fA-F]{64}", supplied):
            errors.append(f"onchain_identity_{field}_invalid")
    if onchain_identity_requires_controller_proof(payload):
        for field in ("controller", "chain_id", "registry_address", "record_id"):
            if not payload.get(field):
                errors.append(f"onchain_identity_{field}_missing")
    proof_url = payload.get("proof_url", "")
    if proof_url:
        errors.extend(secure_url_errors(proof_url, field="onchain_identity_proof_url"))
    return errors


def verify_updated_at(record: dict[str, Any], policy: TrustPolicy) -> list[str]:
    supplied = str(record.get("updated_at") or "")
    if not supplied:
        return ["missing_updated_at"]
    parsed = parse_time(supplied)
    if parsed is None:
        return ["updated_at_invalid"]
    errors: list[str] = []
    now = policy.current_time()
    if parsed > now + dt.timedelta(seconds=policy.future_skew_seconds):
        errors.append("updated_at_in_future")
    if policy.max_age_days > 0 and parsed < now - dt.timedelta(days=policy.max_age_days):
        errors.append("record_stale")
    return errors


def verify_domain_proof(record: dict[str, Any], proof: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    supplied_hash = str(proof.get("record_hash") or "")
    expected_hash = registry_record_hash(record)
    if not supplied_hash:
        errors.append("domain_proof_record_hash_missing")
    elif not hmac.compare_digest(expected_hash.lower(), supplied_hash.lower()):
        errors.append("domain_proof_record_hash_mismatch")
    required = ["merchant_id", "domain", "manifest_url", "payment_network", "payment_recipient", "updated_at"]
    if record.get("revocation_url"):
        required.append("revocation_url")
    required.append("registry_claim_hash" if record.get("registry_claim_hash") else "manifest_hash")
    for field, expected in controller_proof_fields(record).items():
        supplied = str(proof.get(field) or "")
        if expected and supplied and expected.lower() != supplied.lower():
            errors.append(f"domain_proof_{field}_mismatch")
        elif expected and not supplied:
            errors.append(f"domain_proof_{field}_missing")
    for field in required:
        expected = str(record.get(field) or "")
        supplied = str(proof.get(field) or "")
        if expected and supplied and expected != supplied:
            errors.append(f"domain_proof_{field}_mismatch")
        elif expected and not supplied:
            errors.append(f"domain_proof_{field}_missing")
    return errors


def validate_revocation_document(record: dict[str, Any], document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_merchant = str(record.get("merchant_id") or "")
    supplied_merchant = str(document.get("merchant_id") or "")
    if supplied_merchant and expected_merchant and supplied_merchant != expected_merchant:
        errors.append("revocation_merchant_id_mismatch")
    expected_domain = normalized_domain(record.get("domain"))
    supplied_domain = normalized_domain(document.get("domain"))
    if supplied_domain and expected_domain and supplied_domain != expected_domain:
        errors.append("revocation_domain_mismatch")
    return errors


def revocation_document_revokes_record(record: dict[str, Any], document: dict[str, Any]) -> bool:
    candidates: list[dict[str, Any]] = [document]
    for key in ("revocations", "revoked_records", "records"):
        value = document.get(key)
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))
    expected_hash = registry_record_hash(record)
    expected_merchant = str(record.get("merchant_id") or "")
    expected_domain = normalized_domain(record.get("domain"))
    for candidate in candidates:
        if not (candidate.get("revoked") or candidate.get("revoked_at")):
            continue
        supplied_hash = str(candidate.get("record_hash") or candidate.get("registry_record_hash") or "")
        if supplied_hash:
            if hmac.compare_digest(expected_hash.lower(), supplied_hash.lower()):
                return True
            continue
        supplied_merchant = str(candidate.get("merchant_id") or "")
        supplied_domain = normalized_domain(candidate.get("domain"))
        if (
            str(candidate.get("applies_to") or "").lower() in {"merchant", "all_records"}
            and expected_merchant
            and supplied_merchant == expected_merchant
            and (not supplied_domain or supplied_domain == expected_domain)
        ):
            return True
    return False


def verify_registry_claim(record: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    expected_hash = str(record.get("registry_claim_hash") or "")
    if not expected_hash:
        expected_manifest_hash = str(record.get("manifest_hash") or "")
        hash_alg = str(record.get("manifest_hash_alg") or "sha-256").lower()
        errors = [] if hash_alg in {"sha-256", "sha256"} else ["manifest_hash_alg_unsupported"]
        if not expected_manifest_hash:
            errors.append("missing_manifest_hash")
        elif not hmac.compare_digest(expected_manifest_hash, canonical_json_hash(manifest)):
            errors.append("manifest_hash_mismatch")
        return errors
    errors: list[str] = []
    if str(record.get("registry_claim_hash_alg") or "sha-256").lower() not in {"sha-256", "sha256"}:
        errors.append("registry_claim_hash_alg_unsupported")
    discovery = manifest.get("discovery") if isinstance(manifest.get("discovery"), dict) else {}
    claim = discovery.get("registry_claim") if isinstance(discovery.get("registry_claim"), dict) else {}
    if not claim:
        errors.append("registry_claim_missing_in_manifest")
        return errors
    if not hmac.compare_digest(expected_hash, canonical_json_hash(claim)):
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
    list_fields = (
        ("ship_to_countries", lambda value: str(value).upper()),
        ("supported_protocols", str),
        ("protocol_profile_ids", str),
    )
    for field, normalizer in list_fields:
        expected = sorted(normalizer(value) for value in record.get(field, []) if value)
        supplied = sorted(normalizer(value) for value in claim.get(field, []) if value)
        if expected and expected != supplied:
            errors.append(f"registry_claim_{field}_mismatch")
    expected_facets = record.get("discovery_facets")
    supplied_facets = claim.get("discovery_facets")
    if isinstance(expected_facets, dict) and not isinstance(supplied_facets, dict):
        errors.append("registry_claim_discovery_facets_missing")
    elif isinstance(supplied_facets, dict) and not isinstance(expected_facets, dict):
        errors.append("registry_record_discovery_facets_missing")
    elif isinstance(expected_facets, dict) and canonical_json_hash(expected_facets) != canonical_json_hash(supplied_facets):
        errors.append("registry_claim_discovery_facets_mismatch")
    expected_onchain = onchain_identity_payload(record)
    supplied_onchain = onchain_identity_payload(claim)
    if expected_onchain and not supplied_onchain:
        errors.append("registry_claim_onchain_identity_missing")
    elif expected_onchain and canonical_json_hash(expected_onchain) != canonical_json_hash(supplied_onchain):
        errors.append("registry_claim_onchain_identity_mismatch")
    expected_endpoints = record.get("endpoints") if isinstance(record.get("endpoints"), dict) else {}
    supplied_endpoints = claim.get("endpoints") if isinstance(claim.get("endpoints"), dict) else {}
    for name, endpoint in expected_endpoints.items():
        supplied = supplied_endpoints.get(name)
        if endpoint and supplied and endpoint != supplied:
            errors.append(f"registry_claim_endpoint_{name}_mismatch")
        elif endpoint and not supplied:
            errors.append(f"registry_claim_endpoint_{name}_missing")
    return errors


def manifest_payment_binding(manifest: dict[str, Any]) -> tuple[str, str]:
    for profile in protocol_profiles(manifest):
        profile_id = str(profile.get("id") or "")
        protocol_id = str(profile.get("payment_protocol_id") or "")
        if profile_id in {"mpp-http-auth", "tempo-mpp"} or protocol_id == "tempo-mpp":
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


def verify_payment_binding(record: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    manifest_network, manifest_recipient = manifest_payment_binding(manifest)
    expected_recipient = str(record.get("payment_recipient") or "").lower()
    expected_network = str(record.get("payment_network") or "").lower()
    if expected_recipient and not manifest_recipient:
        return ["payment_recipient_missing_in_manifest"]
    if expected_recipient and expected_recipient != manifest_recipient.lower():
        return ["payment_recipient_mismatch"]
    if expected_network and manifest_network and expected_network != manifest_network.lower():
        return ["payment_network_mismatch"]
    return []


def verify_shipping_scope(record: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    expected = {str(value).upper() for value in record.get("ship_to_countries", []) if value}
    delivery = manifest.get("delivery") if isinstance(manifest.get("delivery"), dict) else {}
    supplied = {str(value).upper() for value in delivery.get("ship_to_countries", []) if value}
    if expected and not supplied:
        return ["shipping_scope_missing_in_manifest"]
    if expected and not expected.issubset(supplied):
        return ["shipping_scope_mismatch"]
    return []


def verify_endpoint_scope(record: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    endpoints = manifest.get("endpoints") if isinstance(manifest.get("endpoints"), dict) else {}
    for required in ("catalog", "quote"):
        if not endpoints.get(required):
            errors.append(f"endpoint_{required}_missing")
    for name, value in endpoints.items():
        endpoint = str(value or "")
        if not endpoint or endpoint.startswith("/"):
            continue
        errors.extend(secure_url_errors(endpoint, field=f"endpoint_{name}", domain=record.get("domain")))
    return errors


def _document(
    record: dict[str, Any],
    explicit: dict[str, Any] | None,
    snapshot_field: str,
    *,
    allow_embedded_snapshot: bool = True,
) -> tuple[dict[str, Any] | None, str]:
    if isinstance(explicit, dict):
        return explicit, "snapshot"
    snapshot = record.get(snapshot_field)
    if allow_embedded_snapshot and isinstance(snapshot, dict):
        return snapshot, "snapshot"
    return None, "url"


def _fetch_document(fetch_json: JsonFetcher | None, url: str) -> dict[str, Any] | None:
    if fetch_json is None:
        return None
    value = fetch_json(url)
    return value if isinstance(value, dict) else None


def _dedupe(errors: list[str]) -> list[str]:
    return list(dict.fromkeys(errors))


def verify_registry_record(
    record: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
    proof: dict[str, Any] | None = None,
    revocation: dict[str, Any] | None = None,
    fetch_json: JsonFetcher | None = None,
    policy: TrustPolicy | None = None,
) -> dict[str, Any]:
    """Verify one Registry Record through the complete trust interface."""

    policy = policy or TrustPolicy()
    errors: list[str] = []
    merchant_id = str(record.get("merchant_id") or "")
    domain = str(record.get("domain") or "")
    manifest_url = str(record.get("manifest_url") or "")
    if not merchant_id:
        errors.append("missing_merchant_id")
    if not manifest_url:
        errors.append("missing_manifest_url")
    if not domain:
        errors.append("missing_domain")
    elif not normalized_domain(domain):
        errors.append("domain_invalid")
    if record.get("revoked_at"):
        errors.append("record_revoked")
    errors.extend(verify_updated_at(record, policy))
    errors.extend(secure_url_errors(manifest_url, field="manifest_url", domain=domain))
    errors.extend(verify_onchain_identity(record))
    errors.extend(discovery_facets.validate_discovery_facets(record.get("discovery_facets")))

    signature_alg = str(record.get("signature_alg") or "").lower()
    signature = str(record.get("signature") or "")
    proof_type = ""
    proof_url = ""
    # Proof and revocation snapshots are not buyer-authoritative. A live
    # verifier with a fetch adapter must consult the current well-known control
    # documents instead of allowing either an embedded or caller-supplied
    # snapshot to mask loss of domain control or a later revocation. Explicit
    # control snapshots remain available only to callers that opt into
    # deterministic offline library verification by omitting fetch_json.
    live_documents = fetch_json is not None
    proof_document, proof_source = _document(
        record,
        None if live_documents else proof,
        "proof_snapshot",
        allow_embedded_snapshot=not live_documents,
    )
    if signature_alg in {"https-domain-proof", "agentcart-domain-v1"}:
        proof_descriptor = record.get("proof") if isinstance(record.get("proof"), dict) else {}
        proof_type = str(proof_descriptor.get("type") or "").lower()
        proof_url = str(proof_descriptor.get("url") or "")
        if proof_type not in {"https-well-known", "agentcart-domain-v1"}:
            errors.append("domain_proof_type_unsupported")
        proof_url_issues = secure_url_errors(proof_url, field="domain_proof_url", domain=domain, well_known=True)
        errors.extend(proof_url_issues)
        if proof_document is None and not proof_url_issues:
            try:
                proof_document = _fetch_document(fetch_json, proof_url)
            except Exception:
                proof_document = None
        if proof_document is None:
            errors.append("domain_proof_fetch_failed")
        else:
            errors.extend(verify_domain_proof(record, proof_document))
    elif signature_alg == "hmac-sha256":
        if not policy.hmac_secret:
            errors.append("signature_secret_missing")
        else:
            expected = "hmac-sha256:" + hmac.new(
                policy.hmac_secret.encode("utf-8"),
                canonical_json(registry_signature_payload(record)).encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            supplied = signature if signature.startswith("hmac-sha256:") else f"hmac-sha256:{signature}"
            if not hmac.compare_digest(expected, supplied):
                errors.append("signature_invalid")
    elif signature_alg in {"", "none"} and not signature:
        errors.append("missing_signature")
    else:
        errors.append("signature_alg_unsupported")

    revocation_document, revocation_source = _document(
        record,
        None if live_documents else revocation,
        "revocation_snapshot",
        allow_embedded_snapshot=not live_documents,
    )
    revocation_url = str(record.get("revocation_url") or "")
    if revocation_url:
        revocation_url_issues = secure_url_errors(
            revocation_url,
            field="revocation_url",
            domain=domain,
            well_known=True,
        )
        errors.extend(revocation_url_issues)
        if revocation_document is None and not revocation_url_issues:
            try:
                revocation_document = _fetch_document(fetch_json, revocation_url)
            except Exception:
                revocation_document = None
        if revocation_document is None:
            errors.append("revocation_fetch_failed")
        else:
            errors.extend(validate_revocation_document(record, revocation_document))
            if revocation_document_revokes_record(record, revocation_document):
                errors.append("record_revoked_by_revocation_document")

    # A manifest snapshot is safe to retain as an archive input because the
    # Registry Record commits its identity, endpoints, payment, shipping, and
    # registry claim fields and all are checked below. Unlike proof/revocation,
    # it is not a mutable domain-control signal.
    manifest_document, manifest_source = _document(record, manifest, "manifest_snapshot")
    manifest_url_issues = secure_url_errors(manifest_url, field="manifest_url", domain=domain)
    if manifest_document is None and not manifest_url_issues:
        try:
            manifest_document = _fetch_document(fetch_json, manifest_url)
        except Exception:
            manifest_document = None
    if manifest_document is None:
        errors.append("manifest_fetch_failed")
    else:
        errors.extend(verify_registry_claim(record, manifest_document))
        merchant = manifest_document.get("merchant") if isinstance(manifest_document.get("merchant"), dict) else {}
        manifest_merchant_id = str(merchant.get("id") or "")
        if merchant_id and manifest_merchant_id and merchant_id != manifest_merchant_id:
            errors.append("merchant_id_mismatch")
        errors.extend(verify_payment_binding(record, manifest_document))
        errors.extend(verify_shipping_scope(record, manifest_document))
        errors.extend(verify_endpoint_scope(record, manifest_document))

    errors = _dedupe(errors)
    return {
        "contract": TRUST_CONTRACT,
        "implementation": TRUST_IMPLEMENTATION,
        "state": "verified" if not errors else "rejected",
        "errors": errors,
        "checked_at": isoformat(policy.current_time()),
        "signature_alg": signature_alg,
        "proof_type": proof_type,
        "record_hash": registry_record_hash(record),
        "manifest": manifest_document,
        "proof": proof_document,
        "revocation": revocation_document,
        "manifest_source": manifest_source,
        "proof_source": proof_source,
        "revocation_source": revocation_source,
    }
