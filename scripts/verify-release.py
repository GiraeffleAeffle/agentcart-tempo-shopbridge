#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def safe_relative_path(value: Any) -> pathlib.Path:
    raw = str(value or "")
    path = pathlib.PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"artifact path is unsafe: {raw}")
    return pathlib.Path(*path.parts)


def source_text(root: pathlib.Path, value: Any) -> str | None:
    try:
        path = root / safe_relative_path(value)
    except ValueError:
        return None
    if not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def version_from_source(root: pathlib.Path, component: str, meta: dict[str, Any]) -> str | None:
    text = source_text(root, meta.get("source"))
    if text is None:
        return None
    if component == "gateway":
        data = json.loads(text)
        version = data.get("version")
        return version if isinstance(version, str) else None
    if component == "woocommerce_shopbridge":
        match = re.search(r"^\s*\*\s*Version:\s*([^\s]+)\s*$", text, flags=re.MULTILINE)
        return match.group(1) if match else None
    if component == "shopbridge_direct_skill":
        match = re.match(r"---\n(.*?)\n---\n", text, flags=re.S)
        if not match:
            return None
        for line in match.group(1).splitlines():
            if line.startswith("version:"):
                return line.split(":", 1)[1].strip().strip('"')
    return None


def verify_release(
    *,
    manifest_path: pathlib.Path,
    root: pathlib.Path,
    expected_manifest_sha256: str = "",
    expected_source_commit: str = "",
) -> list[str]:
    errors: list[str] = []
    if not manifest_path.exists():
        return [f"manifest missing: {manifest_path}"]
    actual_manifest_sha256 = sha256(manifest_path)
    if expected_manifest_sha256 and actual_manifest_sha256 != expected_manifest_sha256:
        errors.append("manifest_sha256_mismatch")
    try:
        manifest = load_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"manifest_invalid: {exc}"]

    if manifest.get("schema") != "agentcart.release.v1":
        errors.append("schema_mismatch")
    release = manifest.get("release") if isinstance(manifest.get("release"), dict) else {}
    if expected_source_commit and str(release.get("source_git_commit") or "") != expected_source_commit:
        errors.append("source_git_commit_mismatch")
    if not str(release.get("version") or ""):
        errors.append("release_version_missing")

    components = manifest.get("components") if isinstance(manifest.get("components"), dict) else {}
    for component, meta in components.items():
        if not isinstance(meta, dict):
            errors.append(f"component_{component}_invalid")
            continue
        version = str(meta.get("version") or "")
        if not version:
            errors.append(f"component_{component}_version_missing")
        source_version = version_from_source(root, str(component), meta)
        if source_version and source_version != version:
            errors.append(f"component_{component}_source_version_mismatch")

    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    if not artifacts:
        errors.append("artifacts_missing")
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"artifact_{index}_invalid")
            continue
        try:
            artifact_path = root / safe_relative_path(artifact.get("file"))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not artifact_path.exists():
            errors.append(f"artifact_missing:{artifact.get('file')}")
            continue
        expected_bytes = int(artifact.get("bytes") or -1)
        actual_bytes = artifact_path.stat().st_size
        if expected_bytes != actual_bytes:
            errors.append(f"artifact_bytes_mismatch:{artifact.get('file')}")
        expected_hash = str(artifact.get("sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            errors.append(f"artifact_sha256_invalid:{artifact.get('file')}")
        elif sha256(artifact_path) != expected_hash:
            errors.append(f"artifact_sha256_mismatch:{artifact.get('file')}")
        component = str(artifact.get("component") or "")
        if component and component not in components:
            errors.append(f"artifact_component_unknown:{component}")
        elif component and str(artifact.get("version") or "") != str(components[component].get("version") or ""):
            errors.append(f"artifact_component_version_mismatch:{component}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify AgentCart release artifacts against a release manifest.")
    parser.add_argument("--manifest", default=str(ROOT / "dist/agentcart-release.json"))
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--expected-manifest-sha256", default="")
    parser.add_argument("--expected-source-commit", default="")
    args = parser.parse_args(argv)

    manifest_path = pathlib.Path(args.manifest).resolve()
    root = pathlib.Path(args.root).resolve()
    errors = verify_release(
        manifest_path=manifest_path,
        root=root,
        expected_manifest_sha256=args.expected_manifest_sha256,
        expected_source_commit=args.expected_source_commit,
    )
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "manifest": str(manifest_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
