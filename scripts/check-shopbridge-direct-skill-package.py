#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "gateway" / "shopbridge-direct-skill"
PORTABLE_REQUIRED_FILES = {
    "SKILL.md",
    "scripts/shopbridge-command.py",
    "scripts/shopbridge_discovery_facets.py",
    "scripts/shopbridge_safe_http.py",
    "scripts/shopbridge_registry_trust.py",
    "scripts/shopbridge_onchain_projection.py",
    "scripts/shopbridge_onchain_rpc.py",
}
OPTIONAL_ADAPTER_FILES = {"agents/openai.yaml"}
FORBIDDEN_PARTS = {"__pycache__", ".DS_Store", "__MACOSX"}
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


def skill_frontmatter(source: str) -> str:
    match = re.match(r"^---\n(.*?)\n---\n", source, flags=re.S)
    if not match:
        raise ValueError("SKILL.md must start with YAML frontmatter")
    return match.group(1)


def validate_skill_dir(skill_dir: pathlib.Path = SKILL_DIR) -> list[str]:
    errors: list[str] = []
    for relative in sorted(PORTABLE_REQUIRED_FILES):
        if not (skill_dir / relative).is_file():
            errors.append(f"required skill file is missing: {relative}")
    skill_path = skill_dir / "SKILL.md"
    if skill_path.is_file():
        try:
            frontmatter = skill_frontmatter(skill_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(str(exc))
        else:
            top_level = {
                line.split(":", 1)[0]
                for line in frontmatter.splitlines()
                if line and not line[0].isspace() and ":" in line
            }
            unexpected = top_level - {"name", "description", "metadata"}
            if unexpected:
                errors.append(f"unexpected top-level SKILL.md metadata: {', '.join(sorted(unexpected))}")
            if not re.search(r'^name:\s*shopbridge-direct\s*$', frontmatter, flags=re.M):
                errors.append("SKILL.md name must be shopbridge-direct")
            version = re.search(r'^\s+version:\s*"?([^"\s]+)"?\s*$', frontmatter, flags=re.M)
            if not version or not SEMVER_RE.fullmatch(version.group(1)):
                errors.append("SKILL.md metadata.version must be valid SemVer")
    metadata_path = skill_dir / "agents" / "openai.yaml"
    if metadata_path.is_file():
        metadata = metadata_path.read_text(encoding="utf-8")
        for marker in ("display_name:", "short_description:", "default_prompt:", "$shopbridge-direct"):
            if marker not in metadata:
                errors.append(f"agents/openai.yaml must contain {marker}")
    return errors


def validate_zip(zip_path: pathlib.Path) -> list[str]:
    errors: list[str] = []
    try:
        with zipfile.ZipFile(zip_path) as archive:
            corrupt = archive.testzip()
            if corrupt:
                errors.append(f"ZIP contains a corrupt entry: {corrupt}")
            names = {name.rstrip("/") for name in archive.namelist() if name and not name.endswith("/")}
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"cannot read skill ZIP: {exc}"]
    prefix = "shopbridge-direct-skill/"
    if any(not name.startswith(prefix) for name in names):
        errors.append("every ZIP entry must be inside shopbridge-direct-skill/")
    relative_names = {name.removeprefix(prefix) for name in names if name.startswith(prefix)}
    missing = PORTABLE_REQUIRED_FILES - relative_names
    if missing:
        errors.append(f"ZIP is missing required files: {', '.join(sorted(missing))}")
    for name in sorted(relative_names):
        parts = pathlib.PurePosixPath(name).parts
        if any(part in FORBIDDEN_PARTS for part in parts) or name.endswith((".pyc", ".pyo")):
            errors.append(f"ZIP contains generated or platform-specific file: {name}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the installable ShopBridge direct skill folder and ZIP.")
    parser.add_argument("--skill-dir", type=pathlib.Path, default=SKILL_DIR)
    parser.add_argument("--zip", type=pathlib.Path)
    args = parser.parse_args(argv)
    errors = validate_skill_dir(args.skill_dir)
    if args.zip:
        errors.extend(validate_zip(args.zip))
    if errors:
        for error in errors:
            print(f"ShopBridge direct skill package check failed: {error}", file=sys.stderr)
        return 1
    print("ShopBridge direct skill package ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
