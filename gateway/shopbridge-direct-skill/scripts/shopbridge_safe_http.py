"""Bounded, redirect-free HTTP JSON transport for ShopBridge discovery.

Merchant and registry URLs are untrusted inputs. Public requests resolve every
address before connecting, reject non-global targets, and pin the connection to
the accepted DNS result so a second lookup cannot rebind it to a private host.
Local HTTP is available only through the caller's explicit ``allow_private``
opt-in for development fixtures.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import ssl
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable


DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024
DEFAULT_MAX_REQUEST_BYTES = 1024 * 1024
Resolver = Callable[..., list[tuple[int, int, int, str, tuple[Any, ...]]]]


class SafeHttpError(RuntimeError):
    def __init__(self, code: str, *, status: int = 0, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class SafeTarget:
    url: urllib.parse.SplitResult
    hostname: str
    port: int
    addresses: tuple[tuple[int, int, int, tuple[Any, ...]], ...]


def _global_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global


def resolve_safe_target(
    raw_url: str,
    *,
    allow_private: bool = False,
    resolver: Resolver = socket.getaddrinfo,
) -> SafeTarget:
    try:
        parsed = urllib.parse.urlsplit(str(raw_url or ""))
        port = parsed.port
    except ValueError as exc:
        raise SafeHttpError("url_invalid", detail=str(exc)) from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise SafeHttpError("url_invalid")
    if parsed.username or parsed.password:
        raise SafeHttpError("url_userinfo_forbidden")
    if not allow_private and parsed.scheme != "https":
        raise SafeHttpError("url_requires_https")
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise SafeHttpError("url_hostname_invalid", detail=str(exc)) from exc
    port = port or (443 if parsed.scheme == "https" else 80)
    try:
        resolved = resolver(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise SafeHttpError("dns_resolution_failed", detail=str(exc)) from exc

    addresses: list[tuple[int, int, int, tuple[Any, ...]]] = []
    seen: set[tuple[int, str, int]] = set()
    for family, socktype, protocol, _canonical, sockaddr in resolved:
        if family not in {socket.AF_INET, socket.AF_INET6} or not sockaddr:
            continue
        address = str(sockaddr[0])
        key = (family, address, int(sockaddr[1]))
        if key in seen:
            continue
        seen.add(key)
        if not allow_private and not _global_address(address):
            raise SafeHttpError("url_private_address_forbidden")
        addresses.append((family, socktype or socket.SOCK_STREAM, protocol, sockaddr))
    if not addresses:
        raise SafeHttpError("dns_address_missing")
    return SafeTarget(parsed, hostname, port, tuple(addresses))


def _connect(addresses: tuple[tuple[int, int, int, tuple[Any, ...]], ...], timeout: float) -> socket.socket:
    last_error: OSError | None = None
    for family, socktype, protocol, sockaddr in addresses:
        connection = socket.socket(family, socktype, protocol)
        try:
            connection.settimeout(timeout)
            connection.connect(sockaddr)
            return connection
        except OSError as exc:
            last_error = exc
            connection.close()
    raise SafeHttpError("connection_failed", detail=str(last_error or "no resolved address connected"))


class _PinnedHttpConnection(http.client.HTTPConnection):
    def __init__(self, target: SafeTarget, *, timeout: float) -> None:
        super().__init__(target.hostname, target.port, timeout=timeout)
        self._pinned_addresses = target.addresses

    def connect(self) -> None:
        self.sock = _connect(self._pinned_addresses, float(self.timeout or 0))


class _PinnedHttpsConnection(http.client.HTTPSConnection):
    def __init__(self, target: SafeTarget, *, timeout: float) -> None:
        super().__init__(
            target.hostname,
            target.port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._pinned_addresses = target.addresses

    def connect(self) -> None:
        raw_socket = _connect(self._pinned_addresses, float(self.timeout or 0))
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except BaseException:
            raw_socket.close()
            raise


def _request_target(parsed: urllib.parse.SplitResult) -> str:
    path = urllib.parse.quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
    query = urllib.parse.quote(parsed.query, safe="=&?/:;+,%@[]!$'()*-._~")
    return f"{path}?{query}" if query else path


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: Any = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 30,
    allow_private: bool = False,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    resolver: Resolver = socket.getaddrinfo,
) -> Any:
    normalized_method = str(method or "GET").upper()
    if normalized_method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise SafeHttpError("method_unsupported")
    if timeout_seconds <= 0 or timeout_seconds > 120:
        raise SafeHttpError("timeout_invalid")
    if max_response_bytes < 1 or max_request_bytes < 1:
        raise SafeHttpError("size_limit_invalid")
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    if body is not None and len(body) > max_request_bytes:
        raise SafeHttpError("request_too_large")

    target = resolve_safe_target(url, allow_private=allow_private, resolver=resolver)
    connection_type = _PinnedHttpsConnection if target.url.scheme == "https" else _PinnedHttpConnection
    connection = connection_type(target, timeout=timeout_seconds)
    request_headers = {"Accept": "application/json", "Connection": "close", **(headers or {})}
    if body is not None and not any(name.lower() == "content-type" for name in request_headers):
        request_headers["Content-Type"] = "application/json"
    try:
        connection.request(
            normalized_method,
            _request_target(target.url),
            body=body,
            headers=request_headers,
        )
        response = connection.getresponse()
        declared_length = response.getheader("Content-Length")
        if declared_length:
            try:
                if int(declared_length) > max_response_bytes:
                    raise SafeHttpError("response_too_large", status=response.status)
            except ValueError as exc:
                raise SafeHttpError("content_length_invalid", status=response.status) from exc
        raw = response.read(max_response_bytes + 1)
        if len(raw) > max_response_bytes:
            raise SafeHttpError("response_too_large", status=response.status)
        if 300 <= response.status < 400:
            raise SafeHttpError("redirect_forbidden", status=response.status)
        if response.status < 200 or response.status >= 300:
            raise SafeHttpError(
                "upstream_http_error",
                status=response.status,
                detail=raw.decode("utf-8", errors="replace")[:4096],
            )
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SafeHttpError("response_json_invalid", status=response.status, detail=str(exc)) from exc
    except SafeHttpError:
        raise
    except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
        raise SafeHttpError("request_failed", detail=str(exc)) from exc
    finally:
        connection.close()


def fetch_json_object(
    url: str,
    *,
    timeout_seconds: float = 30,
    allow_private: bool = False,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    value = request_json(
        url,
        timeout_seconds=timeout_seconds,
        allow_private=allow_private,
        max_response_bytes=max_response_bytes,
    )
    if not isinstance(value, dict):
        raise SafeHttpError("response_json_object_required")
    return value
