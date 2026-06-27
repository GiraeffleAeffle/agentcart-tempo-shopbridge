#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


def fail(message: str) -> None:
    raise ValueError(message)


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        fail(f"{label} version marker not found")
    return updated


def load_json(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail(f"{path.relative_to(ROOT)} must contain a JSON object")
    return data


def write_json(path: pathlib.Path, data: dict[str, Any], *, check: bool) -> None:
    if check:
        return
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def stamp_gateway_package(version: str, *, check: bool) -> None:
    package_path = ROOT / "gateway/package.json"
    package = load_json(package_path)
    package["version"] = version
    write_json(package_path, package, check=check)

    lock_path = ROOT / "gateway/package-lock.json"
    lock = load_json(lock_path)
    lock["version"] = version
    packages = lock.get("packages")
    if isinstance(packages, dict) and isinstance(packages.get(""), dict):
        packages[""]["version"] = version
    write_json(lock_path, lock, check=check)


def stamp_text_file(path: pathlib.Path, pattern: str, replacement: str, label: str, *, check: bool) -> None:
    text = path.read_text(encoding="utf-8")
    updated = replace_once(text, pattern, replacement, label)
    if not check:
        path.write_text(updated, encoding="utf-8")


def stamp_all(version: str, *, check: bool) -> None:
    if not SEMVER_RE.fullmatch(version):
        fail(f"release version must be semantic-release style SemVer without build metadata: {version}")

    stamp_gateway_package(version, check=check)
    stamp_text_file(
        ROOT / "woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php",
        r"^(\s*\*\s*Version:\s*)[^\s]+(\s*)$",
        rf"\g<1>{version}\g<2>",
        "WooCommerce plugin header",
        check=check,
    )
    stamp_text_file(
        ROOT / "woocommerce-shopbridge/agentcart-shopbridge/readme.txt",
        r"^(Stable tag:\s*)[^\s]+(\s*)$",
        rf"\g<1>{version}\g<2>",
        "WordPress readme stable tag",
        check=check,
    )
    stamp_text_file(
        ROOT / "gateway/shopbridge-direct-skill/SKILL.md",
        r"^(version:\s*)[^\s]+(\s*)$",
        rf"\g<1>{version}\g<2>",
        "ShopBridge direct skill frontmatter",
        check=check,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stamp semantic-release's next version into shipped AgentCart surfaces.")
    parser.add_argument("version")
    parser.add_argument("--check", action="store_true", help="Validate all version markers without modifying files.")
    args = parser.parse_args(argv)
    try:
        stamp_all(args.version, check=args.check)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"release version stamp failed: {exc}", file=sys.stderr)
        return 1
    action = "validated" if args.check else "stamped"
    print(f"release version {action}: {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
