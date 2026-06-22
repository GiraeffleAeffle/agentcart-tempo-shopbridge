#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "docs" / "fixtures" / "verifier"
PLUGIN = ROOT / "woocommerce-shopbridge" / "agentcart-shopbridge" / "agentcart-shopbridge.php"


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
    require(quote.get("quote_hash") == quote_hash, "payment request quote.quote_hash must match quote_hash")
    require(receipt.get("quote_hash") == quote_hash, "payment receipt quote_hash must match quote_hash")
    amount = require_positive_int(payload, "expected.amount_cents")
    require(quote.get("total_cents") == amount, "payment request expected amount must match quote total")
    require(receipt.get("amount_cents") == amount, "payment receipt amount must match quote total")
    currency = require_non_empty_string(payload, "expected.currency").upper()
    require(quote.get("currency") == currency, "payment request expected currency must match quote currency")
    require(receipt.get("currency") == currency, "payment receipt currency must match quote currency")
    require_rail(payload, "expected.rail")
    require_rail(payload, "payment_receipt.method")
    profile = require_non_empty_string(payload, "expected.stripe_profile_id")
    require(receipt.get("stripe_profile_id") == profile, "payment receipt Stripe profile must match expected profile")
    protocol = stripe_protocol(quote)
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
    require(payload.get("stripe_profile_id") == path_value(request, "expected.stripe_profile_id"), "payment profile mismatch")
    require_non_empty_string(payload, "transaction_reference")
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
    require_non_empty_string(payload, "refund_reference")
    require(payload.get("real_refund_verified") is True, "refund success must represent real refund verification")


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


def verify_plugin_contract_fields() -> None:
    source = PLUGIN.read_text(encoding="utf-8")
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
    ]:
        require(literal in refund_body, f"call_refund_verifier missing {literal}")


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
        verify_plugin_contract_fields()
    except (AssertionError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "fixtures": str(FIXTURE_DIR)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
