#!/usr/bin/env python3
"""Gate contracts/ runtime bytecode against EIP-170 after forge test/build.

Uses Foundry JSON artifacts, not forge's human-readable size report. Run from
any directory; --out overrides profile.default.out in the repository config.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tomllib


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
EIP170_LIMIT = 24_576


def artifact_directory(root: pathlib.Path, override: str | None) -> pathlib.Path:
    if override is not None:
        return pathlib.Path(override).resolve()
    config_path = root / "foundry.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    out = config.get("profile", {}).get("default", {}).get("out", "out")
    return root / out


def contract_sizes(out: pathlib.Path, root: pathlib.Path) -> list[tuple[str, str, int]]:
    if not out.is_dir():
        raise ValueError(f"artifact directory does not exist: {out}")
    sizes = []
    for path in sorted(out.rglob("*.json")):
        artifact = json.loads(path.read_text(encoding="utf-8"))
        # Foundry also writes build-info JSON, which is not a contract artifact.
        if "deployedBytecode" not in artifact:
            continue
        metadata = artifact.get("metadata")
        if not isinstance(metadata, dict):
            metadata = json.loads(artifact.get("rawMetadata", "{}"))
        targets = metadata.get("settings", {}).get("compilationTarget", {})
        if len(targets) != 1:
            raise ValueError(f"missing or ambiguous compilation target: {path}")
        source, name = next(iter(targets.items()))
        source_path = pathlib.Path(source)
        if source_path.is_absolute():
            try:
                source_path = source_path.relative_to(root)
            except ValueError:
                continue
        if not source_path.parts or source_path.parts[0] != "contracts":
            continue
        bytecode = artifact["deployedBytecode"]["object"]
        if not isinstance(bytecode, str):
            raise ValueError(f"runtime bytecode is not a string: {path}")
        bytecode = bytecode.removeprefix("0x")
        if not bytecode:
            continue  # Interfaces and abstract contracts have no runtime code.
        if len(bytecode) % 2:
            raise ValueError(f"runtime bytecode has an odd length: {path}")
        # Unlinked library placeholders occupy the same 20 bytes as an address.
        sizes.append((source_path.as_posix(), name, len(bytecode) // 2))
    if not sizes:
        raise ValueError(f"no non-empty contracts/ runtime artifacts found in {out}")
    return sorted(sizes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="Foundry artifact directory (overrides foundry.toml)")
    args = parser.parse_args(argv)
    try:
        sizes = contract_sizes(artifact_directory(ROOT_DIR, args.out), ROOT_DIR)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"Contract size check failed: {error}", file=sys.stderr)
        return 1
    print(f"EIP-170 runtime limit: {EIP170_LIMIT:,} bytes")
    width = max(len(name) for _, name, _ in sizes)
    print(f"{'Contract':<{width}}  {'Bytes':>7}  {'Margin':>7}")
    for _, name, size in sizes:
        print(f"{name:<{width}}  {size:7,d}  {EIP170_LIMIT - size:7,d}")
    offenders = [(source, name, size) for source, name, size in sizes if size > EIP170_LIMIT]
    for source, name, size in offenders:
        print(f"EIP-170 exceeded: {source}:{name}: {size:,} bytes "
              f"({size - EIP170_LIMIT:,} over limit)", file=sys.stderr)
    return 1 if offenders else 0


if __name__ == "__main__":
    sys.exit(main())
