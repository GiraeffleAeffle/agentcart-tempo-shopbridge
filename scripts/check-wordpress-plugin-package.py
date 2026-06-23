#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path


MAX_WORDPRESS_ORG_ZIP_BYTES = 10 * 1024 * 1024
DEFAULT_SLUG = "agentcart-shopbridge"


def fail(message: str) -> None:
    raise AssertionError(message)


def header_value(text: str, name: str) -> str:
    match = re.search(rf"^[ \t*#]*{re.escape(name)}:\s*(.+?)\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def require_header(text: str, name: str, expected: str | None = None) -> str:
    value = header_value(text, name)
    if not value:
        fail(f"missing {name} header")
    if expected is not None and value != expected:
        fail(f"{name} header must be {expected!r}, got {value!r}")
    return value


def package_members(zip_path: Path) -> dict[str, str]:
    with zipfile.ZipFile(zip_path) as archive:
        members = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            with archive.open(info) as handle:
                members[info.filename] = handle.read().decode("utf-8", errors="replace")
        return members


def check_package(zip_path: Path, slug: str) -> None:
    if not zip_path.exists():
        fail(f"package does not exist: {zip_path}")
    size = zip_path.stat().st_size
    if size > MAX_WORDPRESS_ORG_ZIP_BYTES:
        fail(f"WordPress.org plugin ZIP must be under 10 MB, got {size} bytes")

    members = package_members(zip_path)
    names = sorted(members)
    if not names:
        fail("plugin ZIP is empty")
    for name in names:
        if not name.startswith(f"{slug}/"):
            fail(f"ZIP member must live under {slug}/: {name}")
        lowered = name.lower()
        forbidden_parts = [
            "/.git/",
            "/node_modules/",
            "/vendor/bin/",
            "/tests/",
            "/test/",
            "/.env",
            "__macosx",
            ".ds_store",
        ]
        if any(part in lowered for part in forbidden_parts):
            fail(f"ZIP contains development, platform, or secret-looking file: {name}")

    plugin_path = f"{slug}/{slug}.php"
    readme_path = f"{slug}/readme.txt"
    uninstall_path = f"{slug}/uninstall.php"
    for required in [plugin_path, readme_path, uninstall_path]:
        if required not in members:
            fail(f"ZIP missing required file: {required}")

    plugin = members[plugin_path]
    readme = members[readme_path]

    plugin_name = require_header(plugin, "Plugin Name")
    version = require_header(plugin, "Version")
    require_header(plugin, "Description")
    require_header(plugin, "Requires at least")
    require_header(plugin, "Requires PHP")
    require_header(plugin, "Requires Plugins", "woocommerce")
    require_header(plugin, "License")
    require_header(plugin, "License URI")
    require_header(plugin, "Text Domain", slug)
    if "GPL" not in header_value(plugin, "License").upper():
        fail("plugin License header must be GPL-compatible")
    if "defined('ABSPATH')" not in plugin and 'defined("ABSPATH")' not in plugin:
        fail("plugin entrypoint must guard direct access with ABSPATH")

    readme_title_match = re.search(r"^===\s+(.+?)\s+===$", readme, re.MULTILINE)
    if not readme_title_match:
        fail("readme.txt missing WordPress.org title line")
    if readme_title_match.group(1).strip() != plugin_name:
        fail("readme title should match plugin header Plugin Name")

    contributors = require_header(readme, "Contributors")
    if not re.fullmatch(r"[a-z0-9_, -]+", contributors):
        fail("Contributors should contain WordPress.org usernames only")
    tags = [tag.strip() for tag in require_header(readme, "Tags").split(",") if tag.strip()]
    if not 1 <= len(tags) <= 5:
        fail("readme Tags must contain 1 to 5 comma-separated terms")
    if any(" " in tag for tag in tags):
        fail("readme tags should be slug-like terms without spaces")
    require_header(readme, "Requires at least", header_value(plugin, "Requires at least"))
    require_header(readme, "Requires PHP", header_value(plugin, "Requires PHP"))
    require_header(readme, "Requires Plugins", "woocommerce")
    stable_tag = require_header(readme, "Stable tag")
    if stable_tag != version:
        fail(f"readme Stable tag must match plugin Version: {stable_tag!r} != {version!r}")
    require_header(readme, "License", header_value(plugin, "License"))
    require_header(readme, "License URI", header_value(plugin, "License URI"))
    if "== External Services ==" not in readme:
        fail("readme.txt must document external service calls")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the ShopBridge ZIP before WordPress.org submission.")
    parser.add_argument("--zip", default="dist/agentcart-shopbridge.zip", help="Plugin ZIP to check.")
    parser.add_argument("--slug", default=DEFAULT_SLUG, help="Expected plugin slug/folder.")
    args = parser.parse_args()

    try:
        check_package(Path(args.zip), args.slug)
    except (AssertionError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        print(f"wordpress plugin package check failed: {exc}", file=sys.stderr)
        return 1
    print(f"wordpress plugin package check ok: {args.zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
