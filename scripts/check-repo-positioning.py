#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]

ENTRY_DOCS = [
    ROOT / "README.md",
    ROOT / "woocommerce-shopbridge" / "README.md",
    ROOT / "deploy" / "home-server" / "README.md",
    ROOT / "docs" / "REPO_STRATEGY.md",
]

FORBIDDEN_ENTRY_PATTERNS = [
    re.compile(r"\bhackathon\b", re.IGNORECASE),
    re.compile(r"\bjudge(?:s|d|ment)?\b", re.IGNORECASE),
    re.compile(r"\bpitch\b", re.IGNORECASE),
    re.compile(r"\bdevpost\b", re.IGNORECASE),
]


def line_errors(path: pathlib.Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for index, line in enumerate(text.splitlines(), start=1):
        for pattern in FORBIDDEN_ENTRY_PATTERNS:
            if pattern.search(line):
                errors.append(f"{path.relative_to(ROOT)}:{index}: public entry doc uses event-era language: {line.strip()}")
    return errors


def main() -> int:
    errors: list[str] = []
    for path in ENTRY_DOCS:
        if not path.exists():
            errors.append(f"missing entry doc: {path.relative_to(ROOT)}")
            continue
        errors.extend(line_errors(path))

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for required in [
        "production-candidate alpha",
        "ShopBridge is an agent-commerce bridge",
        "direct ShopBridge skill",
        "external beta evidence gate",
    ]:
        if required not in readme:
            errors.append(f"README.md must keep production positioning phrase: {required}")

    strategy = (ROOT / "docs" / "REPO_STRATEGY.md").read_text(encoding="utf-8")
    for required in [
        "merchant plugin should become independently releasable",
        "direct skill path",
        "Split Criteria",
    ]:
        if required not in strategy:
            errors.append(f"docs/REPO_STRATEGY.md must keep production strategy phrase: {required}")

    if errors:
        for error in errors:
            print(f"repo positioning check failed: {error}", file=sys.stderr)
        return 1
    print("repo positioning check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
