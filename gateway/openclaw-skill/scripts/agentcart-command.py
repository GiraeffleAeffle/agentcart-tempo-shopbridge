#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


ENV_PATH = pathlib.Path("/etc/openclaw/agentcart.env")


def load_env_file(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], Any]:
    load_env_file(ENV_PATH)
    base_url = os.environ.get("AGENTCART_URL", "http://127.0.0.1:8099").rstrip("/")
    token = os.environ.get("AGENTCART_TOKEN", "")
    body = None
    headers = {"Accept": "application/json"}
    if token:
        headers["X-AgentCart-Token"] = token
    if payload is not None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    headers.update(extra_headers or {})
    request = urllib.request.Request(base_url + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            parsed = json.loads(raw) if raw else None
            return response.status, dict(response.headers.items()), parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        parsed = json.loads(raw) if raw else {"error": raw.decode(errors="replace")}
        return exc.code, dict(exc.headers.items()), parsed


def first_available_product(search_result: dict[str, Any], product_id: str | None = None) -> dict[str, Any]:
    products = search_result.get("products") or []
    if product_id:
        for product in products:
            if product.get("id") == product_id:
                return product
        raise SystemExit(f"Product {product_id} was not returned by catalog search")
    for product in products:
        if product.get("eligible_for_agent_checkout") and product.get("availability") == "in_stock":
            return product
    raise SystemExit("No in-stock agent-checkout product found")


def checkout_after_approval(approval_id: str, quote_id: str | None = None) -> dict[str, Any]:
    approval = run("approval_status", {"approval_id": approval_id})
    state = approval.get("state")
    if state != "approved":
        return {
            "state": state,
            "approval": approval,
            "next": "Wait for human approval before checkout.",
        }
    quote_id = quote_id or approval["quote_id"]
    checkout = run(
        "checkout",
        {
            "quote_id": quote_id,
            "approval_id": approval_id,
            "idempotency_key": f"openclaw-{approval_id}",
            "simulate_payment": True,
        },
    )
    return {
        "state": "checked_out" if checkout.get("status") in {200, 201} else "checkout_failed",
        "approval": approval,
        "checkout": checkout,
    }


def approval_reference(args: dict[str, Any]) -> tuple[str, str]:
    approval_id = str(args.get("approval_id") or "").strip()
    token = str(args.get("token") or args.get("decision_token") or "").strip()
    approval_url = str(args.get("approval_url") or args.get("url") or "").strip()
    if approval_url:
        parsed = urllib.parse.urlparse(approval_url)
        parts = [part for part in parsed.path.split("/") if part]
        if not approval_id and len(parts) >= 2 and parts[-2] == "approvals":
            approval_id = parts[-1]
        query = urllib.parse.parse_qs(parsed.query)
        if not token and query.get("token"):
            token = query["token"][0]
    if not approval_id:
        raise SystemExit("approval_id or approval_url is required")
    if not token:
        raise SystemExit("approval token or approval_url with token is required")
    return approval_id, token


def decide_approval(args: dict[str, Any]) -> dict[str, Any]:
    approval_id, token = approval_reference(args)
    decision = str(args.get("decision") or "approved").strip().lower()
    if decision == "approve":
        decision = "approved"
    if decision == "reject":
        decision = "rejected"
    if decision not in {"approved", "rejected"}:
        raise SystemExit("decision must be approved or rejected")
    payload = {
        "decision": decision,
        "token": token,
        "approver": args.get("approver", "openclaw-chat"),
    }
    status, _headers, body = request_json("POST", f"/v1/approvals/{approval_id}/decision", payload=payload)
    if status >= 400:
        return {"status": status, "body": body}
    return body


def approve_and_checkout(args: dict[str, Any]) -> dict[str, Any]:
    approval = decide_approval({**args, "decision": "approved"})
    if approval.get("status", 200) >= 400:
        return {"state": "approval_failed", "approval": approval}
    if approval.get("state") != "approved":
        return {"state": approval.get("state", "unknown"), "approval": approval}
    checkout = checkout_after_approval(approval["id"], approval.get("quote_id"))
    return {
        "state": checkout.get("state"),
        "approval": approval,
        "checkout": checkout,
    }


def start_demo_purchase(args: dict[str, Any]) -> dict[str, Any]:
    query = args.get("q") or args.get("query") or "buy woo tea"
    quantity = int(args.get("quantity") or 1)
    reason = args.get("reason") or "Household agent was asked to buy tea for low stock"
    ship_to = args.get("ship_to", {"country": "DE", "postal_code": "15344"})
    use_tournament = bool(args.get("use_tournament", not args.get("product_id")))
    tournament: dict[str, Any] | None = None
    product: dict[str, Any] | None = None
    if use_tournament:
        tournament = run(
            "quote_tournament",
            {
                "q": query,
                "country": ship_to.get("country", "DE") if isinstance(ship_to, dict) else "DE",
                "postal_code": ship_to.get("postal_code", "15344") if isinstance(ship_to, dict) else "15344",
                "quantity": quantity,
            },
        )
        winner = tournament.get("winner") if isinstance(tournament, dict) else None
        if not winner:
            return {
                "state": "no_quote_candidate",
                "search_query": query,
                "tournament": tournament,
                "next": "No eligible merchant returned a usable final quote.",
            }
        quote = run("get_quote", {"quote_id": winner["quote_id"]})
        product = {
            "id": winner.get("product_id"),
            "title": winner.get("product_title"),
            "merchant": {"id": winner.get("merchant_id"), "name": winner.get("merchant_name")},
        }
    else:
        search = run("search_catalog", {"q": query})
        product = first_available_product(search, args.get("product_id"))
        quote = run(
            "create_quote",
            {
                "agent_id": args.get("agent_id", "openclaw-household"),
                "reason": reason,
                "items": [{"product_id": product["id"], "quantity": quantity}],
                "ship_to": ship_to,
            },
        )
    if quote.get("policy_result", {}).get("decision") == "deny":
        return {
            "state": "policy_denied",
            "tournament": tournament,
            "selected_product": product,
            "quote": quote,
        }
    approval = run(
        "create_approval",
        {
            "quote_id": quote["id"],
            "channel": args.get("channel", "agent_chat"),
            "delivery_channels": args.get("delivery_channels", ["chat", "home_assistant", "web", "api"]),
        },
    )
    result = {
        "state": "approval_required",
        "search_query": query,
        "tournament": tournament,
        "selected_product": product,
        "quote": quote,
        "approval": approval,
        "next": "Ask the human to approve in chat, Home Assistant, or the approval URL, then call resume_checkout with the approval_id.",
    }
    if not args.get("wait_for_approval"):
        return result

    deadline = time.monotonic() + int(args.get("wait_seconds") or 120)
    interval = max(1, int(args.get("poll_interval") or 3))
    while time.monotonic() < deadline:
        resumed = checkout_after_approval(approval["id"], quote["id"])
        if resumed["state"] != "pending":
            return {**result, "resume": resumed}
        time.sleep(interval)
    return {**result, "state": "approval_timeout"}


def run(command: str, args: dict[str, Any]) -> Any:
    if command == "health":
        return request_json("GET", "/health")[2]
    if command == "capabilities":
        return request_json("GET", "/.well-known/agentcart.json")[2]
    if command == "integration_status":
        return request_json("GET", "/v1/integrations/status")[2]
    if command == "list_open_tasks":
        query = urllib.parse.urlencode({"limit": args.get("limit", 20)})
        return request_json("GET", f"/v1/tasks/open?{query}")[2]
    if command == "energy_surplus":
        return request_json("GET", "/v1/energy/surplus")[2]
    if command == "search_catalog":
        query = urllib.parse.urlencode({"q": args.get("q", "")})
        return request_json("GET", f"/v1/catalog/search?{query}")[2]
    if command == "registry":
        return request_json("GET", "/v1/registry")[2]
    if command == "quote_tournament":
        query = urllib.parse.urlencode(
            {
                "q": args.get("q") or args.get("query") or "tea",
                "country": args.get("country") or "DE",
                "postal_code": args.get("postal_code") or "15344",
                "quantity": args.get("quantity") or 1,
            }
        )
        return request_json("GET", f"/v1/quote-tournament?{query}")[2]
    if command == "get_product":
        return request_json("GET", f"/v1/products/{args['product_id']}")[2]
    if command == "get_quote":
        return request_json("GET", f"/v1/quotes/{args['quote_id']}")[2]
    if command == "create_quote":
        payload = dict(args)
        payload.setdefault("agent_id", "openclaw-household")
        return request_json("POST", "/v1/quotes", payload=payload)[2]
    if command == "create_approval":
        return request_json("POST", "/v1/approvals", payload=args)[2]
    if command == "approval_status":
        return request_json("GET", f"/v1/approvals/{args['approval_id']}")[2]
    if command in {"approve_purchase", "reject_purchase"}:
        decision = "rejected" if command == "reject_purchase" else args.get("decision", "approved")
        return decide_approval({**args, "decision": decision})
    if command == "approve_and_checkout":
        return approve_and_checkout(args)
    if command == "checkout":
        payload = {
            "quote_id": args["quote_id"],
            "approval_id": args["approval_id"],
            "idempotency_key": args.get("idempotency_key") or f"openclaw-{uuid.uuid4().hex}",
        }
        headers = {"Idempotency-Key": payload["idempotency_key"]}
        status, response_headers, body = request_json("POST", "/v1/checkout", payload=payload, extra_headers=headers)
        if status != 402 or not args.get("simulate_payment"):
            return {"status": status, "headers": response_headers, "body": body}
        authorization = body["demo_authorization"]
        headers["Authorization"] = authorization
        status, response_headers, body = request_json("POST", "/v1/checkout", payload=payload, extra_headers=headers)
        return {"status": status, "headers": response_headers, "body": body}
    if command == "order_status":
        return request_json("GET", f"/v1/orders/{args['order_id']}")[2]
    if command == "audit":
        return request_json("GET", f"/v1/audit/{args['purchase_id']}")[2]
    if command == "buy_favorite_tea":
        return start_demo_purchase(
            {
                **args,
                "q": args.get("q") or "buy my favorite tea",
                "reason": args.get("reason") or "Household agent was asked to buy Max's favorite tea",
                "use_tournament": args.get("use_tournament", not args.get("product_id")),
                "channel": args.get("channel", "agent_chat"),
                "delivery_channels": args.get("delivery_channels", ["chat", "home_assistant", "web", "api"]),
            }
        )
    if command in {"start_demo_purchase", "buy_tea_demo"}:
        return start_demo_purchase(args)
    if command == "resume_checkout":
        return checkout_after_approval(args["approval_id"], args.get("quote_id"))
    if command == "demo_low_tea":
        return request_json("POST", "/v1/demo/low-tea", payload={})[2]
    if command == "demo_woo_tea":
        return request_json("POST", "/v1/demo/woo-tea", payload={})[2]
    raise SystemExit(f"Unknown command: {command}")


def main() -> int:
    payload = json.load(sys.stdin)
    command = payload.get("command")
    args = payload.get("args") or {}
    if not isinstance(args, dict):
        raise SystemExit("args must be an object")
    result = run(command, args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
