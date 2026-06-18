#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request


def load_env_file() -> None:
    env_file = pathlib.Path(os.environ.get("HOUSEHOLD_OS_ENV_FILE", "/etc/openclaw/household-os.env"))
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    load_env_file()
    url = os.environ.get("HOUSEHOLD_OS_URL", "http://127.0.0.1:8088").rstrip("/") + "/api/command"
    token = os.environ.get("HOUSEHOLD_OS_TOKEN", "")
    payload = sys.stdin.read().strip()
    if not payload:
        print("Expected a JSON command on stdin", file=sys.stderr)
        return 2
    try:
        json.loads(payload)
    except json.JSONDecodeError as error:
        print(f"Invalid JSON: {error}", file=sys.stderr)
        return 2

    request = urllib.request.Request(
        url,
        data=payload.encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Household-Actor": "openclaw",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            print(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        print(error.read().decode("utf-8"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
