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
SKILL_VERSION_PATTERN = r'^(\s+version:\s*")[^"]+("\s*)$'


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
    root_package = ROOT / "package.json"
    root_data = load_json(root_package)
    root_data["version"] = version
    write_json(root_package, root_data, check=check)
    root_lock = ROOT / "package-lock.json"
    if root_lock.exists():
        data = load_json(root_lock)
        data["version"] = version
        if isinstance(data.get("packages", {}).get(""), dict):
            data["packages"][""]["version"] = version
        write_json(root_lock, data, check=check)
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
        SKILL_VERSION_PATTERN,
        rf"\g<1>{version}\g<2>",
        "ShopBridge direct skill metadata",
        check=check,
    )
    for skill in ("gateway/openclaw-skill", "household-os/openclaw-skill"):
        stamp_text_file(ROOT / skill / "SKILL.md", SKILL_VERSION_PATTERN,
                        rf"\g<1>{version}\g<2>", f"{skill} metadata", check=check)
    for chart in ("agentcart-shopbridge", "agentcart-shopbridge-registry"):
        path = ROOT / "charts" / chart / "Chart.yaml"
        stamp_text_file(path, r'^(version:\s*)[^\s]+(\s*)$', rf'\g<1>{version}\g<2>', f"{chart} chart", check=check)
        stamp_text_file(path, r'^(appVersion:\s*)[^\n]+$', rf'\g<1>"{version}"', f"{chart} application", check=check)


def verify_versions(version: str) -> None:
    for name in ("package.json", "gateway/package.json", "package-lock.json", "gateway/package-lock.json"):
        path = ROOT / name
        if not path.exists():
            continue
        data = load_json(path)
        if data.get("version") != version or ("packages" in data and data.get("packages", {}).get("", {}).get("version") != version):
            fail(f"{name} release version differs from {version}")
    markers = {
        "woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php": r"\* Version: ([^\s]+)",
        "woocommerce-shopbridge/agentcart-shopbridge/readme.txt": r"^Stable tag: ([^\s]+)",
        "charts/agentcart-shopbridge/files/plugin/agentcart-shopbridge.php": r"\* Version: ([^\s]+)",
        "charts/agentcart-shopbridge/files/plugin/readme.txt": r"^Stable tag: ([^\s]+)",
        **{name: r'^\s+version: "([^"]+)"' for name in ("gateway/shopbridge-direct-skill/SKILL.md", "gateway/openclaw-skill/SKILL.md", "household-os/openclaw-skill/SKILL.md")},
    }
    for name, pattern in markers.items():
        match = re.search(pattern, (ROOT / name).read_text(), flags=re.MULTILINE)
        if not match or match.group(1) != version:
            fail(f"{name} release version differs from {version}")
    for chart in ("agentcart-shopbridge", "agentcart-shopbridge-registry"):
        text = (ROOT / "charts" / chart / "Chart.yaml").read_text()
        for key in ("version", "appVersion"):
            match = re.search(rf'^{key}:\s*"?([^"\s]+)"?$', text, flags=re.MULTILINE)
            if not match or match.group(1) != version:
                fail(f"{chart} {key} differs from {version}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stamp semantic-release's next version into shipped AgentCart surfaces.")
    parser.add_argument("version")
    parser.add_argument("--check", action="store_true", help="Validate all version markers without modifying files.")
    parser.add_argument("--verify", action="store_true", help="Require source, lockfiles, skills and chart copies to match the requested version.")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            verify_versions(args.version)
        else:
            # Check every marker before writing any part of the release cohort.
            stamp_all(args.version, check=True)
            if not args.check:
                stamp_all(args.version, check=False)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"release version stamp failed: {exc}", file=sys.stderr)
        return 1
    action = "verified" if args.verify else "validated" if args.check else "stamped"
    print(f"release version {action}: {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
