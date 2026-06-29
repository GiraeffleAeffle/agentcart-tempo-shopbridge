#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import re
import sys
from copy import deepcopy
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "docs" / "fixtures" / "verifier"
PLUGIN = ROOT / "woocommerce-shopbridge" / "agentcart-shopbridge" / "agentcart-shopbridge.php"
VERIFIER_CLIENT = PLUGIN.parent / "includes" / "trait-agentcart-shopbridge-verifier-client.php"
STRIPE_VERIFIER = ROOT / "gateway" / "scripts" / "stripe-mpp-verifier.mjs"
SQLITE_REPLAY_STORE = ROOT / "gateway" / "scripts" / "verifier-sqlite-replay-store.mjs"
SQLITE_REPLAY_SMOKE = ROOT / "gateway" / "scripts" / "verifier-sqlite-replay-smoke.sh"


def load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURE_DIR / name
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{path} must contain a JSON object")
    return data


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def path_value(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        require(isinstance(current, dict), f"{dotted} parent is not an object")
        require(part in current, f"{dotted} is missing")
        current = current[part]
    return current


def set_path_value(data: dict[str, Any], dotted: str, value: Any) -> None:
    current: Any = data
    parts = dotted.split(".")
    for part in parts[:-1]:
        require(isinstance(current, dict), f"{dotted} parent is not an object")
        require(part in current, f"{dotted} parent is missing")
        current = current[part]
    require(isinstance(current, dict), f"{dotted} parent is not an object")
    current[parts[-1]] = value


def require_non_empty_string(data: dict[str, Any], dotted: str) -> str:
    value = path_value(data, dotted)
    require(isinstance(value, str) and value.strip() != "", f"{dotted} must be a non-empty string")
    return value


def require_positive_int(data: dict[str, Any], dotted: str) -> int:
    value = path_value(data, dotted)
    require(isinstance(value, int) and value > 0, f"{dotted} must be a positive integer")
    return value


def require_rail(data: dict[str, Any], dotted: str) -> str:
    rail = require_non_empty_string(data, dotted)
    require(rail == "stripe-card-mpp", f"{dotted} must be stripe-card-mpp")
    return rail


def require_quote_hash(value: str, label: str) -> None:
    require(bool(re.fullmatch(r"[0-9a-f]{64}", value)), f"{label} must be a lowercase SHA-256 hex string")


def stripe_protocol(quote: dict[str, Any]) -> dict[str, Any]:
    payment = quote.get("payment_requirements")
    require(isinstance(payment, dict), "quote.payment_requirements must be an object")
    verification = payment.get("verification")
    require(isinstance(verification, dict), "quote.payment_requirements.verification must be an object")
    require(
        verification.get("external_verifier_configured") is True,
        "quote must advertise external verifier mode",
    )
    protocols = payment.get("protocols")
    require(isinstance(protocols, list), "quote.payment_requirements.protocols must be an array")
    for protocol in protocols:
        if isinstance(protocol, dict) and protocol.get("id") == "stripe-card-mpp":
            return protocol
    raise AssertionError("quote.payment_requirements.protocols must include stripe-card-mpp")


def verify_payment_request(payload: dict[str, Any]) -> None:
    require(path_value(payload, "operation") == "payment", "payment request operation must be payment")
    quote = path_value(payload, "quote")
    receipt = path_value(payload, "payment_receipt")
    expected = path_value(payload, "expected")
    require(isinstance(quote, dict), "payment request quote must be an object")
    require(isinstance(receipt, dict), "payment request payment_receipt must be an object")
    require(isinstance(expected, dict), "payment request expected must be an object")
    quote_hash = require_non_empty_string(payload, "quote_hash")
    require_quote_hash(quote_hash, "payment request quote_hash")
    payment_contract_hash = require_non_empty_string(payload, "payment_contract_hash")
    require_quote_hash(payment_contract_hash, "payment request payment_contract_hash")
    require(quote.get("quote_hash") == quote_hash, "payment request quote.quote_hash must match quote_hash")
    require(receipt.get("quote_hash") == quote_hash, "payment receipt quote_hash must match quote_hash")
    require(
        receipt.get("payment_contract_hash") == payment_contract_hash,
        "payment receipt payment_contract_hash must match request payment_contract_hash",
    )
    amount = require_positive_int(payload, "expected.amount_cents")
    require(quote.get("total_cents") == amount, "payment request expected amount must match quote total")
    require(receipt.get("amount_cents") == amount, "payment receipt amount must match quote total")
    currency = require_non_empty_string(payload, "expected.currency").upper()
    require(quote.get("currency") == currency, "payment request expected currency must match quote currency")
    require(receipt.get("currency") == currency, "payment receipt currency must match quote currency")
    require_rail(payload, "expected.rail")
    require(
        path_value(payload, "expected.payment_contract_hash") == payment_contract_hash,
        "payment expected payment_contract_hash must match request payment_contract_hash",
    )
    require_rail(payload, "payment_receipt.method")
    profile = require_non_empty_string(payload, "expected.stripe_profile_id")
    require(receipt.get("stripe_profile_id") == profile, "payment receipt Stripe profile must match expected profile")
    protocol = stripe_protocol(quote)
    require(
        path_value(payload, "quote.payment_requirements.payment_contract_hash") == payment_contract_hash,
        "quote payment requirements payment_contract_hash must match request payment_contract_hash",
    )
    require(
        path_value(payload, "quote.payment_requirements.verification.payment_contract_hash") == payment_contract_hash,
        "quote verification payment_contract_hash must match request payment_contract_hash",
    )
    require(protocol.get("stripe_profile_id") == profile, "quote Stripe profile must match expected profile")
    require(protocol.get("network_id") == profile, "quote Stripe network id must match expected profile")
    require_non_empty_string(payload, "agentcart_order_id")
    require_non_empty_string(payload, "expected.merchant_id")


def verify_payment_success(payload: dict[str, Any], request: dict[str, Any]) -> None:
    require(payload.get("ok") is True, "payment success ok must be true")
    require_rail(payload, "rail")
    require(payload.get("amount_cents") == path_value(request, "expected.amount_cents"), "payment amount mismatch")
    require(payload.get("currency") == path_value(request, "expected.currency"), "payment currency mismatch")
    require(payload.get("quote_hash") == path_value(request, "quote_hash"), "payment quote_hash mismatch")
    require(
        payload.get("payment_contract_hash") == path_value(request, "payment_contract_hash"),
        "payment contract hash mismatch",
    )
    require(payload.get("stripe_profile_id") == path_value(request, "expected.stripe_profile_id"), "payment profile mismatch")
    reference = require_non_empty_string(payload, "transaction_reference")
    require(payload.get("replay_reference") == reference, "payment replay_reference must match transaction_reference")
    require_quote_hash(require_non_empty_string(payload, "replay_request_hash"), "payment replay_request_hash")
    require(payload.get("real_settlement_verified") is True, "payment success must represent real settlement verification")


def verify_refund_request(payload: dict[str, Any], payment_request: dict[str, Any], payment_success: dict[str, Any]) -> None:
    require(path_value(payload, "operation") == "refund", "refund request operation must be refund")
    merchant_id = path_value(payload, "merchant.id")
    require(merchant_id == path_value(payment_request, "expected.merchant_id"), "refund merchant id mismatch")
    amount = require_positive_int(payload, "expected.amount_cents")
    require(path_value(payload, "refund.amount_cents") == amount, "refund amount must match expected amount")
    currency = require_non_empty_string(payload, "expected.currency").upper()
    require(path_value(payload, "refund.currency") == currency, "refund currency must match expected currency")
    quote_hash = require_non_empty_string(payload, "expected.quote_hash")
    require_quote_hash(quote_hash, "refund request expected.quote_hash")
    require(path_value(payload, "order.quote_hash") == quote_hash, "refund order quote_hash mismatch")
    require(path_value(payment_request, "quote_hash") == quote_hash, "refund quote_hash must match payment quote_hash")
    reference = require_non_empty_string(payload, "expected.original_transaction_reference")
    require(reference == payment_success.get("transaction_reference"), "refund original reference must match payment reference")
    require(path_value(payload, "order.transaction_reference") == reference, "refund order transaction reference mismatch")
    require(path_value(payload, "order.payment_verification.transaction_reference") == reference, "refund payment verification reference mismatch")
    require_rail(payload, "refund.rail")
    require_non_empty_string(payload, "refund.requested_reference")
    require(path_value(payload, "expected.stripe_profile_id") == path_value(payment_request, "expected.stripe_profile_id"), "refund profile mismatch")


def verify_refund_success(payload: dict[str, Any], request: dict[str, Any]) -> None:
    require(payload.get("ok") is True, "refund success ok must be true")
    require_rail(payload, "rail")
    require(payload.get("amount_cents") == path_value(request, "expected.amount_cents"), "refund amount mismatch")
    require(payload.get("currency") == path_value(request, "expected.currency"), "refund currency mismatch")
    require(payload.get("quote_hash") == path_value(request, "expected.quote_hash"), "refund quote_hash mismatch")
    require(
        payload.get("original_transaction_reference") == path_value(request, "expected.original_transaction_reference"),
        "refund original transaction reference mismatch",
    )
    reference = require_non_empty_string(payload, "refund_reference")
    require(payload.get("replay_reference") == reference, "refund replay_reference must match refund_reference")
    require_quote_hash(require_non_empty_string(payload, "replay_request_hash"), "refund replay_request_hash")
    require(payload.get("real_refund_verified") is True, "refund success must represent real refund verification")


def mutated_negative_payload(case: dict[str, Any]) -> dict[str, Any]:
    base_name = require_non_empty_string(case, "base_fixture")
    payload = deepcopy(load_fixture(base_name))
    mutation = case.get("mutation")
    if isinstance(mutation, dict):
        set_path_value(payload, require_non_empty_string(mutation, "path"), mutation.get("value"))
    return payload


def verify_negative_fixture(path: pathlib.Path) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(case, dict), f"{path} must contain a JSON object")
    require(case.get("should_reject") is True, f"{path.name} must set should_reject=true")
    case_name = require_non_empty_string(case, "case")
    expected_rejection = case.get("expected_rejection")
    require(isinstance(expected_rejection, dict), f"{case_name} expected_rejection must be an object")
    require_positive_int(case, "expected_rejection.status")
    require_non_empty_string(case, "expected_rejection.reason")
    payload = mutated_negative_payload(case)

    if case_name == "payment_amount_mismatch":
        require(
            path_value(payload, "payment_receipt.amount_cents") != path_value(payload, "expected.amount_cents"),
            f"{case_name} must mutate payment_receipt.amount_cents away from expected.amount_cents",
        )
    elif case_name == "payment_quote_hash_mismatch":
        require_quote_hash(path_value(payload, "payment_receipt.quote_hash"), f"{case_name} mutated quote hash")
        require(
            path_value(payload, "payment_receipt.quote_hash") != path_value(payload, "quote_hash"),
            f"{case_name} must mutate payment_receipt.quote_hash away from quote_hash",
        )
    elif case_name == "payment_stripe_profile_mismatch":
        require(
            path_value(payload, "payment_receipt.stripe_profile_id")
            != path_value(payload, "expected.stripe_profile_id"),
            f"{case_name} must mutate payment_receipt.stripe_profile_id away from expected.stripe_profile_id",
        )
    elif case_name == "payment_contract_hash_mismatch":
        require_quote_hash(path_value(payload, "payment_receipt.payment_contract_hash"), f"{case_name} mutated payment contract hash")
        require(
            path_value(payload, "payment_receipt.payment_contract_hash") != path_value(payload, "payment_contract_hash"),
            f"{case_name} must mutate payment_receipt.payment_contract_hash away from payment_contract_hash",
        )
    elif case_name == "payment_replay_reference":
        require(case.get("replay_bucket") == "payments", f"{case_name} must replay the payments bucket")
        require_non_empty_string(payload, str(case.get("reference_path") or "transaction_reference"))
    elif case_name == "payment_replay_conflict":
        require(case.get("replay_bucket") == "payments", f"{case_name} must replay the payments bucket")
        require_non_empty_string(payload, str(case.get("reference_path") or "transaction_reference"))
        require(
            path_value(payload, "amount_cents") != path_value(load_fixture("payment-success.stripe-card-mpp.json"), "amount_cents"),
            f"{case_name} must mutate payment amount away from the original replay metadata",
        )
    elif case_name == "refund_original_reference_mismatch":
        require(
            path_value(payload, "expected.original_transaction_reference")
            != path_value(payload, "order.transaction_reference"),
            f"{case_name} must mutate expected.original_transaction_reference away from the order reference",
        )
    elif case_name == "refund_requested_reference_missing":
        require(
            str(path_value(payload, "refund.requested_reference")) == "",
            f"{case_name} must remove refund.requested_reference",
        )
    elif case_name == "refund_replay_reference":
        require(case.get("replay_bucket") == "refunds", f"{case_name} must replay the refunds bucket")
        require_non_empty_string(payload, str(case.get("reference_path") or "refund_reference"))
    else:
        raise AssertionError(f"unknown negative fixture case: {case_name}")


def verify_negative_fixtures() -> None:
    paths = sorted((FIXTURE_DIR / "negative").glob("*.json"))
    require(paths, "negative verifier fixtures are missing")
    seen = set()
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        case_name = str(data.get("case") or "")
        require(case_name not in seen, f"duplicate negative fixture case: {case_name}")
        seen.add(case_name)
        verify_negative_fixture(path)
    required_cases = {
        "payment_amount_mismatch",
        "payment_quote_hash_mismatch",
        "payment_contract_hash_mismatch",
        "payment_stripe_profile_mismatch",
        "payment_replay_reference",
        "payment_replay_conflict",
        "refund_original_reference_mismatch",
        "refund_requested_reference_missing",
        "refund_replay_reference",
    }
    missing = sorted(required_cases - seen)
    require(not missing, f"missing negative verifier fixture cases: {', '.join(missing)}")


def function_body(source: str, name: str) -> str:
    match = re.search(rf"private static function {re.escape(name)}\([^)]*\) \{{", source)
    if not match:
        raise AssertionError(f"function not found: {name}")
    start = match.end()
    depth = 1
    index = start
    while index < len(source) and depth:
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    require(depth == 0, f"function body not closed: {name}")
    return source[start : index - 1]


def plugin_contract_source() -> str:
    return PLUGIN.read_text(encoding="utf-8") + "\n" + VERIFIER_CLIENT.read_text(encoding="utf-8")


def verify_plugin_contract_fields() -> None:
    source = plugin_contract_source()
    payment_body = function_body(source, "call_payment_verifier")
    refund_body = function_body(source, "call_refund_verifier")
    for literal in [
        "'operation' => 'payment'",
        "'quote' => $quote",
        "'quote_hash' =>",
        "'payment_receipt' => $receipt",
        "'agentcart_order_id' =>",
        "'expected' =>",
        "'amount_cents' =>",
        "'currency' =>",
        "'merchant_id' => self::merchant()['id']",
        "'rail' => $rail",
        "'tempo_network' => self::tempo_network()",
        "'tempo_recipient' => self::tempo_recipient()",
        "'stripe_profile_id' => self::stripe_profile_id()",
        "self::verifier_http_post($verifier_url, $payload, $headers, 15)",
        "self::verifier_error_detail($status, $decoded, $raw_body)",
        "agentcart_payment_contract_required",
    ]:
        require(literal in payment_body, f"call_payment_verifier missing {literal}")
    for literal in [
        "'operation' => 'refund'",
        "'merchant' => self::merchant()",
        "'order' =>",
        "'refund' =>",
        "'expected' =>",
        "'agentcart_order_id' =>",
        "'quote_hash' => $quote_hash",
        "'transaction_reference' => $transaction_reference",
        "'payment_verification' =>",
        "'amount_cents' => intval($amount_cents)",
        "'currency' => $currency",
        "'rail' => $rail",
        "'requested_reference' =>",
        "'original_transaction_reference' => $transaction_reference",
        "'tempo_network' => self::tempo_network()",
        "'tempo_recipient' => self::tempo_recipient()",
        "'stripe_profile_id' => self::stripe_profile_id()",
        "self::verifier_http_post($verifier_url, $payload, $headers, 20)",
        "self::verifier_error_detail($status, $decoded, $raw_body)",
    ]:
        require(literal in refund_body, f"call_refund_verifier missing {literal}")
    for literal in [
        "sanitize_payment_verifier_url_setting",
        "normalize_payment_verifier_url",
        "'redirection' => 0",
        "'limit_response_size' => 1048576",
        "verifier_error_detail",
        "raw_body_hash",
        "raw_body_bytes",
    ]:
        require(literal in source, f"plugin verifier HTTP hardening missing {literal}")


def verify_stripe_verifier_replay_fields() -> None:
    source = STRIPE_VERIFIER.read_text(encoding="utf-8")
    for literal in [
        "AGENTCART_VERIFIER_REPLAY_STORE_PATH",
        "AGENTCART_VERIFIER_REPLAY_STORE_DRIVER",
        "STRIPE_MPP_REPLAY_STORE_PATH",
        "AGENTCART_VERIFIER_REPLAY_LOCK_TIMEOUT_MS",
        "AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY",
        "AGENTCART_VERIFIER_REPLAY_JOURNAL_PATH",
        "STRIPE_MPP_REPLAY_JOURNAL_PATH",
        "AGENTCART_VERIFIER_REQUIRE_REPLAY_JOURNAL",
        "requireDurableReplayStore",
        "requireReplayJournal",
        "replay_store_required",
        "replay_store_driver",
        "replay_store_durable",
        "replay_store_error",
        "replay_journal_required",
        "replay_journal_writable",
        "replay_journal_error",
        "agentcart.verifierReplay.v1",
        "agentcart.verifierReplayJournal.v1",
        "const status = readiness()",
        "acquireReplayStoreLock",
        "withReplayStoreMutation",
        "replayStoreDiagnostics",
        "replayJournalDiagnostics",
        "appendReplayJournalEvent",
        "recordReplayJournalClaim",
        "original_transaction_reference_hash",
        "requested_reference_hash",
        "refund_reference_hash",
        "replay_store_locking",
        "replay_store_writable",
        "replay_store_counts",
        "replayStoreLockPath",
        "replayStoreWriteProbe",
        "claimSQLiteReplayReference",
        "sqliteReplayStoreDiagnostics",
        "sqliteReplayStoreWriteProbe",
        "replayStoreDriver === \"sqlite\"",
        "replayRequestHash",
        "replayComparableMetadata",
        "idempotent_replay",
        "replay_conflict",
        "request_hash",
        "claimReplayReference(\"payments\"",
        "claimReplayReference(\"refund_requests\"",
        "claimReplayReference(\"refunds\"",
        "refund.requested_reference is required",
        "idempotencyKey: requestedReference",
        "authoritativeContractHashes",
        "payment_contract_hash is required from the request, expected block, or quote.",
        "payment_contract_hash must be a SHA-256 hex digest.",
        "payment_receipt.payment_contract_hash is required.",
        "providerErrorClass",
        "providerErrorResponse",
        "provider_error_class",
        "provider_status",
        "request_id",
        "retryable",
        "agentcart.verifierMetrics.v1",
        "agentcart.verifierEvent.v1",
        "verifierMetricsSnapshot",
        "recordVerifierResponse",
        "structuredLog",
        "x-agentcart-correlation-id",
        "AGENTCART_VERIFIER_ALERT_WEBHOOK_URL",
        "AGENTCART_VERIFIER_ALERT_WEBHOOK_TOKEN",
        "AGENTCART_VERIFIER_ALERT_MIN_SEVERITY",
        "AGENTCART_VERIFIER_ALERT_THROTTLE_SECONDS",
        "agentcart.verifier_alert_notification.v1",
        "agentcart.verifier_alert_delivery.v1",
        "deliverVerifierAlert",
        "verifierAlertForEvent",
        "verifierAlertFingerprint",
        "x-agentcart-event",
        "verifier.alert",
        "provider_errors",
        "success_rate",
        "latency_ms",
        "real_settlement_verified",
        "real_refund_verified",
        "url.pathname === \"/metrics\"",
        "unauthorized || jsonResponse(verifierMetricsSnapshot())",
    ]:
        require(literal in source, f"stripe verifier missing replay guard: {literal}")
    require(
        source.count("await claimReplayReference(") >= 4,
        "stripe verifier replay claims must be awaited so file locking is effective",
    )
    sqlite_source = SQLITE_REPLAY_STORE.read_text(encoding="utf-8")
    for literal in [
        "agentcart.verifierReplay.sqlite.v1",
        "BEGIN IMMEDIATE",
        "PRIMARY KEY (bucket, reference_hash)",
        "payments",
        "refund_requests",
        "refunds",
        "sqlite-immediate-transaction",
        "claimSQLiteReplayReference",
        "sqliteReplayStoreDiagnostics",
        "replayReferenceHash",
        "replayRequestHash",
    ]:
        require(literal in sqlite_source, f"sqlite replay store missing contract literal: {literal}")
    smoke_source = SQLITE_REPLAY_SMOKE.read_text(encoding="utf-8")
    for literal in [
        "verifier-sqlite-replay-store.mjs",
        "Promise.all",
        "payments",
        "refund_requests",
        "refunds",
        "sqlite-immediate-transaction",
    ]:
        require(literal in smoke_source, f"sqlite replay smoke missing contract literal: {literal}")


def main() -> int:
    try:
        payment_request = load_fixture("payment-request.stripe-card-mpp.json")
        payment_success = load_fixture("payment-success.stripe-card-mpp.json")
        refund_request = load_fixture("refund-request.stripe-card-mpp.json")
        refund_success = load_fixture("refund-success.stripe-card-mpp.json")
        verify_payment_request(payment_request)
        verify_payment_success(payment_success, payment_request)
        verify_refund_request(refund_request, payment_request, payment_success)
        verify_refund_success(refund_success, refund_request)
        verify_negative_fixtures()
        verify_plugin_contract_fields()
        verify_stripe_verifier_replay_fields()
    except (AssertionError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "fixtures": str(FIXTURE_DIR)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
