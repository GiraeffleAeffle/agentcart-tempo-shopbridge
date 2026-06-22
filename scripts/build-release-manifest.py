#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import json
import os
import pathlib
import re
import argparse
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
MANIFEST = DIST / "agentcart-release.json"
SIGNATURE_SCHEMA = "agentcart.release_signature.v1"


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def release_source_commit() -> str:
    return os.getenv("AGENTCART_RELEASE_SOURCE_COMMIT", "").strip()


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


def signature_payload(*, manifest_path: pathlib.Path, root: pathlib.Path, key_id: str = "") -> dict[str, Any]:
    return {
        "schema": SIGNATURE_SCHEMA,
        "alg": "hmac-sha256",
        "key_id": key_id,
        "manifest_file": str(manifest_path.relative_to(root)),
        "manifest_sha256": sha256(manifest_path),
    }


def write_signature(*, manifest_path: pathlib.Path, root: pathlib.Path, signature_path: pathlib.Path, signing_key: str, key_id: str = "") -> None:
    if not signing_key:
        raise SystemExit("release signing requested but signing key is empty")
    payload = signature_payload(manifest_path=manifest_path, root=root, key_id=key_id)
    signature = hmac.new(signing_key.encode("utf-8"), canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()
    signed = {**payload, "signature": signature}
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    signature_path.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Created {signature_path}")


def build_release() -> dict[str, Any]:
    DIST.mkdir(exist_ok=True)
    skill = skill_metadata()
    skill_version = skill.get("version") or "0.1.0-alpha"
    return {
        "schema": "agentcart.release.v1",
        "release": {
            "version": gateway_version(),
            "source_git_commit": release_source_commit(),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the AgentCart release manifest and optional detached signature.")
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--signature-out", default="", help="Write a detached release signature JSON sidecar.")
    parser.add_argument("--signing-key-env", default="AGENTCART_RELEASE_SIGNING_KEY")
    parser.add_argument("--signature-key-id", default=os.getenv("AGENTCART_RELEASE_SIGNING_KEY_ID", "").strip())
    args = parser.parse_args(argv)

    manifest_path = pathlib.Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    manifest_for_signature = manifest_path.resolve()
    try:
        manifest_for_signature.relative_to(ROOT.resolve())
    except ValueError:
        raise SystemExit("manifest path must be inside the repository root")
    release = build_release()
    manifest_for_signature.parent.mkdir(parents=True, exist_ok=True)
    manifest_for_signature.write_text(json.dumps(release, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Created {manifest_for_signature}")
    if args.signature_out:
        signature_path = pathlib.Path(args.signature_out)
        if not signature_path.is_absolute():
            signature_path = ROOT / signature_path
        signing_key = os.getenv(args.signing_key_env, "")
        write_signature(
            manifest_path=manifest_for_signature,
            root=ROOT,
            signature_path=signature_path,
            signing_key=signing_key,
            key_id=args.signature_key_id,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
