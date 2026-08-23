#!/usr/bin/env python3
"""Copy one OCI image manifest to a registry with bounded upload requests.

ORAS may upload a whole layer in one HTTP request. This helper uses the
Distribution API's resumable PATCH flow so slow private tunnels and object
storage backends do not need to keep a large request alive.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import pathlib
import re
import socket
import sys
import tarfile
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, BinaryIO


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REPOSITORY_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*$")
TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class Descriptor:
    digest: str
    size: int
    media_type: str


class RegistryError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout-tar", type=pathlib.Path, required=True)
    parser.add_argument("--manifest-digest", required=True)
    parser.add_argument("--registry", required=True, help="Registry origin, for example http://127.0.0.1:5000")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--chunk-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--request-timeout-seconds", type=int, default=600)
    parser.add_argument("--max-chunk-retries", type=int, default=4)
    return parser.parse_args()


def validate_options(args: argparse.Namespace) -> urllib.parse.ParseResult:
    if not args.layout_tar.is_file() or args.layout_tar.is_symlink():
        raise RegistryError("--layout-tar must be a regular non-symlink file")
    if not DIGEST_RE.fullmatch(args.manifest_digest):
        raise RegistryError("--manifest-digest must be sha256:<64 lowercase hex characters>")
    if not REPOSITORY_RE.fullmatch(args.repository):
        raise RegistryError("--repository is invalid")
    if not TAG_RE.fullmatch(args.tag):
        raise RegistryError("--tag is invalid")
    if args.chunk_bytes < 64 * 1024 or args.chunk_bytes > 4 * 1024 * 1024:
        raise RegistryError("--chunk-bytes must be between 65536 and 4194304")
    if args.request_timeout_seconds < 30 or args.request_timeout_seconds > 1800:
        raise RegistryError("--request-timeout-seconds must be between 30 and 1800")
    if args.max_chunk_retries < 0 or args.max_chunk_retries > 10:
        raise RegistryError("--max-chunk-retries must be between 0 and 10")
    parsed = urllib.parse.urlparse(args.registry.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path not in {"", "/"}:
        raise RegistryError("--registry must be an HTTP(S) origin without a path")
    if parsed.username or parsed.password:
        raise RegistryError("registry credentials must not be placed in the URL")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise RegistryError("plain HTTP is allowed only for a loopback registry tunnel")
    return parsed


def member_name(digest: str) -> str:
    algorithm, value = digest.split(":", 1)
    return f"blobs/{algorithm}/{value}"


def read_member(archive: tarfile.TarFile, digest: str) -> tuple[tarfile.TarInfo, BinaryIO]:
    try:
        member = archive.getmember(member_name(digest))
    except KeyError as exc:
        raise RegistryError(f"OCI layout is missing {digest}") from exc
    stream = archive.extractfile(member)
    if stream is None or not member.isfile():
        raise RegistryError(f"OCI layout member for {digest} is not a regular file")
    return member, stream


def manifest_and_descriptors(layout_tar: pathlib.Path, manifest_digest: str) -> tuple[bytes, str, list[Descriptor]]:
    with tarfile.open(layout_tar, mode="r") as archive:
        member, stream = read_member(archive, manifest_digest)
        manifest_bytes = stream.read()
    if len(manifest_bytes) != member.size:
        raise RegistryError("manifest size differs from the OCI layout")
    if f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}" != manifest_digest:
        raise RegistryError("manifest digest differs from --manifest-digest")
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as exc:
        raise RegistryError("manifest is invalid JSON") from exc
    if not isinstance(manifest, dict):
        raise RegistryError("manifest must be a JSON object")
    media_type = str(manifest.get("mediaType") or "")
    config = manifest.get("config")
    layers = manifest.get("layers")
    if not media_type or not isinstance(config, dict) or not isinstance(layers, list):
        raise RegistryError("manifest must contain mediaType, config, and layers")
    raw_descriptors = [config, *layers]
    descriptors: list[Descriptor] = []
    for raw in raw_descriptors:
        if not isinstance(raw, dict):
            raise RegistryError("manifest descriptor must be an object")
        digest = str(raw.get("digest") or "")
        size = raw.get("size")
        descriptor_media_type = str(raw.get("mediaType") or "")
        if not DIGEST_RE.fullmatch(digest) or isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise RegistryError("manifest descriptor is invalid")
        descriptors.append(Descriptor(digest, size, descriptor_media_type))
    return manifest_bytes, media_type, descriptors


def verify_layout_blobs(layout_tar: pathlib.Path, descriptors: list[Descriptor]) -> None:
    with tarfile.open(layout_tar, mode="r") as archive:
        for descriptor in descriptors:
            member, stream = read_member(archive, descriptor.digest)
            digest = hashlib.sha256()
            size = 0
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
            if size != descriptor.size or member.size != descriptor.size:
                raise RegistryError(f"blob size differs for {descriptor.digest}")
            if f"sha256:{digest.hexdigest()}" != descriptor.digest:
                raise RegistryError(f"blob digest differs for {descriptor.digest}")


class RegistryClient:
    def __init__(
        self,
        origin: urllib.parse.ParseResult,
        repository: str,
        *,
        request_timeout_seconds: int,
    ) -> None:
        self.origin = origin
        self.repository = repository
        self.port = origin.port or (443 if origin.scheme == "https" else 80)
        self.connection_type = (
            http.client.HTTPSConnection if origin.scheme == "https" else http.client.HTTPConnection
        )
        self.request_timeout_seconds = request_timeout_seconds

    def request(
        self,
        method: str,
        target: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        expected: set[int],
    ) -> http.client.HTTPResponse:
        parsed = urllib.parse.urlparse(urllib.parse.urljoin(self.registry_origin(), target))
        if (parsed.scheme, parsed.hostname, parsed.port or self.default_port()) != (
            self.origin.scheme,
            self.origin.hostname,
            self.origin.port or self.default_port(),
        ):
            raise RegistryError("registry returned a cross-origin upload location")
        request_target = urllib.parse.urlunparse(("", "", parsed.path, parsed.params, parsed.query, ""))
        connection = self.connection_type(
            self.origin.hostname,
            self.port,
            timeout=self.request_timeout_seconds,
        )
        try:
            connection.request(method, request_target, body=body, headers=headers or {})
            response = connection.getresponse()
            response_body = response.read(1024 * 1024)
        finally:
            connection.close()
        if response.status not in expected:
            raise RegistryError(
                f"registry {method} {parsed.path} returned {response.status}: "
                f"{response_body.decode('utf-8', errors='replace')[:500]}"
            )
        return response

    def default_port(self) -> int:
        return 443 if self.origin.scheme == "https" else 80

    def registry_origin(self) -> str:
        return urllib.parse.urlunparse(
            (self.origin.scheme, self.origin.netloc, "/", "", "", "")
        )

    def blob_path(self, digest: str) -> str:
        return f"/v2/{self.repository}/blobs/{digest}"

    def has_blob(self, digest: str) -> bool:
        response = self.request("HEAD", self.blob_path(digest), expected={200, 404})
        return response.status == 200

    def start_upload(self) -> str:
        response = self.request(
            "POST",
            f"/v2/{self.repository}/blobs/uploads/",
            body=b"",
            headers={"Content-Length": "0"},
            expected={202},
        )
        location = response.getheader("Location")
        if not location:
            raise RegistryError("registry did not return an upload Location")
        return location

    def patch_chunk(self, location: str, chunk: bytes, offset: int) -> str:
        response = self.request(
            "PATCH",
            location,
            body=chunk,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(chunk)),
                "Content-Range": f"{offset}-{offset + len(chunk) - 1}",
            },
            expected={202},
        )
        next_location = response.getheader("Location")
        if not next_location:
            raise RegistryError("registry did not return the next upload Location")
        return next_location

    def upload_offset(self, location: str) -> tuple[str, int]:
        response = self.request("GET", location, expected={204})
        next_location = response.getheader("Location") or location
        supplied_range = str(response.getheader("Range") or "")
        matched = re.fullmatch(r"(?:bytes=)?0-([0-9]+)", supplied_range)
        if not matched:
            return next_location, 0
        # Distribution uses 0-0 for a new, empty upload as well as byte-range
        # syntax. Callers only use status after a failed non-empty PATCH, so a
        # reported end at or beyond the attempted offset is an accepted byte.
        range_end = int(matched.group(1))
        return next_location, 0 if range_end == 0 else range_end + 1

    def finish_upload(self, location: str, digest: str) -> None:
        parsed = urllib.parse.urlparse(urllib.parse.urljoin(self.registry_origin(), location))
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query.append(("digest", digest))
        target = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
        self.request(
            "PUT",
            target,
            body=b"",
            headers={"Content-Length": "0", "Content-Type": "application/octet-stream"},
            expected={201},
        )

    def put_manifest(self, tag: str, manifest: bytes, media_type: str, expected_digest: str) -> None:
        response = self.request(
            "PUT",
            f"/v2/{self.repository}/manifests/{tag}",
            body=manifest,
            headers={"Content-Type": media_type, "Content-Length": str(len(manifest))},
            expected={201},
        )
        supplied = str(response.getheader("Docker-Content-Digest") or "")
        if supplied and supplied != expected_digest:
            raise RegistryError("registry manifest digest differs")
        verified = self.request(
            "HEAD",
            f"/v2/{self.repository}/manifests/{tag}",
            headers={"Accept": media_type},
            expected={200},
        )
        if str(verified.getheader("Docker-Content-Digest") or "") != expected_digest:
            raise RegistryError("published manifest digest could not be verified")


def upload_blob(
    client: RegistryClient,
    archive: tarfile.TarFile,
    descriptor: Descriptor,
    *,
    chunk_bytes: int,
    max_chunk_retries: int,
) -> None:
    if client.has_blob(descriptor.digest):
        print(f"exists {descriptor.digest} {descriptor.size}", file=sys.stderr)
        return
    _member, stream = read_member(archive, descriptor.digest)
    location = client.start_upload()
    offset = 0
    while chunk := stream.read(chunk_bytes):
        for attempt in range(max_chunk_retries + 1):
            try:
                location = client.patch_chunk(location, chunk, offset)
                break
            except (RegistryError, OSError, TimeoutError, socket.timeout) as exc:
                if attempt >= max_chunk_retries:
                    raise RegistryError(
                        f"chunk at offset {offset} failed after {attempt + 1} attempts: {exc}"
                    ) from exc
                time.sleep(min(2**attempt, 8))
                try:
                    status_location, accepted_offset = client.upload_offset(location)
                except (OSError, RegistryError):
                    accepted_offset = offset
                    status_location = location
                if accepted_offset == offset + len(chunk):
                    location = status_location
                    break
                if accepted_offset != offset:
                    raise RegistryError(
                        f"registry reported unexpected upload offset {accepted_offset}; expected {offset}"
                    ) from exc
                location = status_location
        offset += len(chunk)
        print(f"upload {descriptor.digest} {offset}/{descriptor.size}", file=sys.stderr)
    if offset != descriptor.size:
        raise RegistryError(f"uploaded size differs for {descriptor.digest}")
    client.finish_upload(location, descriptor.digest)
    if not client.has_blob(descriptor.digest):
        raise RegistryError(f"registry did not retain {descriptor.digest}")


def main() -> int:
    args = parse_args()
    origin = validate_options(args)
    manifest, media_type, descriptors = manifest_and_descriptors(
        args.layout_tar, args.manifest_digest
    )
    verify_layout_blobs(args.layout_tar, descriptors)
    client = RegistryClient(
        origin,
        args.repository,
        request_timeout_seconds=args.request_timeout_seconds,
    )
    with tarfile.open(args.layout_tar, mode="r") as archive:
        for descriptor in descriptors:
            upload_blob(
                client,
                archive,
                descriptor,
                chunk_bytes=args.chunk_bytes,
                max_chunk_retries=args.max_chunk_retries,
            )
    client.put_manifest(args.tag, manifest, media_type, args.manifest_digest)
    print(
        json.dumps(
            {
                "schema": "agentcart.oci_registry_publish_receipt.v1",
                "registry": args.registry.rstrip("/"),
                "repository": args.repository,
                "tag": args.tag,
                "manifest_digest": args.manifest_digest,
                "blob_count": len(descriptors),
                "chunk_bytes": args.chunk_bytes,
                "request_timeout_seconds": args.request_timeout_seconds,
                "max_chunk_retries": args.max_chunk_retries,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegistryError, OSError, tarfile.TarError, ValueError) as exc:
        print(f"push-oci-layout-resumable: {exc}", file=sys.stderr)
        raise SystemExit(1)
