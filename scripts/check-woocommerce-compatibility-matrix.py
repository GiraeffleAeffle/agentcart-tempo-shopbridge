#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "gateway" / "config" / "woocommerce_compatibility_matrix.json"
PLUGIN_FILE = ROOT / "woocommerce-shopbridge" / "agentcart-shopbridge" / "agentcart-shopbridge.php"
README_FILE = ROOT / "woocommerce-shopbridge" / "agentcart-shopbridge" / "readme.txt"
SMOKE_SCRIPT = ROOT / "scripts" / "woocommerce-demo-smoke.sh"
RESET_SCRIPT = ROOT / "scripts" / "woocommerce-demo-reset.sh"
MERCHANT_VARIANCE_STRESS_FIELDS = ("tax", "shipping", "stock", "plugins", "checkout")


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: matrix root must be an object")
    return data


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def header_value(source: str, header: str) -> str:
    match = re.search(rf"^\s*\*?\s*{re.escape(header)}:\s*(.+?)\s*$", source, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def validate_matrix(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(data.get("schema") == "agentcart.woocommerce_compatibility_matrix.v1", "schema must be agentcart.woocommerce_compatibility_matrix.v1", errors)
    plugin = data.get("plugin")
    require(isinstance(plugin, dict), "plugin must be an object", errors)
    runtime_matrix = data.get("runtime_matrix")
    require(isinstance(runtime_matrix, list) and bool(runtime_matrix), "runtime_matrix must be a non-empty list", errors)
    verification = data.get("verification")
    require(isinstance(verification, dict), "verification must be an object", errors)

    plugin_source = PLUGIN_FILE.read_text(encoding="utf-8")
    readme_source = README_FILE.read_text(encoding="utf-8")
    if isinstance(plugin, dict):
        wp_min = str(plugin.get("requires_wordpress_at_least") or "")
        php_min = str(plugin.get("requires_php") or "")
        require(wp_min != "", "plugin.requires_wordpress_at_least is required", errors)
        require(php_min != "", "plugin.requires_php is required", errors)
        require(header_value(plugin_source, "Requires at least") == wp_min, "plugin header Requires at least must match matrix", errors)
        require(header_value(plugin_source, "Requires PHP") == php_min, "plugin header Requires PHP must match matrix", errors)
        require(header_value(readme_source, "Requires at least") == wp_min, "readme Requires at least must match matrix", errors)
        require(header_value(readme_source, "Requires PHP") == php_min, "readme Requires PHP must match matrix", errors)
        required_plugins = plugin.get("requires_plugins")
        require(isinstance(required_plugins, list) and "woocommerce" in required_plugins, "plugin.requires_plugins must include woocommerce", errors)

    if isinstance(verification, dict):
        require(str(verification.get("runtime_smoke_script") or "") == "scripts/woocommerce-demo-smoke.sh", "verification.runtime_smoke_script must point to scripts/woocommerce-demo-smoke.sh", errors)
        require(str(verification.get("live_endpoint_smoke") or "") == "scripts/woocommerce-shopbridge-smoke.py", "verification.live_endpoint_smoke must point to scripts/woocommerce-shopbridge-smoke.py", errors)
        endpoint_contract = str(verification.get("endpoint_contract") or "")
        require(endpoint_contract == "gateway/config/shopbridge_endpoint_contract.json", "verification.endpoint_contract must point to gateway/config/shopbridge_endpoint_contract.json", errors)
        require((ROOT / endpoint_contract).exists(), "verification.endpoint_contract file must exist", errors)
        require(str(verification.get("demo_reset_script") or "") == "scripts/woocommerce-demo-reset.sh", "verification.demo_reset_script must point to scripts/woocommerce-demo-reset.sh", errors)
        require(RESET_SCRIPT.exists(), "verification.demo_reset_script file must exist", errors)
        static_gates = verification.get("static_gates")
        require(isinstance(static_gates, list) and "PHPCompatibilityWP" in static_gates, "verification.static_gates must include PHPCompatibilityWP", errors)
        require(isinstance(static_gates, list) and "WordPress Plugin Check" in static_gates, "verification.static_gates must include WordPress Plugin Check", errors)

    seen_ids: set[str] = set()
    runtime_ids: set[str] = set()
    required_count = 0
    if isinstance(runtime_matrix, list):
        for index, entry in enumerate(runtime_matrix):
            if not isinstance(entry, dict):
                errors.append(f"runtime_matrix[{index}] must be an object")
                continue
            entry_id = str(entry.get("id") or "")
            require(entry_id != "", f"runtime_matrix[{index}].id is required", errors)
            require(entry_id not in seen_ids, f"duplicate runtime matrix id: {entry_id}", errors)
            seen_ids.add(entry_id)
            runtime_ids.add(entry_id)
            if entry.get("required_for_release") is True:
                required_count += 1
            for field in ("wordpress", "php", "woocommerce", "wordpress_image", "wordpress_cli_image"):
                require(str(entry.get(field) or "") != "", f"{entry_id}: {field} is required", errors)
            require(str(entry.get("wordpress_image") or "").startswith("wordpress:"), f"{entry_id}: wordpress_image must use the official wordpress image namespace", errors)
            require(str(entry.get("wordpress_cli_image") or "").startswith("wordpress:cli-"), f"{entry_id}: wordpress_cli_image must use a wordpress CLI image", errors)
            require(isinstance(entry.get("host_port"), int) and int(entry.get("host_port")) > 0, f"{entry_id}: host_port must be a positive integer", errors)
            require(isinstance(entry.get("expected_shipping_cents"), int), f"{entry_id}: expected_shipping_cents must be an integer", errors)
    require(required_count >= 1, "runtime_matrix must contain at least one required_for_release entry", errors)

    merchant_profiles = data.get("merchant_variance_profiles")
    require(
        isinstance(merchant_profiles, list) and len(merchant_profiles) >= 2,
        "merchant_variance_profiles must contain at least two profiles",
        errors,
    )
    profile_ids: set[str] = set()
    evidence_ids: set[str] = set()
    required_profile_count = 0
    if isinstance(merchant_profiles, list):
        for index, profile in enumerate(merchant_profiles):
            if not isinstance(profile, dict):
                errors.append(f"merchant_variance_profiles[{index}] must be an object")
                continue
            profile_id = str(profile.get("id") or "")
            require(profile_id != "", f"merchant_variance_profiles[{index}].id is required", errors)
            require(profile_id not in profile_ids, f"duplicate merchant variance profile id: {profile_id}", errors)
            profile_ids.add(profile_id)
            if profile.get("required_for_beta") is True:
                required_profile_count += 1
            for field in ("name", "runtime_entry", "seed_profile", "evidence_id", "expected_result_path", "command"):
                require(str(profile.get(field) or "") != "", f"{profile_id}: {field} is required", errors)
            runtime_entry = str(profile.get("runtime_entry") or "")
            require(runtime_entry in runtime_ids, f"{profile_id}: runtime_entry must reference runtime_matrix", errors)
            require(str(profile.get("seed_profile") or "") == profile_id, f"{profile_id}: seed_profile must match id", errors)
            require(isinstance(profile.get("expected_shipping_cents"), int), f"{profile_id}: expected_shipping_cents must be an integer", errors)
            evidence_id = str(profile.get("evidence_id") or "")
            require(evidence_id not in evidence_ids, f"duplicate merchant variance evidence id: {evidence_id}", errors)
            evidence_ids.add(evidence_id)
            require(
                str(profile.get("expected_result_path") or "") == f"pilot/pilot-merchant-onboarding/{evidence_id}.md",
                f"{profile_id}: expected_result_path must point to pilot/pilot-merchant-onboarding/{evidence_id}.md",
                errors,
            )
            command = str(profile.get("command") or "")
            require("--run-smoke" in command, f"{profile_id}: command must run the smoke harness", errors)
            require(
                f"--merchant-variance-profile {profile_id}" in command,
                f"{profile_id}: command must select the merchant variance profile",
                errors,
            )
            stresses = profile.get("stresses")
            require(isinstance(stresses, dict), f"{profile_id}: stresses must be an object", errors)
            if isinstance(stresses, dict):
                for field in MERCHANT_VARIANCE_STRESS_FIELDS:
                    require(str(stresses.get(field) or "") != "", f"{profile_id}: stresses.{field} is required", errors)
    require(
        required_profile_count >= 2,
        "merchant_variance_profiles must contain at least two required_for_beta profiles",
        errors,
    )

    release_claims = data.get("release_claims")
    require(isinstance(release_claims, list) and len(release_claims) >= 2, "release_claims must contain at least two entries", errors)
    return errors


def selected_entries(data: dict[str, Any], *, entry_id: str, include_optional: bool) -> list[dict[str, Any]]:
    entries = [entry for entry in data.get("runtime_matrix", []) if isinstance(entry, dict)]
    if entry_id:
        return [entry for entry in entries if str(entry.get("id") or "") == entry_id]
    if include_optional:
        return entries
    return [entry for entry in entries if entry.get("required_for_release") is True]


def selected_merchant_variance_profiles(data: dict[str, Any], *, profile_id: str, include_optional: bool) -> list[dict[str, Any]]:
    profiles = [profile for profile in data.get("merchant_variance_profiles", []) if isinstance(profile, dict)]
    if profile_id:
        return [profile for profile in profiles if str(profile.get("id") or "") == profile_id]
    if include_optional:
        return profiles
    return [profile for profile in profiles if profile.get("required_for_beta") is True]


def run_smoke_entry(entry: dict[str, Any], merchant_variance_profile: dict[str, Any] | None = None) -> None:
    entry_id = str(entry["id"])
    profile_id = str((merchant_variance_profile or {}).get("id") or "")
    run_id = "-".join(part for part in (entry_id, profile_id) if part)
    host_port = str(entry["host_port"])
    expected_shipping_cents = str(
        (merchant_variance_profile or {}).get("expected_shipping_cents", entry.get("expected_shipping_cents", 490))
    )
    env = dict(os.environ)
    env.update(
        {
            "COMPOSE_PROJECT_NAME": "agentcart_" + re.sub(r"[^a-zA-Z0-9]+", "_", run_id).strip("_").lower(),
            "WORDPRESS_IMAGE": str(entry["wordpress_image"]),
            "WORDPRESS_CLI_IMAGE": str(entry["wordpress_cli_image"]),
            "WOO_HOST_PORT": host_port,
            "WOO_PUBLIC_URL": f"http://127.0.0.1:{host_port}",
            "AGENTCART_WOO_SMOKE_BASE_URL": f"http://127.0.0.1:{host_port}",
            "AGENTCART_WOO_SMOKE_EXPECT_SHIPPING_CENTS": expected_shipping_cents,
            "AGENTCART_WOO_SMOKE_DOWN_VOLUMES": "1",
        }
    )
    if merchant_variance_profile:
        env["AGENTCART_WOO_VARIANCE_PROFILE"] = str(merchant_variance_profile.get("seed_profile") or profile_id)
        print(f"running WooCommerce compatibility smoke: {entry_id} / {profile_id}", flush=True)
    else:
        print(f"running WooCommerce compatibility smoke: {entry_id}", flush=True)
    subprocess.run([str(SMOKE_SCRIPT), "--down"], cwd=str(ROOT), env=env, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and optionally run the AgentCart ShopBridge WooCommerce compatibility matrix.")
    parser.add_argument("--matrix", type=pathlib.Path, default=DEFAULT_MATRIX)
    parser.add_argument("--run-smoke", action="store_true", help="Run Docker smoke tests for selected matrix entries.")
    parser.add_argument("--include-optional", action="store_true", help="With --run-smoke, include optional matrix entries.")
    parser.add_argument("--entry", default="", help="Run a single matrix entry id.")
    parser.add_argument("--merchant-variance-profile", default="", help="Run a single merchant variance profile id through its runtime entry.")
    args = parser.parse_args(argv)

    data = load_json(args.matrix)
    errors = validate_matrix(data)
    if errors:
        for error in errors:
            print(f"woocommerce compatibility matrix check failed: {error}", file=sys.stderr)
        return 1
    if args.run_smoke:
        if args.merchant_variance_profile:
            profiles = selected_merchant_variance_profiles(
                data,
                profile_id=args.merchant_variance_profile,
                include_optional=args.include_optional,
            )
            entries_by_id = {
                str(entry.get("id") or ""): entry
                for entry in data.get("runtime_matrix", [])
                if isinstance(entry, dict)
            }
            if not profiles:
                print("woocommerce compatibility matrix check failed: no selected merchant variance profiles", file=sys.stderr)
                return 1
            for profile in profiles:
                runtime_entry_id = str(profile["runtime_entry"])
                if args.entry and args.entry != runtime_entry_id:
                    print(
                        "woocommerce compatibility matrix check failed: --entry does not match merchant variance profile runtime_entry",
                        file=sys.stderr,
                    )
                    return 1
                run_smoke_entry(entries_by_id[runtime_entry_id], merchant_variance_profile=profile)
        else:
            entries = selected_entries(data, entry_id=args.entry, include_optional=args.include_optional)
            if not entries:
                print("woocommerce compatibility matrix check failed: no selected runtime entries", file=sys.stderr)
                return 1
            for entry in entries:
                run_smoke_entry(entry)
    print(f"woocommerce compatibility matrix ok: {args.matrix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
