#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_TOOLS_DIR = ROOT / "woocommerce-shopbridge"
COMPOSER_JSON = PLUGIN_TOOLS_DIR / "composer.json"
PHPCS_XML = PLUGIN_TOOLS_DIR / "phpcs.xml.dist"
PLUGIN_DIR = PLUGIN_TOOLS_DIR / "agentcart-shopbridge"
LOCAL_PLUGIN_CHECK = ROOT / "scripts" / "run-wordpress-plugin-check.sh"


def fail(message: str) -> None:
    raise AssertionError(message)


def require_tool_config() -> None:
    if not COMPOSER_JSON.exists():
        fail(f"missing WordPress tooling composer.json: {COMPOSER_JSON}")
    if not PHPCS_XML.exists():
        fail(f"missing PHPCS ruleset: {PHPCS_XML}")

    composer = json.loads(COMPOSER_JSON.read_text(encoding="utf-8"))
    require_dev = composer.get("require-dev")
    if not isinstance(require_dev, dict):
        fail("composer.json must define require-dev")
    for package in [
        "dealerdirect/phpcodesniffer-composer-installer",
        "phpcompatibility/phpcompatibility-wp",
        "squizlabs/php_codesniffer",
        "wp-coding-standards/wpcs",
    ]:
        if package not in require_dev:
            fail(f"composer.json require-dev missing {package}")

    ruleset = PHPCS_XML.read_text(encoding="utf-8")
    for rule in ["WordPress", "PHPCompatibilityWP"]:
        if f'<rule ref="{rule}"' not in ruleset:
            fail(f"phpcs.xml.dist missing {rule}")
    if "<file>agentcart-shopbridge</file>" not in ruleset:
        fail("phpcs.xml.dist must target the packaged plugin directory")


def phpcs_command() -> list[str] | None:
    local_phpcs = PLUGIN_TOOLS_DIR / "vendor" / "bin" / "phpcs"
    if local_phpcs.exists():
        return [str(local_phpcs), "--standard=phpcs.xml.dist"]
    global_phpcs = shutil.which("phpcs")
    if global_phpcs:
        return [global_phpcs, "--standard=phpcs.xml.dist"]
    return None


def run_command(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=str(cwd), check=True)


def plugin_check_command(raw: str, *, strict: bool) -> list[str] | None:
    raw = raw.strip()
    if not raw:
        if strict and LOCAL_PLUGIN_CHECK.exists():
            return [str(LOCAL_PLUGIN_CHECK)]
        return None
    return shlex.split(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or validate official WordPress plugin release gates.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Require external official tools to be installed and runnable.",
    )
    parser.add_argument(
        "--plugin-check-command",
        default=os.getenv("AGENTCART_WORDPRESS_PLUGIN_CHECK_COMMAND", ""),
        help="Command that runs WordPress Plugin Check in a prepared WordPress install.",
    )
    args = parser.parse_args()
    strict = args.strict or os.getenv("AGENTCART_WORDPRESS_OFFICIAL_TOOLS_REQUIRED", "") == "1"

    try:
        require_tool_config()

        phpcs = phpcs_command()
        if phpcs:
            run_command(phpcs, cwd=PLUGIN_TOOLS_DIR)
            print("official PHPCS/WPCS gate ok")
        elif strict:
            fail("PHPCS/WPCS tooling is not installed; run composer install in woocommerce-shopbridge")
        else:
            print("official PHPCS/WPCS gate skipped: phpcs not installed")

        plugin_check = plugin_check_command(args.plugin_check_command, strict=strict)
        if plugin_check:
            run_command(plugin_check, cwd=ROOT)
            print("official WordPress Plugin Check gate ok")
        elif strict:
            fail("WordPress Plugin Check command is not configured")
        else:
            print("official WordPress Plugin Check gate skipped: AGENTCART_WORDPRESS_PLUGIN_CHECK_COMMAND not set")
    except (AssertionError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"wordpress official gate check failed: {exc}", file=sys.stderr)
        return 1

    print(f"wordpress official gate config ok: {PLUGIN_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
