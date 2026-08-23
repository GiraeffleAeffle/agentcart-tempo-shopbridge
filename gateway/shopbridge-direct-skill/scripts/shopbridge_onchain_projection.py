"""Replay finalized ShopBridge registry contract events into discovery state.

The RPC collector is responsible for finality and fetching committed records.
This module is the deterministic projection boundary shared by the gateway and
registry operator tooling.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from typing import Any, Callable


CONTRACT_EVENTS_SCHEMA = "agentcart.onchain_registry_contract_events.v1"
CONTRACT_INDEX_SCHEMA = "agentcart.onchain_registry_contract_index.v1"
LEDGER_PROOF_SCHEMA = "agentcart.onchain_registry_ledger_proof.v1"
PROJECTION_IMPLEMENTATION = "shopbridge_onchain_projection.v1"
RPC_INDEXER_IMPLEMENTATION = "agentcart.onchain_registry_rpc_indexer.v1"
DIRECT_RPC_IMPLEMENTATION = "agentcart.onchain_registry_direct_rpc.v1"
INDEPENDENT_VERIFICATION_SCHEMA = "agentcart.onchain_registry_independent_verification.v1"

ALLOWED_EVENTS = {
    "MerchantRegistered",
    "MerchantUpdated",
    "ControllerChanged",
    "MerchantRevoked",
    "MerchantForceRevoked",
    "SupersessionRequested",
    "SupersessionApproved",
    "SupersessionCanceled",
    "SupersessionActivated",
    "MerchantAttested",
    "MerchantSuspended",
    "MerchantUnsuspended",
    "MerchantFlagged",
    "ValidatorSet",
    "AttestationThresholdSet",
    "GovernanceActionScheduled",
    "GovernanceActionCanceled",
    "WritesPaused",
    "OwnershipTransferStarted",
    "OwnershipTransferred",
}

RECORD_ID_EVENT_FIELDS = {
    "MerchantRegistered": "recordId",
    "MerchantUpdated": "recordId",
    "ControllerChanged": "recordId",
    "MerchantRevoked": "recordId",
    "MerchantForceRevoked": "recordId",
    "SupersessionRequested": "pendingRecordId",
    "SupersessionApproved": "pendingRecordId",
    "SupersessionCanceled": "pendingRecordId",
    "SupersessionActivated": "recordId",
    "MerchantAttested": "recordId",
    "MerchantSuspended": "recordId",
    "MerchantUnsuspended": "recordId",
    "MerchantFlagged": "recordId",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def is_hash(value: Any) -> bool:
    return bool(re.fullmatch(r"(?:0x)?[0-9a-fA-F]{64}", str(value or "")))


def normalized_hash(value: Any, *, prefix: bool = False) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        return ""
    return f"0x{text}" if prefix else text


def is_address(value: Any) -> bool:
    return bool(re.fullmatch(r"0x[0-9a-fA-F]{40}", str(value or "")))


def is_prefixed_hash(value: Any) -> bool:
    return bool(re.fullmatch(r"0x[0-9a-fA-F]{64}", str(value or "")))


def strict_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def event_args(event: dict[str, Any]) -> dict[str, Any]:
    args = event.get("args")
    return args if isinstance(args, dict) else {}


def arg(args: dict[str, Any], *names: str) -> str:
    for name in names:
        value = args.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def record_id(event: dict[str, Any]) -> str:
    name = str(event.get("event") or "")
    field = RECORD_ID_EVENT_FIELDS.get(name, "")
    if not field:
        return ""
    args = event_args(event)
    aliases = {
        "recordId": ("recordId", "record_id"),
        "pendingRecordId": ("pendingRecordId", "pending_record_id"),
    }
    return normalized_hash(arg(args, *aliases[field]), prefix=True)


def event_record_hash(event: dict[str, Any]) -> str:
    args = event_args(event)
    return normalized_hash(arg(args, "recordHash", "record_hash", "newRecordHash", "new_record_hash"))


def attached_record(event: dict[str, Any]) -> dict[str, Any] | None:
    record = event.get("registry_record")
    if isinstance(record, dict):
        return copy.deepcopy(record)
    record = event.get("onchain_record")
    if isinstance(record, dict):
        return copy.deepcopy(record)
    return None


def attached_record_hash(
    event: dict[str, Any],
    record_hash: Callable[[dict[str, Any]], str],
) -> str:
    record = event.get("registry_record")
    if isinstance(record, dict):
        return normalized_hash(record_hash(record))
    record = event.get("onchain_record")
    if isinstance(record, dict):
        return normalized_hash(record.get("record_hash"))
    return ""


def record_identity(record: dict[str, Any]) -> dict[str, Any] | None:
    identity = record.get("onchain_identity")
    if identity is None:
        identity = record.get("erc8004_identity")
    return identity if isinstance(identity, dict) else None


def identity_value(identity: dict[str, Any], *names: str) -> str:
    for name in names:
        value = identity.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def finalized_document_errors(
    document: Any,
    *,
    require_finality: bool,
    expected_chain_id: str = "",
    expected_registry_address: str = "",
    max_age_seconds: int = 0,
    now: dt.datetime | None = None,
    expected_implementation: str = RPC_INDEXER_IMPLEMENTATION,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    if not isinstance(document, dict):
        return [], [{"error": "contract_events_document_must_be_object"}]
    if str(document.get("schema") or "") != CONTRACT_EVENTS_SCHEMA:
        errors.append({"error": "contract_events_schema_mismatch"})
    events = document.get("events")
    if not isinstance(events, list):
        return [], [*errors, {"error": "contract_events_missing"}]
    if any(not isinstance(event, dict) for event in events):
        errors.append({"error": "contract_event_must_be_object"})
        events = [event for event in events if isinstance(event, dict)]

    chain_id = str(document.get("chain_id") or "")
    registry_address = str(document.get("registry_address") or "")
    if expected_chain_id and chain_id != expected_chain_id:
        errors.append({"error": "contract_events_chain_id_mismatch"})
    if expected_registry_address and registry_address.lower() != expected_registry_address.lower():
        errors.append({"error": "contract_events_registry_address_mismatch"})

    if not require_finality:
        return events, errors
    implementation = str(document.get("implementation") or "")
    if implementation != expected_implementation:
        errors.append({"error": "contract_events_indexer_implementation_mismatch"})
    if not re.fullmatch(r"eip155:[0-9]{1,20}", chain_id):
        errors.append({"error": "contract_events_chain_id_invalid"})
    if not is_address(registry_address):
        errors.append({"error": "contract_events_registry_address_invalid"})
    if document.get("complete") is not True:
        errors.append({"error": "contract_events_snapshot_incomplete"})
    document_errors = document.get("errors")
    if not isinstance(document_errors, list) or document_errors:
        errors.append({"error": "contract_events_snapshot_has_errors"})
    reference = now or dt.datetime.now(dt.timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=dt.timezone.utc)
    reference = reference.astimezone(dt.timezone.utc)
    indexed_at = parse_time(document.get("indexed_at"))
    if indexed_at is None:
        errors.append({"error": "contract_events_indexed_at_invalid"})
    else:
        if indexed_at > reference + dt.timedelta(minutes=5):
            errors.append({"error": "contract_events_indexed_at_future"})
        elif max_age_seconds > 0 and indexed_at < reference - dt.timedelta(seconds=max_age_seconds):
            errors.append({"error": "contract_events_snapshot_stale"})

    finality = document.get("finality")
    if not isinstance(finality, dict):
        errors.append({"error": "contract_events_finality_missing"})
        return events, errors
    block_number = strict_nonnegative_int(finality.get("block_number"))
    indexed_from = strict_nonnegative_int(finality.get("indexed_from_block"))
    indexed_to = strict_nonnegative_int(finality.get("indexed_to_block"))
    if str(finality.get("block_tag") or "") != "finalized":
        errors.append({"error": "contract_events_finality_tag_invalid"})
    if block_number is None or not is_prefixed_hash(finality.get("block_hash")):
        errors.append({"error": "contract_events_finalized_block_invalid"})
    finalized_at = parse_time(finality.get("block_time"))
    if finalized_at is None:
        errors.append({"error": "contract_events_finalized_block_time_invalid"})
    elif finalized_at > reference + dt.timedelta(minutes=5):
        errors.append({"error": "contract_events_finalized_block_time_future"})
    elif max_age_seconds > 0 and finalized_at < reference - dt.timedelta(seconds=max_age_seconds):
        errors.append({"error": "contract_events_finalized_block_stale"})
    if indexed_from is None or indexed_to is None:
        errors.append({"error": "contract_events_indexed_range_invalid"})
    elif indexed_from > indexed_to or (block_number is not None and indexed_to > block_number):
        errors.append({"error": "contract_events_indexed_range_not_finalized"})

    if indexed_from is not None and indexed_to is not None:
        for sequence, event in enumerate(events, start=1):
            event_block = strict_nonnegative_int(event.get("block_number"))
            if event_block is None or event_block < indexed_from or event_block > indexed_to:
                errors.append({"sequence": sequence, "error": "contract_event_outside_indexed_range"})
            if not is_prefixed_hash(event.get("block_hash")):
                errors.append({"sequence": sequence, "error": "contract_event_block_hash_invalid"})
            if not is_prefixed_hash(event.get("transaction_hash")):
                errors.append({"sequence": sequence, "error": "contract_event_transaction_hash_invalid"})

    if implementation == DIRECT_RPC_IMPLEMENTATION:
        rpc = document.get("rpc")
        storage = document.get("contract_storage_verification")
        deployment_verification = document.get("deployment_verification")
        profile = str(rpc.get("profile") or "") if isinstance(rpc, dict) else ""
        source = str(document.get("source") or "")
        expected_source = {
            "standard": "direct_json_rpc",
            "myotis": "myotis_verified_json_rpc",
        }.get(profile, "")
        if not expected_source or source != expected_source:
            errors.append({"error": "contract_events_direct_source_profile_mismatch"})
        if not isinstance(storage, dict) or storage.get("status") != "matched":
            errors.append({"error": "contract_events_storage_verification_invalid"})
        else:
            checked_count = strict_nonnegative_int(storage.get("checked_record_count"))
            lifecycle_count = strict_nonnegative_int(document.get("lifecycle_record_count"))
            state_block = strict_nonnegative_int(storage.get("block_number"))
            storage_finalized = strict_nonnegative_int(storage.get("finalized_block_number"))
            if checked_count is None or lifecycle_count is None or checked_count != lifecycle_count:
                errors.append({"error": "contract_events_storage_checked_count_mismatch"})
            if storage_finalized != block_number:
                errors.append({"error": "contract_events_storage_finalized_block_mismatch"})
            if profile == "standard":
                if storage.get("scope") != "same_finalized_block" or state_block != block_number:
                    errors.append({"error": "contract_events_storage_scope_invalid"})
            elif profile == "myotis":
                if (
                    storage.get("scope") != "myotis_verified_head_conservative_cross_check"
                    or state_block is None
                    or block_number is None
                    or state_block < block_number
                ):
                    errors.append({"error": "contract_events_storage_scope_invalid"})
        if (
            not isinstance(deployment_verification, dict)
            or deployment_verification.get("status") not in {"matched", "pinned"}
            or strict_nonnegative_int(deployment_verification.get("block_number")) != indexed_from
            or not is_prefixed_hash(deployment_verification.get("block_hash"))
        ):
            errors.append({"error": "contract_events_deployment_verification_invalid"})
        elif profile == "standard" and deployment_verification.get("scope") != "historical_code_creation_boundary":
            errors.append({"error": "contract_events_deployment_verification_scope_invalid"})
        elif profile == "myotis" and (
            deployment_verification.get("status") != "pinned"
            or deployment_verification.get("scope")
            != "pinned_descriptor_constructor_log_and_verified_index_coverage"
            or deployment_verification.get("pinned_block_hash") is not True
            or not is_prefixed_hash(deployment_verification.get("transaction_hash"))
        ):
            errors.append({"error": "contract_events_deployment_verification_scope_invalid"})
        record_errors = document.get("record_errors")
        if not isinstance(record_errors, list):
            errors.append({"error": "contract_events_record_errors_invalid"})
        else:
            seen_record_errors: set[str] = set()
            for item in record_errors:
                if not isinstance(item, dict):
                    errors.append({"error": "contract_events_record_error_invalid"})
                    continue
                failed_id = normalized_hash(item.get("record_id"), prefix=True)
                if (
                    not is_hash(failed_id)
                    or failed_id in seen_record_errors
                    or not is_hash(normalized_hash(item.get("record_hash"), prefix=True))
                    or not str(item.get("code") or "")
                ):
                    errors.append({"error": "contract_events_record_error_invalid"})
                seen_record_errors.add(failed_id)
        selection = document.get("record_selection")
        selected_record_ids: list[str] = []
        active_record_ids: set[str] = set()
        for event in events:
            name = str(event.get("event") or "")
            target_id = record_id(event)
            if not target_id:
                continue
            if name == "MerchantRegistered":
                active_record_ids.add(target_id)
            elif name in {"MerchantRevoked", "MerchantSuspended"}:
                active_record_ids.discard(target_id)
            elif name == "MerchantUnsuspended":
                active_record_ids.add(target_id)
        if not isinstance(selection, dict):
            errors.append({"error": "contract_events_record_selection_invalid"})
        else:
            raw_selected = selection.get("selected_record_ids")
            active_count = strict_nonnegative_int(selection.get("active_candidate_count"))
            scope_count = strict_nonnegative_int(selection.get("selection_scope_count"))
            selected_count = strict_nonnegative_int(selection.get("selected_record_count"))
            candidate_limit = strict_nonnegative_int(selection.get("candidate_limit"))
            if (
                selection.get("schema") != "agentcart.onchain_registry_candidate_selection.v1"
                or selection.get("algorithm") != "sha256-query-seeded-record-id-sample"
                or selection.get("selection_mode")
                not in {"query_seeded_sample", "exact_record_or_domain"}
                or not re.fullmatch(r"[0-9a-f]{64}", str(selection.get("seed_sha256") or ""))
                or selection.get("before_record_fetch") is not True
                or not isinstance(raw_selected, list)
            ):
                errors.append({"error": "contract_events_record_selection_invalid"})
            else:
                selected_record_ids = [
                    normalized_hash(value, prefix=True) for value in raw_selected
                ]
                if (
                    any(not is_hash(value) for value in selected_record_ids)
                    or len(set(selected_record_ids)) != len(selected_record_ids)
                    or selected_count != len(selected_record_ids)
                    or active_count is None
                    or scope_count is None
                    or selected_count is None
                    or candidate_limit is None
                    or selected_count > active_count
                    or selected_count > scope_count
                    or scope_count > active_count
                    or selected_count > candidate_limit
                    or active_count != len(active_record_ids)
                    or not set(selected_record_ids).issubset(active_record_ids)
                ):
                    errors.append({"error": "contract_events_record_selection_invalid"})
                if any(failed_id not in set(selected_record_ids) for failed_id in seen_record_errors):
                    errors.append({"error": "contract_events_record_error_outside_selection"})

    independent = document.get("independent_verification")
    if independent is not None:
        if not isinstance(independent, dict):
            errors.append({"error": "contract_events_independent_verification_invalid"})
            return events, errors
        if str(independent.get("schema") or "") != INDEPENDENT_VERIFICATION_SCHEMA:
            errors.append({"error": "contract_events_independent_verification_schema_mismatch"})
        if str(independent.get("status") or "") != "matched":
            errors.append({"error": "contract_events_independent_verification_not_matched"})
        common_block = strict_nonnegative_int(independent.get("common_finalized_block"))
        if common_block is None or indexed_to is None or common_block != indexed_to:
            errors.append({"error": "contract_events_independent_verification_range_mismatch"})
        for field in (
            "chain_id_match",
            "registry_address_match",
            "finalized_time_lag_within_limit",
        ):
            if independent.get(field) is not True:
                errors.append({"error": f"contract_events_independent_verification_{field}_invalid"})
        if independent.get("finalized_head_hash_match") not in (None, True):
            errors.append({"error": "contract_events_independent_verification_head_hash_mismatch"})
        primary = independent.get("primary")
        witness = independent.get("witness_path")
        if not isinstance(primary, dict) or not isinstance(witness, dict):
            errors.append({"error": "contract_events_independent_verification_paths_invalid"})
        else:
            comparable = []
            for event in events:
                normalized = {
                    "event": str(event.get("event") or ""),
                    "block_number": int(event.get("block_number") or 0),
                    "block_hash": str(event.get("block_hash") or "").lower(),
                    "block_time": str(event.get("block_time") or ""),
                    "transaction_hash": str(event.get("transaction_hash") or "").lower(),
                    "log_index": int(event.get("log_index") or 0),
                    "args": event.get("args") if isinstance(event.get("args"), dict) else {},
                }
                if isinstance(event.get("registry_record"), dict):
                    normalized["registry_record"] = event["registry_record"]
                if event.get("record_fetch_error"):
                    normalized["record_fetch_error"] = str(event["record_fetch_error"])
                comparable.append(normalized)
            expected_hash = canonical_json_hash(comparable)
            for name, path in (("primary", primary), ("witness", witness)):
                event_count = strict_nonnegative_int(path.get("event_count"))
                supplied_hash = str(path.get("canonical_events_sha256") or "")
                if event_count != len(events):
                    errors.append(
                        {"error": f"contract_events_independent_verification_{name}_count_mismatch"}
                    )
                if supplied_hash != expected_hash:
                    errors.append(
                        {"error": f"contract_events_independent_verification_{name}_hash_mismatch"}
                    )
    return events, errors


def controller_binding_errors(
    events: list[dict[str, Any]],
    *,
    chain_id: str,
    registry_address: str,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    controller_by_record_id: dict[str, str] = {}
    record_document_events = {
        "MerchantRegistered",
        "MerchantUpdated",
        "ControllerChanged",
        "SupersessionActivated",
    }
    for sequence, event in enumerate(events, start=1):
        name = str(event.get("event") or "")
        args = event_args(event)
        target_id = record_id(event)
        supplied_controller = arg(args, "controller", "newController", "new_controller")
        expected_controller = supplied_controller or controller_by_record_id.get(target_id, "")
        if name in record_document_events:
            record = attached_record(event)
            identity = record_identity(record) if isinstance(record, dict) else None
            if identity is None:
                errors.append({"sequence": sequence, "error": "registry_record_onchain_identity_missing"})
            else:
                supplied_chain = identity_value(identity, "chain_id", "chain", "chainId")
                supplied_registry = identity_value(
                    identity, "registry_address", "registry", "registry_contract", "contract"
                )
                supplied_record_id = normalized_hash(
                    identity_value(identity, "record_id", "id"), prefix=True
                )
                identity_controller = identity_value(
                    identity, "controller", "controller_address", "merchant_controller"
                )
                if supplied_chain != chain_id:
                    errors.append({"sequence": sequence, "error": "registry_record_chain_id_mismatch"})
                if supplied_registry.lower() != registry_address.lower():
                    errors.append({"sequence": sequence, "error": "registry_record_registry_address_mismatch"})
                if supplied_record_id != target_id:
                    errors.append({"sequence": sequence, "error": "registry_record_record_id_mismatch"})
                if not expected_controller or identity_controller.lower() != expected_controller.lower():
                    errors.append({"sequence": sequence, "error": "registry_record_controller_mismatch"})
        if target_id and name in {
            "MerchantRegistered",
            "ControllerChanged",
            "SupersessionRequested",
            "SupersessionActivated",
        } and expected_controller:
            controller_by_record_id[target_id] = expected_controller
        if name == "MerchantRevoked":
            controller_by_record_id.pop(target_id, None)
    return errors


def event_ref(event: dict[str, Any], sequence: int) -> dict[str, Any]:
    return {
        "event": str(event.get("event") or ""),
        "sequence": sequence,
        "block_number": int(event.get("block_number") or 0),
        "block_hash": str(event.get("block_hash") or ""),
        "block_time": str(event.get("block_time") or ""),
        "transaction_hash": str(event.get("transaction_hash") or ""),
        "log_index": int(event.get("log_index") or 0),
    }


def verify_contract_events(
    events: list[dict[str, Any]],
    *,
    record_hash: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    seen_logs: set[tuple[str, int]] = set()
    previous_position: tuple[int, int] | None = None
    record_document_events = {
        "MerchantRegistered",
        "MerchantUpdated",
        "ControllerChanged",
        "SupersessionActivated",
    }
    record_hash_events = record_document_events | {
        "SupersessionRequested",
        "SupersessionApproved",
        "MerchantAttested",
    }
    for sequence, event in enumerate(events, start=1):
        name = str(event.get("event") or "")
        args = event_args(event)
        if name not in ALLOWED_EVENTS:
            errors.append({"sequence": sequence, "error": "event_name_unsupported", "event": name})
            continue
        if not args:
            errors.append({"sequence": sequence, "error": "event_args_missing", "event": name})
            continue
        position = (int(event.get("block_number") or 0), int(event.get("log_index") or 0))
        if previous_position is not None and position < previous_position:
            errors.append({"sequence": sequence, "error": "event_order_invalid", "event": name})
        previous_position = position
        tx_hash = str(event.get("transaction_hash") or "").lower()
        if tx_hash:
            log_key = (tx_hash, position[1])
            if log_key in seen_logs:
                errors.append({"sequence": sequence, "error": "event_log_duplicate", "event": name})
            seen_logs.add(log_key)
        if name in RECORD_ID_EVENT_FIELDS and not is_hash(record_id(event)):
            errors.append({"sequence": sequence, "error": "record_id_invalid", "event": name})
        if name in record_hash_events and not is_hash(event_record_hash(event)):
            errors.append({"sequence": sequence, "error": "record_hash_invalid", "event": name})
        if name in record_document_events:
            registry_record = event.get("registry_record")
            onchain_record = event.get("onchain_record")
            if not isinstance(registry_record, dict) and not isinstance(onchain_record, dict):
                errors.append({"sequence": sequence, "error": "registry_record_missing", "event": name})
            if isinstance(registry_record, dict):
                supplied_hash = normalized_hash(record_hash(registry_record))
                if supplied_hash != event_record_hash(event):
                    errors.append(
                        {"sequence": sequence, "error": "registry_record_hash_mismatch", "event": name}
                    )
            if isinstance(onchain_record, dict):
                supplied_hash = normalized_hash(onchain_record.get("record_hash"))
                if supplied_hash != event_record_hash(event):
                    errors.append(
                        {"sequence": sequence, "error": "onchain_record_hash_mismatch", "event": name}
                    )
        for field in ("controller", "newController", "validator", "flagger", "operator", "approver"):
            supplied = args.get(field)
            if supplied not in (None, "") and not is_address(supplied):
                errors.append({"sequence": sequence, "error": f"{field}_invalid", "event": name})
        for field in ("domainHash", "previousRecordId", "pendingRecordId"):
            supplied = args.get(field)
            if supplied not in (None, "") and not is_hash(supplied):
                errors.append({"sequence": sequence, "error": f"{field}_invalid", "event": name})
    return {
        "chain_valid": not errors,
        "errors": errors,
        "event_count": len(events),
        "log_head_hash": canonical_json_hash(events) if events else "",
        "hash_alg": "sha-256",
    }


def ledger_proof(
    *,
    record_hashes: list[str],
    revocation_record_hashes: list[str],
    verification: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema": LEDGER_PROOF_SCHEMA,
        "record_hashes": record_hashes,
        "revocation_record_hashes": revocation_record_hashes,
        "records_hash": canonical_json_hash(record_hashes),
        "revocations_hash": canonical_json_hash(revocation_record_hashes),
        "log_head_hash": str(verification.get("log_head_hash") or ""),
        "event_count": int(verification.get("event_count") or 0),
        "hash_alg": "sha-256",
    }
    return {**payload, "payload_hash": canonical_json_hash(payload)}


def index_contract_events(
    events: list[dict[str, Any]],
    *,
    record_hash: Callable[[dict[str, Any]], str],
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or iso_now()
    verification = verify_contract_events(events, record_hash=record_hash)
    empty = {
        "schema": CONTRACT_INDEX_SCHEMA,
        "generated_at": generated_at,
        "source": "finalized_contract_events",
        "event_count": len(events),
        "log_head_hash": str(verification.get("log_head_hash") or ""),
        "verification": verification,
        "records": [],
        "revocations": [],
        "attestations": [],
        "attestation_quorums": [],
        "suspensions": [],
        "flags": [],
        "supersessions": [],
        "validators": [],
        "attestation_threshold": 1,
        "governance_actions": [],
        "writes_paused": False,
        "ownership": {"owner": "", "pending_owner": ""},
    }
    if not verification["chain_valid"]:
        return {
            **empty,
            "proof": ledger_proof(
                record_hashes=[], revocation_record_hashes=[], verification=verification
            ),
        }

    active: dict[str, dict[str, Any]] = {}
    active_hashes: dict[str, str] = {}
    revocations: dict[str, dict[str, Any]] = {}
    attestations: dict[str, dict[str, Any]] = {}
    suspensions: dict[str, dict[str, Any]] = {}
    flags: list[dict[str, Any]] = []
    supersessions: dict[str, dict[str, Any]] = {}
    validators: dict[str, dict[str, Any]] = {}
    governance_actions: dict[str, dict[str, Any]] = {}
    threshold = 1
    writes_paused = False
    owner = ""
    pending_owner = ""

    def clear_attestations(target_record_id: str) -> None:
        for key, value in list(attestations.items()):
            if value.get("record_id") == target_record_id:
                attestations.pop(key, None)

    def activate(event: dict[str, Any], target_record_id: str, target_hash: str) -> None:
        record = attached_record(event)
        if record is None:
            return
        if not isinstance(event.get("registry_record"), dict):
            record.setdefault("record_id", target_record_id)
            record.setdefault("record_hash", target_hash)
        active[target_record_id] = record
        active_hashes[target_record_id] = target_hash
        revocations.pop(target_hash, None)
        clear_attestations(target_record_id)
        suspensions.pop(target_record_id, None)

    for sequence, event in enumerate(events, start=1):
        name = str(event.get("event") or "")
        args = event_args(event)
        target_id = record_id(event)
        target_hash = event_record_hash(event)
        reference = event_ref(event, sequence)
        if name in {"MerchantRegistered", "MerchantUpdated"}:
            activate(event, target_id, target_hash)
        elif name == "ControllerChanged":
            activate(event, target_id, target_hash)
            if target_id in active and not isinstance(event.get("registry_record"), dict):
                active[target_id]["controller"] = arg(args, "newController", "new_controller")
        elif name == "MerchantRevoked":
            current = active.pop(target_id, None)
            final_hash = active_hashes.pop(target_id, "") or str((current or {}).get("record_hash") or "")
            if final_hash:
                revocations[final_hash] = {
                    "record_hash": final_hash,
                    "record_id": target_id,
                    "reason_hash": arg(args, "reasonHash", "reason_hash"),
                    **reference,
                }
            clear_attestations(target_id)
            suspensions.pop(target_id, None)
        elif name == "MerchantForceRevoked":
            for revocation in revocations.values():
                if revocation.get("record_id") == target_id:
                    revocation.update(
                        {
                            "forced": True,
                            "operator": arg(args, "operator"),
                            "force_event": reference,
                        }
                    )
        elif name == "SupersessionRequested":
            supersessions[target_id] = {
                "pending_record_id": target_id,
                "previous_record_id": normalized_hash(
                    arg(args, "previousRecordId", "previous_record_id"), prefix=True
                ),
                "domain_hash": normalized_hash(arg(args, "domainHash", "domain_hash"), prefix=True),
                "controller": arg(args, "controller"),
                "record_hash": target_hash,
                "reason_hash": arg(args, "reasonHash", "reason_hash"),
                "record_uri": arg(args, "recordURI", "record_uri"),
                "evidence_uri": arg(args, "evidenceURI", "evidence_uri"),
                "available_at": arg(args, "availableAt", "available_at"),
                "state": "requested",
                "request_event": reference,
            }
        elif name == "SupersessionApproved":
            pending = supersessions.setdefault(target_id, {"pending_record_id": target_id})
            pending.update(
                {
                    "state": "approved",
                    "approver": arg(args, "approver"),
                    "available_at": arg(args, "availableAt", "available_at"),
                    "approval_event": reference,
                }
            )
        elif name == "SupersessionCanceled":
            pending = supersessions.setdefault(target_id, {"pending_record_id": target_id})
            pending.update(
                {
                    "state": "canceled",
                    "operator": arg(args, "operator"),
                    "reason_hash": arg(args, "reasonHash", "reason_hash"),
                    "cancel_event": reference,
                }
            )
        elif name == "SupersessionActivated":
            previous_id = normalized_hash(
                arg(args, "previousRecordId", "previous_record_id"), prefix=True
            )
            previous = active.pop(previous_id, None)
            previous_hash = active_hashes.pop(previous_id, "") or str((previous or {}).get("record_hash") or "")
            if previous_hash and previous_hash not in revocations:
                revocations[previous_hash] = {
                    "record_hash": previous_hash,
                    "record_id": previous_id,
                    "reason_hash": str(supersessions.get(target_id, {}).get("reason_hash") or ""),
                    **reference,
                }
            clear_attestations(previous_id)
            suspensions.pop(previous_id, None)
            activate(event, target_id, target_hash)
            pending = supersessions.setdefault(target_id, {"pending_record_id": target_id})
            pending.update({"state": "activated", "activation_event": reference})
        elif name == "MerchantAttested":
            validator = arg(args, "validator").lower()
            if active_hashes.get(target_id) == target_hash:
                attestations[f"{target_id}:{validator}"] = {
                    "record_id": target_id,
                    "record_hash": target_hash,
                    "validator": arg(args, "validator"),
                    "result_hash": arg(args, "resultHash", "result_hash"),
                    "expires_at": arg(args, "expiresAt", "expires_at"),
                    "evidence_uri": arg(args, "evidenceURI", "evidence_uri"),
                    **reference,
                }
        elif name == "MerchantSuspended":
            suspensions[target_id] = {
                "record_id": target_id,
                "reason_hash": arg(args, "reasonHash", "reason_hash"),
                **reference,
            }
            clear_attestations(target_id)
        elif name == "MerchantUnsuspended":
            suspensions.pop(target_id, None)
        elif name == "MerchantFlagged":
            flags.append(
                {
                    "record_id": target_id,
                    "flagger": arg(args, "flagger"),
                    "challenge_type": arg(args, "challengeType", "challenge_type"),
                    "evidence_uri": arg(args, "evidenceURI", "evidence_uri"),
                    **reference,
                }
            )
        elif name == "ValidatorSet":
            validator = arg(args, "validator").lower()
            enabled = args.get("enabled") is True or str(args.get("enabled") or "").lower() == "true"
            validators[validator] = {
                "validator": arg(args, "validator"),
                "enabled": enabled,
                "enabled_sequence": sequence if enabled else 0,
                **reference,
            }
            if not enabled:
                for key in list(attestations):
                    if key.endswith(f":{validator}"):
                        attestations.pop(key, None)
        elif name == "AttestationThresholdSet":
            threshold = int(args.get("threshold") or 0)
        elif name == "GovernanceActionScheduled":
            action_hash = normalized_hash(arg(args, "actionHash", "action_hash"), prefix=True)
            governance_actions[action_hash] = {
                "action_hash": action_hash,
                "ready_at": arg(args, "readyAt", "ready_at"),
                "state": "scheduled",
                **reference,
            }
        elif name == "GovernanceActionCanceled":
            action_hash = normalized_hash(arg(args, "actionHash", "action_hash"), prefix=True)
            governance_actions[action_hash] = {
                "action_hash": action_hash,
                "state": "canceled",
                **reference,
            }
        elif name == "WritesPaused":
            writes_paused = args.get("paused") is True or str(args.get("paused") or "").lower() == "true"
        elif name == "OwnershipTransferStarted":
            pending_owner = arg(args, "newOwner", "new_owner")
        elif name == "OwnershipTransferred":
            owner = arg(args, "newOwner", "new_owner")
            pending_owner = ""

    now = parse_time(generated_at) or dt.datetime.now(dt.timezone.utc)
    current_attestations: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    expiries: dict[str, list[int]] = {}
    for item in attestations.values():
        validator_state = validators.get(str(item.get("validator") or "").lower())
        expires_raw = str(item.get("expires_at") or "")
        expires_at = int(expires_raw) if expires_raw.isdigit() else 0
        current = bool(
            validator_state
            and validator_state.get("enabled") is True
            and int(item.get("sequence") or 0) >= int(validator_state.get("enabled_sequence") or 0)
            and expires_at > int(now.timestamp())
            and item.get("record_id") in active
            and item.get("record_id") not in suspensions
        )
        item["current"] = current
        current_attestations.append(item)
        if current:
            target_id = str(item.get("record_id") or "")
            counts[target_id] = counts.get(target_id, 0) + 1
            expiries.setdefault(target_id, []).append(expires_at)

    active_entries = [
        (target_id, record)
        for target_id, record in active.items()
        if target_id not in suspensions
    ]
    active_entries.sort(
        key=lambda item: (
            str(item[1].get("domain") or ""),
            str(item[1].get("merchant_id") or ""),
            active_hashes.get(item[0], ""),
        )
    )
    records = [record for _, record in active_entries]
    quorum_list = []
    for target_id, _record in active_entries:
        valid_expiries = sorted(expiries.get(target_id, []))
        count = counts.get(target_id, 0)
        quorum_expiry = valid_expiries[-threshold] if threshold > 0 and count >= threshold else 0
        quorum_list.append(
            {
                "record_id": target_id,
                "threshold": threshold,
                "current_attestation_count": count,
                "current": threshold > 0 and count >= threshold,
                "expires_at": str(quorum_expiry) if quorum_expiry else "",
            }
        )

    revocation_list = sorted(revocations.values(), key=lambda item: str(item.get("record_hash") or ""))
    record_hashes = [active_hashes.get(target_id, "") for target_id, _ in active_entries]
    revoked_hashes = [str(item.get("record_hash") or "") for item in revocation_list]
    return {
        **empty,
        "records": records,
        "revocations": revocation_list,
        "attestations": sorted(
            current_attestations,
            key=lambda item: (str(item.get("record_id") or ""), str(item.get("validator") or "")),
        ),
        "attestation_quorums": quorum_list,
        "suspensions": sorted(suspensions.values(), key=lambda item: str(item.get("record_id") or "")),
        "flags": flags,
        "supersessions": sorted(supersessions.values(), key=lambda item: str(item.get("pending_record_id") or "")),
        "validators": sorted(validators.values(), key=lambda item: str(item.get("validator") or "")),
        "attestation_threshold": threshold,
        "governance_actions": sorted(
            governance_actions.values(), key=lambda item: str(item.get("action_hash") or "")
        ),
        "writes_paused": writes_paused,
        "ownership": {"owner": owner, "pending_owner": pending_owner},
        "proof": ledger_proof(
            record_hashes=record_hashes,
            revocation_record_hashes=revoked_hashes,
            verification=verification,
        ),
    }


def index_contract_document(
    document: Any,
    *,
    record_hash: Callable[[dict[str, Any]], str],
    require_finality: bool = False,
    expected_chain_id: str = "",
    expected_registry_address: str = "",
    max_age_seconds: int = 0,
    now: dt.datetime | None = None,
    expected_implementation: str = RPC_INDEXER_IMPLEMENTATION,
) -> dict[str, Any]:
    """Validate an event envelope and replay it through the shared projection.

    Remote discovery sources must set ``require_finality``. Local fixture and
    operator workflows may still replay the legacy schema-only event envelope.
    """

    events, envelope_errors = finalized_document_errors(
        document,
        require_finality=require_finality,
        expected_chain_id=expected_chain_id,
        expected_registry_address=expected_registry_address,
        max_age_seconds=max_age_seconds,
        now=now,
        expected_implementation=expected_implementation,
    )
    generated_at = str(document.get("indexed_at") or "") if isinstance(document, dict) else ""
    index = index_contract_events(events, record_hash=record_hash, generated_at=generated_at or None)
    if require_finality and isinstance(document, dict):
        envelope_errors.extend(
            controller_binding_errors(
                events,
                chain_id=str(document.get("chain_id") or ""),
                registry_address=str(document.get("registry_address") or ""),
            )
        )
    if not envelope_errors:
        if isinstance(document, dict):
            index["chain_id"] = str(document.get("chain_id") or "")
            index["registry_address"] = str(document.get("registry_address") or "")
            if isinstance(document.get("finality"), dict):
                index["finality"] = copy.deepcopy(document["finality"])
            if isinstance(document.get("independent_verification"), dict):
                index["independent_verification"] = copy.deepcopy(
                    document["independent_verification"]
                )
            index["complete"] = document.get("complete") is True if require_finality else True
            if expected_implementation == DIRECT_RPC_IMPLEMENTATION:
                record_errors = copy.deepcopy(document.get("record_errors") or [])
                failed_ids = {
                    normalized_hash(item.get("record_id"), prefix=True)
                    for item in record_errors
                    if isinstance(item, dict)
                }
                selection = copy.deepcopy(document.get("record_selection") or {})
                selected_ids = {
                    normalized_hash(value, prefix=True)
                    for value in selection.get("selected_record_ids", [])
                }

                def projected_record_id(record: dict[str, Any]) -> str:
                    identity = record_identity(record) or {}
                    return normalized_hash(
                        identity_value(identity, "record_id", "id")
                        or record.get("record_id"),
                        prefix=True,
                    )

                index["records"] = [
                    record
                    for record in index["records"]
                    if isinstance(record, dict)
                    and projected_record_id(record) in selected_ids
                    and projected_record_id(record) not in failed_ids
                ]
                index["record_errors"] = record_errors
                index["record_selection"] = selection
        return index

    verification = index.get("verification") if isinstance(index.get("verification"), dict) else {}
    verification = {
        **verification,
        "chain_valid": False,
        "errors": [
            *(verification.get("errors") if isinstance(verification.get("errors"), list) else []),
            *envelope_errors,
        ],
    }
    index["verification"] = verification
    for key in (
        "records",
        "revocations",
        "attestations",
        "attestation_quorums",
        "suspensions",
        "flags",
        "supersessions",
        "validators",
        "governance_actions",
    ):
        index[key] = []
    index["proof"] = ledger_proof(
        record_hashes=[], revocation_record_hashes=[], verification=verification
    )
    index["complete"] = False
    return index


def record_anchor(record: dict[str, Any]) -> tuple[str, str, str]:
    identity = record_identity(record) or {}
    return (
        identity_value(identity, "chain_id", "chain", "chainId"),
        identity_value(
            identity,
            "registry_address",
            "registry",
            "registry_contract",
            "contract",
        ).lower(),
        normalized_hash(
            identity_value(identity, "record_id", "id"),
            prefix=True,
        ),
    )


def overlay_records(
    hosted_records: list[dict[str, Any]],
    index: dict[str, Any],
    *,
    record_hash: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    """Apply projected lifecycle state to hosted records deterministically.

    Records anchored to this chain/contract fail closed unless their exact id
    and hash are active. Hash revocations and record suspensions also remove a
    hosted copy. Active onchain records replace a hosted record with the same
    merchant/domain identity; unrelated curated records remain available.
    """

    chain_id = str(index.get("chain_id") or "")
    registry_address = str(index.get("registry_address") or "").lower()
    active_records = [record for record in index.get("records", []) if isinstance(record, dict)]
    active_record_versions = {
        (anchor[2], supplied_hash)
        for record in active_records
        if (anchor := record_anchor(record))[2]
        if (supplied_hash := normalized_hash(record_hash(record)))
    }
    revoked_hashes = {
        supplied_hash
        for entry in index.get("revocations", [])
        if isinstance(entry, dict)
        if (supplied_hash := normalized_hash(entry.get("record_hash")))
    }
    suspended_ids = {
        target_id
        for entry in index.get("suspensions", [])
        if isinstance(entry, dict)
        if (target_id := normalized_hash(entry.get("record_id"), prefix=True))
    }
    active_keys = {
        (str(record.get("merchant_id") or ""), str(record.get("domain") or "").lower())
        for record in active_records
    }

    result: list[dict[str, Any]] = []
    for record in hosted_records:
        supplied_hash = normalized_hash(record_hash(record))
        record_chain, record_registry, target_id = record_anchor(record)
        key = (str(record.get("merchant_id") or ""), str(record.get("domain") or "").lower())
        if supplied_hash in revoked_hashes or target_id in suspended_ids:
            continue
        if chain_id and registry_address and record_chain == chain_id and record_registry == registry_address:
            if (target_id, supplied_hash) not in active_record_versions:
                continue
        if key in active_keys:
            continue
        result.append(record)
    result.extend(active_records)
    return result
