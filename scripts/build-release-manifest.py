#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
MANIFEST = DIST / "agentcart-release.json"


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def plugin_version() -> str:
    source = read_text(ROOT / "woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php")
    match = re.search(r"^\s*\*\s*Version:\s*([^\s]+)\s*$", source, flags=re.MULTILINE)
    if not match:
        raise SystemExit("WooCommerce plugin Version header not found")
    return match.group(1)


def gateway_version() -> str:
    package_json = json.loads(read_text(ROOT / "gateway/package.json"))
    version = package_json.get("version")
    if not isinstance(version, str) or not version:
        raise SystemExit("gateway/package.json version not found")
    return version


def skill_metadata() -> dict[str, str]:
    source = read_text(ROOT / "gateway/shopbridge-direct-skill/SKILL.md")
    match = re.match(r"---\n(.*?)\n---\n", source, flags=re.S)
    if not match:
        raise SystemExit("ShopBridge direct skill frontmatter not found")
    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    if not metadata.get("name"):
        raise SystemExit("ShopBridge direct skill name not found")
    return metadata


def artifact(path: pathlib.Path, *, component: str, version: str) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"artifact missing: {path}")
    return {
        "component": component,
        "version": version,
        "file": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def main() -> int:
    DIST.mkdir(exist_ok=True)
    skill = skill_metadata()
    skill_version = skill.get("version") or "0.1.0-alpha"
    release = {
        "schema": "agentcart.release.v1",
        "release": {
            "version": gateway_version(),
            "source_git_commit": git_commit(),
            "stability": "alpha",
        },
        "components": {
            "gateway": {
                "version": gateway_version(),
                "source": "gateway/package.json",
            },
            "woocommerce_shopbridge": {
                "version": plugin_version(),
                "source": "woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php",
            },
            "shopbridge_direct_skill": {
                "version": skill_version,
                "source": "gateway/shopbridge-direct-skill/SKILL.md",
                "name": skill["name"],
            },
        },
        "artifacts": [
            artifact(
                DIST / "agentcart-shopbridge.zip",
                component="woocommerce_shopbridge",
                version=plugin_version(),
            ),
            artifact(
                DIST / "shopbridge-direct-skill.zip",
                component="shopbridge_direct_skill",
                version=skill_version,
            ),
        ],
        "upgrade": {
            "plugin": "Upload dist/agentcart-shopbridge.zip in WordPress, or replace wp-content/plugins/agentcart-shopbridge after backing up settings.",
            "skill": "Replace the installed shopbridge-direct-skill folder or reinstall dist/shopbridge-direct-skill.zip in the buyer agent.",
            "rollback": "Keep the previous ZIPs and this manifest; reinstall the previous artifact if verification or smoke tests fail.",
        },
    }
    MANIFEST.write_text(json.dumps(release, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Created {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
