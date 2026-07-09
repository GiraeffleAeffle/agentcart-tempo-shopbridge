#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import pathlib
import re
import sys
import urllib.parse


TRUTHY = {"1", "true", "yes", "on"}
MIN_SHARED_SECRET_CHARACTERS = 32
SIGNED_REQUEST_PRODUCTION_MODES = {
    "require_checkout",
    "require_mutations",
    "require_all_sensitive",
}
DEPLOYMENT_PROFILES = {"standard", "hetzner-usd-staging"}
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


def strong_shared_secret(values: dict[str, str], key: str, *, allow_placeholders: bool) -> bool:
    value = values.get(key, "").strip()
    if not value:
        return False
    if allow_placeholders and is_placeholder(value):
        return True
    return not is_placeholder(value) and len(value) >= MIN_SHARED_SECRET_CHARACTERS


def require_strong_secret(
    values: dict[str, str],
    key: str,
    errors: list[str],
    *,
    allow_placeholders: bool,
) -> None:
    if not configured(values, key, allow_placeholders=allow_placeholders):
        return
    if not strong_shared_secret(values, key, allow_placeholders=allow_placeholders):
        errors.append(f"{key} must contain at least {MIN_SHARED_SECRET_CHARACTERS} characters and must not be a placeholder")


def apply_deployment_profile(values: dict[str, str], profile: str = "standard") -> dict[str, str]:
    normalized = dict(values)
    if profile == "standard":
        return normalized
    if profile != "hetzner-usd-staging":
        raise ValueError(f"unsupported deployment profile: {profile}")
    normalized.update(
        {
            "AGENTCART_DEPLOYMENT_PROFILE": profile,
            "WOOCOMMERCE_MODE": "plugin",
            "AGENTCART_CHECKOUT_MODE": "external_verifier_only",
            "AGENTCART_PAYMENT_VERIFIER_URL": "http://agentcart-usd-verifier:4260/agentcart/verify",
            "AGENTCART_PAYMENT_VERIFIER_TOKEN": values.get("STAGING_PAYMENT_VERIFIER_TOKEN", ""),
            "AGENTCART_ALLOW_PRIVATE_PAYMENT_VERIFIER_URL": "true",
            "AGENTCART_PAYMENT_VERIFIER_TRUST_MODE": "pinned_internal",
            "AGENTCART_VERIFIER_REPLAY_STORE_DRIVER": "sqlite",
            "AGENTCART_VERIFIER_REPLAY_STORE_PATH": "/data/replay-store.sqlite",
            "AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY": "true",
            "AGENTCART_VERIFIER_REPLAY_JOURNAL_PATH": "/data/replay-journal.jsonl",
            "AGENTCART_VERIFIER_REQUIRE_REPLAY_JOURNAL": "true",
            "AGENTCART_SIGNED_REQUEST_MODE": values.get("STAGING_SIGNED_REQUEST_MODE", ""),
            "AGENTCART_SIGNED_REQUEST_SECRET": values.get("STAGING_SIGNED_REQUEST_SECRET", ""),
            "WOOCOMMERCE_SIGNED_REQUEST_SECRET": values.get("STAGING_SIGNED_REQUEST_SECRET", ""),
            "WOOCOMMERCE_AGENTCART_TOKEN": values.get("STAGING_SHOPBRIDGE_TOKEN", ""),
            "MPP_SECRET_KEY": values.get("STAGING_MPP_SECRET_KEY", ""),
        }
    )
    return normalized


def pinned_internal_verifier_url_error(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    host = (parsed.hostname or "").strip().lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return "pinned_internal payment verifier URL must be an absolute HTTP(S) URL"
    if host == "localhost" or host.endswith(".localhost"):
        return "pinned_internal payment verifier URL must not use a loopback host"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." in host and not host.endswith(".internal"):
            return "pinned_internal payment verifier URL must use a Docker/internal hostname or private IP"
        return ""
    if address.is_loopback or address.is_unspecified:
        return "pinned_internal payment verifier URL must not use a loopback or unspecified IP"
    if address.is_global:
        return "pinned_internal payment verifier URL must not use a public IP"
    return ""


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
    else:
        require_strong_secret(
            values,
            "AGENTCART_PAYMENT_VERIFIER_TOKEN",
            errors,
            allow_placeholders=allow_placeholders,
        )
    private_verifier_allowed = values.get("AGENTCART_ALLOW_PRIVATE_PAYMENT_VERIFIER_URL", "").strip().lower() in TRUTHY
    verifier_trust_mode = values.get("AGENTCART_PAYMENT_VERIFIER_TRUST_MODE", "public").strip().lower() or "public"
    if verifier_trust_mode not in {"public", "pinned_internal"}:
        errors.append("AGENTCART_PAYMENT_VERIFIER_TRUST_MODE must be public or pinned_internal")
    if private_verifier_allowed and verifier_trust_mode != "pinned_internal":
        errors.append(
            "AGENTCART_ALLOW_PRIVATE_PAYMENT_VERIFIER_URL must be false or unset for public production payment profiles"
        )
    if verifier_trust_mode == "pinned_internal":
        if not private_verifier_allowed:
            errors.append("pinned_internal verifier trust requires AGENTCART_ALLOW_PRIVATE_PAYMENT_VERIFIER_URL=true")
        internal_url_error = pinned_internal_verifier_url_error(values.get("AGENTCART_PAYMENT_VERIFIER_URL", ""))
        if internal_url_error:
            errors.append(internal_url_error)

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
    elif configured(values, "AGENTCART_SIGNED_REQUEST_SECRET", allow_placeholders=allow_placeholders):
        require_strong_secret(
            values,
            "AGENTCART_SIGNED_REQUEST_SECRET",
            errors,
            allow_placeholders=allow_placeholders,
        )

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

    for key in ("WOOCOMMERCE_SIGNED_REQUEST_SECRET", "SHOPBRIDGE_SIGNED_REQUEST_SECRET"):
        require_strong_secret(values, key, errors, allow_placeholders=allow_placeholders)
    for key in ("WOOCOMMERCE_AGENTCART_TOKEN", "AGENTCART_SHOPBRIDGE_TOKEN"):
        require_strong_secret(values, key, errors, allow_placeholders=allow_placeholders)
    if values.get("AGENTCART_DEPLOYMENT_PROFILE") == "hetzner-usd-staging":
        if not configured(values, "MPP_SECRET_KEY", allow_placeholders=allow_placeholders):
            errors.append("MPP_SECRET_KEY must be configured for the Hetzner USD staging profile")
        else:
            require_strong_secret(values, "MPP_SECRET_KEY", errors, allow_placeholders=allow_placeholders)

    merchant_hmac = values.get("AGENTCART_SIGNED_REQUEST_SECRET", "").strip()
    buyer_hmac = values.get("WOOCOMMERCE_SIGNED_REQUEST_SECRET", "").strip()
    if merchant_hmac and buyer_hmac and merchant_hmac != buyer_hmac:
        errors.append("AGENTCART_SIGNED_REQUEST_SECRET and WOOCOMMERCE_SIGNED_REQUEST_SECRET must match for HMAC signing")

    verifier_token = values.get("AGENTCART_PAYMENT_VERIFIER_TOKEN", "").strip()
    merchant_token = (
        values.get("WOOCOMMERCE_AGENTCART_TOKEN", "").strip()
        or values.get("AGENTCART_SHOPBRIDGE_TOKEN", "").strip()
    )
    credential_groups = {
        "payment verifier token": verifier_token,
        "signed request HMAC secret": merchant_hmac,
        "merchant gateway token": merchant_token,
        "MPP secret": values.get("MPP_SECRET_KEY", "").strip(),
    }
    labels = list(credential_groups)
    for index, left_label in enumerate(labels):
        left_value = credential_groups[left_label]
        if not left_value or (allow_placeholders and is_placeholder(left_value)):
            continue
        for right_label in labels[index + 1 :]:
            right_value = credential_groups[right_label]
            if right_value and left_value == right_value:
                errors.append(f"{left_label} and {right_label} must be distinct credentials")

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
    parser.add_argument(
        "--deployment-profile",
        choices=sorted(DEPLOYMENT_PROFILES),
        default="standard",
        help="Normalize a deployment-specific provisioning env before validation.",
    )
    args = parser.parse_args(argv)

    try:
        values = apply_deployment_profile(parse_env_files(args.env_file), args.deployment_profile)
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
