#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


def request_json(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str = "",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], Any]:
    body = None
    request_headers = {"Accept": "application/json"}
    if token:
        request_headers["X-AgentCart-Token"] = token
    if payload is not None:
        body = json.dumps(payload).encode()
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    request = urllib.request.Request(base_url.rstrip("/") + path, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, dict(response.headers), json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        parsed = json.loads(raw) if raw else {"error": f"HTTP {exc.code}"}
        return exc.code, dict(exc.headers), parsed


def money(cents: int, currency: str) -> str:
    return f"{cents / 100:.2f} {currency}"


def print_step(title: str, obj: Any | None = None) -> None:
    print(f"\n== {title}")
    if obj is not None:
        print(json.dumps(obj, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an AgentCart household-agent purchase demo.")
    parser.add_argument("--url", default=os.getenv("AGENTCART_URL", "http://127.0.0.1:8099"))
    parser.add_argument("--token", default=os.getenv("AGENTCART_TOKEN", ""))
    parser.add_argument("--query", default="woo tea")
    parser.add_argument("--product-id", default="")
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--reason", default="Home Assistant tea stock sensor is low")
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--poll-interval", type=int, default=3)
    parser.add_argument("--no-wait", action="store_true", help="Stop after creating the approval request.")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print_step(f"Agent searches catalog for {args.query!r}")
    status, _headers, search = request_json(
        base_url,
        "GET",
        "/v1/catalog/search?" + urllib.parse.urlencode({"q": args.query}),
        token=args.token,
    )
    if status != 200:
        print_step(f"Search failed with HTTP {status}", search)
        return 1
    products = search.get("products", [])
    if not products:
        print("No products returned.")
        return 1
    for index, product in enumerate(products, start=1):
        print(
            f"{index}. {product['id']} | {product['title']} | "
            f"{money(product['price_hint']['amount_cents'], product['price_hint']['currency'])} | "
            f"{product['merchant']['name']}"
        )

    product = next((item for item in products if item["id"] == args.product_id), None) if args.product_id else products[0]
    if not product:
        print(f"Product not found in search results: {args.product_id}")
        return 1
    print_step(f"Agent selected {product['title']} from {product['merchant']['name']}")

    quote_payload = {
        "agent_id": "household-agent-demo",
        "reason": args.reason,
        "items": [{"product_id": product["id"], "quantity": args.quantity}],
        "ship_to": {"country": "DE", "postal_code": "15344"},
    }
    status, _headers, quote = request_json(base_url, "POST", "/v1/quotes", token=args.token, payload=quote_payload)
    if status != 201:
        print_step(f"Quote failed with HTTP {status}", quote)
        return 1
    print_step(
        f"Quote {quote['id']}: {money(quote['total_cents'], quote['currency'])}; policy {quote['policy_result']['decision']}",
        quote,
    )
    if quote["policy_result"]["decision"] == "deny":
        print("Policy denied this quote. Stopping before approval/payment.")
        return 1

    status, _headers, approval = request_json(
        base_url,
        "POST",
        "/v1/approvals",
        token=args.token,
        payload={"quote_id": quote["id"], "channel": "cli"},
    )
    if status != 201:
        print_step(f"Approval creation failed with HTTP {status}", approval)
        return 1
    print_step("Approval request created")
    print(f"Open this URL and approve: {approval['decision_url']}")
    if args.no_wait:
        return 0

    deadline = time.time() + args.wait_seconds
    current = approval
    while time.time() < deadline:
        status, _headers, current = request_json(base_url, "GET", f"/v1/approvals/{approval['id']}", token=args.token)
        if status != 200:
            print_step(f"Approval poll failed with HTTP {status}", current)
            return 1
        print(f"Approval state: {current['state']}")
        if current["state"] == "approved":
            break
        if current["state"] in {"rejected", "expired"}:
            print("Approval did not pass. Stopping before checkout.")
            return 1
        time.sleep(args.poll_interval)
    else:
        print("Timed out waiting for approval.")
        return 1

    checkout_payload = {
        "quote_id": quote["id"],
        "approval_id": approval["id"],
        "idempotency_key": f"cli-{uuid.uuid4().hex}",
    }
    body_text = json.dumps(checkout_payload)
    print_step("Agent starts HTTP 402 payment-auth checkout")
    status, headers, first = post_raw_json(
        base_url,
        "/v1/checkout",
        body_text,
        token=args.token,
        headers={"Idempotency-Key": checkout_payload["idempotency_key"]},
    )
    if status != 402:
        print_step(f"Expected 402, got HTTP {status}", first)
        return 1
    print_step("Payment challenge received", first["challenge"])

    status, headers, second = post_raw_json(
        base_url,
        "/v1/checkout",
        body_text,
        token=args.token,
        headers={
            "Idempotency-Key": checkout_payload["idempotency_key"],
            "Authorization": first["demo_authorization"],
        },
    )
    if status != 201:
        print_step(f"Checkout failed with HTTP {status}", second)
        return 1
    print_step("Order created", second["order"])
    print(f"\nMerchant order: {second['order']['merchant_order_id']}")
    print(f"Payment receipt: {second['payment_receipt']['id']}")
    return 0


def post_raw_json(
    base_url: str,
    path: str,
    body_text: str,
    *,
    token: str,
    headers: dict[str, str],
) -> tuple[int, dict[str, str], Any]:
    request_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **headers,
    }
    if token:
        request_headers["X-AgentCart-Token"] = token
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=body_text.encode(),
        headers=request_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, dict(response.headers), json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, dict(exc.headers), json.loads(raw) if raw else {"error": f"HTTP {exc.code}"}


if __name__ == "__main__":
    raise SystemExit(main())
