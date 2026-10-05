#!/usr/bin/env python3
"""Render the public site with Python 3.11+ and no third-party dependencies."""

import argparse
import html
import json
from pathlib import Path
import re
from string import Template
import sys
from urllib.parse import urlsplit

SITE = Path(__file__).resolve().parent
SOURCE = SITE / "src"
RELEASE_FILE = SITE / "release.json"
REPOSITORY = "https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge"
PAGES = (
    ("home", "index.html", "/", "AgentCart ShopBridge — commerce for buyer agents", "A WooCommerce plugin, direct buyer agent skill and quote-bound payment verification. Current public pilot: testnet and sandbox only."),
    ("merchants", "merchants/index.html", "/merchants/", "WooCommerce integration guide — AgentCart ShopBridge", "Install the ShopBridge WooCommerce plugin, configure a verifier and prepare for supervised Tempo Moderato testnet enrollment."),
    ("agents", "agents/index.html", "/agents/", "ShopBridge Direct buyer agent skill — AgentCart", "Download and install the service-free ShopBridge Direct skill. Discover verified merchants, compare quotes and prepare approval-safe checkout."),
    ("legal", "legal/index.html", "/legal/", "Legal notice — AgentCart", "Information pursuant to § 5 DDG and the responsible person for content pursuant to § 18 (2) MStV."),
    ("privacy", "privacy/index.html", "/privacy/", "Privacy — AgentCart", "Privacy information for agentcart.eu: hosting, transient request processing, downloads, email contact and your GDPR rights."),
    ("404", "404.html", "/404.html", "Page not found — AgentCart", "This page could not be found. Return to AgentCart or read the merchant and buyer agent guides."),
)
REQUIRED_FILES = tuple(page[1] for page in PAGES) + (
    "assets/site.css", "assets/favicon.svg", "robots.txt", "sitemap.xml",
)


def load_release(path=RELEASE_FILE):
    """Validate the single source of truth before emitting or checking pages."""
    try:
        release = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(release, dict):
            raise ValueError("expected a JSON object")
        for field in ("tag", "version", "release_url", "manifest_url"):
            if not isinstance(release.get(field), str) or not release[field]:
                raise ValueError(f"missing or invalid {field}")
        if not re.fullmatch(r"\d+\.\d+\.\d+", release["version"]):
            raise ValueError("version must be a numeric semantic version")
        tag = release["tag"]
        if tag != "v" + release["version"]:
            raise ValueError("tag must equal v + version")
        if release["release_url"] != f"{REPOSITORY}/releases/tag/{tag}":
            raise ValueError("release_url does not match tag")
        download_base = f"{REPOSITORY}/releases/download/{tag}"
        if release["manifest_url"] != f"{download_base}/agentcart-release.json":
            raise ValueError("manifest_url does not match tag")
        assets = release.get("assets")
        if not isinstance(assets, dict):
            raise ValueError("missing assets object")
        for key, name in (("plugin", "agentcart-shopbridge.zip"), ("skill", "shopbridge-direct-skill.zip")):
            asset = assets.get(key)
            if not isinstance(asset, dict):
                raise ValueError(f"missing assets.{key}")
            if asset.get("name") != name or asset.get("url") != f"{download_base}/{name}":
                raise ValueError(f"invalid assets.{key} name or download URL")
            if not isinstance(asset.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]):
                raise ValueError(f"missing or invalid assets.{key}.sha256")
            if type(asset.get("bytes")) is not int or asset["bytes"] <= 0:
                raise ValueError(f"missing or invalid assets.{key}.bytes")
        return release
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def render(path, values):
    try:
        return Template(path.read_text(encoding="utf-8")).substitute(values)
    except (OSError, KeyError, ValueError) as exc:
        raise ValueError(f"cannot render {path}: {exc}") from exc


def build(out, base_url):
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("--base-url must be an HTTPS origin, for example https://agentcart.eu")
    base_url = base_url.rstrip("/")
    out = out.resolve()
    if out == SITE or out in SITE.parents or out == SOURCE or SOURCE in out.parents:
        raise ValueError("output directory must not overwrite the repository or site sources")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"output directory must be empty: {out}")
    release = load_release()
    values = {key: html.escape(release[key], quote=True) for key in ("tag", "version", "release_url", "manifest_url")}
    values["base_url"] = html.escape(base_url, quote=True)
    for key, asset in release["assets"].items():
        for field in ("name", "url", "sha256", "bytes"):
            values[f"{key}_{field}"] = html.escape(str(asset[field]), quote=True)
    tree = {}
    for name, destination, url, title, description in PAGES:
        navigation = []
        for label, nav_url in (("Home", "/"), ("Merchants", "/merchants/"), ("Agents", "/agents/")):
            current = ' aria-current="page"' if url == nav_url else ""
            navigation.append(f'<a href="{nav_url}"{current}>{label}</a>')
        page_values = values | {
            "title": html.escape(title, quote=True),
            "description": html.escape(description, quote=True),
            "canonical": html.escape(base_url + url, quote=True),
            "navigation": "\n        ".join(navigation),
            "content": render(SOURCE / "pages" / f"{name}.html", values).rstrip(),
        }
        tree[destination] = render(SOURCE / "layout.html", page_values).encode("utf-8")
    tree["robots.txt"] = render(SOURCE / "robots.txt", values).encode("utf-8")
    entries = "\n".join(f"  <url><loc>{html.escape(base_url + page[2])}</loc></url>" for page in PAGES if page[0] != "404")
    tree["sitemap.xml"] = render(SOURCE / "sitemap.xml", values | {"entries": entries}).encode("utf-8")
    asset_dir = SOURCE / "assets"
    if not asset_dir.is_dir():
        raise ValueError(f"missing assets directory: {asset_dir}")
    for path in sorted(asset_dir.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"source assets must not be symlinks: {path}")
        if path.is_file():
            tree["assets/" + path.relative_to(asset_dir).as_posix()] = path.read_bytes()
    for name in REQUIRED_FILES:
        if name not in tree or not tree[name]:
            raise ValueError(f"missing or empty required output: {name}")
    for name, data in sorted(tree.items()):
        destination = out / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    print(f"Built {len(tree)} files in {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="empty output directory")
    parser.add_argument("--base-url", default="https://agentcart.eu", help="public HTTPS origin for canonical URLs and sitemap")
    args = parser.parse_args()
    try:
        build(args.out, args.base_url)
    except (OSError, ValueError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
