#!/usr/bin/env python3
"""Check a built public site without fetching URLs or using dependencies."""

import argparse
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urljoin, urlsplit
import xml.etree.ElementTree as ET

# Import shared release validation without creating files in the source tree.
sys.dont_write_bytecode = True
from build import PAGES, REQUIRED_FILES, load_release

FORBIDDEN = re.compile(r"hackathon|judge|pitch|devpost", re.IGNORECASE)
VERSION = re.compile(r"(?<![\w.])v?(\d+\.\d+\.\d+)(?![\w.])")
SHA256 = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
LOAD_TAGS = {"script", "img", "iframe", "source", "object", "embed", "audio", "video", "track", "image", "use"}


class Page(HTMLParser):
    def __init__(self, name, errors):
        super().__init__(convert_charrefs=True)
        self.name = name
        self.errors = errors
        self.stack = []
        self.references = []
        self.ids = set()
        self.lang = None
        self.title = []
        self.descriptions = []
        self.canonicals = []
        self.h1_count = 0
        self.markers = []
        self.active_markers = []

    def fail(self, message):
        self.errors.append(f"{self.name}: {message}")

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        in_svg = tag == "svg" or "svg" in self.stack
        if in_svg:
            if tag in {"script", "style", "foreignobject"}:
                self.fail(f"forbidden SVG <{tag}> element")
            # Inspect every attribute, including duplicates, before dict conversion
            # can hide an earlier value that a browser would use.
            for key, value in attrs:
                if key in {"href", "xlink:href"} and (not value or not value.startswith("#")):
                    self.fail("SVG references must be same-document # fragments")
        if tag in {"script", "style", "base"}:
            self.fail(f"forbidden <{tag}> element")
        if "style" in attributes:
            self.fail("inline style attribute")
        if any(key.startswith("on") for key, _ in attrs):
            self.fail("inline event handler")
        if tag == "html":
            self.lang = attributes.get("lang")
        if tag == "h1":
            self.h1_count += 1
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        if tag == "meta" and (attributes.get("name") or "").lower() == "description":
            self.descriptions.append(attributes.get("content", ""))
        rel = (attributes.get("rel") or "").lower().split()
        if tag == "link" and "canonical" in rel:
            self.canonicals.append(attributes.get("href", ""))
        for key in ("href", "src", "data", "poster", "xlink:href"):
            value = attributes.get(key)
            if not value:
                continue
            resource = (tag in LOAD_TAGS or (tag == "link" and rel != ["canonical"])) and not (in_svg and value.startswith("#"))
            self.references.append((value, resource, tag))
        srcset = attributes.get("srcset")
        if srcset:
            for candidate in srcset.split(","):
                parts = candidate.split()
                if parts:
                    self.references.append((parts[0], True, tag))
        for kind in ("version", "asset", "sha256", "bytes"):
            key = f"data-release-{kind}"
            if key in attributes:
                marker = {"kind": kind, "key": attributes[key], "href": attributes.get("href"), "text": [], "depth": len(self.stack)}
                self.markers.append(marker)
                if tag not in VOID:
                    self.active_markers.append(marker)
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            self.stack = self.stack[:index]
            self.active_markers = [marker for marker in self.active_markers if marker["depth"] < index]

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if "title" in self.stack and "svg" not in self.stack:
            self.title.append(data)
        for marker in self.active_markers:
            marker["text"].append(data)


def local_target(root, page_name, value, origin):
    """Resolve root, relative and same-origin links, keeping paths in DIR."""
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in {"http", "https"} or parsed.netloc != urlsplit(origin).netloc:
            return None
    page_url = "/" + page_name
    path = unquote(urlsplit(urljoin(origin + page_url, value)).path)
    relative = path.lstrip("/")
    if path.endswith("/"):
        relative += "index.html"
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"internal URL escapes the output directory: {value}")
    return target


def check(root):
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"not an output directory: {root}")
    release = load_release()
    errors = []
    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            errors.append(f"missing required file: {name}")
    pages = {}
    files = sorted(root.rglob("*"))
    for path in files:
        if path.is_symlink():
            errors.append(f"symlinks are not allowed: {path.relative_to(root)}")
            continue
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        if FORBIDDEN.search(data.decode("utf-8", errors="replace")):
            errors.append(f"{name}: forbidden wording")
        if path.suffix != ".html":
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{name}: HTML must be UTF-8")
            continue
        page = Page(name, errors)
        page.feed(text)
        page.close()
        pages[name] = page
        if page.lang != "en":
            page.fail('missing <html lang="en">')
        if not "".join(page.title).strip():
            page.fail("missing or empty <title>")
        if len(page.descriptions) != 1 or not page.descriptions[0].strip():
            page.fail("missing or empty meta description")
        if len(page.canonicals) != 1 or not page.canonicals[0].strip():
            page.fail("missing canonical link")
        if page.h1_count != 1:
            page.fail("expected exactly one h1")
        for match in VERSION.finditer(text):
            if match.group(1) != release["version"]:
                page.fail(f"release version differs from release.json: {match.group(0)}")
        allowed_hashes = {asset["sha256"] for asset in release["assets"].values()}
        for match in SHA256.finditer(text):
            if match.group(0) not in allowed_hashes:
                page.fail("SHA-256 differs from release.json")
        versions = [marker for marker in page.markers if marker["kind"] == "version"]
        if not versions:
            page.fail("missing release version metadata")
        for marker in page.markers:
            kind, key = marker["kind"], marker["key"]
            value = "".join(marker["text"]).strip()
            if kind == "version":
                if key != release["version"] or value != release["version"]:
                    page.fail("release version differs from release.json")
            elif key not in release["assets"]:
                page.fail(f"unknown release asset: {key}")
            else:
                asset = release["assets"][key]
                if kind == "asset" and (marker["href"] != asset["url"] or asset["name"] not in value):
                    page.fail(f"{key} download differs from release.json")
                if kind == "sha256" and value != asset["sha256"]:
                    page.fail(f"{key} SHA-256 differs from release.json")
                if kind == "bytes" and value != f'{asset["bytes"]} bytes':
                    page.fail(f"{key} size differs from release.json")
        allowed_downloads = {release["manifest_url"]} | {asset["url"] for asset in release["assets"].values()}
        for value, _, _ in page.references:
            if "/releases/download/" in value or urlsplit(value).path.endswith(".zip"):
                if value not in allowed_downloads:
                    page.fail(f"download URL differs from release.json: {value}")
            if "/releases/tag/" in value and value != release["release_url"]:
                page.fail(f"release URL differs from release.json: {value}")
    for name, key in (("merchants/index.html", "plugin"), ("agents/index.html", "skill")):
        page = pages.get(name)
        if page:
            for kind in ("asset", "sha256", "bytes"):
                if not any(marker["kind"] == kind and marker["key"] == key for marker in page.markers):
                    page.fail(f"missing {key} release {kind}")
    home = pages.get("index.html")
    origin = "https://agentcart.eu"
    if home and len(home.canonicals) == 1:
        parsed = urlsplit(home.canonicals[0])
        if parsed.scheme != "https" or not parsed.netloc or parsed.path != "/" or parsed.query or parsed.fragment:
            home.fail("home canonical must be an HTTPS origin with a trailing slash")
        else:
            origin = f"{parsed.scheme}://{parsed.netloc}"
    expected_paths = {page[1]: page[2] for page in PAGES}
    for name, page in pages.items():
        if name in expected_paths and page.canonicals != [origin + expected_paths[name]]:
            page.fail("canonical URL does not match the page path and site origin")
        for value, resource, tag in page.references:
            parsed = urlsplit(value)
            # Even same-origin absolute loads are rejected: assets must be /assets/ URLs.
            if resource and (parsed.scheme or parsed.netloc):
                page.fail(f"non-local resource on <{tag}>: {value}")
            if parsed.scheme and parsed.scheme not in {"https", "http", "mailto", "tel"}:
                page.fail(f"forbidden URL scheme: {parsed.scheme}")
            try:
                target = local_target(root, name, value, origin)
            except ValueError as exc:
                page.fail(str(exc))
                continue
            if target is None:
                continue
            if not target.is_file():
                page.fail(f"unresolved internal URL: {value}")
                continue
            target_name = target.relative_to(root).as_posix()
            if target_name in pages and parsed.fragment and unquote(parsed.fragment) not in pages[target_name].ids:
                page.fail(f"unresolved internal fragment: {value}")
            if resource and not value.startswith("/assets/"):
                page.fail(f"asset URL must start with /assets/: {value}")
    for path in files:
        if not path.is_file() or path.is_symlink():
            continue
        name = path.relative_to(root).as_posix()
        if path.suffix == ".css":
            css = path.read_text(encoding="utf-8")
            if re.search(r"@import\b", css, re.IGNORECASE):
                errors.append(f"{name}: CSS imports are not allowed")
            for match in re.finditer(r"url\(\s*['\"]?([^)'\"\s]+)", css, re.IGNORECASE):
                value = match.group(1)
                if not value.startswith("/assets/") or not (root / unquote(urlsplit(value).path).lstrip("/")).is_file():
                    errors.append(f"{name}: non-local or missing CSS resource: {value}")
        if path.suffix == ".svg":
            try:
                svg = ET.fromstring(path.read_bytes())
                for element in svg.iter():
                    if element.tag.rsplit("}", 1)[-1] in {"script", "style", "foreignObject"}:
                        errors.append(f"{name}: forbidden SVG element")
                    for key, value in element.attrib.items():
                        key = key.rsplit("}", 1)[-1]
                        if key == "style" or key.lower().startswith("on"):
                            errors.append(f"{name}: inline SVG styling or handler")
                        if key in {"href", "src"} and not value.startswith("#"):
                            errors.append(f"{name}: SVG resource references are not allowed")
            except ET.ParseError as exc:
                errors.append(f"{name}: invalid SVG: {exc}")
    sitemap = root / "sitemap.xml"
    if sitemap.is_file():
        try:
            document = ET.fromstring(sitemap.read_bytes())
            urls = [node.text for node in document.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
            expected = [origin + page[2] for page in PAGES if page[0] != "404"]
            if urls != expected:
                errors.append("sitemap.xml: URLs do not match the public pages")
        except ET.ParseError as exc:
            errors.append(f"sitemap.xml: invalid XML: {exc}")
    robots = root / "robots.txt"
    if robots.is_file() and f"Sitemap: {origin}/sitemap.xml" not in robots.read_text(encoding="utf-8"):
        errors.append("robots.txt: missing or inconsistent sitemap URL")
    if errors:
        raise ValueError("\n".join(errors))
    print(f"Checked {len(pages)} HTML pages and {sum(path.is_file() for path in files)} files: OK")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="built static tree")
    args = parser.parse_args()
    try:
        check(args.directory)
    except (OSError, ValueError) as exc:
        print(f"Check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
