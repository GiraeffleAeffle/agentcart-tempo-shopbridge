from __future__ import annotations

import importlib.util
import json
import pathlib
import socket
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "shopbridge-direct-skill" / "scripts" / "shopbridge_safe_http.py"
SPEC = importlib.util.spec_from_file_location("shopbridge_safe_http_test", MODULE_PATH)
safe_http = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["shopbridge_safe_http_test"] = safe_http
SPEC.loader.exec_module(safe_http)


class SafeHttpHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1/private")
            self.end_headers()
            return
        if self.path == "/large":
            body = json.dumps({"value": "x" * 2048}).encode("utf-8")
        else:
            body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        return


class ShopBridgeSafeHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), SafeHttpHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def local_url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.server.server_port}{path}"

    def test_public_resolution_rejects_every_non_global_address(self) -> None:
        def private_resolver(*_args: object, **_kwargs: object):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

        with self.assertRaises(safe_http.SafeHttpError) as raised:
            safe_http.resolve_safe_target(
                "https://registry.example/records.json",
                resolver=private_resolver,
            )

        self.assertEqual(raised.exception.code, "url_private_address_forbidden")

    def test_public_resolution_is_retained_as_the_pinned_connection_target(self) -> None:
        def public_resolver(*_args: object, **_kwargs: object):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

        target = safe_http.resolve_safe_target(
            "https://registry.example/records.json",
            resolver=public_resolver,
        )

        self.assertEqual(target.hostname, "registry.example")
        self.assertEqual(target.addresses[0][3], ("93.184.216.34", 443))

    def test_local_transport_requires_opt_in(self) -> None:
        with self.assertRaises(safe_http.SafeHttpError) as raised:
            safe_http.fetch_json_object(self.local_url("/ok"))
        self.assertEqual(raised.exception.code, "url_requires_https")

        result = safe_http.fetch_json_object(self.local_url("/ok"), allow_private=True)
        self.assertEqual(result, {"ok": True})

    def test_redirects_are_rejected_instead_of_followed(self) -> None:
        with self.assertRaises(safe_http.SafeHttpError) as raised:
            safe_http.fetch_json_object(self.local_url("/redirect"), allow_private=True)

        self.assertEqual(raised.exception.code, "redirect_forbidden")
        self.assertEqual(raised.exception.status, 302)

    def test_response_limit_is_enforced_before_json_parsing(self) -> None:
        with self.assertRaises(safe_http.SafeHttpError) as raised:
            safe_http.fetch_json_object(
                self.local_url("/large"),
                allow_private=True,
                max_response_bytes=256,
            )

        self.assertEqual(raised.exception.code, "response_too_large")


if __name__ == "__main__":
    unittest.main()
