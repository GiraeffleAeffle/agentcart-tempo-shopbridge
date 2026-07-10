#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys


TITLE_RE = re.compile(
    r"^(?P<type>feat|fix|perf|refactor|docs|style|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[a-z0-9][a-z0-9._/-]*)\))?"
    r"(?P<breaking>!)?: (?P<summary>[^\r\n]{1,100})$"
)
RELEASE_TYPES = {"feat": "minor", "fix": "patch", "perf": "patch", "revert": "patch"}


def validate_title(title: str) -> tuple[list[str], str]:
    value = str(title or "").strip()
    errors: list[str] = []
    if len(value) > 120:
        errors.append("PR title must be at most 120 characters")
    match = TITLE_RE.fullmatch(value)
    if not match:
        errors.append(
            "PR title must use conventional syntax, for example "
            "'feat(skill): add direct checkout' or 'fix(release): publish artifacts'"
        )
        return errors, "invalid"
    summary = match.group("summary")
    if summary.endswith("."):
        errors.append("PR title summary must not end with a period")
    if summary[0].isupper():
        errors.append("PR title summary must start with a lowercase character")
    if match.group("breaking"):
        return errors, "major"
    return errors, RELEASE_TYPES.get(match.group("type"), "none")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a squash-merge-safe conventional PR title.")
    parser.add_argument("--title", default=os.getenv("PR_TITLE", ""), help="PR title; defaults to PR_TITLE.")
    args = parser.parse_args(argv)
    errors, release = validate_title(args.title)
    if errors:
        for error in errors:
            print(f"PR title check failed: {error}", file=sys.stderr)
        return 1
    print(f"PR title ok (semantic-release impact: {release})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
