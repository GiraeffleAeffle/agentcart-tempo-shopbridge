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
    verifier_http_body = function_body(source, "verifier_http_post")
    registry_body = function_body(source, "call_registry_connection")
    public_fetch_body = function_body(source, "fetch_public_json")
    registry_health_body = function_body(source, "fetch_registry_connection_json")
    if source.count("wp_remote_post(") != 2:
        fail("external HTTP calls should be limited to the payment/refund verifier and registry connection wrappers")
    if source.count("wp_remote_get(") != 2:
        fail("external HTTP GET calls should be limited to public endpoint checks and registry health checks")
    for name, body in [("payment verifier", payment_body), ("refund verifier", refund_body)]:
        for literal in [
            "'Content-Type' => 'application/json'",
            "$headers['Authorization'] = 'Bearer ' . $token",
            "self::verifier_http_post($verifier_url, $payload, $headers,",
            "is_wp_error($response)",
            "wp_remote_retrieve_response_code($response)",
            "wp_remote_retrieve_body($response)",
            "json_decode($raw_body, true)",
        ]:
            if literal not in body:
                fail(f"{name} HTTP call missing review guard: {literal}")
    for literal in [
        "self::normalize_payment_verifier_url($verifier_url)",
        "wp_remote_post($url",
        "'headers' => $headers",
        "'body' => wp_json_encode($payload)",
        "'timeout' => intval($timeout)",
        "'redirection' => 0",
        "'limit_response_size' => 1048576",
    ]:
        if literal not in verifier_http_body:
            fail(f"verifier HTTP wrapper missing review guard: {literal}")
    for literal in [
        "wp_remote_post($registry_url",
        "'Content-Type' => 'application/json'",
        "'Accept' => 'application/json'",
        "$headers['Authorization'] = 'Bearer ' . $token",
        "wp_json_encode($payload",
        "'timeout' =>",
        "'redirection' => 0",
        "is_wp_error($response)",
        "wp_remote_retrieve_response_code($response)",
        "wp_remote_retrieve_body($response)",
        "json_decode($raw_body, true)",
    ]:
        if literal not in registry_body:
            fail(f"registry connection HTTP call missing review guard: {literal}")
    for name, body in [("public endpoint fetch", public_fetch_body), ("registry health fetch", registry_health_body)]:
        for literal in [
            "wp_remote_get(",
            "'Accept' => 'application/json'",
            "'timeout' =>",
            "is_wp_error($response)",
            "wp_remote_retrieve_response_code($response)",
            "wp_remote_retrieve_body($response)",
            "json_decode($raw_body, true)",
        ]:
            if literal not in body:
                fail(f"{name} HTTP call missing review guard: {literal}")
    for literal in [
        "$headers['Authorization'] = 'Bearer ' . $token",
        "$headers['X-AgentCart-Token'] = $token",
        "'redirection' => 0",
    ]:
        if literal not in registry_health_body:
            fail(f"registry health HTTP call missing review guard: {literal}")
    if re.search(r"\b(curl_exec|file_get_contents)\s*\(", source):
        fail("use WordPress HTTP APIs instead of curl_exec/file_get_contents")


def check_admin_badge_escaping(source: str) -> None:
    body = function_body(source, "admin_status_badge")
    for literal in ["esc_attr($background)", "esc_attr($color)", "esc_html($label)"]:
        if literal not in body:
            fail(f"admin_status_badge must escape generated HTML: {literal}")


def check_rate_limit_controls(source: str) -> None:
    well_known_body = function_body(source, "maybe_serve_well_known_manifest")
    policy_body = function_body(source, "rate_limit_policy")
    limiter_body = function_body(source, "enforce_rate_limit_for_client")
    error_body = function_body(source, "rate_limit_error")
    key_body = function_body(source, "rate_limit_client_key_from_server")
    document_body = function_body(source, "public_rate_limits_document")
    for literal in [
        "enforce_well_known_rate_limit($path)",
        "header('Retry-After: '",
        "'/.well-known/agentcart-registry-proof.json'",
        "'/.well-known/agentcart-registry-revocations.json'",
        "'/.well-known/agentcart-registry-bundle.json'",
    ]:
        if literal not in well_known_body:
            fail(f"well-known registry endpoints must be rate limited: {literal}")
    for bucket in ["'catalog'", "'registry'", "'quote'", "'checkout'", "'order_status'", "'refund'", "'cancellation'"]:
        if bucket not in policy_body:
            fail(f"rate limit policy missing bucket: {bucket}")
    for literal in ["get_transient($transient)", "set_transient($transient", "rate_limit_error("]:
        if literal not in limiter_body:
            fail(f"rate limiter missing transient guard: {literal}")
    for literal in ["'retry_after_seconds'", "'reset_at'", "gmdate('c'", "'remaining'"]:
        if literal not in error_body:
            fail(f"rate limit error missing retry metadata: {literal}")
    for literal in ["wp_unslash($_SERVER['REMOTE_ADDR']", "wp_unslash($_SERVER['HTTP_USER_AGENT']"]:
        if literal not in key_body:
            fail(f"rate limit client key must use sanitized server data: {literal}")
    if "x-forwarded-for" in key_body.lower():
        fail("rate limit client key must not trust X-Forwarded-For directly")
    if "'registry'" not in document_body:
        fail("capability document must advertise registry rate limits")


def main() -> int:
    try:
        source = PLUGIN.read_text(encoding="utf-8")
        check_superglobal_unslash(source)
        check_custom_admin_actions(source)
        check_external_http_verifier_calls(source)
        check_admin_badge_escaping(source)
        check_rate_limit_controls(source)
    except (AssertionError, OSError) as exc:
        print(f"wordpress plugin review check failed: {exc}", file=sys.stderr)
        return 1
    print(f"wordpress plugin review check ok: {PLUGIN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
