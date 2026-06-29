#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pathlib
import re
import sys


TRUTHY = {"1", "true", "yes", "on"}
SIGNED_REQUEST_PRODUCTION_MODES = {
    "require_checkout",
    "require_mutations",
    "require_all_sensitive",
}
PLACEHOLDER_PATTERNS = [
    re.compile(r"^replace-with-", re.IGNORECASE),
    re.compile(r"^example-", re.IGNORECASE),
    re.compile(r"^changeme$", re.IGNORECASE),
    re.compile(r"^todo$", re.IGNORECASE),
]


def parse_env_file(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"{path}:{line_number}: invalid env key {key!r}")
        values[key] = unquote_env_value(value.strip())
    return values


def parse_env_files(paths: list[pathlib.Path]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            raise ValueError(f"env file does not exist: {path}")
        merged.update(parse_env_file(path))
    return merged


def unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def is_placeholder(value: str) -> bool:
    stripped = value.strip()
    return any(pattern.search(stripped) for pattern in PLACEHOLDER_PATTERNS)


def configured(values: dict[str, str], key: str, *, allow_placeholders: bool) -> bool:
    value = values.get(key, "").strip()
    if value == "":
        return False
    return allow_placeholders or not is_placeholder(value)


def validate_profile(values: dict[str, str], *, allow_placeholders: bool = False) -> list[str]:
    errors: list[str] = []

    if values.get("WOOCOMMERCE_MODE", "plugin").strip() == "disabled":
        errors.append("WOOCOMMERCE_MODE must not be disabled for a production payment profile")

    checkout_mode = values.get("AGENTCART_CHECKOUT_MODE", "").strip()
    if checkout_mode != "external_verifier_only":
        errors.append("AGENTCART_CHECKOUT_MODE must be external_verifier_only")

    if not configured(values, "AGENTCART_PAYMENT_VERIFIER_URL", allow_placeholders=allow_placeholders):
        errors.append("AGENTCART_PAYMENT_VERIFIER_URL must be configured")
    if not configured(values, "AGENTCART_PAYMENT_VERIFIER_TOKEN", allow_placeholders=allow_placeholders):
        errors.append("AGENTCART_PAYMENT_VERIFIER_TOKEN must be configured")

    durable_replay = values.get("AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY", "").strip().lower()
    if durable_replay not in TRUTHY:
        errors.append("AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY must be true")
    if not configured(values, "AGENTCART_VERIFIER_REPLAY_STORE_PATH", allow_placeholders=allow_placeholders):
        errors.append("AGENTCART_VERIFIER_REPLAY_STORE_PATH must be configured")
    replay_driver = values.get("AGENTCART_VERIFIER_REPLAY_STORE_DRIVER", "").strip().lower()
    if replay_driver != "sqlite":
        errors.append("AGENTCART_VERIFIER_REPLAY_STORE_DRIVER must be sqlite for production payment profiles")

    signed_mode = values.get("AGENTCART_SIGNED_REQUEST_MODE", "").strip()
    if signed_mode not in SIGNED_REQUEST_PRODUCTION_MODES:
        errors.append(
            "AGENTCART_SIGNED_REQUEST_MODE must require checkout or stronger "
            "(require_checkout, require_mutations, or require_all_sensitive)"
        )

    shopbridge_accepts_signed_requests = configured(
        values,
        "AGENTCART_SIGNED_REQUEST_SECRET",
        allow_placeholders=allow_placeholders,
    ) or configured(
        values,
        "AGENTCART_SIGNED_REQUEST_PUBLIC_KEY",
        allow_placeholders=allow_placeholders,
    )
    if not shopbridge_accepts_signed_requests:
        errors.append("AGENTCART_SIGNED_REQUEST_SECRET or AGENTCART_SIGNED_REQUEST_PUBLIC_KEY must be configured")

    buyer_can_sign_requests = any(
        configured(values, key, allow_placeholders=allow_placeholders)
        for key in (
            "WOOCOMMERCE_SIGNED_REQUEST_SECRET",
            "WOOCOMMERCE_SIGNED_REQUEST_PRIVATE_KEY",
            "SHOPBRIDGE_SIGNED_REQUEST_SECRET",
            "SHOPBRIDGE_SIGNED_REQUEST_PRIVATE_KEY",
        )
    )
    if not buyer_can_sign_requests:
        errors.append(
            "a buyer/gateway signing credential must be configured "
            "(WOOCOMMERCE_* or SHOPBRIDGE_* signed request key)"
        )

    merchant_hmac = values.get("AGENTCART_SIGNED_REQUEST_SECRET", "").strip()
    buyer_hmac = values.get("WOOCOMMERCE_SIGNED_REQUEST_SECRET", "").strip()
    if merchant_hmac and buyer_hmac and merchant_hmac != buyer_hmac:
        errors.append("AGENTCART_SIGNED_REQUEST_SECRET and WOOCOMMERCE_SIGNED_REQUEST_SECRET must match for HMAC signing")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a production-shaped ShopBridge payment env profile.")
    parser.add_argument(
        "--env-file",
        action="append",
        required=True,
        type=pathlib.Path,
        help="Env file to load. Pass multiple files to apply later files as overrides.",
    )
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Accept replace-with-* placeholder values. Use this only for checked-in example profiles.",
    )
    args = parser.parse_args(argv)

    try:
        values = parse_env_files(args.env_file)
    except ValueError as exc:
        print(f"production payment profile check failed: {exc}", file=sys.stderr)
        return 1

    errors = validate_profile(values, allow_placeholders=args.allow_placeholders)
    if errors:
        for error in errors:
            print(f"production payment profile check failed: {error}", file=sys.stderr)
        return 1
    print("production payment profile ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
