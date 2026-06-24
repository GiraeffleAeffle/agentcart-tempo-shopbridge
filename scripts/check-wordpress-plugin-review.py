#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "woocommerce-shopbridge" / "agentcart-shopbridge" / "agentcart-shopbridge.php"


def fail(message: str) -> None:
    raise AssertionError(message)


def function_body(source: str, name: str) -> str:
    match = re.search(rf"(?:private|public) static function {re.escape(name)}\([^)]*\) \{{", source)
    if not match:
        fail(f"function not found: {name}")
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
    if depth:
        fail(f"function body not closed: {name}")
    return source[start : index - 1]


def check_superglobal_unslash(source: str) -> None:
    for line_no, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if "$_POST[" in stripped:
            if "isset($_POST[" in stripped or "empty($_POST[" in stripped:
                continue
            if "wp_unslash($_POST[" not in stripped:
                fail(f"line {line_no}: sanitize or cast $_POST values after wp_unslash()")
        if "$_SERVER[" in stripped and "wp_unslash($_SERVER[" not in stripped:
            fail(f"line {line_no}: read $_SERVER values through wp_unslash() before use")


def check_custom_admin_actions(source: str) -> None:
    setup_body = function_body(source, "maybe_handle_setup_action")
    product_body = function_body(source, "maybe_handle_product_exposure_action")
    credential_body = function_body(source, "maybe_handle_credential_action")
    registry_body = function_body(source, "maybe_handle_registry_action")
    for action, body in [
        ("agentcart_shopbridge_setup_action", setup_body),
        ("agentcart_shopbridge_product_action", product_body),
        ("agentcart_shopbridge_credential_action", credential_body),
        ("agentcart_shopbridge_registry_action", registry_body),
    ]:
        if f"check_admin_referer('{action}')" not in body:
            fail(f"custom admin action missing nonce check: {action}")
        if f"wp_nonce_field('{action}')" not in source:
            fail(f"custom admin action missing nonce field: {action}")


def check_external_http_verifier_calls(source: str) -> None:
    payment_body = function_body(source, "call_payment_verifier")
    refund_body = function_body(source, "call_refund_verifier")
    if source.count("wp_remote_post(") != 2:
        fail("external HTTP calls should be limited to the payment/refund verifier wrappers")
    for name, body in [("payment verifier", payment_body), ("refund verifier", refund_body)]:
        for literal in [
            "wp_remote_post($verifier_url",
            "'Content-Type' => 'application/json'",
            "$headers['Authorization'] = 'Bearer ' . $token",
            "wp_json_encode($payload)",
            "'timeout' =>",
            "is_wp_error($response)",
            "wp_remote_retrieve_response_code($response)",
            "wp_remote_retrieve_body($response)",
            "json_decode($raw_body, true)",
        ]:
            if literal not in body:
                fail(f"{name} HTTP call missing review guard: {literal}")
    if re.search(r"\b(curl_exec|file_get_contents)\s*\(", source):
        fail("use WordPress HTTP APIs instead of curl_exec/file_get_contents")


def check_admin_badge_escaping(source: str) -> None:
    body = function_body(source, "admin_status_badge")
    for literal in ["esc_attr($background)", "esc_attr($color)", "esc_html($label)"]:
        if literal not in body:
            fail(f"admin_status_badge must escape generated HTML: {literal}")


def main() -> int:
    try:
        source = PLUGIN.read_text(encoding="utf-8")
        check_superglobal_unslash(source)
        check_custom_admin_actions(source)
        check_external_http_verifier_calls(source)
        check_admin_badge_escaping(source)
    except (AssertionError, OSError) as exc:
        print(f"wordpress plugin review check failed: {exc}", file=sys.stderr)
        return 1
    print(f"wordpress plugin review check ok: {PLUGIN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
