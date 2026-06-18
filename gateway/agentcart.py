#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import html
import hmac
import json
import os
import pathlib
import re
import secrets
import shlex
import shutil
import sys
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import subprocess
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from zoneinfo import ZoneInfo


PRODUCT_ROUTE = re.compile(r"^/v1/products/([A-Za-z0-9_.-]+)$")
QUOTE_ROUTE = re.compile(r"^/v1/quotes/([A-Za-z0-9_-]+)$")
APPROVAL_ROUTE = re.compile(r"^/v1/approvals/([A-Za-z0-9_-]+)$")
APPROVAL_DECISION_ROUTE = re.compile(r"^/v1/approvals/([A-Za-z0-9_-]+)/decision$")
APPROVAL_PAGE_ROUTE = re.compile(r"^/approvals/([A-Za-z0-9_-]+)$")
APPROVAL_PAGE_ACTION_ROUTE = re.compile(r"^/approvals/([A-Za-z0-9_-]+)/(approve|reject)$")
ORDER_ROUTE = re.compile(r"^/v1/orders/([A-Za-z0-9_-]+)$")
ORDER_REFUND_ROUTE = re.compile(r"^/v1/orders/([A-Za-z0-9_-]+)/refunds$")
ORDER_PAGE_ROUTE = re.compile(r"^/orders/([A-Za-z0-9_-]+)$")
AUDIT_ROUTE = re.compile(r"^/v1/audit/([A-Za-z0-9_-]+)$")
DEMO_CHECKOUT_ROUTE = re.compile(r"^/demo/checkout/([A-Za-z0-9_-]+)$")
DEMO_ORDER_REFUND_ROUTE = re.compile(r"^/demo/orders/([A-Za-z0-9_-]+)/refund$")
ENERGY_OFFER_ROUTE = re.compile(r"^/v1/energy/offers/([A-Za-z0-9_-]+)$")
ENERGY_OFFER_ACCEPT_ROUTE = re.compile(r"^/v1/energy/offers/([A-Za-z0-9_-]+)/accept$")
DEMO_ENERGY_OFFER_ACCEPT_ROUTE = re.compile(r"^/demo/energy-offers/([A-Za-z0-9_-]+)/accept$")
DELIVERY_CALENDAR_ROUTE = "/calendar/agentcart-deliveries.ics"

JSON_MIME = "application/json; charset=utf-8"
HTML_MIME = "text/html; charset=utf-8"
TEXT_MIME = "text/plain; charset=utf-8"
APPROVAL_TTL_SECONDS = 15 * 60
QUOTE_TTL_SECONDS = 15 * 60
CHALLENGE_TTL_SECONDS = 5 * 60
ENERGY_DEFAULT_PRICE_CENTS_PER_KWH = 18
ENERGY_DEFAULT_MARKET_REFERENCE_CENTS_PER_KWH = 30
ENERGY_DEFAULT_FEED_IN_REFERENCE_CENTS_PER_KWH = 8
ENERGY_OFFER_DEFAULT_DURATION_MINUTES = 30
ENERGY_OFFER_DEFAULT_VALID_MINUTES = 15


class AgentCartError(Exception):
    status = 500

    def __init__(self, message: str, *, detail: Any | None = None) -> None:
        super().__init__(message)
        self.detail = detail


class BadRequest(AgentCartError):
    status = 400


class Unauthorized(AgentCartError):
    status = 401


class Forbidden(AgentCartError):
    status = 403


class NotFound(AgentCartError):
    status = 404


class Conflict(AgentCartError):
    status = 409


class PaymentProviderUnavailable(AgentCartError):
    status = 503


class UpstreamError(AgentCartError):
    status = 502


@dataclass(frozen=True)
class Config:
    bind: str
    port: int
    timezone: str
    public_url: str
    agentcart_token: str
    state_path: pathlib.Path
    audit_log_path: pathlib.Path
    policy_path: pathlib.Path | None
    homeassistant_url: str
    homeassistant_token: str
    ha_notify_services: tuple[str, ...]
    homeassistant_calendar_entity_id: str
    energy_solar_power_entity: str
    energy_battery_level_entity: str
    energy_battery_power_entity: str
    energy_grid_export_entity: str
    energy_grid_import_entity: str
    energy_house_output_entity: str
    energy_min_export_w: float
    energy_min_battery_percent: float
    vikunja_api_url: str
    vikunja_web_url: str
    vikunja_token: str
    vikunja_project_id: int | None
    default_ship_country: str
    default_ship_postal_code: str
    woocommerce_mode: str
    woocommerce_base_url: str
    woocommerce_consumer_key: str
    woocommerce_consumer_secret: str
    woocommerce_agentcart_token: str
    woocommerce_merchant_id: str
    woocommerce_merchant_name: str
    payment_provider: str
    agentcash_proof_url: str
    agentcash_command: str
    agentcash_proof_required: bool
    agentcash_timeout_seconds: int
    tempo_mpp_endpoint: str
    tempo_mpp_proof_url: str
    tempo_mpp_command: str
    tempo_mpp_network: str
    tempo_mpp_account: str
    tempo_mpp_proof_required: bool
    tempo_mpp_timeout_seconds: int
    tempo_mpp_recipient_address: str
    delivery_calendar_enabled: bool
    delivery_calendar_token: str

    @classmethod
    def from_env(cls) -> "Config":
        data_dir = pathlib.Path(os.getenv("AGENTCART_DATA_DIR", "./data"))
        policy_path = os.getenv("AGENTCART_POLICY_PATH", "")
        project_id = os.getenv("VIKUNJA_PROJECT_ID", "")
        return cls(
            bind=os.getenv("AGENTCART_BIND", "127.0.0.1"),
            port=int(os.getenv("AGENTCART_PORT", "8099")),
            timezone=os.getenv("AGENTCART_TIMEZONE", "Europe/Berlin"),
            public_url=os.getenv("AGENTCART_PUBLIC_URL", "http://127.0.0.1:8099").rstrip("/"),
            agentcart_token=os.getenv("AGENTCART_TOKEN", ""),
            state_path=pathlib.Path(os.getenv("AGENTCART_STATE_PATH", str(data_dir / "state.json"))),
            audit_log_path=pathlib.Path(os.getenv("AGENTCART_AUDIT_LOG_PATH", str(data_dir / "audit.jsonl"))),
            policy_path=pathlib.Path(policy_path) if policy_path else None,
            homeassistant_url=os.getenv("HOMEASSISTANT_URL", "").rstrip("/"),
            homeassistant_token=os.getenv("HOMEASSISTANT_TOKEN", ""),
            ha_notify_services=csv_env("HA_NOTIFY_SERVICES"),
            homeassistant_calendar_entity_id=os.getenv("HOMEASSISTANT_CALENDAR_ENTITY_ID", "").strip(),
            energy_solar_power_entity=os.getenv(
                "AGENTCART_ENERGY_SOLAR_POWER_ENTITY",
                "sensor.solarbank_3_e2700_pro_solarleistung",
            ).strip(),
            energy_battery_level_entity=os.getenv(
                "AGENTCART_ENERGY_BATTERY_LEVEL_ENTITY",
                "sensor.solarbank_3_e2700_pro_ladestand",
            ).strip(),
            energy_battery_power_entity=os.getenv(
                "AGENTCART_ENERGY_BATTERY_POWER_ENTITY",
                "sensor.solarbank_3_e2700_pro_akkuleistung",
            ).strip(),
            energy_grid_export_entity=os.getenv(
                "AGENTCART_ENERGY_GRID_EXPORT_ENTITY",
                "sensor.smart_meter_netzeinspeisung",
            ).strip(),
            energy_grid_import_entity=os.getenv(
                "AGENTCART_ENERGY_GRID_IMPORT_ENTITY",
                "sensor.smart_meter_netzbezug",
            ).strip(),
            energy_house_output_entity=os.getenv(
                "AGENTCART_ENERGY_HOUSE_OUTPUT_ENTITY",
                "sensor.solarbank_3_e2700_pro_ac_hausabgabe",
            ).strip(),
            energy_min_export_w=float(os.getenv("AGENTCART_ENERGY_MIN_EXPORT_W", "100")),
            energy_min_battery_percent=float(os.getenv("AGENTCART_ENERGY_MIN_BATTERY_PERCENT", "70")),
            vikunja_api_url=os.getenv("VIKUNJA_API_URL", "").rstrip("/"),
            vikunja_web_url=os.getenv("VIKUNJA_WEB_URL", "").rstrip("/"),
            vikunja_token=os.getenv("VIKUNJA_TOKEN", ""),
            vikunja_project_id=int(project_id) if project_id else None,
            default_ship_country=os.getenv("AGENTCART_DEFAULT_SHIP_COUNTRY", "DE"),
            default_ship_postal_code=os.getenv("AGENTCART_DEFAULT_SHIP_POSTAL_CODE", "15344"),
            woocommerce_mode=os.getenv("WOOCOMMERCE_MODE", "mock").strip().lower(),
            woocommerce_base_url=os.getenv("WOOCOMMERCE_BASE_URL", "").rstrip("/"),
            woocommerce_consumer_key=os.getenv("WOOCOMMERCE_CONSUMER_KEY", ""),
            woocommerce_consumer_secret=os.getenv("WOOCOMMERCE_CONSUMER_SECRET", ""),
            woocommerce_agentcart_token=os.getenv("WOOCOMMERCE_AGENTCART_TOKEN", "").strip(),
            woocommerce_merchant_id=os.getenv("WOOCOMMERCE_MERCHANT_ID", "woocommerce-demo-tea"),
            woocommerce_merchant_name=os.getenv("WOOCOMMERCE_MERCHANT_NAME", "Woo Demo Tea Shop"),
            payment_provider=os.getenv("AGENTCART_PAYMENT_PROVIDER", "demo").strip().lower(),
            agentcash_proof_url=os.getenv("AGENTCART_AGENTCASH_PROOF_URL", "").strip(),
            agentcash_command=os.getenv("AGENTCART_AGENTCASH_COMMAND", "npx -y agentcash@latest fetch").strip(),
            agentcash_proof_required=bool_env("AGENTCART_AGENTCASH_PROOF_REQUIRED", False),
            agentcash_timeout_seconds=int(os.getenv("AGENTCART_AGENTCASH_TIMEOUT_SECONDS", "60")),
            tempo_mpp_endpoint=os.getenv("AGENTCART_TEMPO_MPP_ENDPOINT", "").strip(),
            tempo_mpp_proof_url=os.getenv("AGENTCART_TEMPO_MPP_PROOF_URL", "").strip(),
            tempo_mpp_command=os.getenv("AGENTCART_TEMPO_MPP_COMMAND", "npx mppx").strip(),
            tempo_mpp_network=os.getenv("AGENTCART_TEMPO_MPP_NETWORK", "testnet").strip(),
            tempo_mpp_account=os.getenv("AGENTCART_TEMPO_MPP_ACCOUNT", "agentcart-test").strip(),
            tempo_mpp_proof_required=bool_env("AGENTCART_TEMPO_MPP_PROOF_REQUIRED", False),
            tempo_mpp_timeout_seconds=int(os.getenv("AGENTCART_TEMPO_MPP_TIMEOUT_SECONDS", "90")),
            tempo_mpp_recipient_address=os.getenv("AGENTCART_TEMPO_RECIPIENT_ADDRESS", "").strip(),
            delivery_calendar_enabled=bool_env("AGENTCART_DELIVERY_CALENDAR_ENABLED", False),
            delivery_calendar_token=os.getenv("AGENTCART_DELIVERY_CALENDAR_TOKEN", "").strip(),
        )


def csv_env(name: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in os.getenv(name, "").split(",") if part.strip())


def bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def isoformat(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> dt.datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return dt.datetime.fromisoformat(value)


def json_default(value: Any) -> str:
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value)


def b64url_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=json_default).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def parse_b64url_json(value: str) -> Any:
    padding = "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode((value + padding).encode())
    return json.loads(decoded)


def sha256_b64(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return base64.b64encode(digest).decode()


def money(cents: int, currency: str = "EUR") -> str:
    return f"{cents / 100:.2f} {currency}"


def cents(value: Any, *, field: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value * 100))
    if isinstance(value, str):
        return int(round(float(value) * 100))
    raise BadRequest(f"{field} must be an integer cent amount or decimal string")


def safe_int(value: Any, *, field: str, minimum: int = 1, maximum: int = 100) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise BadRequest(f"{field} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise BadRequest(f"{field} must be between {minimum} and {maximum}")
    return parsed


def safe_float(value: Any, *, field: str, minimum: float = 0.0, maximum: float = 100.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise BadRequest(f"{field} must be a number") from exc
    if parsed < minimum or parsed > maximum:
        raise BadRequest(f"{field} must be between {minimum:g} and {maximum:g}")
    return parsed


def tempo_explorer_url(network: str, reference: str) -> str | None:
    if not reference.startswith("0x"):
        return None
    if network == "testnet":
        return f"https://explore.testnet.tempo.xyz/tx/{reference}"
    if network == "mainnet":
        return f"https://explore.tempo.xyz/tx/{reference}"
    return None


def tempo_default_settlement_asset(network: str) -> dict[str, str]:
    if network == "mainnet":
        return {
            "asset": "USDC.e",
            "denomination": "USD stablecoin",
            "token_standard": "TIP-20",
            "network": "mainnet",
        }
    return {
        "asset": "pathUSD",
        "denomination": "USD stablecoin",
        "token_standard": "TIP-20",
        "network": network or "testnet",
        "token_address": "0x20c0000000000000000000000000000000000000",
    }


def parse_http_header_block(block: str) -> dict[str, Any] | None:
    lines = [line.rstrip("\r") for line in block.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("HTTP/"):
        return None
    status_parts = lines[0].split(" ", 2)
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    status_code = None
    if len(status_parts) > 1 and status_parts[1].isdigit():
        status_code = int(status_parts[1])
    return {"status_line": lines[0], "status_code": status_code, "headers": headers}


def parse_mppx_output(stdout: str, *, network: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        return {"body": json.loads(text)}
    except json.JSONDecodeError:
        pass

    sections = re.split(r"\r?\n\r?\n", text)
    header_blocks: list[dict[str, Any]] = []
    body_sections: list[str] = []
    for section in sections:
        header_block = parse_http_header_block(section)
        if header_block:
            header_blocks.append(header_block)
        elif section.strip():
            body_sections.append(section.strip())

    result: dict[str, Any] = {"raw_tail": text[-8000:]}
    if header_blocks:
        result["http_exchange"] = header_blocks
        result["response_headers"] = header_blocks[-1]["headers"]
        receipt_header = header_blocks[-1]["headers"].get("payment-receipt")
        if receipt_header:
            result["payment_receipt_header"] = receipt_header
            try:
                receipt = parse_b64url_json(receipt_header)
                result["payment_receipt"] = receipt
                reference = str(receipt.get("reference") or "")
                if reference:
                    result["transaction_reference"] = reference
                    explorer_url = tempo_explorer_url(network, reference)
                    if explorer_url:
                        result["explorer_url"] = explorer_url
            except (ValueError, json.JSONDecodeError):
                result["payment_receipt_decode_error"] = "invalid payment receipt header"

    if body_sections:
        body_text = "\n\n".join(body_sections)
        try:
            result["body"] = json.loads(body_text)
        except json.JSONDecodeError:
            result["body"] = body_text[-4000:]
    return result


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(text).split())


def search_tokens(query: str) -> list[str]:
    stop = {"a", "an", "and", "buy", "for", "my", "of", "order", "our", "please", "some", "the", "to"}
    return [token for token in re.findall(r"[a-z0-9]+", query.lower()) if token not in stop]


def product_matches_query(product: dict[str, Any], query: str) -> bool:
    tokens = search_tokens(query)
    if not tokens:
        return True
    haystack = " ".join(
        [
            str(product.get("title", "")),
            str(product.get("description", "")),
            str(product.get("category", "")),
            str(product.get("brand", "")),
            str(product.get("sku", "")),
            str(product.get("id", "")),
        ]
    ).lower()
    return all(token in haystack for token in tokens)


def parse_price_cents(value: Any, *, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(round(float(str(value)) * 100))
    except (TypeError, ValueError):
        return default


def basic_auth_header(username: str, password: str) -> str:
    raw = f"{username}:{password}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def command_available(command: str) -> bool:
    parts = shlex.split(command)
    return bool(parts and shutil.which(parts[0]))


PRODUCT_ALIASES = {
    "favorite_tea": "tea_hazels_chocolate_100g",
    "my_favorite_tea": "tea_hazels_chocolate_100g",
    "hazels_chocolate": "tea_hazels_chocolate_100g",
    "hazels_chocolate_tea": "tea_hazels_chocolate_100g",
}


def normalize_alias(value: str) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", value.lower()))


def resolve_product_alias(value: str) -> str | None:
    normalized = normalize_alias(value)
    if normalized in PRODUCT_ALIASES:
        return PRODUCT_ALIASES[normalized]
    if "favorite" in normalized and "tea" in normalized:
        return PRODUCT_ALIASES["favorite_tea"]
    if "hazel" in normalized and "chocolate" in normalized:
        return PRODUCT_ALIASES["hazels_chocolate"]
    return None


def catalog_query_for_intent(value: str) -> str:
    alias = resolve_product_alias(value)
    if alias == "tea_hazels_chocolate_100g":
        return "Hazel's Chocolate Tea"
    return value


def add_business_days(start: dt.date, days: int) -> dt.date:
    current = start
    remaining = max(days, 0)
    while remaining:
        current += dt.timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def delivery_window_from_estimate(
    estimate: dict[str, Any],
    *,
    timezone: str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    tz = ZoneInfo(timezone)
    current = (now or utcnow()).astimezone(tz).date()
    min_days = int(estimate.get("min_days", 2))
    max_days = int(estimate.get("max_days", 4))
    return {
        "source": "merchant_quote",
        "label": str(estimate.get("label") or f"{min_days}-{max_days} business days"),
        "earliest_date": add_business_days(current, min_days).isoformat(),
        "latest_date": add_business_days(current, max_days).isoformat(),
        "confidence": "estimated",
        "timezone": timezone,
    }


def parse_date(value: Any) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def ical_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ical_fold(line: str) -> list[str]:
    if len(line.encode("utf-8")) <= 75:
        return [line]
    folded: list[str] = []
    current = ""
    for char in line:
        candidate = current + char
        if current and len(candidate.encode("utf-8")) > 75:
            folded.append(current)
            current = " " + char
        else:
            current = candidate
    if current:
        folded.append(current)
    return folded


class DemoTeaShopAdapter:
    adapter_type = "demo"

    merchant = {
        "id": "demo-tea-shop",
        "name": "Futura Demo Tea Shop",
        "merchant_of_record": {
            "name": "Futura Demo Tea Shop GmbH",
            "country": "DE",
            "vat_id": "DE-DEMO-TEA",
            "support_email": "support@example.invalid",
        },
        "terms_url": "https://example.invalid/futura-tea/terms",
        "returns_url": "https://example.invalid/futura-tea/returns",
    }

    products = {
        "tea_sencha_100g": {
            "id": "tea_sencha_100g",
            "merchant_id": "demo-tea-shop",
            "sku": "FTS-SENCHA-100",
            "title": "Sencha Daily Green Tea",
            "description": "Balanced loose leaf green tea for weekday refills.",
            "category": "grocery.tea",
            "brand": "Futura Tea",
            "unit_size": "100 g",
            "image_urls": [],
            "price_cents": 849,
            "currency": "EUR",
            "vat_rate_bps": 700,
            "stock": 12,
            "availability": "in_stock",
            "shipping_regions": ["DE"],
            "eligible_for_agent_checkout": True,
        },
        "tea_assam_250g": {
            "id": "tea_assam_250g",
            "merchant_id": "demo-tea-shop",
            "sku": "FTS-ASSAM-250",
            "title": "Assam Breakfast Tea",
            "description": "Malty black tea for morning pots.",
            "category": "grocery.tea",
            "brand": "Futura Tea",
            "unit_size": "250 g",
            "image_urls": [],
            "price_cents": 1290,
            "currency": "EUR",
            "vat_rate_bps": 700,
            "stock": 8,
            "availability": "in_stock",
            "shipping_regions": ["DE"],
            "eligible_for_agent_checkout": True,
        },
        "tea_rooibos_150g": {
            "id": "tea_rooibos_150g",
            "merchant_id": "demo-tea-shop",
            "sku": "FTS-ROOIBOS-150",
            "title": "Rooibos Evening Tea",
            "description": "Caffeine-free rooibos blend for evening stock.",
            "category": "grocery.tea",
            "brand": "Futura Tea",
            "unit_size": "150 g",
            "image_urls": [],
            "price_cents": 990,
            "currency": "EUR",
            "vat_rate_bps": 700,
            "stock": 6,
            "availability": "in_stock",
            "shipping_regions": ["DE"],
            "eligible_for_agent_checkout": True,
        },
        "tea_hazels_chocolate_100g": {
            "id": "tea_hazels_chocolate_100g",
            "merchant_id": "demo-tea-shop",
            "sku": "FTS-HAZEL-CHOCO-100",
            "title": "Hazel's Chocolate Tea",
            "description": "Household favorite chocolate tea blend for cozy refills.",
            "category": "grocery.tea",
            "brand": "Futura Tea",
            "unit_size": "100 g",
            "image_urls": [],
            "price_cents": 1090,
            "currency": "EUR",
            "vat_rate_bps": 700,
            "stock": 10,
            "availability": "in_stock",
            "shipping_regions": ["DE"],
            "eligible_for_agent_checkout": True,
            "preference_keys": ["favorite_tea", "my_favorite_tea"],
        },
    }

    def search_products(self, query: str, stock: dict[str, int]) -> list[dict[str, Any]]:
        results = []
        for product in self.products.values():
            if product_matches_query(product, query):
                results.append(self.with_stock(product, stock))
        return results

    def get_product(self, product_id: str, stock: dict[str, int]) -> dict[str, Any]:
        product = self.products.get(product_id)
        if not product:
            raise NotFound(f"Unknown product: {product_id}")
        return self.with_stock(product, stock)

    def with_stock(self, product: dict[str, Any], stock: dict[str, int]) -> dict[str, Any]:
        current_stock = int(stock.get(product["id"], product["stock"]))
        result = dict(product)
        result["stock"] = current_stock
        result["availability"] = "in_stock" if current_stock > 0 else "out_of_stock"
        result["merchant"] = self.merchant
        result["price_hint"] = {
            "amount_cents": result.pop("price_cents"),
            "currency": product["currency"],
            "includes_vat": True,
        }
        return result

    def initial_stock(self) -> dict[str, int]:
        return {product_id: int(product["stock"]) for product_id, product in self.products.items()}

    def source_product(self, product_id: str) -> dict[str, Any]:
        product = self.products.get(product_id)
        if not product:
            raise NotFound(f"Unknown product: {product_id}")
        return dict(product)

    def create_merchant_order(self, order: dict[str, Any], _quote: dict[str, Any]) -> dict[str, Any]:
        return {
            "platform": "demo-tea-shop",
            "state": "created",
            "id": order["merchant_order_id"],
            "url": None,
            "note": "Local demo merchant order created inside AgentCart.",
        }

    def create_merchant_refund(self, order: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        amount_cents = int(request.get("amount_cents") or order.get("total_cents") or 0)
        return {
            "platform": "demo-tea-shop",
            "state": "demo_refund_recorded",
            "order_id": order.get("merchant_order_id"),
            "refund_id": f"DEMO-REFUND-{uuid.uuid4().hex[:8].upper()}",
            "amount_cents": amount_cents,
            "currency": order.get("currency") or "EUR",
            "rail": str(request.get("rail") or "agentcart-demo"),
            "real_refund_verified": False,
            "verification": {
                "state": "demo_refund_recorded",
                "mode": "demo_merchant",
                "real_refund_verified": False,
                "note": "Demo merchant refund record only; no payment rail refund was executed.",
            },
        }


class WooCommerceAdapter:
    adapter_type = "woocommerce"

    mock_products = {
        "woo_201": {
            "id": "woo_201",
            "source_product_id": 201,
            "merchant_id": "woocommerce-demo-tea",
            "sku": "WOO-SENCHA-100",
            "title": "Woo Sencha Green Tea",
            "description": "Opt-in WooCommerce tea product exposed through AgentBridge.",
            "category": "grocery.tea",
            "brand": "Woo Tea Merchant",
            "unit_size": "100 g",
            "image_urls": [],
            "price_cents": 1199,
            "currency": "EUR",
            "vat_rate_bps": 700,
            "stock": 9,
            "availability": "in_stock",
            "shipping_regions": ["DE"],
            "eligible_for_agent_checkout": True,
        },
        "woo_202": {
            "id": "woo_202",
            "source_product_id": 202,
            "merchant_id": "woocommerce-demo-tea",
            "sku": "WOO-HERBAL-120",
            "title": "Woo Herbal Evening Tea",
            "description": "Caffeine-free household refill from a WooCommerce-style shop.",
            "category": "grocery.tea",
            "brand": "Woo Tea Merchant",
            "unit_size": "120 g",
            "image_urls": [],
            "price_cents": 899,
            "currency": "EUR",
            "vat_rate_bps": 700,
            "stock": 7,
            "availability": "in_stock",
            "shipping_regions": ["DE"],
            "eligible_for_agent_checkout": True,
        },
        "woo_203": {
            "id": "woo_203",
            "source_product_id": 203,
            "merchant_id": "woocommerce-demo-tea",
            "sku": "WOO-HAZEL-100",
            "title": "Hazel's Chocolate Tea",
            "description": "Opt-in WooCommerce offer for the household favorite tea.",
            "category": "grocery.tea",
            "brand": "Woo Tea Merchant",
            "unit_size": "100 g",
            "image_urls": [],
            "price_cents": 990,
            "currency": "EUR",
            "vat_rate_bps": 700,
            "stock": 11,
            "availability": "in_stock",
            "shipping_regions": ["DE"],
            "eligible_for_agent_checkout": True,
        },
    }

    def __init__(self, config: Config) -> None:
        self.config = config
        self.mode = config.woocommerce_mode
        self.products = self.build_products()
        self.merchant = {
            "id": config.woocommerce_merchant_id,
            "name": config.woocommerce_merchant_name,
            "merchant_of_record": {
                "name": config.woocommerce_merchant_name,
                "country": "DE",
                "vat_id": "configured-in-woocommerce",
                "support_email": "configured-in-woocommerce",
            },
            "terms_url": f"{config.woocommerce_base_url}/terms" if config.woocommerce_base_url else "https://example.invalid/woo/terms",
            "returns_url": f"{config.woocommerce_base_url}/returns" if config.woocommerce_base_url else "https://example.invalid/woo/returns",
        }

    def enabled(self) -> bool:
        return self.mode in {"mock", "rest", "plugin"}

    def build_products(self) -> dict[str, dict[str, Any]]:
        products = {key: dict(value) for key, value in self.mock_products.items()}
        for product in products.values():
            product["merchant_id"] = self.config.woocommerce_merchant_id
            product["brand"] = self.config.woocommerce_merchant_name
        return products

    def initial_stock(self) -> dict[str, int]:
        if not self.enabled() or self.mode != "mock":
            return {}
        return {product_id: int(product["stock"]) for product_id, product in self.products.items()}

    def search_products(self, query: str, stock: dict[str, int]) -> list[dict[str, Any]]:
        if not self.enabled():
            return []
        if self.mode == "plugin":
            return self.search_plugin_products(query, stock)
        if self.mode == "rest":
            return self.search_rest_products(query, stock)
        results = []
        for product in self.products.values():
            if product_matches_query(product, query):
                results.append(self.with_stock(product, stock))
        return results

    def get_product(self, product_id: str, stock: dict[str, int]) -> dict[str, Any]:
        product = self.source_product(product_id)
        return self.with_stock(product, stock)

    def source_product(self, product_id: str) -> dict[str, Any]:
        if not self.enabled():
            raise NotFound(f"WooCommerce adapter is disabled: {product_id}")
        if self.mode == "plugin":
            return self.fetch_plugin_product(product_id)
        if self.mode == "rest":
            return self.fetch_rest_product(product_id)
        product = self.products.get(product_id)
        if not product:
            raise NotFound(f"Unknown WooCommerce product: {product_id}")
        return dict(product)

    def with_stock(self, product: dict[str, Any], stock: dict[str, int]) -> dict[str, Any]:
        if self.mode in {"plugin", "rest"}:
            current_stock = int(product.get("stock", 0))
        else:
            current_stock = int(stock.get(product["id"], product.get("stock", 0)))
        result = dict(product)
        result["stock"] = current_stock
        result["availability"] = "in_stock" if current_stock > 0 else "out_of_stock"
        result["merchant"] = self.merchant
        result["price_hint"] = {
            "amount_cents": result.pop("price_cents"),
            "currency": product["currency"],
            "includes_vat": True,
        }
        result["adapter"] = self.adapter_type
        return result

    def search_rest_products(self, query: str, stock: dict[str, int]) -> list[dict[str, Any]]:
        self.require_rest_config()
        params = {
            "status": "publish",
            "per_page": "10",
        }
        if query.strip():
            params["search"] = query.strip()
        url = self.rest_url("/wp-json/wc/v3/products", params)
        raw_products = self.woo_json(url, method="GET")
        if not isinstance(raw_products, list):
            raise UpstreamError("WooCommerce products response was not a list")
        return [self.with_stock(self.normalize_rest_product(raw), stock) for raw in raw_products]

    def search_plugin_products(self, query: str, stock: dict[str, int]) -> list[dict[str, Any]]:
        self.require_plugin_config()
        params = {"search": query.strip(), "limit": "12"}
        raw = self.plugin_json(self.plugin_url("/wp-json/agentcart/v1/catalog", params), method="GET")
        raw_products = raw.get("products") if isinstance(raw, dict) else raw
        if not isinstance(raw_products, list):
            raise UpstreamError("AgentCart WooCommerce plugin catalog response was not a list")
        return [self.with_stock(self.normalize_plugin_product(product), stock) for product in raw_products]

    def fetch_plugin_product(self, product_id: str) -> dict[str, Any]:
        self.require_plugin_config()
        source_id = self.parse_woo_product_id(product_id)
        raw = self.plugin_json(self.plugin_url(f"/wp-json/agentcart/v1/products/{source_id}", {}), method="GET")
        if not isinstance(raw, dict):
            raise UpstreamError("AgentCart WooCommerce plugin product response was not an object")
        return self.normalize_plugin_product(raw)

    def normalize_plugin_product(self, raw: dict[str, Any]) -> dict[str, Any]:
        source_id = int(raw.get("source_product_id") or raw.get("id") or raw.get("product_id"))
        product_id = str(raw.get("product_id") or raw.get("id") or f"woo_{source_id}")
        if product_id.isdigit():
            product_id = f"woo_{product_id}"
        return {
            "id": product_id,
            "source_product_id": source_id,
            "merchant_id": str(raw.get("merchant_id") or self.config.woocommerce_merchant_id),
            "sku": str(raw.get("sku") or f"WOO-{source_id}"),
            "title": strip_html(str(raw.get("title") or raw.get("name") or f"WooCommerce Product {source_id}")),
            "description": strip_html(str(raw.get("description") or "")),
            "category": str(raw.get("category") or "household.supplies"),
            "brand": str(raw.get("brand") or self.config.woocommerce_merchant_name),
            "unit_size": str(raw.get("unit_size") or "unit"),
            "image_urls": raw.get("image_urls") if isinstance(raw.get("image_urls"), list) else [],
            "price_cents": int(raw.get("price_cents") or raw.get("amount_cents") or 0),
            "currency": str(raw.get("currency") or "EUR"),
            "vat_rate_bps": int(raw.get("vat_rate_bps") or 1900),
            "stock": int(raw.get("stock") if raw.get("stock") is not None else 999),
            "availability": str(raw.get("availability") or "in_stock"),
            "shipping_regions": raw.get("shipping_regions") if isinstance(raw.get("shipping_regions"), list) else ["DE"],
            "eligible_for_agent_checkout": bool(raw.get("eligible_for_agent_checkout", True)),
        }

    def fetch_rest_product(self, product_id: str) -> dict[str, Any]:
        self.require_rest_config()
        source_id = self.parse_woo_product_id(product_id)
        url = self.rest_url(f"/wp-json/wc/v3/products/{source_id}", {})
        raw_product = self.woo_json(url, method="GET")
        if not isinstance(raw_product, dict):
            raise UpstreamError("WooCommerce product response was not an object")
        return self.normalize_rest_product(raw_product)

    def normalize_rest_product(self, raw: dict[str, Any]) -> dict[str, Any]:
        source_id = int(raw["id"])
        product_id = f"woo_{source_id}"
        categories = raw.get("categories") or []
        category = "grocery.tea"
        if categories and isinstance(categories[0], dict) and categories[0].get("slug"):
            category = f"woocommerce.{categories[0]['slug']}"
        images = raw.get("images") or []
        image_urls = [image.get("src") for image in images if isinstance(image, dict) and image.get("src")]
        manage_stock = bool(raw.get("manage_stock"))
        stock_quantity = raw.get("stock_quantity")
        stock = int(stock_quantity) if manage_stock and stock_quantity is not None else 999
        return {
            "id": product_id,
            "source_product_id": source_id,
            "merchant_id": self.config.woocommerce_merchant_id,
            "sku": raw.get("sku") or f"WOO-{source_id}",
            "title": strip_html(raw.get("name") or f"WooCommerce Product {source_id}"),
            "description": strip_html(raw.get("short_description") or raw.get("description") or ""),
            "category": category,
            "brand": self.config.woocommerce_merchant_name,
            "unit_size": raw.get("weight") or "unit",
            "image_urls": image_urls,
            "price_cents": parse_price_cents(raw.get("price")),
            "currency": "EUR",
            "vat_rate_bps": 700,
            "stock": stock,
            "availability": "in_stock" if raw.get("stock_status", "instock") == "instock" else "out_of_stock",
            "shipping_regions": ["DE"],
            "eligible_for_agent_checkout": True,
        }

    def create_plugin_quote(
        self,
        *,
        items: list[dict[str, Any]],
        ship_to: dict[str, Any],
        agent_id: str,
        reason: str,
    ) -> dict[str, Any]:
        self.require_plugin_config()
        payload = {
            "agent_id": agent_id,
            "reason": reason,
            "items": [
                {
                    "product_id": item["product_id"],
                    "source_product_id": item.get("source_product_id"),
                    "quantity": int(item["quantity"]),
                }
                for item in items
            ],
            "ship_to": ship_to,
        }
        raw = self.plugin_json(self.plugin_url("/wp-json/agentcart/v1/quote", {}), method="POST", payload=payload)
        if not isinstance(raw, dict):
            raise UpstreamError("AgentCart WooCommerce plugin quote response was not an object")
        return self.normalize_plugin_quote(raw)

    def normalize_plugin_quote(self, raw: dict[str, Any]) -> dict[str, Any]:
        items = raw.get("items")
        if not isinstance(items, list) or not items:
            raise UpstreamError("AgentCart WooCommerce plugin quote is missing items")
        normalized_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            source_id = int(item.get("source_product_id") or item.get("product_id") or item.get("id"))
            product_id = str(item.get("product_id") or f"woo_{source_id}")
            if product_id.isdigit():
                product_id = f"woo_{product_id}"
            normalized_items.append(
                {
                    "product_id": product_id,
                    "source_product_id": source_id,
                    "sku": str(item.get("sku") or f"WOO-{source_id}"),
                    "title": strip_html(str(item.get("title") or item.get("name") or f"WooCommerce Product {source_id}")),
                    "quantity": int(item.get("quantity") or 1),
                    "unit_price_cents": int(item.get("unit_price_cents") or 0),
                    "line_total_cents": int(item.get("line_total_cents") or 0),
                    "currency": str(item.get("currency") or raw.get("currency") or "EUR"),
                    "category": str(item.get("category") or "household.supplies"),
                    "vat_rate_bps": int(item.get("vat_rate_bps") or 1900),
                }
            )
        if not normalized_items:
            raise UpstreamError("AgentCart WooCommerce plugin quote has no usable items")
        return {
            "merchant_quote_id": str(raw.get("id") or raw.get("quote_id") or ""),
            "merchant": raw.get("merchant") if isinstance(raw.get("merchant"), dict) else self.merchant,
            "items": normalized_items,
            "subtotal_cents": int(raw.get("subtotal_cents") or 0),
            "shipping": raw.get("shipping") if isinstance(raw.get("shipping"), dict) else {"amount_cents": 0, "currency": "EUR", "method": "woocommerce", "vat_rate_bps": 1900},
            "vat_lines": raw.get("vat_lines") if isinstance(raw.get("vat_lines"), list) else [],
            "total_cents": int(raw.get("total_cents") or 0),
            "currency": str(raw.get("currency") or "EUR"),
            "delivery_estimate": raw.get("delivery_estimate") if isinstance(raw.get("delivery_estimate"), dict) else {"min_days": 2, "max_days": 4, "label": "2-4 business days"},
            "delivery_window": raw.get("delivery_window") if isinstance(raw.get("delivery_window"), dict) else None,
            "stock_reserved_until": raw.get("stock_reserved_until"),
            "stock_reservation": raw.get("stock_reservation") if isinstance(raw.get("stock_reservation"), dict) else None,
            "quote_hash": str(raw.get("quote_hash") or ""),
            "payment_requirements": raw.get("payment_requirements") if isinstance(raw.get("payment_requirements"), dict) else {},
            "expires_at": raw.get("expires_at"),
            "terms_url": str(raw.get("terms_url") or self.merchant["terms_url"]),
            "returns_url": str(raw.get("returns_url") or self.merchant["returns_url"]),
            "merchant_of_record": raw.get("merchant_of_record") if isinstance(raw.get("merchant_of_record"), dict) else self.merchant["merchant_of_record"],
        }

    def create_merchant_order(self, order: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
        if self.mode == "plugin":
            return self.create_plugin_order(order, quote)
        if self.mode != "rest":
            return {
                "platform": "woocommerce-mock",
                "state": "created",
                "id": f"WOO-MOCK-{order['id'][-8:].upper()}",
                "url": None,
                "note": "Mock WooCommerce order created. Configure WOOCOMMERCE_MODE=rest to post real Woo orders.",
            }
        self.require_rest_config()
        payload = {
            "status": "processing",
            "set_paid": True,
            "payment_method": "tempo_mpp",
            "payment_method_title": "Tempo MPP via AgentBridge",
            "line_items": [
                {
                    "product_id": int(item["source_product_id"]),
                    "quantity": int(item["quantity"]),
                }
                for item in quote["items"]
            ],
            "meta_data": [
                {"key": "agentcart_order_id", "value": order["id"]},
                {"key": "agentcart_quote_id", "value": quote["id"]},
                {"key": "agentcart_payment_receipt_id", "value": order["payment_receipt"]["id"]},
                {"key": "agentcart_reason", "value": quote["reason"]},
            ],
        }
        raw_order = self.woo_json(self.rest_url("/wp-json/wc/v3/orders", {}), method="POST", payload=payload)
        if not isinstance(raw_order, dict):
            raise UpstreamError("WooCommerce order response was not an object")
        order_id = raw_order.get("id")
        return {
            "platform": "woocommerce",
            "state": "created",
            "id": str(order_id),
            "url": raw_order.get("permalink") or f"{self.config.woocommerce_base_url}/wp-admin/post.php?post={order_id}&action=edit",
            "status": raw_order.get("status"),
            "number": raw_order.get("number"),
        }

    def create_plugin_order(self, order: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
        self.require_plugin_config()
        payload = {
            "agentcart_order_id": order["id"],
            "agentcart_quote_id": quote["id"],
            "merchant_quote_id": quote.get("merchant_quote_id"),
            "quote_hash": quote.get("quote_hash"),
            "reason": quote.get("reason"),
            "quote": quote,
            "payment_receipt": order.get("payment_receipt"),
            "items": [
                {
                    "product_id": item.get("product_id"),
                    "source_product_id": item.get("source_product_id"),
                    "quantity": int(item.get("quantity") or 1),
                }
                for item in quote.get("items", [])
            ],
        }
        raw_order = self.plugin_json(self.plugin_url("/wp-json/agentcart/v1/orders", {}), method="POST", payload=payload)
        if not isinstance(raw_order, dict):
            raise UpstreamError("AgentCart WooCommerce plugin order response was not an object")
        order_id = raw_order.get("id")
        return {
            "platform": "woocommerce-agentcart-plugin",
            "state": str(raw_order.get("state") or "created"),
            "id": str(order_id),
            "url": raw_order.get("url") or f"{self.config.woocommerce_base_url}/wp-admin/post.php?post={order_id}&action=edit",
            "status": raw_order.get("status"),
            "number": raw_order.get("number"),
            "payment_method": raw_order.get("payment_method"),
            "status_url": raw_order.get("status_url"),
            "status_token": raw_order.get("status_token"),
            "fulfillment": raw_order.get("fulfillment") if isinstance(raw_order.get("fulfillment"), dict) else {},
            "payment_verification": raw_order.get("payment_verification") if isinstance(raw_order.get("payment_verification"), dict) else {},
        }

    def create_merchant_refund(self, order: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        amount_cents = safe_int(
            request.get("amount_cents", order.get("total_cents", 1)),
            field="amount_cents",
            minimum=1,
            maximum=max(1, int(order.get("total_cents") or 1)),
        )
        reason = str(request.get("reason") or "AgentCart demo refund").strip() or "AgentCart demo refund"
        rail = str(request.get("rail") or order.get("payment_receipt", {}).get("method") or "agentcart-demo")
        if self.mode == "plugin":
            return self.create_plugin_refund(order, amount_cents=amount_cents, reason=reason, rail=rail)
        return {
            "platform": "woocommerce-mock",
            "state": "demo_refund_recorded",
            "order_id": str(order.get("merchant_order_id") or ""),
            "refund_id": f"WOO-REFUND-MOCK-{uuid.uuid4().hex[:8].upper()}",
            "amount_cents": amount_cents,
            "currency": order.get("currency") or "EUR",
            "rail": rail,
            "real_refund_verified": False,
            "verification": {
                "state": "demo_refund_recorded",
                "mode": "agentcart_mock",
                "real_refund_verified": False,
                "note": "Mock WooCommerce refund record only. No Stripe, card, Tempo, stablecoin, or EUR rail refund was executed.",
            },
        }

    def create_plugin_refund(self, order: dict[str, Any], *, amount_cents: int, reason: str, rail: str) -> dict[str, Any]:
        self.require_plugin_config()
        merchant_order = order.get("merchant_order") if isinstance(order.get("merchant_order"), dict) else {}
        merchant_order_id = str(merchant_order.get("id") or order.get("merchant_order_id") or "")
        if not merchant_order_id:
            raise BadRequest("order has no merchant order id to refund")
        payload = {
            "amount_cents": amount_cents,
            "reason": reason,
            "rail": rail,
            "agentcart_order_id": order.get("id"),
            "payment_receipt_id": (order.get("payment_receipt") or {}).get("id"),
        }
        raw_refund = self.plugin_json(
            self.plugin_url(f"/wp-json/agentcart/v1/orders/{merchant_order_id}/refunds", {}),
            method="POST",
            payload=payload,
        )
        if not isinstance(raw_refund, dict):
            raise UpstreamError("AgentCart WooCommerce plugin refund response was not an object")
        return raw_refund

    def require_rest_config(self) -> None:
        if not self.config.woocommerce_base_url:
            raise BadRequest("WOOCOMMERCE_BASE_URL is required for WOOCOMMERCE_MODE=rest")
        if not self.config.woocommerce_consumer_key or not self.config.woocommerce_consumer_secret:
            raise BadRequest("WooCommerce consumer key and secret are required for WOOCOMMERCE_MODE=rest")

    def require_plugin_config(self) -> None:
        if not self.config.woocommerce_base_url:
            raise BadRequest("WOOCOMMERCE_BASE_URL is required for WOOCOMMERCE_MODE=plugin")
        if not self.config.woocommerce_agentcart_token:
            raise BadRequest("WOOCOMMERCE_AGENTCART_TOKEN is required for WOOCOMMERCE_MODE=plugin")

    def parse_woo_product_id(self, product_id: str) -> int:
        if not product_id.startswith("woo_"):
            raise NotFound(f"Unknown WooCommerce product id: {product_id}")
        try:
            return int(product_id.split("_", 1)[1])
        except ValueError as exc:
            raise NotFound(f"Invalid WooCommerce product id: {product_id}") from exc

    def rest_url(self, path: str, params: dict[str, str]) -> str:
        url = self.config.woocommerce_base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return url

    def plugin_url(self, path: str, params: dict[str, str]) -> str:
        if path.startswith("/wp-json/"):
            rest_route = "/" + path[len("/wp-json/") :]
        else:
            rest_route = path
        query = {"rest_route": rest_route, **{key: value for key, value in params.items() if value is not None}}
        url = self.config.woocommerce_base_url + "/index.php?" + urllib.parse.urlencode(query)
        if not params:
            return url
        return url

    def woo_json(
        self,
        url: str,
        *,
        method: str,
        payload: dict[str, Any] | None = None,
        timeout: int = 15,
    ) -> Any:
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": basic_auth_header(self.config.woocommerce_consumer_key, self.config.woocommerce_consumer_secret),
        }
        if payload is not None:
            body = json.dumps(payload, default=json_default).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise UpstreamError(f"WooCommerce HTTP {exc.code} for {url}", detail=detail) from exc
        except urllib.error.URLError as exc:
            raise UpstreamError(f"WooCommerce request failed for {url}", detail=str(exc)) from exc

    def plugin_json(
        self,
        url: str,
        *,
        method: str,
        payload: dict[str, Any] | None = None,
        timeout: int = 15,
    ) -> Any:
        body = None
        headers = {
            "Accept": "application/json",
            "X-AgentCart-Merchant-Token": self.config.woocommerce_agentcart_token,
        }
        if payload is not None:
            body = json.dumps(payload, default=json_default).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise UpstreamError(f"AgentCart WooCommerce plugin HTTP {exc.code} for {url}", detail=detail) from exc
        except urllib.error.URLError as exc:
            raise UpstreamError(f"AgentCart WooCommerce plugin request failed for {url}", detail=str(exc)) from exc


class PaymentProvider:
    name = "base"
    protocol = "mpp"
    method = "unsupported"
    intent = "charge"
    currency = "EUR"
    real_settlement = False
    supported = False

    def capability(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "protocol": self.protocol,
            "method": self.method,
            "intent": self.intent,
            "currency": self.currency,
            "real_settlement": self.real_settlement,
            "supported": self.supported,
        }

    def openapi_offer(self, *, max_amount_cents: int) -> dict[str, Any]:
        amount: str | None = str(max(0, max_amount_cents))
        if self.method == "demo":
            amount = None
        return {
            "amount": amount,
            "currency": self.currency,
            "description": "AgentCart checkout for an approved, quote-bound household purchase",
            "intent": self.intent,
            "method": self.method,
        }

    def require_supported(self) -> None:
        if not self.supported:
            raise PaymentProviderUnavailable(
                f"payment provider {self.name} is not implemented/configured in this demo"
            )

    def challenge_fields(self) -> dict[str, Any]:
        self.require_supported()
        return {
            "method": self.method,
            "intent": self.intent,
            "protocol": self.protocol,
            "real_settlement": self.real_settlement,
        }

    def authorization_hint(self, _challenge: dict[str, Any]) -> str | None:
        return None

    def parse_authorization(self, _authorization: str) -> str:
        self.require_supported()
        raise Forbidden("payment authorization is not supported")

    def receipt(
        self,
        *,
        quote: dict[str, Any],
        approval: dict[str, Any],
        challenge: dict[str, Any],
        authorization: str,
    ) -> dict[str, Any]:
        self.require_supported()
        return {
            "id": f"payrcpt_{uuid.uuid4().hex[:16]}",
            "protocol": self.protocol,
            "method": self.method,
            "status": "succeeded",
            "amount_cents": quote["total_cents"],
            "currency": quote["currency"],
            "merchant_id": quote["merchant_id"],
            "quote_id": quote["id"],
            "approval_id": approval["id"],
            "challenge_id": challenge["id"],
            "authorization_hash": hashlib.sha256(authorization.encode()).hexdigest(),
            "receipt_signature": None,
            "real_settlement": self.real_settlement,
            "paid_at": isoformat(utcnow()),
        }


class DemoPaymentProvider(PaymentProvider):
    name = "demo"
    protocol = "mpp"
    method = "demo"
    real_settlement = False
    supported = True

    def authorization_hint(self, challenge: dict[str, Any]) -> str | None:
        return f"Payment demo:{challenge['id']}"

    def parse_authorization(self, authorization: str) -> str:
        if not authorization.startswith("Payment "):
            raise Forbidden("Authorization must use the Payment scheme")
        credential = authorization[len("Payment ") :].strip()
        if not credential.startswith("demo:"):
            raise Forbidden("only demo payment credentials are supported by the demo provider")
        challenge_id = credential[len("demo:") :].strip()
        if not challenge_id:
            raise Forbidden("demo payment credential is missing challenge id")
        return challenge_id

    def receipt(
        self,
        *,
        quote: dict[str, Any],
        approval: dict[str, Any],
        challenge: dict[str, Any],
        authorization: str,
    ) -> dict[str, Any]:
        receipt = super().receipt(
            quote=quote,
            approval=approval,
            challenge=challenge,
            authorization=authorization,
        )
        receipt["protocol"] = "mpp-shaped-demo"
        receipt["receipt_signature"] = "demo-not-a-real-signature"
        return receipt


class DeferredPaymentProvider(PaymentProvider):
    supported = False

    def __init__(self, *, name: str, protocol: str, method: str, endpoint: str = "") -> None:
        self.name = name
        self.protocol = protocol
        self.method = method
        self.endpoint = endpoint
        self.real_settlement = True

    def capability(self) -> dict[str, Any]:
        result = super().capability()
        result["endpoint_configured"] = bool(self.endpoint)
        result["reason"] = "Provider mode is reserved for real settlement integration and fails closed until implemented."
        return result

    def require_supported(self) -> None:
        raise PaymentProviderUnavailable(
            f"{self.name} real settlement is not implemented yet; use AGENTCART_PAYMENT_PROVIDER=demo"
        )


DEFAULT_POLICY = {
    "household_id": "max-household-demo",
    "max_order_total_cents": 2500,
    "monthly_budget_cents": 5000,
    "auto_approve_below_cents": 0,
    "require_human_approval": True,
    "allowed_merchants": ["demo-tea-shop", "woocommerce-demo-tea", "woocommerce-demo-shop"],
    "blocked_merchants": [],
    "allowed_categories": ["grocery.tea", "woocommerce.tea", "woocommerce.personal-care", "woocommerce.household", "woocommerce.coffee"],
    "blocked_categories": ["alcohol", "tobacco", "gift-card", "medicine"],
    "allowed_ship_countries": ["DE"],
    "replay_window_seconds": 300,
}


class AgentCartService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.adapter = DemoTeaShopAdapter()
        self.adapters = self.build_adapters()
        self.payment_provider = self.build_payment_provider()
        self.lock = threading.RLock()
        self.state = self.load_state()
        self.ensure_state_shape()

    def build_adapters(self) -> dict[str, Any]:
        adapters: dict[str, Any] = {self.adapter.merchant["id"]: self.adapter}
        woo = WooCommerceAdapter(self.config)
        if woo.enabled():
            adapters[woo.merchant["id"]] = woo
        return adapters

    def build_payment_provider(self) -> PaymentProvider:
        provider = self.config.payment_provider
        if provider == "demo":
            return DemoPaymentProvider()
        if provider == "tempo_mpp":
            return DeferredPaymentProvider(
                name="tempo_mpp",
                protocol="mpp",
                method="tempo_mpp",
                endpoint=self.config.tempo_mpp_endpoint,
            )
        if provider in {"agentcash", "agentcash_x402"}:
            return DeferredPaymentProvider(
                name="agentcash_x402",
                protocol="x402",
                method="agentcash",
                endpoint=self.config.agentcash_proof_url,
            )
        raise RuntimeError(f"Unsupported AGENTCART_PAYMENT_PROVIDER: {provider}")

    def load_state(self) -> dict[str, Any]:
        if not self.config.state_path.exists():
            return {}
        try:
            return json.loads(self.config.state_path.read_text())
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid AgentCart state file: {self.config.state_path}") from exc

    def save_state(self) -> None:
        self.config.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.config.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True, default=json_default) + "\n")
        tmp.replace(self.config.state_path)

    def ensure_state_shape(self) -> None:
        with self.lock:
            self.state.setdefault("quotes", {})
            self.state.setdefault("approvals", {})
            self.state.setdefault("orders", {})
            self.state.setdefault("energy_offers", {})
            self.state.setdefault("challenges", {})
            self.state.setdefault("idempotency", {})
            self.state.setdefault("audit_tail", [])
            stock = self.state.setdefault("stock", {})
            for adapter in self.adapters.values():
                for product_id, quantity in adapter.initial_stock().items():
                    stock.setdefault(product_id, int(quantity))
            self.save_state()

    def expire_stale_approvals_locked(self) -> bool:
        changed = False
        now = utcnow()
        for approval in self.state.get("approvals", {}).values():
            if approval.get("state") != "pending":
                continue
            try:
                expires_at = parse_time(str(approval.get("expires_at") or ""))
            except ValueError:
                continue
            if expires_at < now:
                approval["state"] = "expired"
                changed = True
        return changed

    def read_policy(self) -> dict[str, Any]:
        if not self.config.policy_path:
            return dict(DEFAULT_POLICY)
        try:
            policy = json.loads(self.config.policy_path.read_text())
        except FileNotFoundError:
            return dict(DEFAULT_POLICY)
        merged = dict(DEFAULT_POLICY)
        merged.update(policy)
        return merged

    def audit(
        self,
        event_type: str,
        *,
        actor: str,
        reason: str,
        purchase_id: str | None = None,
        refs: dict[str, Any] | None = None,
        policy_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "id": f"audit_{uuid.uuid4().hex[:16]}",
            "event_type": event_type,
            "actor": actor,
            "reason": reason,
            "purchase_id": purchase_id,
            "refs": refs or {},
            "policy_result": policy_result,
            "timestamp": isoformat(utcnow()),
        }
        self.config.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config.audit_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, default=json_default) + "\n")
        with self.lock:
            tail = self.state.setdefault("audit_tail", [])
            tail.append(event)
            del tail[:-100]
            self.save_state()
        return event

    def list_audit_events(self, purchase_id: str | None = None) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if self.config.audit_log_path.exists():
            for line in self.config.audit_log_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if purchase_id is None or event.get("purchase_id") == purchase_id:
                    events.append(event)
        if not events:
            for event in self.state.get("audit_tail", []):
                if purchase_id is None or event.get("purchase_id") == purchase_id:
                    events.append(event)
        return events[-200:]

    def registry_document(self) -> dict[str, Any]:
        entries = []
        for adapter in self.adapters.values():
            merchant = adapter.merchant
            manifest_url = self.registry_manifest_url(adapter)
            shipping_countries = self.registry_shipping_countries(adapter)
            manifest_basis = {
                "merchant_id": merchant["id"],
                "manifest_url": manifest_url,
                "protocols": ["agentcart-shopbridge", self.payment_provider.protocol],
                "payment_network": self.config.tempo_mpp_network,
                "payment_recipient": self.config.tempo_mpp_recipient_address,
                "shipping_countries": shipping_countries,
            }
            manifest_hash = hashlib.sha256(
                json.dumps(manifest_basis, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            parsed = urllib.parse.urlparse(manifest_url)
            entries.append(
                {
                    "merchant_id": merchant["id"],
                    "name": merchant["name"],
                    "adapter_type": getattr(adapter, "adapter_type", "unknown"),
                    "domain": parsed.netloc or "local-demo",
                    "manifest_url": manifest_url,
                    "manifest_hash_alg": "sha-256",
                    "manifest_hash": manifest_hash,
                    "supported_protocols": ["agentcart-shopbridge", self.payment_provider.protocol],
                    "payment": {
                        "network": self.config.tempo_mpp_network,
                        "recipient": self.config.tempo_mpp_recipient_address or None,
                        "recipient_configured": bool(self.config.tempo_mpp_recipient_address),
                    },
                    "delivery": {
                        "ship_to_countries": shipping_countries,
                    },
                    "ranking": {
                        "paid_placement": False,
                        "role": "identity_anchor_only",
                    },
                    "merchant_of_record": merchant["merchant_of_record"],
                    "terms_url": merchant.get("terms_url"),
                    "returns_url": merchant.get("returns_url"),
                }
            )
        entries.sort(key=lambda entry: entry["name"])
        return {
            "registry": {
                "name": "AgentCart demo merchant registry",
                "scope": "identity_and_integrity_anchor",
                "public_data_only": True,
                "no_catalog_prices_or_household_demand_onchain": True,
            },
            "entries": entries,
            "market_design": {
                "discovery": "public registry plus well-known manifests",
                "competition": "private quote requests to selected merchants",
                "ranking": "user-owned policy; no hidden sponsored ranking",
                "payment": "MPP/x402-style proof bound to quote hash and merchant terms",
            },
        }

    def registry_manifest_url(self, adapter: Any) -> str:
        if getattr(adapter, "adapter_type", "") == "woocommerce" and self.config.woocommerce_base_url:
            return f"{self.config.woocommerce_base_url}/.well-known/agentcart.json"
        return f"{self.config.public_url}/.well-known/agentcart.json#{adapter.merchant['id']}"

    def registry_shipping_countries(self, adapter: Any) -> list[str]:
        try:
            products = adapter.search_products("", self.state.get("stock", {}))
        except Exception:
            products = []
        countries = sorted(
            {
                str(country).upper()
                for product in products
                for country in (product.get("shipping_regions") or [])
                if country
            }
        )
        return countries or [self.config.default_ship_country]

    def quote_tournament(self, request: dict[str, Any]) -> dict[str, Any]:
        query = str(request.get("query") or request.get("q") or "tea").strip() or "tea"
        catalog_query = catalog_query_for_intent(query)
        quantity = safe_int(request.get("quantity", 1), field="quantity", minimum=1, maximum=20)
        country = str(request.get("country") or request.get("ship_country") or self.config.default_ship_country).upper()
        postal_code = str(request.get("postal_code") or self.config.default_ship_postal_code)
        max_candidates = safe_int(request.get("max_candidates", 6), field="max_candidates", minimum=1, maximum=12)
        catalog = self.search_catalog(catalog_query)
        registry_entries = {entry["merchant_id"]: entry for entry in self.registry_document()["entries"]}
        candidates = []
        rejected = []
        seen: set[str] = set()
        for product in catalog["products"]:
            product_id = str(product.get("id") or product.get("product_id") or "")
            if not product_id or product_id in seen:
                continue
            seen.add(product_id)
            if not product.get("eligible_for_agent_checkout", True):
                rejected.append({"product_id": product_id, "reason": "product is not eligible for agent checkout"})
                continue
            shipping_regions = [str(value).upper() for value in product.get("shipping_regions") or []]
            if shipping_regions and country not in shipping_regions:
                rejected.append(
                    {
                        "product_id": product_id,
                        "title": product.get("title"),
                        "merchant_id": product.get("merchant_id"),
                        "reason": f"merchant does not ship to {country}",
                    }
                )
                continue
            try:
                quote = self.create_quote(
                    {
                        "agent_id": "agentcart-quote-tournament",
                        "reason": f"private quote competition for '{query}'",
                        "items": [{"product_id": product_id, "quantity": quantity}],
                        "ship_to": {"country": country, "postal_code": postal_code},
                        "idempotency_key": f"tournament-{uuid.uuid4().hex[:10]}",
                    }
                )
            except AgentCartError as exc:
                rejected.append(
                    {
                        "product_id": product_id,
                        "title": product.get("title"),
                        "merchant_id": product.get("merchant_id"),
                        "reason": str(exc),
                        "detail": exc.detail,
                    }
                )
                continue
            policy = quote.get("policy_result", {})
            delivery = quote.get("delivery_window") or {}
            registry_entry = registry_entries.get(quote["merchant_id"], {})
            payment_requirements = (
                quote.get("payment_requirements")
                if isinstance(quote.get("payment_requirements"), dict)
                else {}
            )
            payment_protocols = (
                payment_requirements.get("protocols")
                if isinstance(payment_requirements.get("protocols"), list)
                else []
            )
            settlement_asset = next(
                (
                    protocol.get("settlement_asset")
                    for protocol in payment_protocols
                    if isinstance(protocol, dict) and isinstance(protocol.get("settlement_asset"), dict)
                ),
                None,
            )
            payment_methods = [
                str(protocol.get("method") or protocol.get("protocol") or protocol.get("id") or "unknown")
                for protocol in payment_protocols
                if isinstance(protocol, dict)
            ]
            candidate = {
                "quote_id": quote["id"],
                "merchant_id": quote["merchant_id"],
                "merchant_name": quote["merchant"]["name"],
                "product_id": quote["items"][0]["product_id"],
                "product_title": quote["items"][0]["title"],
                "quantity": quantity,
                "total_cents": quote["total_cents"],
                "currency": quote["currency"],
                "delivery_window": delivery,
                "policy_result": policy,
                "payment_requirements": payment_requirements,
                "payment_summary": {
                    "quote_currency": quote.get("currency"),
                    "methods": payment_methods or [self.payment_provider.protocol],
                    "settlement_asset": settlement_asset,
                },
                "registry": {
                    "manifest_url": registry_entry.get("manifest_url"),
                    "manifest_hash": registry_entry.get("manifest_hash"),
                    "paid_placement": False,
                },
                "rank_reasons": self.quote_rank_reasons(quote, registry_entry),
            }
            candidates.append(candidate)
            if len(candidates) >= max_candidates:
                break
        candidates.sort(
            key=lambda candidate: (
                candidate["policy_result"].get("decision") == "deny",
                int(candidate["total_cents"]),
                str(candidate.get("delivery_window", {}).get("latest_date") or "9999-12-31"),
                str(candidate["merchant_name"]),
            )
        )
        for index, candidate in enumerate(candidates, start=1):
            candidate["rank"] = index
            candidate["winner"] = index == 1 and candidate["policy_result"].get("decision") != "deny"
        winner = next((candidate for candidate in candidates if candidate.get("winner")), None)
        return {
            "query": query,
            "catalog_query": catalog_query,
            "ship_to": {"country": country, "postal_code": postal_code},
            "quantity": quantity,
            "market_design": {
                "registry_role": "public identity anchor",
                "quote_request": "private RFQ to selected merchants",
                "ranking": "local user policy, total price, delivery window; no paid placement",
            },
            "candidates": candidates,
            "winner": winner,
            "rejected": rejected,
        }

    def quote_rank_reasons(self, quote: dict[str, Any], registry_entry: dict[str, Any]) -> list[str]:
        reasons = [
            f"final total {money(int(quote['total_cents']), quote['currency'])}",
            f"policy decision {quote.get('policy_result', {}).get('decision', 'unknown')}",
        ]
        delivery = quote.get("delivery_window") or {}
        if delivery.get("latest_date"):
            reasons.append(f"merchant ETA by {delivery['latest_date']}")
        if registry_entry.get("manifest_hash"):
            reasons.append("merchant manifest hash is registered")
        reasons.append("no paid ranking signal used")
        return reasons

    def capability_document(self) -> dict[str, Any]:
        return {
            "name": "AgentCart",
            "version": "0.2.0",
            "description": "Household-safe merchant adapter for agent-compatible checkout.",
            "capabilities": {
                "catalog_search": True,
                "quote": True,
                "policy_evaluation": True,
                "human_approval": {
                    "portable": True,
                    "decision_api": "/v1/approvals/{approval_id}/decision",
                    "channels": ["api", "web", "chat", "home_assistant", "external"],
                    "home_assistant_optional": bool(
                        self.config.homeassistant_url
                        and self.config.homeassistant_token
                        and self.config.ha_notify_services
                    ),
                },
                "checkout": {
                    "payment_auth_scheme": "Payment",
                    "mpp_http_auth_shape": self.payment_provider.protocol == "mpp",
                    "mpp_production_provider_configured": self.payment_provider.name != "demo",
                    "provider": self.payment_provider.capability(),
                    "methods": [self.payment_provider.method],
                    "intents": ["charge"],
                    "notes": [
                        "Checkout uses HTTP 402, WWW-Authenticate: Payment, Authorization: Payment, request digest binding, idempotency, and Payment-Receipt.",
                        "The default demo provider is not a production MPP payment method; Tempo MPP value proof is attached separately when configured.",
                    ],
                },
                "orders": True,
                "audit_log": True,
                "open_tasks": bool(self.config.vikunja_api_url and self.config.vikunja_token),
                "energy_surplus_check": bool(self.config.homeassistant_url and self.config.homeassistant_token),
                "energy_offer_demo": {
                    "enabled": bool(self.config.homeassistant_url and self.config.homeassistant_token),
                    "settlement_scope": "demo_payment_proof_only_no_physical_grid_settlement",
                    "requires_compliant_energy_sharing_stack": True,
                },
                "delivery_calendar": {
                    "home_assistant_write": bool(
                        self.config.homeassistant_url
                        and self.config.homeassistant_token
                        and self.config.homeassistant_calendar_entity_id
                    ),
                    "ics_feed": self.config.delivery_calendar_enabled,
                },
            },
            "endpoints": {
                "catalog_search": "/v1/catalog/search?q=tea",
                "quote": "/v1/quotes",
                "approval": "/v1/approvals",
                "checkout": "/v1/checkout",
                "orders": "/v1/orders/{order_id}",
                "audit": "/v1/audit/{purchase_id}",
                "openapi": "/openapi.json",
                "llms": "/llms.txt",
                "registry": "/v1/registry",
                "quote_tournament": "/v1/quote-tournament?q=tea&country=DE",
                "integrations": "/v1/integrations/status",
                "open_tasks": "/v1/tasks/open?limit=20",
                "energy_surplus": "/v1/energy/surplus",
                "energy_offers": "/v1/energy/offers",
                "delivery_calendar": DELIVERY_CALENDAR_ROUTE,
            },
            "merchant_adapters": [
                {
                    "id": adapter.merchant["id"],
                    "name": adapter.merchant["name"],
                    "type": adapter.adapter_type,
                }
                for adapter in self.adapters.values()
            ],
            "safety": {
                "requires_policy_check": True,
                "supports_portable_approval": True,
                "supports_home_assistant_approval": True,
                "quote_expiry_seconds": QUOTE_TTL_SECONDS,
                "challenge_expiry_seconds": CHALLENGE_TTL_SECONDS,
                "idempotency_required_for_checkout": True,
                "merchant_of_record_remains_merchant": True,
            },
        }

    def openapi_document(self) -> dict[str, Any]:
        policy = self.read_policy()
        max_order = int(policy.get("max_order_total_cents", 2500))
        security = [{"AgentCartToken": []}, {"BearerAuth": []}]
        return {
            "openapi": "3.1.0",
            "info": {
                "title": "AgentCart Household Commerce Bridge",
                "version": "0.2.0",
                "description": (
                    "AgentCart exposes opt-in merchant catalog, quote, policy, approval, "
                    "checkout, order, and audit endpoints for household agents."
                ),
                "x-guidance": (
                    "Use catalog search to find eligible products, create a quote for a final "
                    "tax/shipping-inclusive price, request explicit human approval, then call "
                    "checkout. Do not scrape third-party shops or bypass approval."
                ),
            },
            "x-service-info": {
                "categories": ["commerce", "household", "agentic-commerce"],
                "docs": {
                    "homepage": self.config.public_url,
                    "apiReference": "/openapi.json",
                    "llms": "/llms.txt",
                },
            },
            "servers": [{"url": self.config.public_url}],
            "security": security,
            "paths": {
                "/.well-known/agentcart.json": {
                    "get": {
                        "operationId": "getAgentCartCapabilities",
                        "summary": "Get AgentCart capability document",
                        "security": [],
                        "responses": {"200": {"description": "Capabilities"}},
                    }
                },
                "/llms.txt": {
                    "get": {
                        "operationId": "getAgentCartLlmsText",
                        "summary": "Get human-readable agent guidance",
                        "security": [],
                        "responses": {"200": {"description": "Agent guidance"}},
                    }
                },
                "/v1/catalog/search": {
                    "get": {
                        "operationId": "searchCatalog",
                        "summary": "Search opt-in merchant catalog",
                        "parameters": [
                            {
                                "name": "q",
                                "in": "query",
                                "schema": {"type": "string"},
                                "description": "Natural-language search query such as 'buy woo tea'.",
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "Catalog search results",
                                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CatalogSearchResult"}}},
                            },
                            "401": {"description": "AgentCart token required"},
                        },
                    }
                },
                "/v1/registry": {
                    "get": {
                        "operationId": "getMerchantRegistry",
                        "summary": "Get public merchant identity and manifest-integrity registry",
                        "security": [],
                        "responses": {
                            "200": {
                                "description": "Merchant registry",
                                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/MerchantRegistry"}}},
                            }
                        },
                    }
                },
                "/v1/quote-tournament": {
                    "get": {
                        "operationId": "runQuoteTournament",
                        "summary": "Run a private quote competition across eligible merchants",
                        "parameters": [
                            {"name": "q", "in": "query", "schema": {"type": "string"}, "description": "Product search query"},
                            {"name": "country", "in": "query", "schema": {"type": "string"}, "description": "Destination country code"},
                            {"name": "postal_code", "in": "query", "schema": {"type": "string"}, "description": "Destination postal code"},
                            {"name": "quantity", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 20}},
                        ],
                        "responses": {
                            "200": {
                                "description": "Ranked quote candidates",
                                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/QuoteTournament"}}},
                            },
                            "401": {"description": "AgentCart token required"},
                        },
                    }
                },
                "/v1/quotes": {
                    "post": {
                        "operationId": "createQuote",
                        "summary": "Create final quote with VAT, shipping, stock, policy result, and merchant-of-record",
                        "requestBody": {
                            "required": True,
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CreateQuoteRequest"}}},
                        },
                        "responses": {
                            "201": {
                                "description": "Quote",
                                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Quote"}}},
                            },
                            "409": {"description": "Stock or quote conflict"},
                        },
                    }
                },
                "/v1/quotes/{quote_id}": {
                    "get": {
                        "operationId": "getQuote",
                        "summary": "Get an existing quote by id",
                        "parameters": [{"name": "quote_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                        "responses": {
                            "200": {
                                "description": "Quote",
                                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Quote"}}},
                            },
                            "404": {"description": "Unknown quote"},
                        },
                    }
                },
                "/v1/approvals": {
                    "post": {
                        "operationId": "createApproval",
                        "summary": "Create a portable human consent request for a quote",
                        "requestBody": {
                            "required": True,
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CreateApprovalRequest"}}},
                        },
                        "responses": {
                            "201": {
                                "description": "Approval request",
                                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Approval"}}},
                            },
                            "403": {"description": "Policy denied quote"},
                        },
                    }
                },
                "/v1/approvals/{approval_id}/decision": {
                    "post": {
                        "operationId": "decideApproval",
                        "summary": "Approve or reject a pending quote",
                        "parameters": [{"name": "approval_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                        "requestBody": {
                            "required": True,
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApprovalDecisionRequest"}}},
                        },
                        "responses": {
                            "200": {"description": "Updated approval"},
                            "403": {"description": "Invalid approval token"},
                        },
                    }
                },
                "/v1/checkout": {
                    "post": {
                        "operationId": "checkout",
                        "summary": "Checkout an approved quote through the configured payment provider",
                        "x-payment-info": {
                            "offers": [self.payment_provider.openapi_offer(max_amount_cents=max_order)],
                        },
                        "x-agentcart-payment-provider": self.payment_provider.capability(),
                        "x-agentcart-price": {
                            "mode": "dynamic_quote_bound",
                            "currency": "EUR",
                            "max_cents": max_order,
                            "note": "Final amount comes from the approved quote; demo provider advertises null amount because it is not real settlement.",
                        },
                        "requestBody": {
                            "required": True,
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CheckoutRequest"}}},
                        },
                        "responses": {
                            "201": {
                                "description": "Order accepted and payment receipt returned",
                                "headers": {
                                    "Payment-Receipt": {
                                        "description": "Base64url JSON payment receipt",
                                        "schema": {"type": "string"},
                                    }
                                },
                                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CheckoutResponse"}}},
                            },
                            "402": {"description": "Payment Required; retry with Authorization: Payment"},
                            "403": {"description": "Approval or payment credential rejected"},
                        },
                    }
                },
                "/v1/orders/{order_id}": {
                    "get": {
                        "operationId": "getOrder",
                        "summary": "Get order state",
                        "parameters": [{"name": "order_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                        "responses": {"200": {"description": "Order"}},
                    }
                },
                "/v1/audit/{purchase_id}": {
                    "get": {
                        "operationId": "getAuditLog",
                        "summary": "Get audit log for a quote/purchase",
                        "parameters": [{"name": "purchase_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                        "responses": {"200": {"description": "Audit events"}},
                    }
                },
                "/v1/integrations/status": {
                    "get": {
                        "operationId": "getIntegrationStatus",
                        "summary": "Get Home Assistant, Vikunja, AgentCash, and payment-provider readiness",
                        "responses": {"200": {"description": "Integration status"}},
                    }
                },
                "/v1/tasks/open": {
                    "get": {
                        "operationId": "listOpenTasks",
                        "summary": "List open Vikunja tasks for household-agent context",
                        "parameters": [
                            {
                                "name": "limit",
                                "in": "query",
                                "schema": {"type": "integer", "minimum": 1, "maximum": 100},
                            }
                        ],
                        "responses": {"200": {"description": "Open tasks"}},
                    }
                },
                "/v1/energy/surplus": {
                    "get": {
                        "operationId": "getEnergySurplus",
                        "summary": "Read Home Assistant energy telemetry and decide whether surplus is offerable",
                        "responses": {"200": {"description": "Energy surplus decision"}},
                    }
                },
                "/v1/energy/offers": {
                    "get": {
                        "operationId": "listEnergyOffers",
                        "summary": "List demo household energy offers",
                        "responses": {"200": {"description": "Energy offers"}},
                    },
                    "post": {
                        "operationId": "createEnergyOffer",
                        "summary": "Create a short-lived demo energy-sharing offer from current Home Assistant telemetry",
                        "requestBody": {
                            "required": False,
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CreateEnergyOfferRequest"}}},
                        },
                        "responses": {
                            "201": {
                                "description": "Energy offer",
                                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/EnergyOffer"}}},
                            },
                            "409": {"description": "Current household telemetry is not offerable"},
                        },
                    },
                },
                "/v1/energy/offers/{offer_id}": {
                    "get": {
                        "operationId": "getEnergyOffer",
                        "summary": "Get one demo energy-sharing offer",
                        "parameters": [{"name": "offer_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                        "responses": {"200": {"description": "Energy offer"}},
                    }
                },
                "/v1/energy/offers/{offer_id}/accept": {
                    "post": {
                        "operationId": "acceptEnergyOffer",
                        "summary": "Accept a demo energy offer and attach an MPP-compatible value proof",
                        "parameters": [{"name": "offer_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                        "requestBody": {
                            "required": False,
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AcceptEnergyOfferRequest"}}},
                        },
                        "responses": {
                            "200": {
                                "description": "Accepted offer with demo settlement receipt",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "offer": {"$ref": "#/components/schemas/EnergyOffer"},
                                                "settlement": {"$ref": "#/components/schemas/EnergySettlement"},
                                            },
                                        }
                                    }
                                },
                            },
                            "409": {"description": "Offer expired or no longer open"},
                        },
                    }
                },
                DELIVERY_CALENDAR_ROUTE: {
                    "get": {
                        "operationId": "getDeliveryCalendarFeed",
                        "summary": "Get token-protected read-only AgentCart delivery calendar feed",
                        "security": [],
                        "parameters": [
                            {"name": "token", "in": "query", "required": True, "schema": {"type": "string"}}
                        ],
                        "responses": {"200": {"description": "ICS calendar feed"}},
                    }
                },
            },
            "components": {
                "securitySchemes": {
                    "AgentCartToken": {"type": "apiKey", "in": "header", "name": "X-AgentCart-Token"},
                    "BearerAuth": {"type": "http", "scheme": "bearer"},
                },
                "schemas": self.openapi_schemas(),
            },
        }

    def openapi_schemas(self) -> dict[str, Any]:
        money_fields = {
            "amount_cents": {"type": "integer"},
            "currency": {"type": "string"},
        }
        return {
            "CatalogSearchResult": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "products": {"type": "array", "items": {"$ref": "#/components/schemas/Product"}},
                    "merchants": {"type": "array", "items": {"$ref": "#/components/schemas/Merchant"}},
                },
                "required": ["query", "products", "merchants"],
            },
            "Product": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "merchant_id": {"type": "string"},
                    "sku": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "brand": {"type": "string"},
                    "unit_size": {"type": "string"},
                    "availability": {"type": "string"},
                    "stock": {"type": "integer"},
                    "eligible_for_agent_checkout": {"type": "boolean"},
                    "price_hint": {"type": "object", "properties": money_fields},
                },
                "required": ["id", "merchant_id", "title", "category", "availability", "eligible_for_agent_checkout"],
            },
            "Merchant": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "merchant_of_record": {"type": "object"},
                    "terms_url": {"type": "string"},
                    "returns_url": {"type": "string"},
                },
                "required": ["id", "name", "merchant_of_record"],
            },
            "MerchantRegistry": {
                "type": "object",
                "properties": {
                    "registry": {"type": "object"},
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "merchant_id": {"type": "string"},
                                "name": {"type": "string"},
                                "domain": {"type": "string"},
                                "manifest_url": {"type": "string"},
                                "manifest_hash": {"type": "string"},
                                "supported_protocols": {"type": "array", "items": {"type": "string"}},
                                "delivery": {"type": "object"},
                                "ranking": {"type": "object"},
                            },
                        },
                    },
                    "market_design": {"type": "object"},
                },
                "required": ["registry", "entries", "market_design"],
            },
            "QuoteTournament": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "catalog_query": {"type": "string"},
                    "ship_to": {"type": "object"},
                    "quantity": {"type": "integer"},
                    "market_design": {"type": "object"},
                    "candidates": {"type": "array", "items": {"type": "object"}},
                    "winner": {"type": ["object", "null"]},
                    "rejected": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["query", "catalog_query", "ship_to", "quantity", "market_design", "candidates", "winner", "rejected"],
            },
            "CreateQuoteRequest": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "string"},
                                "quantity": {"type": "integer", "minimum": 1},
                            },
                            "required": ["product_id", "quantity"],
                        },
                    },
                    "ship_to": {
                        "type": "object",
                        "properties": {
                            "country": {"type": "string"},
                            "postal_code": {"type": "string"},
                        },
                    },
                },
                "required": ["items", "reason"],
            },
            "Quote": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "merchant": {"$ref": "#/components/schemas/Merchant"},
                    "items": {"type": "array", "items": {"type": "object"}},
                    "subtotal_cents": {"type": "integer"},
                    "shipping": {"type": "object"},
                    "vat_lines": {"type": "array", "items": {"type": "object"}},
                    "total_cents": {"type": "integer"},
                    "currency": {"type": "string"},
                    "policy_result": {"$ref": "#/components/schemas/PolicyResult"},
                    "delivery_window": {"type": "object"},
                    "expires_at": {"type": "string"},
                },
                "required": ["id", "merchant", "items", "total_cents", "currency", "policy_result", "expires_at"],
            },
            "PolicyResult": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string", "enum": ["allow", "requires_approval", "deny"]},
                    "requires_approval": {"type": "boolean"},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["decision", "requires_approval", "reasons"],
            },
            "CreateApprovalRequest": {
                "type": "object",
                "properties": {
                    "quote_id": {"type": "string"},
                    "channel": {"type": "string"},
                    "delivery_channels": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["api", "web", "chat", "home_assistant", "external"]},
                    },
                },
                "required": ["quote_id"],
            },
            "Approval": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "quote_id": {"type": "string"},
                    "state": {"type": "string", "enum": ["pending", "approved", "rejected", "expired"]},
                    "channel": {"type": "string"},
                    "delivery_channels": {"type": "array", "items": {"type": "string"}},
                    "decision_url": {"type": "string"},
                    "decision_api": {"type": "object"},
                    "consent_request": {"type": "object"},
                    "expires_at": {"type": "string"},
                },
                "required": ["id", "quote_id", "state", "expires_at"],
            },
            "ApprovalDecisionRequest": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string", "enum": ["approved", "rejected"]},
                    "token": {"type": "string"},
                    "approver": {"type": "string"},
                },
                "required": ["decision", "token"],
            },
            "CheckoutRequest": {
                "type": "object",
                "properties": {
                    "quote_id": {"type": "string"},
                    "approval_id": {"type": "string"},
                    "idempotency_key": {"type": "string"},
                },
                "required": ["quote_id", "approval_id", "idempotency_key"],
            },
            "CheckoutResponse": {
                "type": "object",
                "properties": {
                    "order": {"$ref": "#/components/schemas/Order"},
                    "payment_receipt": {"$ref": "#/components/schemas/PaymentReceipt"},
                },
                "required": ["order", "payment_receipt"],
            },
            "PaymentReceipt": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "protocol": {"type": "string"},
                    "method": {"type": "string"},
                    "status": {"type": "string"},
                    "real_settlement": {"type": "boolean"},
                    "amount_cents": {"type": "integer"},
                    "currency": {"type": "string"},
                },
                "required": ["id", "protocol", "method", "status", "amount_cents", "currency"],
            },
            "CreateEnergyOfferRequest": {
                "type": "object",
                "properties": {
                    "price_cents_per_kwh": {"type": "integer", "minimum": 1, "maximum": 80},
                    "market_reference_cents_per_kwh": {"type": "integer", "minimum": 1, "maximum": 100},
                    "feed_in_reference_cents_per_kwh": {"type": "integer", "minimum": 0, "maximum": 80},
                    "duration_minutes": {"type": "integer", "minimum": 5, "maximum": 120},
                    "valid_minutes": {"type": "integer", "minimum": 1, "maximum": 60},
                    "buyer_scope": {"type": "string"},
                    "seller_household_id": {"type": "string"},
                },
            },
            "AcceptEnergyOfferRequest": {
                "type": "object",
                "properties": {
                    "buyer_id": {"type": "string"},
                    "buyer_display_name": {"type": "string"},
                    "accepted_kwh": {"type": "number", "minimum": 0.001},
                },
            },
            "EnergyOffer": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "state": {"type": "string", "enum": ["open", "accepting", "accepted", "expired"]},
                    "commodity": {"type": "string"},
                    "quantity_kwh": {"type": "number"},
                    "price_cents_per_kwh": {"type": "integer"},
                    "estimated_total_cents": {"type": "integer"},
                    "currency": {"type": "string"},
                    "valid_until": {"type": "string"},
                    "telemetry_snapshot": {"type": "object"},
                    "legal_scope": {"type": "object"},
                    "settlement": {"$ref": "#/components/schemas/EnergySettlement"},
                },
                "required": ["id", "state", "commodity", "quantity_kwh", "price_cents_per_kwh", "currency", "valid_until"],
            },
            "EnergySettlement": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "offer_id": {"type": "string"},
                    "state": {"type": "string"},
                    "accepted_kwh": {"type": "number"},
                    "amount_cents": {"type": "integer"},
                    "currency": {"type": "string"},
                    "payment_receipt": {"$ref": "#/components/schemas/PaymentReceipt"},
                    "legal_settlement": {"type": "boolean"},
                    "physical_delivery": {"type": "boolean"},
                },
            },
            "Order": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "merchant_order_id": {"type": "string"},
                    "quote_id": {"type": "string"},
                    "approval_id": {"type": "string"},
                    "state": {"type": "string"},
                    "delivery_window": {"type": "object"},
                    "shipment": {"type": "object"},
                    "calendar_event": {"type": "object"},
                    "payment_receipt": {"$ref": "#/components/schemas/PaymentReceipt"},
                },
                "required": ["id", "quote_id", "approval_id", "state", "payment_receipt"],
            },
        }

    def llms_text(self) -> str:
        provider = self.payment_provider.capability()
        return f"""# AgentCart

AgentCart is a household-controlled commerce bridge for local agents.

Base URL: {self.config.public_url}

Use it for opt-in household purchases only. Do not scrape third-party shops.

Recommended flow:
0. If asked about household context, list open tasks: GET /v1/tasks/open?limit=20
1. Search catalog: GET /v1/catalog/search?q=tea
   - "my favorite tea" resolves to Hazel's Chocolate Tea.
2. Optional but recommended: inspect opt-in merchants and compare private final quotes:
   - GET /v1/registry
   - GET /v1/quote-tournament?q=tea&country=DE
3. Create quote: POST /v1/quotes
4. Request human approval: POST /v1/approvals
   - Approval is portable: render consent_request in chat, mobile, web, or home automation.
5. Wait for explicit approval by chat, Home Assistant, or approval page.
6. Checkout approved quote: POST /v1/checkout
7. On 402, retry with Authorization: Payment credential.
8. Read order, delivery window, shipment status, calendar sync state, and audit log.

Safety rules:
- A quote can only contain one merchant in this MVP.
- Policy is evaluated at quote and checkout.
- Human approval is required by default and can be delivered by API, web, chat, or Home Assistant.
- Merchant remains merchant of record.
- Payment provider: {provider["name"]}
- Real settlement: {str(provider["real_settlement"]).lower()}
- Provider supported: {str(provider["supported"]).lower()}
- Delivery calendar feed: {DELIVERY_CALENDAR_ROUTE}

Discovery:
- OpenAPI: /openapi.json
- Capabilities: /.well-known/agentcart.json

Current caveat:
The default demo provider follows the HTTP 402 Payment-auth shape but does not move real funds. Use a real
Tempo MPP or AgentCash/x402 provider only after explicit configuration and a
separate human confirmation.
"""

    def integration_status(self) -> dict[str, Any]:
        return {
            "home_assistant": {
                "configured": bool(self.config.homeassistant_url and self.config.homeassistant_token),
                "url": self.config.homeassistant_url or None,
                "notify_services": list(self.config.ha_notify_services),
                "approval_notifications_ready": bool(
                    self.config.homeassistant_url
                    and self.config.homeassistant_token
                    and self.config.ha_notify_services
                ),
                "calendar_entity_id": self.config.homeassistant_calendar_entity_id or None,
                "delivery_calendar_write_ready": bool(
                    self.config.homeassistant_url
                    and self.config.homeassistant_token
                    and self.config.homeassistant_calendar_entity_id
                ),
            },
            "delivery_calendar": {
                "ics_enabled": self.config.delivery_calendar_enabled,
                "token_configured": bool(self.config.delivery_calendar_token),
                "path": DELIVERY_CALENDAR_ROUTE,
            },
            "energy": {
                "configured": bool(self.config.homeassistant_url and self.config.homeassistant_token),
                "surplus_check_ready": bool(self.config.homeassistant_url and self.config.homeassistant_token),
                "entities": {
                    "solar_power": self.config.energy_solar_power_entity or None,
                    "battery_level": self.config.energy_battery_level_entity or None,
                    "battery_power": self.config.energy_battery_power_entity or None,
                    "grid_export": self.config.energy_grid_export_entity or None,
                    "grid_import": self.config.energy_grid_import_entity or None,
                    "house_output": self.config.energy_house_output_entity or None,
                },
                "thresholds": {
                    "min_export_w": self.config.energy_min_export_w,
                    "min_battery_percent": self.config.energy_min_battery_percent,
                },
            },
            "vikunja": {
                "configured": bool(
                    self.config.vikunja_api_url
                    and self.config.vikunja_token
                    and self.config.vikunja_project_id is not None
                ),
                "api_url": self.config.vikunja_api_url or None,
                "web_url": self.config.vikunja_web_url or None,
                "project_id": self.config.vikunja_project_id,
                "open_tasks_ready": bool(self.config.vikunja_api_url and self.config.vikunja_token),
            },
            "agentcash": {
                "proof_configured": bool(self.config.agentcash_proof_url),
                "proof_required": self.config.agentcash_proof_required,
                "proof_url": self.config.agentcash_proof_url or None,
                "command": self.config.agentcash_command,
                "command_available": command_available(self.config.agentcash_command),
                "timeout_seconds": self.config.agentcash_timeout_seconds,
            },
            "tempo_mpp": {
                "proof_configured": bool(self.config.tempo_mpp_proof_url),
                "proof_required": self.config.tempo_mpp_proof_required,
                "proof_url": self.config.tempo_mpp_proof_url or None,
                "command": self.config.tempo_mpp_command,
                "command_available": command_available(self.config.tempo_mpp_command),
                "account": self.config.tempo_mpp_account or None,
                "network": self.config.tempo_mpp_network,
                "settlement_asset": tempo_default_settlement_asset(self.config.tempo_mpp_network),
                "recipient_configured": bool(self.config.tempo_mpp_recipient_address),
                "recipient_address": self.config.tempo_mpp_recipient_address or None,
                "timeout_seconds": self.config.tempo_mpp_timeout_seconds,
                "quote_currency_note": "Merchant quotes stay in their store currency, currently EUR in the demo. The Tempo proof is a separate USD-stablecoin testnet proof unless a production verifier performs quote-bound FX/settlement.",
                "note": "Self-serve testnet payments use mppx and pathUSD. Stripe SPT/card acceptance still requires Stripe profile and payment-method access.",
            },
            "payment": {
                "provider": self.payment_provider.capability(),
            },
        }

    def create_tempo_mpp_value_proof(self, quote: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
        if not self.config.tempo_mpp_proof_url:
            return {"state": "skipped", "reason": "Tempo MPP proof URL is not configured"}
        started = utcnow()
        if self.config.tempo_mpp_proof_url.startswith("mock://"):
            return {
                "state": "succeeded",
                "provider": "tempo_mpp",
                "mode": "mock",
                "network": self.config.tempo_mpp_network,
                "settlement_asset": tempo_default_settlement_asset(self.config.tempo_mpp_network),
                "quote_currency": quote.get("currency"),
                "quote_total_cents": quote.get("total_cents"),
                "real_settlement": False,
                "value_transfer": False,
                "settlement_note": "Mock proof only; no EUR merchant settlement and no USD-stablecoin value transfer.",
                "url": self.config.tempo_mpp_proof_url,
                "quote_id": quote["id"],
                "approval_id": approval["id"],
                "created_at": isoformat(started),
                "receipt": {
                    "id": f"tempo_mock_{uuid.uuid4().hex[:12]}",
                    "status": "succeeded",
                    "amount": "0.00",
                    "network": "mock",
                },
            }

        command = shlex.split(self.config.tempo_mpp_command)
        if not command:
            result = {"state": "failed", "reason": "AGENTCART_TEMPO_MPP_COMMAND is empty"}
            if self.config.tempo_mpp_proof_required:
                raise UpstreamError("Tempo MPP proof command is empty", detail=result)
            return result

        full_command = [*command, self.config.tempo_mpp_proof_url]
        if self.config.tempo_mpp_network:
            full_command.extend(["--network", self.config.tempo_mpp_network])
        if self.config.tempo_mpp_account:
            full_command.extend(["--account", self.config.tempo_mpp_account])
        if "--include" not in full_command and "-i" not in full_command:
            full_command.append("--include")
        full_command.extend(["--format", "json"])

        try:
            completed = subprocess.run(
                full_command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.config.tempo_mpp_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            result = {
                "state": "failed",
                "provider": "tempo_mpp",
                "mode": "mppx-cli",
                "network": self.config.tempo_mpp_network,
                "settlement_asset": tempo_default_settlement_asset(self.config.tempo_mpp_network),
                "quote_currency": quote.get("currency"),
                "quote_total_cents": quote.get("total_cents"),
                "url": self.config.tempo_mpp_proof_url,
                "error": str(exc),
                "created_at": isoformat(started),
            }
            if self.config.tempo_mpp_proof_required:
                raise UpstreamError("Tempo MPP proof failed", detail=result) from exc
            return result

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        parsed: Any = None
        proof_details: dict[str, Any] = {}
        if stdout:
            proof_details = parse_mppx_output(stdout, network=self.config.tempo_mpp_network)
            parsed = proof_details.get("body", stdout[-4000:])
        result = {
            "state": "succeeded" if completed.returncode == 0 else "failed",
            "provider": "tempo_mpp",
            "mode": "mppx-cli",
            "network": self.config.tempo_mpp_network,
            "settlement_asset": tempo_default_settlement_asset(self.config.tempo_mpp_network),
            "quote_currency": quote.get("currency"),
            "quote_total_cents": quote.get("total_cents"),
            "real_settlement": completed.returncode == 0 and self.config.tempo_mpp_network == "mainnet",
            "value_transfer": completed.returncode == 0,
            "settlement_note": "Tempo MPP proof uses the configured Tempo asset. In the hackathon setup this is a USD-stablecoin proof artifact, not EUR settlement of the physical WooCommerce order.",
            "url": self.config.tempo_mpp_proof_url,
            "command": full_command[:1] + ["..."],
            "returncode": completed.returncode,
            "stdout": parsed,
            "stderr": stderr[-4000:] if stderr else "",
            "quote_id": quote["id"],
            "approval_id": approval["id"],
            "created_at": isoformat(started),
        }
        result.update(proof_details)
        if completed.returncode != 0 and self.config.tempo_mpp_proof_required:
            raise UpstreamError("Tempo MPP proof command failed", detail=result)
        return result

    def create_external_value_proof(self, quote: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
        tempo_proof = self.create_tempo_mpp_value_proof(quote, approval)
        if tempo_proof["state"] != "skipped":
            return tempo_proof
        return self.create_agentcash_value_proof(quote, approval)

    def create_agentcash_value_proof(self, quote: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
        if not self.config.agentcash_proof_url:
            return {"state": "skipped", "reason": "AgentCash proof URL is not configured"}
        started = utcnow()
        if self.config.agentcash_proof_url.startswith("mock://"):
            return {
                "state": "succeeded",
                "provider": "agentcash_x402",
                "mode": "mock",
                "real_settlement": False,
                "url": self.config.agentcash_proof_url,
                "quote_id": quote["id"],
                "approval_id": approval["id"],
                "created_at": isoformat(started),
                "receipt": {
                    "id": f"agentcash_mock_{uuid.uuid4().hex[:12]}",
                    "status": "succeeded",
                    "amount": "0.00",
                    "network": "mock",
                },
            }

        command = shlex.split(self.config.agentcash_command)
        if not command:
            result = {"state": "failed", "reason": "AGENTCART_AGENTCASH_COMMAND is empty"}
            if self.config.agentcash_proof_required:
                raise UpstreamError("AgentCash proof command is empty", detail=result)
            return result
        full_command = [*command, self.config.agentcash_proof_url]
        try:
            completed = subprocess.run(
                full_command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.config.agentcash_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            result = {
                "state": "failed",
                "provider": "agentcash_x402",
                "url": self.config.agentcash_proof_url,
                "error": str(exc),
                "created_at": isoformat(started),
            }
            if self.config.agentcash_proof_required:
                raise UpstreamError("AgentCash proof failed", detail=result) from exc
            return result

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        parsed: Any = None
        if stdout:
            try:
                parsed = json.loads(stdout)
            except json.JSONDecodeError:
                parsed = stdout[-4000:]
        result = {
            "state": "succeeded" if completed.returncode == 0 else "failed",
            "provider": "agentcash_x402",
            "mode": "agentcash-cli",
            "real_settlement": completed.returncode == 0,
            "url": self.config.agentcash_proof_url,
            "command": full_command[:1] + ["..."],
            "returncode": completed.returncode,
            "stdout": parsed,
            "stderr": stderr[-4000:] if stderr else "",
            "quote_id": quote["id"],
            "approval_id": approval["id"],
            "created_at": isoformat(started),
        }
        if completed.returncode != 0 and self.config.agentcash_proof_required:
            raise UpstreamError("AgentCash proof command failed", detail=result)
        return result

    def search_catalog(self, query: str) -> dict[str, Any]:
        with self.lock:
            products: list[dict[str, Any]] = []
            merchants = []
            for adapter in self.adapters.values():
                adapter_products = adapter.search_products(query, self.state["stock"])
                if adapter_products:
                    merchants.append(adapter.merchant)
                    products.extend(adapter_products)
            alias_product_id = resolve_product_alias(query)
            if alias_product_id and alias_product_id not in {product["id"] for product in products}:
                adapter = self.adapter_for_product(alias_product_id)
                product = adapter.get_product(alias_product_id, self.state["stock"])
                products.insert(0, product)
                if adapter.merchant["id"] not in {merchant["id"] for merchant in merchants}:
                    merchants.insert(0, adapter.merchant)
        return {
            "query": query,
            "products": products,
            "merchant": merchants[0] if merchants else self.adapter.merchant,
            "merchants": merchants,
        }

    def get_product(self, product_id: str) -> dict[str, Any]:
        with self.lock:
            resolved_product_id = self.canonical_product_id(product_id)
            adapter = self.adapter_for_product(resolved_product_id)
            return adapter.get_product(resolved_product_id, self.state["stock"])

    def canonical_product_id(self, product_id: str) -> str:
        return resolve_product_alias(product_id) or product_id

    def adapter_for_product(self, product_id: str) -> Any:
        product_id = self.canonical_product_id(product_id)
        if product_id.startswith("woo_"):
            for adapter in self.adapters.values():
                if getattr(adapter, "adapter_type", "") == "woocommerce":
                    return adapter
        for adapter in self.adapters.values():
            if product_id in getattr(adapter, "products", {}):
                return adapter
        raise NotFound(f"Unknown product: {product_id}")

    def adapter_for_merchant(self, merchant_id: str) -> Any:
        adapter = self.adapters.get(merchant_id)
        if not adapter:
            raise NotFound(f"Unknown merchant adapter: {merchant_id}")
        return adapter

    def create_quote(self, request: dict[str, Any]) -> dict[str, Any]:
        items = request.get("items")
        if not isinstance(items, list) or not items:
            raise BadRequest("items must be a non-empty list")
        ship_to = request.get("ship_to") or {}
        if not isinstance(ship_to, dict):
            raise BadRequest("ship_to must be an object")
        ship_country = ship_to.get("country") or self.config.default_ship_country
        ship_postal_code = ship_to.get("postal_code") or self.config.default_ship_postal_code
        normalized_ship_to = dict(ship_to)
        normalized_ship_to["country"] = ship_country
        normalized_ship_to.setdefault("postal_code", ship_postal_code)
        normalized_ship_to.setdefault("postcode", ship_postal_code)
        reason = str(request.get("reason") or "household agent requested quote")
        agent_id = str(request.get("agent_id") or "unknown-agent")
        remote_quote = self.try_create_remote_merchant_quote(
            items,
            ship_to=normalized_ship_to,
            agent_id=agent_id,
            reason=reason,
            idempotency_key=request.get("idempotency_key"),
        )
        if remote_quote is not None:
            return remote_quote

        line_items: list[dict[str, Any]] = []
        subtotal_cents = 0
        vat_buckets: dict[int, int] = {}
        merchant_id: str | None = None

        with self.lock:
            stock = self.state["stock"]
            for raw_item in items:
                if not isinstance(raw_item, dict):
                    raise BadRequest("each item must be an object")
                product_id = self.canonical_product_id(str(raw_item.get("product_id") or ""))
                quantity = safe_int(raw_item.get("quantity", 1), field="quantity", minimum=1, maximum=20)
                adapter = self.adapter_for_product(product_id)
                product = adapter.source_product(product_id)
                if merchant_id and merchant_id != product["merchant_id"]:
                    raise BadRequest("a quote can only contain one merchant in this MVP")
                merchant_id = product["merchant_id"]
                available = int(stock.get(product_id, product["stock"]))
                stock.setdefault(product_id, available)
                if available < quantity:
                    raise Conflict(f"Only {available} units available for {product_id}")
                if ship_country not in product["shipping_regions"]:
                    raise BadRequest(f"{product_id} cannot ship to {ship_country}")

                unit_cents = int(product["price_cents"])
                total_cents = unit_cents * quantity
                subtotal_cents += total_cents
                vat_rate_bps = int(product["vat_rate_bps"])
                vat_buckets[vat_rate_bps] = vat_buckets.get(vat_rate_bps, 0) + total_cents
                line_items.append(
                    {
                        "product_id": product_id,
                        "source_product_id": product.get("source_product_id", product_id),
                        "sku": product["sku"],
                        "title": product["title"],
                        "quantity": quantity,
                        "unit_price_cents": unit_cents,
                        "line_total_cents": total_cents,
                        "currency": product["currency"],
                        "category": product["category"],
                        "vat_rate_bps": vat_rate_bps,
                    }
                )

            shipping_cents = 0 if subtotal_cents >= 3500 else 490
            shipping_vat_rate_bps = 1900
            vat_buckets[shipping_vat_rate_bps] = vat_buckets.get(shipping_vat_rate_bps, 0) + shipping_cents
            total_cents = subtotal_cents + shipping_cents
            now = utcnow()
            delivery_estimate = {
                "min_days": 2,
                "max_days": 4,
                "label": "2-4 business days",
            }
            quote_id = f"quote_{uuid.uuid4().hex[:16]}"
            quote = {
                "id": quote_id,
                "state": "quoted",
                "agent_id": agent_id,
                "reason": reason,
                "merchant_id": merchant_id or self.adapter.merchant["id"],
                "merchant": self.adapter_for_merchant(merchant_id or self.adapter.merchant["id"]).merchant,
                "items": line_items,
                "ship_to": normalized_ship_to,
                "subtotal_cents": subtotal_cents,
                "shipping": {
                    "amount_cents": shipping_cents,
                    "currency": "EUR",
                    "method": "demo-standard",
                    "vat_rate_bps": shipping_vat_rate_bps,
                },
                "vat_lines": self.vat_lines(vat_buckets),
                "total_cents": total_cents,
                "currency": "EUR",
                "delivery_estimate": delivery_estimate,
                "delivery_window": delivery_window_from_estimate(
                    delivery_estimate,
                    timezone=self.config.timezone,
                    now=now,
                ),
                "stock_reserved_until": isoformat(now + dt.timedelta(seconds=QUOTE_TTL_SECONDS)),
                "expires_at": isoformat(now + dt.timedelta(seconds=QUOTE_TTL_SECONDS)),
                "nonce": secrets.token_urlsafe(18),
                "idempotency_key": request.get("idempotency_key") or f"quote-{uuid.uuid4().hex[:10]}",
                "terms_url": self.adapter_for_merchant(merchant_id or self.adapter.merchant["id"]).merchant["terms_url"],
                "returns_url": self.adapter_for_merchant(merchant_id or self.adapter.merchant["id"]).merchant["returns_url"],
                "merchant_of_record": self.adapter_for_merchant(merchant_id or self.adapter.merchant["id"]).merchant["merchant_of_record"],
                "created_at": isoformat(now),
            }
            policy_result = self.evaluate_policy_for_quote(quote)
            quote["policy_result"] = policy_result
            self.state["quotes"][quote_id] = quote
            self.save_state()

        self.audit(
            "quote.created",
            actor=agent_id,
            reason=reason,
            purchase_id=quote_id,
            refs={"quote_id": quote_id, "product_ids": [item["product_id"] for item in line_items]},
            policy_result=policy_result,
        )
        return quote

    def try_create_remote_merchant_quote(
        self,
        raw_items: list[Any],
        *,
        ship_to: dict[str, Any],
        agent_id: str,
        reason: str,
        idempotency_key: Any,
    ) -> dict[str, Any] | None:
        normalized_items: list[dict[str, Any]] = []
        adapter: Any | None = None
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise BadRequest("each item must be an object")
            product_id = self.canonical_product_id(str(raw_item.get("product_id") or ""))
            quantity = safe_int(raw_item.get("quantity", 1), field="quantity", minimum=1, maximum=20)
            item_adapter = self.adapter_for_product(product_id)
            if getattr(item_adapter, "mode", "") != "plugin":
                return None
            if adapter is not None and item_adapter is not adapter:
                raise BadRequest("a quote can only contain one merchant in this MVP")
            adapter = item_adapter
            normalized_items.append({"product_id": product_id, "quantity": quantity})
        if adapter is None:
            return None

        merchant_quote = adapter.create_plugin_quote(
            items=normalized_items,
            ship_to=ship_to,
            agent_id=agent_id,
            reason=reason,
        )
        now = utcnow()
        delivery_estimate = merchant_quote["delivery_estimate"]
        delivery_window = merchant_quote.get("delivery_window") or delivery_window_from_estimate(
            delivery_estimate,
            timezone=self.config.timezone,
            now=now,
        )
        quote_id = f"quote_{uuid.uuid4().hex[:16]}"
        expires_at = str(merchant_quote.get("expires_at") or isoformat(now + dt.timedelta(seconds=QUOTE_TTL_SECONDS)))
        quote = {
            "id": quote_id,
            "state": "quoted",
            "agent_id": agent_id,
            "reason": reason,
            "merchant_id": adapter.merchant["id"],
            "merchant": merchant_quote.get("merchant") or adapter.merchant,
            "merchant_quote_id": merchant_quote.get("merchant_quote_id"),
            "items": merchant_quote["items"],
            "ship_to": ship_to,
            "subtotal_cents": merchant_quote["subtotal_cents"],
            "shipping": merchant_quote["shipping"],
            "vat_lines": merchant_quote["vat_lines"],
            "total_cents": merchant_quote["total_cents"],
            "currency": merchant_quote["currency"],
            "delivery_estimate": delivery_estimate,
            "delivery_window": delivery_window,
            "stock_reserved_until": str(merchant_quote.get("stock_reserved_until") or expires_at),
            "stock_reservation": merchant_quote.get("stock_reservation"),
            "quote_hash": merchant_quote.get("quote_hash"),
            "payment_requirements": merchant_quote.get("payment_requirements") or {},
            "expires_at": expires_at,
            "nonce": secrets.token_urlsafe(18),
            "idempotency_key": idempotency_key or f"quote-{uuid.uuid4().hex[:10]}",
            "terms_url": merchant_quote["terms_url"],
            "returns_url": merchant_quote["returns_url"],
            "merchant_of_record": merchant_quote["merchant_of_record"],
            "created_at": isoformat(now),
        }
        with self.lock:
            for item in quote["items"]:
                quantity = int(item["quantity"])
                product_id = item["product_id"]
                current = int(self.state["stock"].get(product_id, quantity))
                self.state["stock"][product_id] = max(current, quantity)
            policy_result = self.evaluate_policy_for_quote(quote)
            quote["policy_result"] = policy_result
            self.state["quotes"][quote_id] = quote
            self.save_state()

        self.audit(
            "quote.created",
            actor=agent_id,
            reason=f"{reason} (merchant quote from WooCommerce AgentCart plugin)",
            purchase_id=quote_id,
            refs={
                "quote_id": quote_id,
                "merchant_quote_id": quote.get("merchant_quote_id"),
                "product_ids": [item["product_id"] for item in quote["items"]],
            },
            policy_result=policy_result,
        )
        return quote

    def vat_lines(self, buckets: dict[int, int]) -> list[dict[str, Any]]:
        lines = []
        for rate_bps, gross_cents in sorted(buckets.items()):
            if gross_cents <= 0:
                continue
            vat_cents = round(gross_cents * rate_bps / (10000 + rate_bps))
            lines.append(
                {
                    "rate_bps": rate_bps,
                    "taxable_gross_cents": gross_cents,
                    "vat_cents": vat_cents,
                    "currency": "EUR",
                    "included_in_price": True,
                }
            )
        return lines

    def evaluate_policy_for_quote(self, quote: dict[str, Any]) -> dict[str, Any]:
        policy = self.read_policy()
        reasons: list[str] = []
        failures: list[str] = []
        merchant_id = quote["merchant_id"]
        categories = {item["category"] for item in quote["items"]}
        ship_country = quote["ship_to"]["country"]
        total_cents = int(quote["total_cents"])

        if merchant_id in policy.get("blocked_merchants", []):
            failures.append(f"merchant {merchant_id} is blocked")
        allowed_merchants = set(policy.get("allowed_merchants") or [])
        if allowed_merchants and merchant_id not in allowed_merchants:
            failures.append(f"merchant {merchant_id} is not allowlisted")
        blocked_categories = set(policy.get("blocked_categories") or [])
        blocked_hits = sorted(categories & blocked_categories)
        if blocked_hits:
            failures.append(f"blocked category: {', '.join(blocked_hits)}")
        allowed_categories = set(policy.get("allowed_categories") or [])
        if allowed_categories:
            unknown = sorted(categories - allowed_categories)
            if unknown:
                failures.append(f"category not allowlisted: {', '.join(unknown)}")
        allowed_ship_countries = set(policy.get("allowed_ship_countries") or [])
        if allowed_ship_countries and ship_country not in allowed_ship_countries:
            failures.append(f"shipping country {ship_country} is not allowlisted")
        max_order_total = int(policy.get("max_order_total_cents", 0))
        if max_order_total and total_cents > max_order_total:
            failures.append(f"total {money(total_cents)} exceeds max order {money(max_order_total)}")

        monthly_spend = self.monthly_committed_spend(quote.get("created_at"))
        monthly_budget = int(policy.get("monthly_budget_cents", 0))
        if monthly_budget and monthly_spend + total_cents > monthly_budget:
            failures.append(
                f"monthly committed spend would be {money(monthly_spend + total_cents)}, above {money(monthly_budget)}"
            )

        if failures:
            decision = "deny"
            requires_approval = False
            reasons.extend(failures)
        else:
            auto_threshold = int(policy.get("auto_approve_below_cents", 0))
            require_human = bool(policy.get("require_human_approval", True))
            if not require_human and auto_threshold and total_cents <= auto_threshold:
                decision = "allow"
                requires_approval = False
                reasons.append(f"total {money(total_cents)} is within auto-approval threshold")
            else:
                decision = "requires_approval"
                requires_approval = True
                reasons.append("human approval required by household policy")

        return {
            "decision": decision,
            "requires_approval": requires_approval,
            "reasons": reasons,
            "policy": {
                "household_id": policy.get("household_id"),
                "max_order_total_cents": policy.get("max_order_total_cents"),
                "monthly_budget_cents": policy.get("monthly_budget_cents"),
                "auto_approve_below_cents": policy.get("auto_approve_below_cents"),
            },
            "monthly_committed_spend_cents": monthly_spend,
            "evaluated_at": isoformat(utcnow()),
        }

    def monthly_committed_spend(self, created_at: str | None = None) -> int:
        now = parse_time(created_at) if created_at else utcnow()
        month = now.astimezone(dt.timezone.utc).strftime("%Y-%m")
        total = 0
        for order in self.state.get("orders", {}).values():
            created = str(order.get("created_at") or "")
            if created.startswith(month) and order.get("state") not in {"cancelled", "failed"}:
                total += int(order.get("total_cents", 0))
        return total

    def get_quote(self, quote_id: str) -> dict[str, Any]:
        quote = self.state.get("quotes", {}).get(quote_id)
        if not quote:
            raise NotFound(f"Unknown quote: {quote_id}")
        return quote

    def create_approval(self, request: dict[str, Any]) -> dict[str, Any]:
        quote_id = str(request.get("quote_id") or "")
        if not quote_id:
            raise BadRequest("quote_id is required")
        approver_hint = str(request.get("approver_hint") or "household")
        channel = str(request.get("channel") or "agent_api")
        delivery_channels = self.approval_delivery_channels(request, channel)
        with self.lock:
            quote = self.get_quote(quote_id)
            policy_result = self.evaluate_policy_for_quote(quote)
            quote["policy_result"] = policy_result
            if policy_result["decision"] == "deny":
                self.save_state()
                raise Forbidden("policy denied quote", detail=policy_result)
            now = utcnow()
            approval_id = f"approval_{uuid.uuid4().hex[:16]}"
            token = secrets.token_urlsafe(24)
            approval = {
                "id": approval_id,
                "quote_id": quote_id,
                "state": "pending",
                "channel": channel,
                "delivery_channels": delivery_channels,
                "approver_hint": approver_hint,
                "decision_token_hash": self.token_hash(token),
                "decision_url": f"{self.config.public_url}/approvals/{approval_id}?token={urllib.parse.quote(token)}",
                "decision_api": {
                    "method": "POST",
                    "url": f"{self.config.public_url}/v1/approvals/{approval_id}/decision",
                    "token_transport": "json_body.token",
                    "decisions": ["approved", "rejected"],
                },
                "consent_request": self.approval_consent_request(approval_id, quote, policy_result),
                "created_at": isoformat(now),
                "expires_at": isoformat(now + dt.timedelta(seconds=APPROVAL_TTL_SECONDS)),
                "decided_at": None,
                "approver": None,
                "policy_result": policy_result,
                "notification": {"state": "not_sent"},
            }
            self.state["approvals"][approval_id] = approval
            self.save_state()

        if "home_assistant" in delivery_channels:
            notification = self.send_home_assistant_approval(approval, quote, token)
        else:
            notification = {"state": "skipped", "reason": "Home Assistant delivery was not requested"}
        with self.lock:
            self.state["approvals"][approval_id]["notification"] = notification
            self.save_state()
            public = self.public_approval(self.state["approvals"][approval_id])

        public["decision_token"] = token
        self.audit(
            "approval.requested",
            actor="agentcart",
            reason="policy required human approval",
            purchase_id=quote_id,
            refs={"quote_id": quote_id, "approval_id": approval_id, "channel": channel},
            policy_result=policy_result,
        )
        return public

    def approval_delivery_channels(self, request: dict[str, Any], channel: str) -> list[str]:
        raw = request.get("delivery_channels")
        if raw is None:
            raw = request.get("channels")
        if isinstance(raw, str):
            candidates = [part.strip() for part in raw.split(",")]
        elif isinstance(raw, list):
            candidates = [str(part).strip() for part in raw]
        else:
            candidates = []
        if not candidates:
            if channel in {"home_assistant", "phone", "watch"}:
                candidates = ["home_assistant", "web", "api"]
            elif channel in {"chat", "agent_chat", "openclaw"}:
                candidates = ["chat", "web", "api"]
            else:
                candidates = ["web", "api"]
        normalized: list[str] = []
        allowed = {"api", "web", "chat", "home_assistant", "phone", "watch", "external"}
        for candidate in candidates:
            name = candidate.lower().replace("-", "_").replace(" ", "_")
            if name == "ha":
                name = "home_assistant"
            if name not in allowed:
                continue
            if name not in normalized:
                normalized.append(name)
        if "api" not in normalized:
            normalized.append("api")
        return normalized

    def approval_consent_request(
        self,
        approval_id: str,
        quote: dict[str, Any],
        policy_result: dict[str, Any],
    ) -> dict[str, Any]:
        product_summary = ", ".join(f"{item['quantity']}x {item['title']}" for item in quote["items"])
        delivery = quote.get("delivery_window") or delivery_window_from_estimate(
            quote.get("delivery_estimate", {}),
            timezone=self.config.timezone,
        )
        return {
            "kind": "purchase_approval",
            "subject": product_summary,
            "summary": (
                f"Approve purchase of {product_summary} from {quote['merchant']['name']} "
                f"for {money(quote['total_cents'], quote['currency'])}."
            ),
            "merchant": {
                "id": quote["merchant_id"],
                "name": quote["merchant"]["name"],
                "merchant_of_record": quote["merchant_of_record"],
            },
            "total": {"amount_cents": quote["total_cents"], "currency": quote["currency"]},
            "delivery_window": delivery,
            "policy_result": policy_result,
            "decision_endpoint": f"/v1/approvals/{approval_id}/decision",
            "decision_method": "POST",
            "decision_token_transport": "json_body.token",
            "renderable_by": ["chat", "mobile_push", "web", "voice_assistant", "home_automation"],
            "user_consent_required": True,
        }

    def public_approval(self, approval: dict[str, Any]) -> dict[str, Any]:
        result = dict(approval)
        result.pop("decision_token_hash", None)
        return result

    def token_hash(self, token: str) -> str:
        secret = self.config.agentcart_token or "agentcart-dev-token"
        return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()

    def verify_approval_token(self, approval: dict[str, Any], token: str) -> None:
        expected = str(approval.get("decision_token_hash") or "")
        if not expected or not hmac.compare_digest(expected, self.token_hash(token)):
            raise Forbidden("approval token is invalid")

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        approval = self.state.get("approvals", {}).get(approval_id)
        if not approval:
            raise NotFound(f"Unknown approval: {approval_id}")
        return approval

    def decide_approval(self, approval_id: str, request: dict[str, Any]) -> dict[str, Any]:
        decision = str(request.get("decision") or "").lower()
        if decision not in {"approved", "rejected"}:
            raise BadRequest("decision must be approved or rejected")
        token = str(request.get("token") or "")
        approver = str(request.get("approver") or "home-assistant")
        with self.lock:
            approval = self.get_approval(approval_id)
            self.verify_approval_token(approval, token)
            if approval["state"] != "pending":
                return self.public_approval(approval)
            if parse_time(approval["expires_at"]) < utcnow():
                approval["state"] = "expired"
                self.save_state()
                raise Conflict("approval has expired")
            approval["state"] = decision
            approval["approver"] = approver
            approval["decided_at"] = isoformat(utcnow())
            self.save_state()
            public = self.public_approval(approval)

        self.audit(
            f"approval.{decision}",
            actor=approver,
            reason=f"human decision: {decision}",
            purchase_id=approval["quote_id"],
            refs={"approval_id": approval_id, "quote_id": approval["quote_id"]},
            policy_result=approval.get("policy_result"),
        )
        return public

    def send_home_assistant_approval(
        self,
        approval: dict[str, Any],
        quote: dict[str, Any],
        token: str,
    ) -> dict[str, Any]:
        if not self.config.homeassistant_url or not self.config.homeassistant_token or not self.config.ha_notify_services:
            return {"state": "skipped", "reason": "Home Assistant notification is not configured"}

        title = "Approve AgentCart purchase?"
        product_summary = ", ".join(f"{item['quantity']}x {item['title']}" for item in quote["items"])
        message = (
            f"{product_summary} from {quote['merchant']['name']} for {money(quote['total_cents'], quote['currency'])}. "
            f"Reason: {quote['reason']}"
        )
        action_token = token
        data = {
            "title": title,
            "message": message,
            "data": {
                "tag": f"agentcart_{approval['id']}",
                "url": approval["decision_url"],
                "actions": [
                    {
                        "action": f"AGENTCART_APPROVE:{approval['id']}:{action_token}",
                        "title": "Approve",
                    },
                    {
                        "action": f"AGENTCART_REJECT:{approval['id']}:{action_token}",
                        "title": "Reject",
                        "destructive": True,
                    },
                ],
            },
        }
        results = []
        for service in self.config.ha_notify_services:
            if "." not in service:
                results.append({"service": service, "ok": False, "error": "notify service must look like notify.mobile_app_name"})
                continue
            domain, service_name = service.split(".", 1)
            url = f"{self.config.homeassistant_url}/api/services/{domain}/{service_name}"
            try:
                self.http_json(
                    url,
                    method="POST",
                    token=self.config.homeassistant_token,
                    payload=data,
                    timeout=8,
                )
                results.append({"service": service, "ok": True})
            except AgentCartError as exc:
                results.append({"service": service, "ok": False, "error": str(exc), "detail": exc.detail})
        ok = any(result.get("ok") for result in results)
        return {"state": "sent" if ok else "failed", "results": results}

    def home_assistant_state(self, entity_id: str) -> dict[str, Any]:
        url_entity = urllib.parse.quote(entity_id, safe="")
        url = f"{self.config.homeassistant_url}/api/states/{url_entity}"
        response = self.http_json(url, method="GET", token=self.config.homeassistant_token, timeout=10)
        if not isinstance(response, dict):
            raise UpstreamError(f"Home Assistant returned an invalid state for {entity_id}")
        return response

    def numeric_state(self, entity_id: str) -> dict[str, Any]:
        if not entity_id:
            return {"entity_id": None, "state": None, "value": None, "unit": None, "available": False}
        try:
            state = self.home_assistant_state(entity_id)
        except AgentCartError as exc:
            return {
                "entity_id": entity_id,
                "state": None,
                "value": None,
                "unit": None,
                "available": False,
                "error": str(exc),
                "detail": exc.detail,
            }
        raw_state = state.get("state")
        try:
            value = float(str(raw_state).replace(",", "."))
        except (TypeError, ValueError):
            value = None
        attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        return {
            "entity_id": entity_id,
            "state": raw_state,
            "value": value,
            "unit": attributes.get("unit_of_measurement"),
            "friendly_name": attributes.get("friendly_name"),
            "available": value is not None,
        }

    def energy_surplus(self) -> dict[str, Any]:
        if not self.config.homeassistant_url or not self.config.homeassistant_token:
            return {"state": "skipped", "reason": "Home Assistant is not configured"}

        sensors = {
            "solar_power_w": self.numeric_state(self.config.energy_solar_power_entity),
            "battery_level_percent": self.numeric_state(self.config.energy_battery_level_entity),
            "battery_power_w": self.numeric_state(self.config.energy_battery_power_entity),
            "grid_export_w": self.numeric_state(self.config.energy_grid_export_entity),
            "grid_import_w": self.numeric_state(self.config.energy_grid_import_entity),
            "house_output_w": self.numeric_state(self.config.energy_house_output_entity),
        }
        grid_export = sensors["grid_export_w"]["value"] or 0.0
        grid_import = sensors["grid_import_w"]["value"] or 0.0
        net_export_w = max(0.0, grid_export - grid_import)
        solar_power = sensors["solar_power_w"]["value"] or 0.0
        house_output = sensors["house_output_w"]["value"] or 0.0
        potential_surplus_w = max(0.0, solar_power - house_output)
        battery_level = sensors["battery_level_percent"]["value"]
        min_export = self.config.energy_min_export_w
        min_battery = self.config.energy_min_battery_percent
        battery_reserve_w = (
            solar_power
            if battery_level is not None and battery_level >= max(min_battery, 90.0) and solar_power >= min_export
            else 0.0
        )
        offer_candidates = {
            "grid_export": net_export_w,
            "solar_minus_household_output": potential_surplus_w,
            "battery_backed_solar_reserve": battery_reserve_w,
        }
        offer_basis, offer_basis_w = max(offer_candidates.items(), key=lambda item: item[1])

        reasons = []
        if offer_basis_w < min_export:
            reasons.append(
                f"offerable surplus {offer_basis_w:.0f} W is below {min_export:.0f} W threshold "
                f"(net export {net_export_w:.0f} W, solar surplus {potential_surplus_w:.0f} W, "
                f"battery-backed reserve {battery_reserve_w:.0f} W)"
            )
        if battery_level is None:
            reasons.append("battery level is unavailable")
        elif battery_level < min_battery:
            reasons.append(f"battery level {battery_level:.0f}% is below {min_battery:.0f}% threshold")
        if not reasons:
            reasons.append(f"{offer_basis.replace('_', ' ')} and battery thresholds are satisfied")

        offerable = offer_basis_w >= min_export and battery_level is not None and battery_level >= min_battery
        state = "surplus_available" if offerable else "no_surplus"
        return {
            "state": state,
            "offerable": offerable,
            "evaluated_at": isoformat(utcnow()),
            "net_export_w": round(net_export_w, 3),
            "potential_surplus_w": round(potential_surplus_w, 3),
            "battery_backed_reserve_w": round(battery_reserve_w, 3),
            "offer_basis_w": round(offer_basis_w, 3),
            "offer_basis": offer_basis,
            "thresholds": {
                "min_export_w": min_export,
                "min_battery_percent": min_battery,
            },
            "sensors": sensors,
            "recommendation": (
                "Surplus could be offered to a neighbor demo market after explicit human approval."
                if offerable
                else "Do not offer household energy for sale right now."
            ),
            "reasons": reasons,
            "scope": "read_only_detection_only_no_settlement",
        }

    def energy_legal_scope(self) -> dict[str, Any]:
        return {
            "jurisdiction": "DE",
            "framework": "EnWG §42c energy sharing",
            "prototype_scope": "demo_discovery_and_payment_proof_only",
            "physical_delivery": False,
            "legal_settlement": False,
            "requires_before_real_use": [
                "eligible energy-sharing participants in the required distribution grid area",
                "contract for joint use and electricity supply terms",
                "compliant smart metering and 15-minute allocation",
                "residual electricity supplier and balancing responsibilities",
                "taxes, levies, grid charges, billing, cancellation, and consumer information handling",
            ],
            "judge_note": (
                "AgentCart can expose a safe offer and consent/payment trail. "
                "A real neighbourhood energy sale needs a compliant energy-sharing stack outside this demo."
            ),
        }

    def create_energy_offer(self, request: dict[str, Any] | None = None) -> dict[str, Any]:
        request = request or {}
        surplus = self.energy_surplus()
        if not surplus.get("offerable"):
            raise Conflict("current household energy telemetry is not offerable", detail=surplus)

        price_cents_per_kwh = safe_int(
            request.get("price_cents_per_kwh", ENERGY_DEFAULT_PRICE_CENTS_PER_KWH),
            field="price_cents_per_kwh",
            minimum=1,
            maximum=80,
        )
        market_reference = safe_int(
            request.get("market_reference_cents_per_kwh", ENERGY_DEFAULT_MARKET_REFERENCE_CENTS_PER_KWH),
            field="market_reference_cents_per_kwh",
            minimum=1,
            maximum=100,
        )
        feed_in_reference = safe_int(
            request.get("feed_in_reference_cents_per_kwh", ENERGY_DEFAULT_FEED_IN_REFERENCE_CENTS_PER_KWH),
            field="feed_in_reference_cents_per_kwh",
            minimum=0,
            maximum=80,
        )
        duration_minutes = safe_int(
            request.get("duration_minutes", ENERGY_OFFER_DEFAULT_DURATION_MINUTES),
            field="duration_minutes",
            minimum=5,
            maximum=120,
        )
        valid_minutes = safe_int(
            request.get("valid_minutes", ENERGY_OFFER_DEFAULT_VALID_MINUTES),
            field="valid_minutes",
            minimum=1,
            maximum=60,
        )
        generated_kwh = float(surplus.get("offer_basis_w") or surplus.get("net_export_w") or 0.0) * duration_minutes / 60.0 / 1000.0
        requested_max = safe_float(request.get("max_kwh", generated_kwh), field="max_kwh", minimum=0.001, maximum=20.0)
        quantity_kwh = round(min(generated_kwh, requested_max), 3)
        if quantity_kwh <= 0:
            raise Conflict("current surplus is too small for an offer", detail=surplus)

        now = utcnow()
        offer_id = f"energy_offer_{uuid.uuid4().hex[:12]}"
        offer = {
            "id": offer_id,
            "state": "open",
            "seller_household_id": str(request.get("seller_household_id") or "max-household-demo"),
            "buyer_scope": str(request.get("buyer_scope") or "neighbor-demo"),
            "commodity": "electricity",
            "source": "home_assistant_energy_surplus",
            "quantity_kwh": quantity_kwh,
            "duration_minutes": duration_minutes,
            "price_cents_per_kwh": price_cents_per_kwh,
            "market_reference_cents_per_kwh": market_reference,
            "feed_in_reference_cents_per_kwh": feed_in_reference,
            "estimated_total_cents": max(1, int(round(quantity_kwh * price_cents_per_kwh))),
            "currency": "EUR",
            "valid_from": isoformat(now),
            "valid_until": isoformat(now + dt.timedelta(minutes=valid_minutes)),
            "telemetry_snapshot": surplus,
            "discovery": {
                "agent_visible": True,
                "category": "household.energy_surplus",
                "description": "Short-lived demo offer for locally generated surplus electricity.",
            },
            "legal_scope": self.energy_legal_scope(),
            "settlement": None,
            "created_at": isoformat(now),
            "updated_at": isoformat(now),
        }
        with self.lock:
            self.state["energy_offers"][offer_id] = offer
            self.save_state()
        self.audit(
            "energy.offer_created",
            actor="agentcart",
            reason="Home Assistant telemetry passed surplus and battery thresholds, so a neighbour demo offer was created",
            purchase_id=offer_id,
            refs={
                "offer_id": offer_id,
                "quantity_kwh": quantity_kwh,
                "price_cents_per_kwh": price_cents_per_kwh,
                "net_export_w": surplus.get("net_export_w"),
                "potential_surplus_w": surplus.get("potential_surplus_w"),
                "offer_basis": surplus.get("offer_basis"),
                "offer_basis_w": surplus.get("offer_basis_w"),
                "battery_level_percent": (surplus.get("sensors") or {}).get("battery_level_percent", {}).get("value"),
            },
        )
        return offer

    def list_energy_offers(self) -> dict[str, Any]:
        with self.lock:
            self.expire_energy_offers_locked()
            self.save_state()
            offers = sort_by_time(list(self.state.get("energy_offers", {}).values()))[-50:]
        return {"offers": offers}

    def expire_energy_offers_locked(self) -> bool:
        changed = False
        now = utcnow()
        for offer in self.state.get("energy_offers", {}).values():
            if offer.get("state") != "open":
                continue
            try:
                valid_until = parse_time(str(offer.get("valid_until") or ""))
            except ValueError:
                continue
            if valid_until < now:
                offer["state"] = "expired"
                offer["updated_at"] = isoformat(now)
                changed = True
        return changed

    def get_energy_offer(self, offer_id: str) -> dict[str, Any]:
        with self.lock:
            changed = self.expire_energy_offers_locked()
            offer = self.state.get("energy_offers", {}).get(offer_id)
            if changed:
                self.save_state()
            if not offer:
                raise NotFound(f"Unknown energy offer: {offer_id}")
            return offer

    def accept_energy_offer(self, offer_id: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        request = request or {}
        now = utcnow()
        with self.lock:
            offer = self.state.get("energy_offers", {}).get(offer_id)
            if not offer:
                raise NotFound(f"Unknown energy offer: {offer_id}")
            self.expire_energy_offers_locked()
            if offer.get("state") != "open":
                self.save_state()
                raise Conflict(f"energy offer is {offer.get('state')}")
            accepted_kwh = safe_float(
                request.get("accepted_kwh", offer.get("quantity_kwh")),
                field="accepted_kwh",
                minimum=0.001,
                maximum=float(offer.get("quantity_kwh") or 0.001),
            )
            accepted_kwh = round(min(accepted_kwh, float(offer.get("quantity_kwh") or 0.0)), 3)
            acceptance_id = f"energy_accept_{uuid.uuid4().hex[:12]}"
            offer["state"] = "accepting"
            offer["acceptance"] = {
                "id": acceptance_id,
                "buyer_id": str(request.get("buyer_id") or "neighbor-demo"),
                "buyer_display_name": str(request.get("buyer_display_name") or "Demo Neighbour"),
                "accepted_kwh": accepted_kwh,
                "accepted_at": isoformat(now),
            }
            offer["updated_at"] = isoformat(now)
            self.save_state()

        amount_cents = max(1, int(round(accepted_kwh * int(offer["price_cents_per_kwh"]))))
        proof = self.create_external_value_proof({"id": offer_id}, {"id": acceptance_id})
        receipt = {
            "id": f"pay_energy_{uuid.uuid4().hex[:12]}",
            "protocol": "mpp",
            "method": "tempo_mpp" if proof.get("provider") == "tempo_mpp" else "demo_payment_proof",
            "status": "succeeded" if proof.get("state") in {"succeeded", "skipped"} else "proof_failed_but_demo_recorded",
            "real_settlement": False,
            "amount_cents": amount_cents,
            "currency": "EUR",
            "created_at": isoformat(utcnow()),
            "note": (
                "The app-level amount represents the demo energy offer. "
                "The linked MPP proof URL may be a fixed hackathon test resource."
            ),
        }
        if proof.get("state") != "skipped":
            receipt["external_value_proof"] = proof
            receipt["real_settlement"] = bool(proof.get("real_settlement")) and proof.get("network") == "mainnet"

        settlement = {
            "id": f"energy_settle_{uuid.uuid4().hex[:12]}",
            "offer_id": offer_id,
            "acceptance_id": acceptance_id,
            "state": "demo_settled",
            "accepted_kwh": accepted_kwh,
            "price_cents_per_kwh": int(offer["price_cents_per_kwh"]),
            "amount_cents": amount_cents,
            "currency": "EUR",
            "payment_receipt": receipt,
            "legal_settlement": False,
            "physical_delivery": False,
            "scope": "demo_contract_and_payment_proof_only_no_physical_grid_settlement",
            "created_at": isoformat(utcnow()),
        }
        with self.lock:
            current = self.state["energy_offers"][offer_id]
            current["state"] = "accepted"
            current["settlement"] = settlement
            current["updated_at"] = isoformat(utcnow())
            self.save_state()
            offer_snapshot = current
        self.audit(
            "energy.offer_accepted",
            actor=str(request.get("buyer_id") or "neighbor-demo"),
            reason="Demo neighbour accepted the discoverable household surplus-energy offer",
            purchase_id=offer_id,
            refs={
                "offer_id": offer_id,
                "acceptance_id": acceptance_id,
                "settlement_id": settlement["id"],
                "payment_receipt_id": receipt["id"],
                "mpp_reference": proof_reference(proof),
                "explorer_url": proof_explorer_url(proof),
                "legal_settlement": False,
                "physical_delivery": False,
            },
        )
        return {"offer": offer_snapshot, "settlement": settlement}

    def http_json(
        self,
        url: str,
        *,
        method: str,
        token: str,
        payload: dict[str, Any] | None = None,
        timeout: int = 10,
    ) -> Any:
        body = None
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if payload is not None:
            body = json.dumps(payload, default=json_default).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise UpstreamError(f"upstream HTTP {exc.code} for {url}", detail=detail) from exc
        except urllib.error.URLError as exc:
            raise UpstreamError(f"upstream request failed for {url}", detail=str(exc)) from exc

    def checkout(self, request: dict[str, Any], headers: dict[str, str], raw_body: bytes) -> tuple[int, dict[str, str], dict[str, Any]]:
        quote_id = str(request.get("quote_id") or "")
        approval_id = str(request.get("approval_id") or "")
        idempotency_key = str(request.get("idempotency_key") or headers.get("idempotency-key") or "")
        if not quote_id:
            raise BadRequest("quote_id is required")
        if not approval_id:
            raise BadRequest("approval_id is required")
        if not idempotency_key:
            raise BadRequest("idempotency_key or Idempotency-Key header is required")

        with self.lock:
            existing_order_id = self.state["idempotency"].get(idempotency_key)
            if existing_order_id:
                order = self.state["orders"][existing_order_id]
                return 200, {}, {"idempotent_replay": True, "order": order}

            quote = self.get_quote(quote_id)
            approval = self.get_approval(approval_id)
            self.require_checkout_ready(quote, approval)

        authorization = headers.get("authorization", "")
        if not authorization:
            challenge = self.create_payment_challenge(quote, approval, raw_body, idempotency_key)
            authorization_hint = self.payment_provider.authorization_hint(challenge)
            headers_out = {
                "WWW-Authenticate": self.payment_challenge_header(challenge),
                "Cache-Control": "no-store",
            }
            response_body = {
                "type": "https://agentcart.local/problems/payment-required",
                "title": "Payment Required",
                "status": 402,
                "detail": "Retry this checkout with an Authorization: Payment credential.",
                "challenge": challenge,
            }
            if authorization_hint:
                response_body["authorization_hint"] = authorization_hint
            if self.payment_provider.name == "demo" and authorization_hint:
                response_body["demo_authorization"] = authorization_hint
            return (
                402,
                headers_out,
                response_body,
            )

        challenge_id = self.payment_provider.parse_authorization(authorization)
        with self.lock:
            challenge = self.state["challenges"].get(challenge_id)
            if not challenge:
                raise Forbidden("payment challenge is unknown")
            if challenge.get("used_at"):
                raise Conflict("payment challenge has already been used")
            if parse_time(challenge["expires_at"]) < utcnow():
                raise Conflict("payment challenge has expired")
            if challenge["quote_id"] != quote_id or challenge["approval_id"] != approval_id:
                raise Forbidden("payment credential does not match quote and approval")
            if challenge["request_digest"] != sha256_b64(raw_body):
                raise Forbidden("payment credential is not bound to this checkout request body")

            quote = self.get_quote(quote_id)
            approval = self.get_approval(approval_id)
            self.require_checkout_ready(quote, approval)
            policy_result = self.evaluate_policy_for_quote(quote)
            if policy_result["decision"] == "deny":
                raise Forbidden("policy denied quote at checkout", detail=policy_result)
            order = self.create_order_locked(
                quote,
                approval,
                challenge,
                authorization,
                idempotency_key=idempotency_key,
                policy_result=policy_result,
            )
            challenge["used_at"] = isoformat(utcnow())
            self.save_state()

        receipt = order["payment_receipt"]
        headers_out = {
            "Payment-Receipt": b64url_json(receipt),
            "Location": f"/v1/orders/{order['id']}",
        }
        return 201, headers_out, {"order": order, "payment_receipt": receipt}

    def require_checkout_ready(self, quote: dict[str, Any], approval: dict[str, Any]) -> None:
        if parse_time(quote["expires_at"]) < utcnow():
            raise Conflict("quote has expired")
        if approval["quote_id"] != quote["id"]:
            raise BadRequest("approval does not belong to quote")
        if approval["state"] != "approved":
            raise Forbidden(f"approval is {approval['state']}")

    def create_payment_challenge(
        self,
        quote: dict[str, Any],
        approval: dict[str, Any],
        raw_body: bytes,
        idempotency_key: str,
    ) -> dict[str, Any]:
        now = utcnow()
        challenge = {
            "id": f"chal_{uuid.uuid4().hex[:16]}",
            "realm": "agentcart.local",
            **self.payment_provider.challenge_fields(),
            "quote_id": quote["id"],
            "approval_id": approval["id"],
            "merchant_id": quote["merchant_id"],
            "amount_cents": quote["total_cents"],
            "currency": quote["currency"],
            "request_digest": sha256_b64(raw_body),
            "idempotency_key": idempotency_key,
            "created_at": isoformat(now),
            "expires_at": isoformat(now + dt.timedelta(seconds=CHALLENGE_TTL_SECONDS)),
            "used_at": None,
            "request": {
                "quote_id": quote["id"],
                "approval_id": approval["id"],
                "amount_cents": quote["total_cents"],
                "currency": quote["currency"],
                "merchant_id": quote["merchant_id"],
                "digest_alg": "sha-256",
            },
        }
        with self.lock:
            self.state["challenges"][challenge["id"]] = challenge
            self.save_state()
        self.audit(
            "payment.challenge_created",
            actor="agentcart",
            reason="checkout reached HTTP 402 Payment authentication step",
            purchase_id=quote["id"],
            refs={"challenge_id": challenge["id"], "quote_id": quote["id"], "approval_id": approval["id"]},
        )
        return challenge

    def payment_challenge_header(self, challenge: dict[str, Any]) -> str:
        request_param = b64url_json(challenge["request"])
        digest = f"sha-256=:{challenge['request_digest']}:"
        return (
            f'Payment id="{challenge["id"]}", '
            f'realm="{challenge["realm"]}", '
            f'method="{challenge["method"]}", '
            f'intent="{challenge["intent"]}", '
            f'expires="{challenge["expires_at"]}", '
            f'digest="{digest}", '
            f'request="{request_param}"'
        )

    def parse_demo_authorization(self, authorization: str) -> str:
        if not authorization.startswith("Payment "):
            raise Forbidden("Authorization must use the Payment scheme")
        credential = authorization[len("Payment ") :].strip()
        if not credential.startswith("demo:"):
            raise Forbidden("only demo payment credentials are supported in this MVP")
        challenge_id = credential[len("demo:") :].strip()
        if not challenge_id:
            raise Forbidden("demo payment credential is missing challenge id")
        return challenge_id

    def create_order_locked(
        self,
        quote: dict[str, Any],
        approval: dict[str, Any],
        challenge: dict[str, Any],
        authorization: str,
        *,
        idempotency_key: str,
        policy_result: dict[str, Any],
    ) -> dict[str, Any]:
        for item in quote["items"]:
            product_id = item["product_id"]
            quantity = int(item["quantity"])
            available = int(self.state["stock"].get(product_id, 0))
            if available < quantity:
                raise Conflict(f"stock changed; only {available} units available for {product_id}")

        order_id = f"order_{uuid.uuid4().hex[:16]}"
        receipt = self.payment_provider.receipt(
            quote=quote,
            approval=approval,
            challenge=challenge,
            authorization=authorization,
        )
        value_proof = self.create_external_value_proof(quote, approval)
        if value_proof["state"] != "skipped":
            receipt["external_value_proof"] = value_proof
        order = {
            "id": order_id,
            "merchant_order_id": f"FTS-{order_id[-8:].upper()}",
            "quote_id": quote["id"],
            "approval_id": approval["id"],
            "merchant_id": quote["merchant_id"],
            "state": "accepted",
            "items": quote["items"],
            "total_cents": quote["total_cents"],
            "currency": quote["currency"],
            "delivery_estimate": quote["delivery_estimate"],
            "delivery_window": quote.get("delivery_window")
            or delivery_window_from_estimate(quote["delivery_estimate"], timezone=self.config.timezone),
            "shipment": self.initial_shipment_state(quote),
            "merchant_of_record": quote["merchant_of_record"],
            "payment_receipt": receipt,
            "merchant_order": {"state": "pending"},
            "vikunja_task": {"state": "pending"},
            "calendar_event": {"state": "pending"},
            "created_at": isoformat(utcnow()),
            "updated_at": isoformat(utcnow()),
        }
        adapter = self.adapter_for_merchant(quote["merchant_id"])
        merchant_order = adapter.create_merchant_order(order, quote)
        order["merchant_order"] = merchant_order
        if merchant_order.get("id"):
            order["merchant_order_id"] = str(merchant_order["id"])
        fulfillment = merchant_order.get("fulfillment")
        if isinstance(fulfillment, dict) and fulfillment:
            order["shipment"].update(
                {
                    "carrier": fulfillment.get("carrier"),
                    "tracking_number": fulfillment.get("tracking_number"),
                    "tracking_url": fulfillment.get("tracking_url"),
                    "status": fulfillment.get("state") or order["shipment"]["status"],
                    "source": fulfillment.get("source") or order["shipment"]["source"],
                    "note": fulfillment.get("note") or order["shipment"]["note"],
                }
            )
        for item in quote["items"]:
            self.state["stock"][item["product_id"]] = int(self.state["stock"][item["product_id"]]) - int(item["quantity"])
        self.state["orders"][order_id] = order
        self.state["idempotency"][idempotency_key] = order_id
        self.save_state()

        self.audit(
            "order.created",
            actor="agentcart",
            reason=f"approved quote paid through {receipt['method']} checkout",
            purchase_id=quote["id"],
            refs={"order_id": order_id, "quote_id": quote["id"], "challenge_id": challenge["id"]},
            policy_result=policy_result,
        )
        order["vikunja_task"] = self.sync_vikunja_task(order, quote)
        order["calendar_event"] = self.sync_home_assistant_delivery_event(order, quote)
        self.state["orders"][order_id] = order
        self.save_state()
        return order

    def initial_shipment_state(self, quote: dict[str, Any]) -> dict[str, Any]:
        return {
            "carrier": None,
            "tracking_number": None,
            "tracking_url": None,
            "status": "not_shipped",
            "estimated_delivery": quote.get("delivery_window", {}).get("latest_date"),
            "last_checked_at": None,
            "source": "merchant_demo",
            "note": "Tracking starts once the merchant provides a carrier and tracking number.",
        }

    def sync_vikunja_task(self, order: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
        if not self.config.vikunja_api_url or not self.config.vikunja_token or self.config.vikunja_project_id is None:
            return {"state": "skipped", "reason": "Vikunja is not configured"}
        product_summary = ", ".join(f"{item['quantity']}x {item['title']}" for item in order["items"])
        title = f"Ordered: {product_summary}"
        delivery_window = order.get("delivery_window") or {}
        delivery_line = delivery_window.get("label") or order["delivery_estimate"]["label"]
        if delivery_window.get("earliest_date") and delivery_window.get("latest_date"):
            delivery_line = (
                f"{delivery_line} ({delivery_window['earliest_date']} to {delivery_window['latest_date']})"
            )
        description = (
            f"AgentCart order `{order['id']}`\n\n"
            f"- Merchant: {quote['merchant']['name']}\n"
            f"- Total: {money(order['total_cents'], order['currency'])}\n"
            f"- Reason: {quote['reason']}\n"
            f"- Approval: {order['approval_id']}\n"
            f"- Payment receipt: {order['payment_receipt']['id']}\n"
            f"- Delivery estimate: {delivery_line}\n"
            f"- Shipment status: {order.get('shipment', {}).get('status', 'not_shipped')}\n"
        )
        payload = {
            "title": title,
            "description": description,
            "labels": [{"title": "shopping"}, {"title": "agentcart"}],
        }
        due_date = delivery_window.get("latest_date")
        if due_date:
            payload["due_date"] = f"{due_date}T18:00:00{self.local_timezone_offset_suffix()}"
        url = f"{self.config.vikunja_api_url}/projects/{self.config.vikunja_project_id}/tasks"
        matched_task = self.match_open_purchase_task(order)
        try:
            response = self.http_json(
                url,
                method="PUT",
                token=self.config.vikunja_token,
                payload=payload,
                timeout=10,
            )
            task_id = response.get("id") if isinstance(response, dict) else None
            result = {
                "state": "created",
                "task_id": task_id,
                "url": f"{self.config.vikunja_web_url}/tasks/{task_id}" if self.config.vikunja_web_url and task_id else None,
                "matched_open_task": matched_task,
            }
        except AgentCartError as exc:
            result = {"state": "failed", "error": str(exc), "detail": exc.detail, "matched_open_task": matched_task}
        self.audit(
            "vikunja.sync",
            actor="agentcart",
            reason=f"Vikunja task sync {result['state']}",
            purchase_id=quote["id"],
            refs={"order_id": order["id"], "vikunja": result},
        )
        return result

    def local_timezone_offset_suffix(self) -> str:
        offset = utcnow().astimezone(ZoneInfo(self.config.timezone)).utcoffset()
        if offset is None:
            return "Z"
        total_minutes = int(offset.total_seconds() // 60)
        sign = "+" if total_minutes >= 0 else "-"
        total_minutes = abs(total_minutes)
        return f"{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"

    def match_open_purchase_task(self, order: dict[str, Any]) -> dict[str, Any] | None:
        tasks_result = self.list_open_vikunja_tasks(limit=20)
        if tasks_result.get("state") != "ok":
            return None
        product_terms = " ".join(
            " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("sku") or ""),
                    str(item.get("category") or ""),
                ]
            )
            for item in order["items"]
        )
        product_tokens = set(search_tokens(product_terms))
        purchase_markers = {"buy", "order", "ordered", "shopping", "kaufen", "bestellen", "besorgen"}
        for task in tasks_result.get("tasks", []):
            title = str(task.get("title") or "").lower()
            task_tokens = set(search_tokens(title))
            if task_tokens & product_tokens and any(marker in title for marker in purchase_markers):
                return {
                    "id": task.get("id"),
                    "title": task.get("title"),
                    "url": task.get("url"),
                    "match": "product_purchase_intent",
                }
            if "hazel" in product_tokens and "hazel" in task_tokens:
                return {
                    "id": task.get("id"),
                    "title": task.get("title"),
                    "url": task.get("url"),
                    "match": "favorite_product",
                }
        return None

    def list_open_vikunja_tasks(self, *, limit: int = 20) -> dict[str, Any]:
        if not self.config.vikunja_api_url or not self.config.vikunja_token:
            return {"state": "skipped", "reason": "Vikunja is not configured", "tasks": []}
        params = urllib.parse.urlencode({"per_page": str(max(limit * 2, limit))})
        if self.config.vikunja_project_id is not None:
            url = f"{self.config.vikunja_api_url}/projects/{self.config.vikunja_project_id}/tasks?{params}"
        else:
            url = f"{self.config.vikunja_api_url}/tasks/all?{params}"
        try:
            response = self.http_json(url, method="GET", token=self.config.vikunja_token, timeout=10)
        except AgentCartError as exc:
            return {"state": "failed", "error": str(exc), "detail": exc.detail, "tasks": []}
        raw_tasks: list[dict[str, Any]]
        if isinstance(response, list):
            raw_tasks = [task for task in response if isinstance(task, dict)]
        elif isinstance(response, dict) and isinstance(response.get("tasks"), list):
            raw_tasks = [task for task in response["tasks"] if isinstance(task, dict)]
        else:
            raw_tasks = []
        tasks = []
        for task in raw_tasks:
            if task.get("done"):
                continue
            task_id = task.get("id")
            due_date = task.get("due_date")
            if isinstance(due_date, str) and due_date.startswith("0001-01-01"):
                due_date = None
            tasks.append(
                {
                    "id": task_id,
                    "title": task.get("title"),
                    "project_id": task.get("project_id"),
                    "due_date": due_date,
                    "labels": task.get("labels") or [],
                    "url": f"{self.config.vikunja_web_url}/tasks/{task_id}" if self.config.vikunja_web_url and task_id else None,
                }
            )
        tasks.sort(key=lambda task: (task.get("due_date") or "9999", str(task.get("title") or "")))
        return {"state": "ok", "tasks": tasks[:limit]}

    def sync_home_assistant_delivery_event(self, order: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
        if not self.config.homeassistant_url or not self.config.homeassistant_token:
            return {"state": "skipped", "reason": "Home Assistant is not configured"}
        if not self.config.homeassistant_calendar_entity_id:
            return {"state": "skipped", "reason": "HOMEASSISTANT_CALENDAR_ENTITY_ID is not configured"}
        window = order.get("delivery_window") or {}
        earliest = parse_date(window.get("earliest_date"))
        latest = parse_date(window.get("latest_date"))
        if earliest is None or latest is None:
            return {"state": "skipped", "reason": "order has no absolute delivery window"}
        product_summary = ", ".join(f"{item['quantity']}x {item['title']}" for item in order["items"])
        summary = f"Delivery: {product_summary}"
        description = (
            f"AgentCart delivery window\n\n"
            f"Order: {order['id']}\n"
            f"Merchant order: {order['merchant_order_id']}\n"
            f"Merchant: {quote['merchant']['name']}\n"
            f"Total: {money(order['total_cents'], order['currency'])}\n"
            f"Reason: {quote['reason']}\n"
            f"Delivery estimate: {window.get('label', order['delivery_estimate']['label'])}\n"
            f"Shipment status: {order.get('shipment', {}).get('status', 'not_shipped')}\n"
        )
        payload = {
            "entity_id": self.config.homeassistant_calendar_entity_id,
            "summary": summary,
            "description": description,
            "start_date": earliest.isoformat(),
            "end_date": (latest + dt.timedelta(days=1)).isoformat(),
        }
        url = f"{self.config.homeassistant_url}/api/services/calendar/create_event"
        try:
            response = self.http_json(
                url,
                method="POST",
                token=self.config.homeassistant_token,
                payload=payload,
                timeout=10,
            )
            result = {
                "state": "created",
                "entity_id": self.config.homeassistant_calendar_entity_id,
                "summary": summary,
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "response": response,
            }
        except AgentCartError as exc:
            result = {"state": "failed", "error": str(exc), "detail": exc.detail}
        self.audit(
            "calendar.event_created" if result["state"] == "created" else "calendar.event_failed",
            actor="agentcart",
            reason=f"Home Assistant delivery calendar sync {result['state']}",
            purchase_id=quote["id"],
            refs={"order_id": order["id"], "calendar": result},
        )
        return result

    def get_order(self, order_id: str) -> dict[str, Any]:
        order = self.state.get("orders", {}).get(order_id)
        if not order:
            raise NotFound(f"Unknown order: {order_id}")
        return order

    def refund_order(self, order_id: str, request: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            order = json.loads(json.dumps(self.get_order(order_id), default=json_default))
        amount_cents = safe_int(
            request.get("amount_cents", order.get("total_cents", 1)),
            field="amount_cents",
            minimum=1,
            maximum=max(1, int(order.get("total_cents") or 1)),
        )
        reason = str(request.get("reason") or "Hackathon demo refund through WooCommerce ShopBridge").strip()
        rail = str(request.get("rail") or order.get("payment_receipt", {}).get("method") or "agentcart-demo")
        adapter = self.adapter_for_merchant(order["merchant_id"])
        merchant_refund = adapter.create_merchant_refund(
            order,
            {
                "amount_cents": amount_cents,
                "reason": reason,
                "rail": rail,
            },
        )
        refund = {
            "id": f"refund_{uuid.uuid4().hex[:12]}",
            "order_id": order_id,
            "merchant_order_id": order.get("merchant_order_id"),
            "merchant_refund_id": str(merchant_refund.get("refund_id") or merchant_refund.get("id") or ""),
            "state": str(merchant_refund.get("state") or "refund_recorded"),
            "amount_cents": int(merchant_refund.get("amount_cents") or amount_cents),
            "currency": str(merchant_refund.get("currency") or order.get("currency") or "EUR"),
            "rail": str(merchant_refund.get("rail") or rail),
            "reason": reason,
            "real_refund_verified": bool(merchant_refund.get("real_refund_verified")),
            "merchant_refund": merchant_refund,
            "created_at": isoformat(utcnow()),
        }
        with self.lock:
            current_order = self.state["orders"][order_id]
            refunds = current_order.setdefault("refunds", [])
            refunds.append(refund)
            current_order["refund_state"] = (
                "rail_refund_verified" if refund["real_refund_verified"] else "demo_refund_recorded"
            )
            current_order["state"] = "refund_recorded"
            current_order["updated_at"] = isoformat(utcnow())
            self.save_state()
            order_after = current_order

        self.audit(
            "order.refund_recorded",
            actor="agentcart",
            reason=reason,
            purchase_id=order_after["quote_id"],
            refs={
                "order_id": order_id,
                "refund_id": refund["id"],
                "merchant_refund_id": refund["merchant_refund_id"],
                "real_refund_verified": refund["real_refund_verified"],
                "rail": refund["rail"],
            },
        )
        return {"order": order_after, "refund": refund}

    def render_delivery_calendar(self) -> str:
        now = utcnow()
        dtstamp = now.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//AgentCart//Deliveries//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "X-WR-CALNAME:AgentCart Deliveries",
            f"X-WR-TIMEZONE:{ical_escape(self.config.timezone)}",
        ]
        orders = sorted(
            self.state.get("orders", {}).values(),
            key=lambda order: str(order.get("delivery_window", {}).get("earliest_date") or "9999-12-31"),
        )
        for order in orders:
            if order.get("state") not in {"accepted", "fulfilled", "shipped"}:
                continue
            window = order.get("delivery_window") or {}
            earliest = parse_date(window.get("earliest_date"))
            latest = parse_date(window.get("latest_date"))
            if earliest is None or latest is None:
                continue
            product_summary = ", ".join(f"{item['quantity']}x {item['title']}" for item in order.get("items", []))
            summary = f"Delivery: {product_summary or order.get('merchant_order_id', order.get('id', 'AgentCart order'))}"
            description = (
                f"Order: {order.get('id')}\n"
                f"Merchant order: {order.get('merchant_order_id')}\n"
                f"Total: {money(int(order.get('total_cents', 0)), str(order.get('currency', 'EUR')))}\n"
                f"Delivery estimate: {window.get('label', order.get('delivery_estimate', {}).get('label', 'estimated'))}\n"
                f"Shipment status: {order.get('shipment', {}).get('status', 'not_shipped')}"
            )
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{ical_escape(str(order.get('id')))}@agentcart-deliveries",
                    f"DTSTAMP:{dtstamp}",
                    f"DTSTART;VALUE=DATE:{earliest.strftime('%Y%m%d')}",
                    f"DTEND;VALUE=DATE:{(latest + dt.timedelta(days=1)).strftime('%Y%m%d')}",
                    f"SUMMARY:{ical_escape(summary)}",
                    f"DESCRIPTION:{ical_escape(description)}",
                    "TRANSP:TRANSPARENT",
                    "END:VEVENT",
                ]
            )
        lines.append("END:VCALENDAR")
        return "\r\n".join(part for line in lines for part in ical_fold(line)) + "\r\n"

    def dashboard_state(self) -> dict[str, Any]:
        with self.lock:
            if self.expire_stale_approvals_locked():
                self.save_state()
            if self.expire_energy_offers_locked():
                self.save_state()
            return {
                "products": self.search_catalog("")["products"],
                "quotes": sort_by_time(list(self.state["quotes"].values()))[-20:],
                "approvals": sort_by_time(list(self.state["approvals"].values()))[-20:],
                "orders": sort_by_time(list(self.state["orders"].values()))[-20:],
                "energy_offers": sort_by_time(list(self.state["energy_offers"].values()))[-20:],
                "audit": sort_by_time(self.list_audit_events(), field="timestamp")[-50:],
                "policy": self.read_policy(),
                "capabilities": self.capability_document(),
            }

    def demo_trigger_low_tea(self) -> dict[str, Any]:
        quote = self.create_quote(
            {
                "agent_id": "home-assistant",
                "reason": "Home Assistant tea stock sensor reported low household tea stock",
                "items": [{"product_id": "tea_sencha_100g", "quantity": 1}],
                "ship_to": {
                    "country": self.config.default_ship_country,
                    "postal_code": self.config.default_ship_postal_code,
                },
            }
        )
        approval = self.create_approval(
            {"quote_id": quote["id"], "channel": "home_assistant", "delivery_channels": ["home_assistant", "web", "api"]}
        )
        return {"quote": quote, "approval": approval}

    def demo_trigger_woo_tea(self) -> dict[str, Any]:
        catalog = self.search_catalog("Hazel's Chocolate Tea")
        product = next(
            (
                item
                for item in catalog.get("products", [])
                if item.get("merchant_id") == self.config.woocommerce_merchant_id
                and item.get("eligible_for_agent_checkout")
                and item.get("availability") == "in_stock"
            ),
            None,
        )
        product_id = str(product.get("id")) if product else "woo_203"
        quote = self.create_quote(
            {
                "agent_id": "home-assistant",
                "reason": "Household agent selected an opt-in WooCommerce tea merchant",
                "items": [{"product_id": product_id, "quantity": 1}],
                "ship_to": {
                    "country": self.config.default_ship_country,
                    "postal_code": self.config.default_ship_postal_code,
                },
            }
        )
        approval = self.create_approval(
            {"quote_id": quote["id"], "channel": "home_assistant", "delivery_channels": ["home_assistant", "web", "api"]}
        )
        return {"quote": quote, "approval": approval}

    def demo_finish_checkout(self, approval_id: str) -> dict[str, Any]:
        approval = self.get_approval(approval_id)
        quote_id = approval["quote_id"]
        request = {
            "quote_id": quote_id,
            "approval_id": approval_id,
            "idempotency_key": f"demo-{approval_id}",
        }
        raw = json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
        status, _headers, body = self.checkout(request, {"idempotency-key": request["idempotency_key"]}, raw)
        if status != 402:
            return body
        auth = body["demo_authorization"]
        status, _headers, body = self.checkout(
            request,
            {"idempotency-key": request["idempotency_key"], "authorization": auth},
            raw,
        )
        return {"status": status, **body}


class AgentCartHandler(BaseHTTPRequestHandler):
    server_version = "AgentCart/0.1"

    def do_GET(self) -> None:
        self.handle_request("GET")

    def do_POST(self) -> None:
        self.handle_request("POST")

    @property
    def service(self) -> AgentCartService:
        return self.server.service  # type: ignore[attr-defined]

    def handle_request(self, method: str) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            if method == "GET":
                self.route_get(path, parsed)
            elif method == "POST":
                self.route_post(path, parsed)
            else:
                raise NotFound("route not found")
        except AgentCartError as exc:
            self.send_error_json(exc.status, str(exc), detail=exc.detail)
        except Exception as exc:  # pragma: no cover - defensive server logging
            traceback.print_exc()
            self.send_error_json(500, "internal server error", detail=str(exc))

    def route_get(self, path: str, parsed: urllib.parse.ParseResult) -> None:
        query = urllib.parse.parse_qs(parsed.query)
        if path == "/health":
            self.send_json({"ok": True, "service": "agentcart", "time": isoformat(utcnow())})
            return
        if path == "/.well-known/agentcart.json":
            self.send_json(self.service.capability_document())
            return
        if path == "/openapi.json":
            self.send_json(self.service.openapi_document())
            return
        if path == "/llms.txt":
            self.send_text(self.service.llms_text())
            return
        if path == DELIVERY_CALENDAR_ROUTE:
            self.handle_delivery_calendar(query)
            return
        if path == "/architecture.html":
            architecture_path = pathlib.Path(__file__).with_name("architecture.html")
            if not architecture_path.exists():
                raise NotFound("architecture file not found")
            self.send_html(architecture_path.read_text())
            return
        if path == "/presentation.html":
            presentation_path = pathlib.Path(__file__).with_name("presentation.html")
            if not presentation_path.exists():
                raise NotFound("presentation file not found")
            self.send_html(presentation_path.read_text())
            return
        if path == "/intent-auction-overview.html":
            intent_path = pathlib.Path(__file__).with_name("intent-auction-overview.html")
            if not intent_path.exists():
                raise NotFound("intent auction overview file not found")
            self.send_html(intent_path.read_text())
            return
        if path == "/protocol-fields.html":
            fields_path = pathlib.Path(__file__).with_name("protocol-fields.html")
            if not fields_path.exists():
                raise NotFound("protocol fields file not found")
            self.send_html(fields_path.read_text())
            return
        if path == "/payment-options.html":
            payment_options_path = pathlib.Path(__file__).with_name("payment-options.html")
            if not payment_options_path.exists():
                raise NotFound("payment options file not found")
            self.send_html(payment_options_path.read_text())
            return
        if path == "/onboarding.html":
            onboarding_path = pathlib.Path(__file__).with_name("onboarding.html")
            if not onboarding_path.exists():
                raise NotFound("onboarding file not found")
            self.send_html(onboarding_path.read_text())
            return
        if path == "/agent":
            agent_path = pathlib.Path(__file__).with_name("agent.html")
            if not agent_path.exists():
                raise NotFound("agent console file not found")
            self.send_html(agent_path.read_text())
            return
        if path == "/judge":
            self.send_html(render_judge_view(self.service))
            return
        if path == "/registry":
            self.send_html(
                render_registry_page(
                    self.service,
                    first_query(query, "q"),
                    first_query(query, "country", self.service.config.default_ship_country),
                    first_query(query, "postal_code", self.service.config.default_ship_postal_code),
                )
            )
            return
        if path == "/energy":
            self.send_html(render_energy_page(self.service, first_query(query, "error")))
            return
        if path == "/":
            self.send_html(render_dashboard(self.service.dashboard_state()))
            return
        order_page_match = ORDER_PAGE_ROUTE.match(path)
        if order_page_match:
            self.send_html(render_order_proof_page(self.service, order_page_match.group(1)))
            return
        if path == "/v1/catalog/search":
            self.require_auth_if_configured()
            self.send_json(self.service.search_catalog(first_query(query, "q")))
            return
        if path == "/v1/registry":
            self.send_json(self.service.registry_document())
            return
        if path == "/v1/quote-tournament":
            self.require_auth_if_configured()
            self.send_json(
                self.service.quote_tournament(
                    {
                        "q": first_query(query, "q", first_query(query, "query", "tea")),
                        "country": first_query(query, "country", first_query(query, "ship_country", self.service.config.default_ship_country)),
                        "postal_code": first_query(query, "postal_code", self.service.config.default_ship_postal_code),
                        "quantity": first_query(query, "quantity", "1"),
                        "max_candidates": first_query(query, "max_candidates", "6"),
                    }
                )
            )
            return
        if path == "/v1/dashboard/state":
            self.require_auth_if_configured()
            self.send_json(self.service.dashboard_state())
            return
        if path == "/v1/integrations/status":
            self.require_auth_if_configured()
            self.send_json(self.service.integration_status())
            return
        if path == "/v1/tasks/open":
            self.require_auth_if_configured()
            limit_raw = first_query(query, "limit", "20")
            try:
                limit = max(1, min(100, int(limit_raw)))
            except ValueError as exc:
                raise BadRequest("limit must be an integer") from exc
            self.send_json(self.service.list_open_vikunja_tasks(limit=limit))
            return
        if path == "/v1/energy/surplus":
            self.require_auth_if_configured()
            self.send_json(self.service.energy_surplus())
            return
        if path == "/v1/energy/offers":
            self.require_auth_if_configured()
            self.send_json(self.service.list_energy_offers())
            return
        energy_offer_match = ENERGY_OFFER_ROUTE.match(path)
        if energy_offer_match:
            self.require_auth_if_configured()
            self.send_json(self.service.get_energy_offer(energy_offer_match.group(1)))
            return
        product_match = PRODUCT_ROUTE.match(path)
        if product_match:
            self.require_auth_if_configured()
            self.send_json(self.service.get_product(product_match.group(1)))
            return
        quote_match = QUOTE_ROUTE.match(path)
        if quote_match:
            self.require_auth_if_configured()
            self.send_json(self.service.get_quote(quote_match.group(1)))
            return
        approval_api_match = APPROVAL_ROUTE.match(path)
        if approval_api_match:
            self.require_auth_if_configured()
            approval = self.service.get_approval(approval_api_match.group(1))
            self.send_json(self.service.public_approval(approval))
            return
        approval_page_match = APPROVAL_PAGE_ROUTE.match(path)
        if approval_page_match:
            token = first_query(query, "token")
            self.send_html(render_approval_page(self.service, approval_page_match.group(1), token))
            return
        order_match = ORDER_ROUTE.match(path)
        if order_match:
            self.require_auth_if_configured()
            self.send_json(self.service.get_order(order_match.group(1)))
            return
        audit_match = AUDIT_ROUTE.match(path)
        if audit_match:
            self.require_auth_if_configured()
            self.send_json({"events": self.service.list_audit_events(audit_match.group(1))})
            return
        raise NotFound("route not found")

    def handle_delivery_calendar(self, query: dict[str, list[str]]) -> None:
        if not self.service.config.delivery_calendar_enabled:
            raise NotFound("delivery calendar feed is not enabled")
        if not self.service.config.delivery_calendar_token:
            raise Forbidden("delivery calendar feed token is not configured")
        supplied = first_query(query, "token")
        if not hmac.compare_digest(supplied, self.service.config.delivery_calendar_token):
            raise Unauthorized("missing or invalid delivery calendar token")
        self.send_ical(self.service.render_delivery_calendar())

    def route_post(self, path: str, _parsed: urllib.parse.ParseResult) -> None:
        if path == "/demo/trigger-low-tea":
            result = self.service.demo_trigger_low_tea()
            self.redirect(f"/approvals/{result['approval']['id']}?token={urllib.parse.quote(result['approval']['decision_token'])}")
            return
        if path == "/demo/trigger-woo-tea":
            result = self.service.demo_trigger_woo_tea()
            self.redirect(f"/approvals/{result['approval']['id']}?token={urllib.parse.quote(result['approval']['decision_token'])}")
            return
        if path == "/demo/energy-offer":
            try:
                self.service.create_energy_offer({})
            except AgentCartError as exc:
                self.redirect(f"/energy?error={urllib.parse.quote(str(exc))}")
                return
            self.redirect("/energy")
            return
        demo_energy_accept_match = DEMO_ENERGY_OFFER_ACCEPT_ROUTE.match(path)
        if demo_energy_accept_match:
            try:
                self.service.accept_energy_offer(demo_energy_accept_match.group(1), {})
            except AgentCartError as exc:
                self.redirect(f"/energy?error={urllib.parse.quote(str(exc))}")
                return
            self.redirect("/energy")
            return
        demo_checkout_match = DEMO_CHECKOUT_ROUTE.match(path)
        if demo_checkout_match:
            result = self.service.demo_finish_checkout(demo_checkout_match.group(1))
            order = result.get("order") or {}
            quote_id = order.get("quote_id", "")
            self.redirect(f"/?purchase_id={urllib.parse.quote(quote_id)}")
            return
        demo_refund_match = DEMO_ORDER_REFUND_ROUTE.match(path)
        if demo_refund_match:
            self.service.refund_order(
                demo_refund_match.group(1),
                {"reason": "Hackathon demo: merchant records a refund through WooCommerce ShopBridge"},
            )
            self.redirect(f"/orders/{demo_refund_match.group(1)}")
            return
        page_action_match = APPROVAL_PAGE_ACTION_ROUTE.match(path)
        if page_action_match:
            form = self.read_form()
            decision = "approved" if page_action_match.group(2) == "approve" else "rejected"
            self.service.decide_approval(
                page_action_match.group(1),
                {"decision": decision, "token": form.get("token", ""), "approver": "dashboard"},
            )
            self.redirect(f"/approvals/{page_action_match.group(1)}?token={urllib.parse.quote(form.get('token', ''))}")
            return

        self.require_auth_if_configured()
        raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
        payload = parse_json_body(raw_body)
        if path == "/v1/demo/low-tea":
            self.send_json(self.service.demo_trigger_low_tea(), status=201)
            return
        if path == "/v1/demo/woo-tea":
            self.send_json(self.service.demo_trigger_woo_tea(), status=201)
            return
        if path == "/v1/energy/offers":
            self.send_json(self.service.create_energy_offer(payload), status=201)
            return
        energy_offer_accept_match = ENERGY_OFFER_ACCEPT_ROUTE.match(path)
        if energy_offer_accept_match:
            self.send_json(self.service.accept_energy_offer(energy_offer_accept_match.group(1), payload))
            return
        if path == "/v1/quotes":
            self.send_json(self.service.create_quote(payload), status=201)
            return
        if path == "/v1/policies/evaluate":
            quote_id = str(payload.get("quote_id") or "")
            if quote_id:
                quote = self.service.get_quote(quote_id)
            else:
                quote = self.service.create_quote(payload)
            self.send_json(self.service.evaluate_policy_for_quote(quote))
            return
        if path == "/v1/approvals":
            self.send_json(self.service.create_approval(payload), status=201)
            return
        approval_decision_match = APPROVAL_DECISION_ROUTE.match(path)
        if approval_decision_match:
            self.send_json(self.service.decide_approval(approval_decision_match.group(1), payload))
            return
        if path == "/v1/checkout":
            headers = {key.lower(): value for key, value in self.headers.items()}
            status, headers_out, body = self.service.checkout(payload, headers, raw_body)
            self.send_json(body, status=status, headers=headers_out)
            return
        order_refund_match = ORDER_REFUND_ROUTE.match(path)
        if order_refund_match:
            self.send_json(self.service.refund_order(order_refund_match.group(1), payload), status=201)
            return
        raise NotFound("route not found")

    def read_form(self) -> dict[str, str]:
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0")).decode()
        parsed = urllib.parse.parse_qs(raw)
        return {key: values[0] for key, values in parsed.items()}

    def require_auth_if_configured(self) -> None:
        token = self.service.config.agentcart_token
        if not token:
            return
        header_token = self.headers.get("X-AgentCart-Token", "").strip()
        if header_token and hmac.compare_digest(header_token, token):
            return
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise Unauthorized("Bearer authorization or X-AgentCart-Token is required")
        supplied = auth[len("Bearer ") :].strip()
        if not hmac.compare_digest(supplied, token):
            raise Forbidden("invalid AgentCart token")

    def send_json(self, payload: Any, *, status: int = 200, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True, default=json_default).encode()
        self.send_response(status)
        self.send_header("Content-Type", JSON_MIME)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, markup: str, *, status: int = 200) -> None:
        body = markup.encode()
        self.send_response(status)
        self.send_header("Content-Type", HTML_MIME)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text: str, *, status: int = 200) -> None:
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", TEXT_MIME)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_ical(self, text: str, *, status: int = 200) -> None:
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/calendar; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_error_json(self, status: int, message: str, *, detail: Any | None = None) -> None:
        self.send_json({"error": {"message": message, "detail": detail, "status": status}}, status=status)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("client=<redacted> - - [%s] %s\n" % (self.log_date_time_string(), fmt % args))


def first_query(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0]


def parse_json_body(raw_body: bytes) -> dict[str, Any]:
    if not raw_body:
        return {}
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise BadRequest("request body must be JSON") from exc
    if not isinstance(parsed, dict):
        raise BadRequest("request body must be a JSON object")
    return parsed


def canonical_body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=json_default).encode()


def esc(value: Any) -> str:
    return html.escape(str(value))


def payment_proof(order: dict[str, Any]) -> dict[str, Any]:
    receipt = order.get("payment_receipt") or {}
    proof = receipt.get("external_value_proof")
    return proof if isinstance(proof, dict) else {}


def proof_body(proof: dict[str, Any]) -> dict[str, Any]:
    for key in ("body", "stdout"):
        value = proof.get(key)
        if isinstance(value, dict):
            return value
    return {}


def proof_reference(proof: dict[str, Any]) -> str:
    if proof.get("transaction_reference"):
        return str(proof["transaction_reference"])
    receipt = proof.get("payment_receipt")
    if isinstance(receipt, dict) and receipt.get("reference"):
        return str(receipt["reference"])
    return ""


def proof_explorer_url(proof: dict[str, Any]) -> str:
    if proof.get("explorer_url"):
        return str(proof["explorer_url"])
    reference = proof_reference(proof)
    return tempo_explorer_url(str(proof.get("network") or ""), reference) or ""


def proof_status_label(order: dict[str, Any]) -> str:
    proof = payment_proof(order)
    if not proof:
        return "not attached"
    label = f"{proof.get('provider', 'proof')} {proof.get('state', 'unknown')}"
    reference = proof_reference(proof)
    if reference:
        label += f" ({reference[:10]}...)"
    return label


def link_or_text(url: Any, label: str | None = None) -> str:
    if not url:
        return ""
    url_text = str(url)
    return f"<a href=\"{esc(url_text)}\" target=\"_blank\" rel=\"noreferrer\">{esc(label or url_text)}</a>"


def approval_notification_summary(approval: dict[str, Any]) -> str:
    notification = approval.get("notification") if isinstance(approval.get("notification"), dict) else {}
    state = str(notification.get("state") or "not_sent")
    results = notification.get("results") if isinstance(notification.get("results"), list) else []
    sent_to = [str(result.get("service")) for result in results if isinstance(result, dict) and result.get("ok")]
    if sent_to:
        return f"{state}: {', '.join(sent_to)}"
    return state


def payment_proof_text(receipt: dict[str, Any]) -> str:
    proof = receipt.get("external_value_proof") if isinstance(receipt.get("external_value_proof"), dict) else {}
    if not proof:
        return "No external value proof attached."
    parts = [str(proof.get("provider") or "proof"), str(proof.get("state") or "unknown")]
    if proof.get("network"):
        parts.append(str(proof["network"]))
    if proof.get("value_transfer") is not None:
        parts.append(f"value_transfer={str(proof.get('value_transfer')).lower()}")
    if proof.get("real_settlement") is not None:
        parts.append(f"real_settlement={str(proof.get('real_settlement')).lower()}")
    body = proof_body(proof)
    if body.get("amount"):
        parts.append(f"amount={body['amount']}")
    reference = proof_reference(proof)
    if reference:
        parts.append(f"reference={reference[:12]}...")
    explorer = proof_explorer_url(proof)
    if explorer:
        parts.append(f"explorer={explorer}")
    return ", ".join(parts)


def sort_by_time(items: list[dict[str, Any]], field: str = "created_at") -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: str(item.get(field) or ""))


def render_registry_page(service: AgentCartService, query_text: str = "", country: str = "DE", postal_code: str = "") -> str:
    registry = service.registry_document()
    entries = registry.get("entries", [])
    tournament: dict[str, Any] | None = None
    tournament_error = ""
    normalized_query = query_text.strip()
    if normalized_query:
        try:
            tournament = service.quote_tournament(
                {
                    "q": normalized_query,
                    "country": country,
                    "postal_code": postal_code,
                    "quantity": 1,
                    "max_candidates": 6,
                }
            )
        except AgentCartError as exc:
            tournament_error = str(exc)

    def countries(value: Any) -> str:
        items = list(value) if isinstance(value, list) else []
        if len(items) > 8:
            return f"{', '.join(str(item) for item in items[:8])} +{len(items) - 8} more"
        return ", ".join(str(item) for item in items) or "not declared"

    def payment_cell(candidate: dict[str, Any]) -> str:
        summary = candidate.get("payment_summary") if isinstance(candidate.get("payment_summary"), dict) else {}
        quote_currency = str(summary.get("quote_currency") or candidate.get("currency") or "EUR")
        methods = summary.get("methods") if isinstance(summary.get("methods"), list) else []
        method_label = ", ".join(str(method) for method in methods) if methods else "demo"
        settlement_asset = summary.get("settlement_asset") if isinstance(summary.get("settlement_asset"), dict) else None
        if settlement_asset:
            asset = str(settlement_asset.get("asset") or "")
            denomination = str(settlement_asset.get("denomination") or "")
            network = str(settlement_asset.get("network") or "")
            return (
                f"Quote: {esc(quote_currency)}<br>"
                f"<span class=\"muted\">MPP method: {esc(method_label)}</span><br>"
                f"<span class=\"muted\">Settlement proof: {esc(asset)} {esc(denomination)} {esc(network)}</span>"
            )
        return f"Quote: {esc(quote_currency)}<br><span class=\"muted\">Payment method: {esc(method_label)}</span>"

    entry_rows = "\n".join(
        f"""
        <tr>
          <td>{esc(entry.get('name'))}<br><span class="muted">{esc(entry.get('merchant_id'))}</span></td>
          <td>{esc(entry.get('domain'))}</td>
          <td>{link_or_text(entry.get('manifest_url'), 'manifest')}</td>
          <td><code>{esc(str(entry.get('manifest_hash') or '')[:16])}...</code></td>
          <td>{esc(countries((entry.get('delivery') or {}).get('ship_to_countries')))}</td>
          <td>{esc('no paid placement' if not (entry.get('ranking') or {}).get('paid_placement') else 'sponsored')}</td>
        </tr>
        """
        for entry in entries
    )

    winner = (tournament or {}).get("winner") if isinstance(tournament, dict) else None
    winner_html = (
        f"""
        <section class="winner">
          <h2>Current Winner</h2>
          <dl>
            <dt>Merchant</dt><dd>{esc(winner.get('merchant_name'))}</dd>
            <dt>Product</dt><dd>{esc(winner.get('product_title'))}</dd>
            <dt>Total</dt><dd>{esc(money(int(winner.get('total_cents') or 0), winner.get('currency', 'EUR')))}</dd>
            <dt>Payment</dt><dd>{payment_cell(winner)}</dd>
            <dt>Delivery</dt><dd>{esc((winner.get('delivery_window') or {}).get('earliest_date', ''))} to {esc((winner.get('delivery_window') or {}).get('latest_date', ''))}</dd>
            <dt>Quote</dt><dd><code>{esc(winner.get('quote_id'))}</code></dd>
          </dl>
        </section>
        """
        if isinstance(winner, dict)
        else ""
    )
    candidate_rows = "\n".join(
        f"""
        <tr>
          <td>{esc(candidate.get('rank'))}</td>
          <td>{esc(candidate.get('merchant_name'))}<br><span class="muted">{esc(candidate.get('merchant_id'))}</span></td>
          <td>{esc(candidate.get('product_title'))}<br><span class="muted"><code>{esc(candidate.get('quote_id'))}</code></span></td>
          <td>{esc(money(int(candidate.get('total_cents') or 0), candidate.get('currency', 'EUR')))}</td>
          <td>{payment_cell(candidate)}</td>
          <td>{esc((candidate.get('delivery_window') or {}).get('latest_date', ''))}</td>
          <td>{'<br>'.join(esc(reason) for reason in candidate.get('rank_reasons', []))}</td>
        </tr>
        """
        for candidate in ((tournament or {}).get("candidates") or [])
    )
    rejected_rows = "\n".join(
        f"<tr><td>{esc(item.get('title') or item.get('product_id'))}</td><td>{esc(item.get('merchant_id') or '')}</td><td>{esc(item.get('reason'))}</td></tr>"
        for item in ((tournament or {}).get("rejected") or [])
    )
    tournament_html = (
        f"""
        {winner_html}
        <h2>Private Quote Tournament</h2>
        <table>
          <thead><tr><th>Rank</th><th>Merchant</th><th>Quote</th><th>Total</th><th>Payment</th><th>ETA latest</th><th>Ranking reasons</th></tr></thead>
          <tbody>{candidate_rows or '<tr><td colspan="7">No eligible quote candidates.</td></tr>'}</tbody>
        </table>
        <h2>Rejected Candidates</h2>
        <table>
          <thead><tr><th>Product</th><th>Merchant</th><th>Reason</th></tr></thead>
          <tbody>{rejected_rows or '<tr><td colspan="3">No rejected candidates.</td></tr>'}</tbody>
        </table>
        """
        if tournament
        else (
            f"<div class='error'>{esc(tournament_error)}</div>"
            if tournament_error
            else "<p class='muted'>Enter a query to create comparable, short-lived quotes from eligible merchants.</p>"
        )
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentCart Merchant Registry</title>
  <style>
    :root {{ color-scheme: light; --ink:#172027; --muted:#5d6870; --line:#d9e0e6; --panel:#f5f8f7; --brand:#0a6c60; --accent:#8a4b12; --bad:#9b1c1c; }}
    body {{ margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#fff; }}
    header {{ padding:28px 32px 20px; background:#eef5f2; border-bottom:1px solid var(--line); }}
    main {{ max-width:1180px; margin:0 auto; padding:22px 24px 44px; }}
    h1 {{ margin:0 0 8px; font-size:30px; letter-spacing:0; }}
    h2 {{ margin:26px 0 12px; font-size:18px; letter-spacing:0; }}
    h3 {{ margin:0 0 8px; font-size:15px; letter-spacing:0; }}
    .lead {{ max-width:920px; color:var(--muted); font-size:15px; }}
    .actions, form {{ display:flex; flex-wrap:wrap; gap:10px; align-items:end; margin-top:16px; }}
    .button, button {{ border:1px solid var(--brand); background:var(--brand); color:#fff; border-radius:6px; padding:9px 12px; font-weight:650; text-decoration:none; cursor:pointer; }}
    .secondary {{ background:#fff; color:var(--brand); }}
    label {{ display:grid; gap:5px; color:var(--muted); font-size:12px; text-transform:uppercase; }}
    input {{ min-width:150px; border:1px solid var(--line); border-radius:6px; padding:9px 10px; font:inherit; color:var(--ink); }}
    table {{ width:100%; border-collapse:collapse; border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
    th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ background:var(--panel); font-size:12px; color:#3d4951; text-transform:uppercase; }}
    tr:last-child td {{ border-bottom:0; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(245px,1fr)); gap:12px; }}
    .card, .winner {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .winner {{ border-color:#b6d7ce; background:#f1faf7; }}
    .muted {{ color:var(--muted); }}
    .error {{ border:1px solid #e3b3b3; color:var(--bad); background:#fff2f2; border-radius:8px; padding:10px 12px; margin-top:14px; }}
    dl {{ display:grid; grid-template-columns:110px 1fr; gap:5px 12px; margin:0; }}
    dt {{ color:var(--muted); }}
    dd {{ margin:0; word-break:break-word; }}
    code {{ background:#eef1f3; padding:2px 5px; border-radius:4px; }}
    a {{ color:var(--brand); }}
    @media (max-width:800px) {{ header {{ padding:22px 20px 16px; }} main {{ padding:18px 16px 34px; }} input {{ min-width:0; width:100%; }} }}
  </style>
</head>
<body>
  <header>
    <h1>AgentCart Merchant Registry</h1>
    <p class="lead">The registry is an identity and integrity anchor for opt-in shops. It does not publish household demand, does not rank by advertising spend, and does not settle payments. Agents use it to find manifests, then request private final quotes.</p>
    <div class="actions">
      <a class="button secondary" href="/">Dashboard</a>
      <a class="button secondary" href="/judge">Judge View</a>
      <a class="button secondary" href="/intent-auction-overview.html">Intent Market</a>
      <a class="button secondary" href="/protocol-fields.html">Field Map</a>
      <a class="button secondary" href="/v1/registry">Registry JSON</a>
      <a class="button" href="/registry?q=Hazel%27s%20Chocolate%20Tea&country=DE&postal_code=15344">Hazel Comparison</a>
    </div>
    <form method="get" action="/registry">
      <label>Product intent <input name="q" value="{esc(normalized_query)}" placeholder="Hazel's Chocolate Tea"></label>
      <label>Ship country <input name="country" value="{esc(country or service.config.default_ship_country)}" maxlength="2"></label>
      <label>Postal code <input name="postal_code" value="{esc(postal_code or service.config.default_ship_postal_code)}"></label>
      <button type="submit">Run Quote Tournament</button>
    </form>
  </header>
  <main>
    <section class="grid">
      <div class="card"><h3>Public Registry</h3><p>Only public merchant identity, manifest URLs, delivery countries, and hash anchors belong here.</p></div>
      <div class="card"><h3>Private RFQ</h3><p>The concrete buyer intent is sent only to selected merchants as a quote request, then bound to a quote hash.</p></div>
      <div class="card"><h3>User-Owned Ranking</h3><p>The household agent ranks by policy, final price, delivery, stock, and trust. No paid placement signal is used.</p></div>
    </section>

    <h2>Registered Merchants</h2>
    <table>
      <thead><tr><th>Merchant</th><th>Domain</th><th>Manifest</th><th>Hash anchor</th><th>Ships to</th><th>Ranking</th></tr></thead>
      <tbody>{entry_rows or '<tr><td colspan="6">No registered merchants.</td></tr>'}</tbody>
    </table>

    {tournament_html}
  </main>
</body>
</html>"""


def render_dashboard(state: dict[str, Any]) -> str:
    products = state["products"]
    quotes = list(reversed(state["quotes"]))
    approvals = list(reversed(state["approvals"]))
    orders = list(reversed(state["orders"]))
    energy_offers = list(reversed(state.get("energy_offers", [])))
    audit = list(reversed(state["audit"]))
    def product_image(product: dict[str, Any]) -> str:
        urls = product.get("image_urls") if isinstance(product.get("image_urls"), list) else []
        if not urls:
            return ""
        return f"<img class=\"product-image\" src=\"{esc(urls[0])}\" alt=\"{esc(product['title'])}\">"

    product_cards = "\n".join(
        f"""
        <article class="item">
          {product_image(product)}
          <h3>{esc(product['title'])}</h3>
          <p>{esc(product['description'])}</p>
          <dl>
            <dt>SKU</dt><dd>{esc(product['sku'])}</dd>
            <dt>Unit</dt><dd>{esc(product['unit_size'])}</dd>
            <dt>Price</dt><dd>{esc(money(product['price_hint']['amount_cents'], product['currency']))}</dd>
            <dt>Stock</dt><dd>{esc(product['stock'])}</dd>
          </dl>
        </article>
        """
        for product in products
    )
    quote_rows = "\n".join(
        f"<tr><td>{esc(quote['id'])}</td><td>{esc(quote['reason'])}</td><td>{esc(money(quote['total_cents'], quote['currency']))}</td><td>{esc(quote['policy_result']['decision'])}</td></tr>"
        for quote in quotes[:8]
    )
    approval_rows = "\n".join(
        f"<tr><td><a href=\"/approvals/{esc(approval['id'])}\">{esc(approval['id'])}</a></td><td>{esc(approval['quote_id'])}</td><td>{esc(approval['state'])}</td><td>{esc(approval.get('approver') or '')}</td></tr>"
        for approval in approvals[:8]
    )
    order_rows = "\n".join(
        f"<tr><td><a href=\"/orders/{esc(order['id'])}\">{esc(order['id'])}</a></td><td>{esc(order['merchant_order_id'])}</td><td>{esc(order['state'])}</td><td>{esc(money(order['total_cents'], order['currency']))}</td><td>{esc(proof_status_label(order))}</td><td>{esc(order.get('vikunja_task', {}).get('state', ''))}</td></tr>"
        for order in orders[:8]
    )
    energy_rows = "\n".join(
        f"<tr><td>{esc(offer['id'])}</td><td>{esc(offer['state'])}</td><td>{esc(offer.get('quantity_kwh'))} kWh</td><td>{esc(offer.get('price_cents_per_kwh'))} ct/kWh</td><td>{esc(money(int(offer.get('estimated_total_cents') or 0), offer.get('currency', 'EUR')))}</td><td>{esc(((offer.get('settlement') or {}).get('payment_receipt') or {}).get('status', ''))}</td></tr>"
        for offer in energy_offers[:8]
    )
    audit_rows = "\n".join(
        f"<tr><td>{esc(event['timestamp'])}</td><td>{esc(event['event_type'])}</td><td>{esc(event['actor'])}</td><td>{esc(event['reason'])}</td></tr>"
        for event in audit[:12]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentCart</title>
  <style>
    :root {{ color-scheme: light; --ink:#1d252c; --muted:#5f6b73; --line:#d9e0e6; --panel:#f6f8f9; --brand:#0a6c60; --accent:#9b4d16; }}
    body {{ margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#fff; }}
    header {{ padding:28px 32px 18px; border-bottom:1px solid var(--line); background:#eef5f2; }}
    h1 {{ margin:0 0 6px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:28px 0 12px; font-size:18px; letter-spacing:0; }}
    h3 {{ margin:0 0 8px; font-size:15px; letter-spacing:0; }}
    main {{ max-width:1180px; margin:0 auto; padding:0 24px 40px; }}
    .topline {{ color:var(--muted); max-width:840px; }}
    .actions {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:18px; }}
    button, .button {{ border:1px solid var(--brand); background:var(--brand); color:#fff; border-radius:6px; padding:9px 12px; font-weight:650; cursor:pointer; text-decoration:none; }}
    .secondary {{ background:#fff; color:var(--brand); }}
    .grid {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); }}
    .item {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .product-image {{ width:100%; aspect-ratio:1/1; object-fit:cover; border-radius:6px; margin-bottom:12px; background:var(--panel); }}
    dl {{ display:grid; grid-template-columns:72px 1fr; gap:3px 10px; margin:10px 0 0; }}
    dt {{ color:var(--muted); }}
    dd {{ margin:0; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
    th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ background:var(--panel); color:#3d4951; font-size:12px; text-transform:uppercase; }}
    tr:last-child td {{ border-bottom:0; }}
    code {{ background:#eef1f3; padding:2px 5px; border-radius:4px; }}
    .two {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
    @media (max-width:800px) {{ .two {{ grid-template-columns:1fr; }} header {{ padding:22px 20px 16px; }} main {{ padding:0 16px 32px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>AgentCart</h1>
    <div class="topline">Household-safe agent checkout bridge: catalog, quote, policy, Home Assistant approval, HTTP 402 payment, merchant order, Vikunja task, audit log.</div>
    <form class="actions" method="post" action="/demo/trigger-low-tea">
      <button type="submit">Simulate Tea Stock Low</button>
      <button type="submit" formaction="/demo/trigger-woo-tea">Simulate Woo Tea Purchase</button>
      <a class="button secondary" href="/agent">Agent Console</a>
      <a class="button secondary" href="/.well-known/agentcart.json">Capability Document</a>
      <a class="button secondary" href="/architecture.html">Architecture</a>
      <a class="button secondary" href="/presentation.html">Presentation</a>
      <a class="button secondary" href="/intent-auction-overview.html">Intent Market</a>
      <a class="button secondary" href="/registry?q=sencha">Registry</a>
      <a class="button secondary" href="/judge">Judge View</a>
      <a class="button secondary" href="/energy">Energy Market</a>
    </form>
  </header>
  <main>
    <h2>Demo Catalog</h2>
    <section class="grid">{product_cards}</section>
    <section class="two">
      <div>
        <h2>Quotes</h2>
        <table><thead><tr><th>ID</th><th>Reason</th><th>Total</th><th>Policy</th></tr></thead><tbody>{quote_rows or '<tr><td colspan="4">No quotes yet.</td></tr>'}</tbody></table>
      </div>
      <div>
        <h2>Approvals</h2>
        <table><thead><tr><th>ID</th><th>Quote</th><th>State</th><th>Approver</th></tr></thead><tbody>{approval_rows or '<tr><td colspan="4">No approvals yet.</td></tr>'}</tbody></table>
      </div>
    </section>
    <h2>Orders</h2>
    <table><thead><tr><th>ID</th><th>Merchant Order</th><th>State</th><th>Total</th><th>Payment Proof</th><th>Vikunja</th></tr></thead><tbody>{order_rows or '<tr><td colspan="6">No orders yet.</td></tr>'}</tbody></table>
    <h2>Energy Offers</h2>
    <table><thead><tr><th>ID</th><th>State</th><th>Quantity</th><th>Price</th><th>Total</th><th>Settlement</th></tr></thead><tbody>{energy_rows or '<tr><td colspan="6">No energy offers yet.</td></tr>'}</tbody></table>
    <h2>Audit Log</h2>
    <table><thead><tr><th>Time</th><th>Event</th><th>Actor</th><th>Reason</th></tr></thead><tbody>{audit_rows or '<tr><td colspan="4">No audit events yet.</td></tr>'}</tbody></table>
  </main>
</body>
</html>"""


def render_judge_view(service: AgentCartService) -> str:
    state = service.dashboard_state()
    orders = state.get("orders", [])
    offers = state.get("energy_offers", [])
    latest_order = orders[-1] if orders else {}
    latest_offer = offers[-1] if offers else {}
    latest_approval = service.get_approval(latest_order["approval_id"]) if latest_order else {}
    latest_order_receipt = latest_order.get("payment_receipt") if isinstance(latest_order.get("payment_receipt"), dict) else {}
    latest_order_proof = latest_order_receipt.get("external_value_proof") if isinstance(latest_order_receipt.get("external_value_proof"), dict) else {}
    latest_merchant_order = latest_order.get("merchant_order") if isinstance(latest_order.get("merchant_order"), dict) else {}
    latest_task = latest_order.get("vikunja_task") if isinstance(latest_order.get("vikunja_task"), dict) else {}
    latest_calendar = latest_order.get("calendar_event") if isinstance(latest_order.get("calendar_event"), dict) else {}
    latest_settlement = latest_offer.get("settlement") if isinstance(latest_offer.get("settlement"), dict) else {}
    latest_energy_receipt = latest_settlement.get("payment_receipt") if isinstance(latest_settlement.get("payment_receipt"), dict) else {}
    latest_energy_proof = (
        latest_energy_receipt.get("external_value_proof")
        if isinstance(latest_energy_receipt.get("external_value_proof"), dict)
        else {}
    )
    order_explorer = proof_explorer_url(latest_order_proof) if latest_order_proof else ""
    energy_explorer = proof_explorer_url(latest_energy_proof) if latest_energy_proof else ""
    audit = list(reversed(state.get("audit", [])))[:10]
    audit_rows = "\n".join(
        f"<tr><td>{esc(event.get('timestamp'))}</td><td>{esc(event.get('event_type'))}</td><td>{esc(event.get('reason'))}</td></tr>"
        for event in audit
    )
    order_summary = (
        f"""
        <dl>
          <dt>Order</dt><dd><a href="/orders/{esc(latest_order.get('id'))}">{esc(latest_order.get('id'))}</a></dd>
          <dt>Product</dt><dd>{esc(', '.join(f"{item.get('quantity')}x {item.get('title')}" for item in latest_order.get('items', [])))}</dd>
          <dt>Total</dt><dd>{esc(money(int(latest_order.get('total_cents') or 0), latest_order.get('currency', 'EUR')))}</dd>
          <dt>Merchant ETA</dt><dd>{esc((latest_order.get('delivery_window') or {}).get('earliest_date', ''))} to {esc((latest_order.get('delivery_window') or {}).get('latest_date', ''))}</dd>
          <dt>Approval</dt><dd>{esc(latest_approval.get('state') or '')} via {esc(latest_approval.get('approver') or latest_approval.get('channel') or '')}<br>{esc(approval_notification_summary(latest_approval))}</dd>
          <dt>Woo admin</dt><dd>{link_or_text(latest_merchant_order.get('url'), f"Open order {latest_order.get('merchant_order_id')}") or esc(latest_order.get('merchant_order_id') or '')}</dd>
          <dt>Vikunja</dt><dd>{link_or_text(latest_task.get('url'), f"Task {latest_task.get('task_id')}") or esc(latest_task.get('state') or '')}</dd>
          <dt>Calendar</dt><dd>{esc(latest_calendar.get('state') or '')}{(': ' + esc(latest_calendar.get('reason'))) if latest_calendar.get('reason') else ''}</dd>
          <dt>Tempo proof</dt><dd>{f"<a href='{esc(order_explorer)}' target='_blank' rel='noreferrer'>Explorer reference</a>" if order_explorer else esc(proof_status_label(latest_order))}</dd>
        </dl>
        """
        if latest_order
        else "<p class='muted'>No tea order has been completed yet.</p>"
    )
    energy_summary = (
        f"""
        <dl>
          <dt>Offer</dt><dd>{esc(latest_offer.get('id'))}</dd>
          <dt>State</dt><dd>{esc(latest_offer.get('state'))}</dd>
          <dt>Quantity</dt><dd>{esc(latest_offer.get('quantity_kwh'))} kWh</dd>
          <dt>Price</dt><dd>{esc(latest_offer.get('price_cents_per_kwh'))} ct/kWh below {esc(latest_offer.get('market_reference_cents_per_kwh'))} ct/kWh reference</dd>
          <dt>Settlement</dt><dd>{esc(latest_settlement.get('state') or 'not accepted yet')}</dd>
          <dt>Tempo proof</dt><dd>{f"<a href='{esc(energy_explorer)}' target='_blank' rel='noreferrer'>Explorer reference</a>" if energy_explorer else esc(payment_proof_text(latest_energy_receipt) if latest_energy_receipt else 'not attached')}</dd>
        </dl>
        """
        if latest_offer
        else "<p class='muted'>No energy offer has been created yet.</p>"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentCart Judge View</title>
  <style>
    :root {{ color-scheme: light; --ink:#172027; --muted:#5d6870; --line:#d9e0e6; --panel:#f5f8f7; --brand:#0a6c60; --warn:#8a4b12; --good:#0a6c60; }}
    body {{ margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#fff; }}
    header {{ padding:28px 32px 20px; background:#eef5f2; border-bottom:1px solid var(--line); }}
    main {{ max-width:1180px; margin:0 auto; padding:22px 24px 44px; }}
    h1 {{ margin:0 0 8px; font-size:30px; letter-spacing:0; }}
    h2 {{ margin:26px 0 12px; font-size:18px; letter-spacing:0; }}
    h3 {{ margin:0 0 6px; font-size:15px; letter-spacing:0; }}
    .lead {{ max-width:900px; color:var(--muted); font-size:15px; }}
    .actions {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }}
    .button {{ border:1px solid var(--brand); background:var(--brand); color:#fff; border-radius:6px; padding:9px 12px; font-weight:650; text-decoration:none; }}
    .secondary {{ background:#fff; color:var(--brand); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }}
    .card {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .band {{ border:1px solid var(--line); border-radius:8px; padding:16px; background:var(--panel); }}
    .step {{ border-left:4px solid var(--brand); padding-left:12px; min-height:80px; }}
    .warn {{ color:var(--warn); font-weight:700; }}
    .ok {{ color:var(--good); font-weight:700; }}
    .muted {{ color:var(--muted); }}
    dl {{ display:grid; grid-template-columns:110px 1fr; gap:5px 12px; margin:0; }}
    dt {{ color:var(--muted); }}
    dd {{ margin:0; word-break:break-word; }}
    table {{ width:100%; border-collapse:collapse; border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
    th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ background:var(--panel); font-size:12px; color:#3d4951; text-transform:uppercase; }}
    tr:last-child td {{ border-bottom:0; }}
    code {{ background:#eef1f3; padding:2px 5px; border-radius:4px; }}
    a {{ color:var(--brand); }}
    @media (max-width:800px) {{ header {{ padding:22px 20px 16px; }} main {{ padding:18px 16px 34px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>AgentCart Judge View</h1>
    <p class="lead">The project is not another payment primitive. It is a practical bridge that lets opt-in merchants and households expose machine-readable offers, quote final terms, enforce household policy, get human consent, attach MPP-compatible payment proof, and leave an audit trail.</p>
    <div class="actions">
      <a class="button" href="/">Dashboard</a>
      <a class="button secondary" href="/energy">Energy Market</a>
      <a class="button secondary" href="/architecture.html">Architecture</a>
      <a class="button secondary" href="/presentation.html">Presentation</a>
      <a class="button secondary" href="/intent-auction-overview.html">Intent Market</a>
      <a class="button secondary" href="/registry?q=sencha">Registry</a>
    </div>
  </header>
  <main>
    <section class="band">
      <h2>What Judges Should See</h2>
      <div class="grid">
        <div class="step"><h3>1. Agent-readable offer</h3><p>Products and surplus energy are exposed as structured resources, not scraped browser pages.</p></div>
        <div class="step"><h3>2. Final terms before payment</h3><p>Quote or offer includes price, validity, stock or telemetry, merchant/seller identity, delivery or legal scope.</p></div>
        <div class="step"><h3>3. Household safety</h3><p>Policy, explicit approval, budgets, idempotency, and audit logs are first-class.</p></div>
        <div class="step"><h3>4. MPP-compatible proof</h3><p>Checkout/settlement attaches a Tempo MPP proof when configured, with explorer reference when available.</p></div>
      </div>
    </section>

    <h2>Tea Purchase Flow</h2>
    <div class="grid">
      <div class="card"><h3>Live Result</h3>{order_summary}</div>
      <div class="card"><h3>Demo Script</h3><p>Ask the Household OS chat: <code>Use AgentCart to buy my favorite tea. Discover shops, get the best final quote, and ask me for approval.</code> Then approve in chat or on phone/watch. The order page proves each step.</p></div>
      <div class="card"><h3>Why It Matters</h3><p>Most shops do not expose MPP/x402-native catalog and quote flows. AgentCart shows the missing adapter layer without secretly buying from third-party shops.</p></div>
    </div>

    <h2>Energy Sharing Flow</h2>
    <div class="grid">
      <div class="card"><h3>Live Result</h3>{energy_summary}</div>
      <div class="card"><h3>Demo Script</h3><p>Ask the Household OS chat: <code>Offer our excess energy to the neighbour and settle it as a demo</code>, or use the Energy Market page.</p></div>
      <div class="card"><h3>Legal Scope</h3><p><span class="warn">Demo only.</span> German energy sharing under EnWG §42c is plausible from June 2026, but real use needs smart metering, contracts, grid-area eligibility, residual supply, balancing, billing, taxes, levies, and consumer information handling.</p><p><a href="https://www.gesetze-im-internet.de/enwg_2005/__42c.html" target="_blank" rel="noreferrer">§42c EnWG</a> · <a href="https://www.interreg-central.eu/news/germany-introduces-energy-sharing/" target="_blank" rel="noreferrer">implementation context</a></p></div>
    </div>

    <h2>Recent Audit</h2>
    <table><thead><tr><th>Time</th><th>Event</th><th>Reason</th></tr></thead><tbody>{audit_rows or '<tr><td colspan="3">No audit events yet.</td></tr>'}</tbody></table>
  </main>
</body>
</html>"""


def render_energy_page(service: AgentCartService, error: str = "") -> str:
    surplus = service.energy_surplus()
    offers = list(reversed(service.list_energy_offers()["offers"]))
    sensor_rows = "\n".join(
        f"<tr><td>{esc(label)}</td><td>{esc((sensor or {}).get('value'))}</td><td>{esc((sensor or {}).get('unit') or '')}</td><td>{esc((sensor or {}).get('friendly_name') or (sensor or {}).get('entity_id') or '')}</td></tr>"
        for label, sensor in (surplus.get("sensors") or {}).items()
    )
    offer_rows = []
    for offer in offers[:12]:
        settlement = offer.get("settlement") if isinstance(offer.get("settlement"), dict) else {}
        receipt = settlement.get("payment_receipt") if isinstance(settlement.get("payment_receipt"), dict) else {}
        proof = receipt.get("external_value_proof") if isinstance(receipt.get("external_value_proof"), dict) else {}
        explorer = proof_explorer_url(proof) if proof else ""
        accept_form = (
            f"<form method='post' action='/demo/energy-offers/{esc(offer['id'])}/accept'><button type='submit'>Accept as neighbour</button></form>"
            if offer.get("state") == "open"
            else esc(settlement.get("state") or offer.get("state"))
        )
        proof_cell = (
            f"<a href='{esc(explorer)}' target='_blank' rel='noreferrer'>Tempo explorer</a>"
            if explorer
            else esc(payment_proof_text(receipt) if receipt else "")
        )
        offer_rows.append(
            f"<tr><td>{esc(offer['id'])}</td><td>{esc(offer.get('state'))}</td><td>{esc(offer.get('quantity_kwh'))} kWh</td><td>{esc(offer.get('price_cents_per_kwh'))} ct/kWh</td><td>{esc(money(int(offer.get('estimated_total_cents') or 0), offer.get('currency', 'EUR')))}</td><td>{accept_form}</td><td>{proof_cell}</td></tr>"
        )
    offer_rows_html = "\n".join(offer_rows)
    can_offer = bool(surplus.get("offerable"))
    reasons = "".join(f"<li>{esc(reason)}</li>" for reason in surplus.get("reasons", []))
    error_html = f"<div class='error'>{esc(error)}</div>" if error else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentCart Energy Market</title>
  <style>
    :root {{ color-scheme: light; --ink:#172027; --muted:#5d6870; --line:#d9e0e6; --panel:#f5f8f7; --brand:#0a6c60; --bad:#9b1c1c; --warn:#8a4b12; }}
    body {{ margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#fff; }}
    header {{ padding:26px 32px 18px; background:#eef5f2; border-bottom:1px solid var(--line); }}
    main {{ max-width:1160px; margin:0 auto; padding:20px 24px 42px; }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:26px 0 12px; font-size:18px; letter-spacing:0; }}
    .lead, .muted {{ color:var(--muted); }}
    .actions {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }}
    button, .button {{ border:1px solid var(--brand); background:var(--brand); color:#fff; border-radius:6px; padding:9px 12px; font-weight:650; cursor:pointer; text-decoration:none; }}
    button[disabled] {{ opacity:.5; cursor:not-allowed; }}
    .secondary {{ background:#fff; color:var(--brand); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:12px; }}
    .card {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .notice {{ border:1px solid #d9c8a9; background:#fff8ec; border-radius:8px; padding:14px; }}
    .error {{ border:1px solid #e3b3b3; color:var(--bad); background:#fff2f2; border-radius:8px; padding:10px 12px; margin-top:14px; }}
    .state {{ font-weight:750; color:{'#0a6c60' if can_offer else '#9b1c1c'}; }}
    table {{ width:100%; border-collapse:collapse; border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
    th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ background:var(--panel); font-size:12px; color:#3d4951; text-transform:uppercase; }}
    tr:last-child td {{ border-bottom:0; }}
    code {{ background:#eef1f3; padding:2px 5px; border-radius:4px; }}
    a {{ color:var(--brand); }}
    @media (max-width:800px) {{ header {{ padding:22px 20px 16px; }} main {{ padding:18px 16px 34px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>AgentCart Energy Market</h1>
    <p class="lead">A demo market where household energy telemetry becomes a discoverable, short-lived neighbour offer with explicit demo settlement proof.</p>
    <div class="actions">
      <a class="button secondary" href="/">Dashboard</a>
      <a class="button secondary" href="/judge">Judge View</a>
      <form method="post" action="/demo/energy-offer"><button type="submit" {'disabled' if not can_offer else ''}>Create Offer From Current Surplus</button></form>
    </div>
    {error_html}
  </header>
  <main>
    <section class="grid">
      <div class="card">
        <h2>Current Decision</h2>
        <p class="state">{esc(surplus.get('state'))}</p>
        <p>Net export: <strong>{esc(surplus.get('net_export_w', ''))} W</strong></p>
        <p>Potential solar surplus: <strong>{esc(surplus.get('potential_surplus_w', ''))} W</strong></p>
        <p>Battery-backed reserve: <strong>{esc(surplus.get('battery_backed_reserve_w', ''))} W</strong></p>
        <p>Offer basis: <strong>{esc(surplus.get('offer_basis', ''))}</strong> at {esc(surplus.get('offer_basis_w', ''))} W</p>
        <ul>{reasons}</ul>
        <p class="muted">{esc(surplus.get('recommendation', ''))}</p>
      </div>
      <div class="notice">
        <h2>Legal Boundary</h2>
        <p>This demo does not deliver electricity through the grid and does not create a legally settled supply contract. Real German energy sharing under EnWG §42c needs eligible participants, compliant metering, allocation, residual supply, balancing, billing, taxes/levies/grid charges, and consumer information handling.</p>
      </div>
    </section>

    <h2>Home Assistant Energy Snapshot</h2>
    <table><thead><tr><th>Signal</th><th>Value</th><th>Unit</th><th>Entity</th></tr></thead><tbody>{sensor_rows or '<tr><td colspan="4">No sensors available.</td></tr>'}</tbody></table>

    <h2>Discoverable Offers</h2>
    <table><thead><tr><th>ID</th><th>State</th><th>Quantity</th><th>Price</th><th>Total</th><th>Neighbour Action</th><th>Proof</th></tr></thead><tbody>{offer_rows_html or '<tr><td colspan="7">No energy offers yet.</td></tr>'}</tbody></table>
  </main>
</body>
</html>"""


def render_order_proof_page(service: AgentCartService, order_id: str) -> str:
    order = service.get_order(order_id)
    quote = service.get_quote(order["quote_id"])
    approval = service.get_approval(order["approval_id"])
    receipt = order.get("payment_receipt") or {}
    proof = payment_proof(order)
    body = proof_body(proof)
    settlement_asset = (
        proof.get("settlement_asset")
        if isinstance(proof.get("settlement_asset"), dict)
        else tempo_default_settlement_asset(str(proof.get("network") or ""))
    )
    receipt_reference = proof_reference(proof)
    explorer = proof_explorer_url(proof)
    mpp_receipt = proof.get("payment_receipt") if isinstance(proof.get("payment_receipt"), dict) else {}
    merchant_order = order.get("merchant_order") if isinstance(order.get("merchant_order"), dict) else {}
    calendar_event = order.get("calendar_event") if isinstance(order.get("calendar_event"), dict) else {}
    refunds = order.get("refunds") if isinstance(order.get("refunds"), list) else []
    audit_events = service.list_audit_events(order["quote_id"])
    audit_rows = "\n".join(
        f"<tr><td>{esc(event['timestamp'])}</td><td>{esc(event['event_type'])}</td><td>{esc(event['actor'])}</td><td>{esc(event['reason'])}</td></tr>"
        for event in audit_events
    )
    item_rows = "\n".join(
        f"<tr><td>{esc(item['quantity'])}x {esc(item['title'])}</td><td>{esc(money(item['line_total_cents'], item['currency']))}</td><td>{esc(item['category'])}</td></tr>"
        for item in order.get("items", [])
    )
    proof_rows = "\n".join(
        f"<tr><td>{esc(label)}</td><td>{value}</td></tr>"
        for label, value in [
            ("Provider", esc(proof.get("provider") or "not attached")),
            ("State", esc(proof.get("state") or "not attached")),
            ("Network", esc(proof.get("network") or "")),
            ("Quote currency", esc(proof.get("quote_currency") or order.get("currency") or "")),
            ("Tempo settlement asset", esc(settlement_asset.get("asset") or "")),
            ("Tempo denomination", esc(settlement_asset.get("denomination") or "")),
            ("Value transfer", esc(proof.get("value_transfer") if proof else "")),
            ("Real settlement", esc(proof.get("real_settlement") if proof else receipt.get("real_settlement"))),
            ("Settlement note", esc(proof.get("settlement_note") or "")),
            ("Paid amount", esc(body.get("amount") or "")),
            ("Recipient", f"<code>{esc(body.get('recipient') or '')}</code>"),
            ("Token", f"<code>{esc(body.get('token') or '')}</code>"),
            ("Delivered at", esc(body.get("delivered_at") or "")),
            ("MPP receipt status", esc(mpp_receipt.get("status") or "")),
            ("MPP receipt method", esc(mpp_receipt.get("method") or "")),
            ("MPP receipt time", esc(mpp_receipt.get("timestamp") or "")),
            (
                "Receipt reference",
                f"<code>{esc(receipt_reference)}</code>"
                if not explorer
                else f"<a href=\"{esc(explorer)}\" target=\"_blank\" rel=\"noreferrer\"><code>{esc(receipt_reference)}</code></a>",
            ),
        ]
    )
    refund_rows = "\n".join(
        f"""
        <tr>
          <td>{esc(refund.get('id') or '')}<br><span class="topline">{esc(refund.get('merchant_refund_id') or '')}</span></td>
          <td>{esc(refund.get('state') or '')}</td>
          <td>{esc(money(int(refund.get('amount_cents') or 0), refund.get('currency', 'EUR')))}</td>
          <td>{esc(refund.get('rail') or '')}</td>
          <td>{esc(refund.get('real_refund_verified'))}</td>
          <td>{esc(refund.get('reason') or '')}</td>
        </tr>
        """
        for refund in refunds
        if isinstance(refund, dict)
    )
    refund_action = (
        f"""
        <form method="post" action="/demo/orders/{esc(order['id'])}/refund" style="margin-top:10px">
          <button class="button" type="submit">Record Demo Refund</button>
        </form>
        <p class="topline">This records a WooCommerce refund through ShopBridge. In demo mode it does not claim Stripe, card, Tempo, stablecoin, or EUR rail funds moved.</p>
        """
        if not refunds
        else "<p class=\"topline\">Refund already recorded for this demo order.</p>"
    )
    task = order.get("vikunja_task") or {}
    delivery = order.get("delivery_window") or {}
    shipment = order.get("shipment") or {}
    calendar_feed_url = ""
    if service.config.delivery_calendar_enabled and service.config.delivery_calendar_token:
        calendar_feed_url = f"{service.config.public_url}{DELIVERY_CALENDAR_ROUTE}?token={urllib.parse.quote(service.config.delivery_calendar_token)}"
    notify_results = ""
    notification = approval.get("notification") if isinstance(approval.get("notification"), dict) else {}
    for result in notification.get("results", []) if isinstance(notification.get("results"), list) else []:
        if isinstance(result, dict):
            status = "sent" if result.get("ok") else "failed"
            notify_results += f"<li>{esc(result.get('service') or '')}: {esc(status)}{(' - ' + esc(result.get('error'))) if result.get('error') else ''}</li>"
    merchant_link = link_or_text(merchant_order.get("url"), f"Open Woo order {order.get('merchant_order_id')}")
    tempo_link = link_or_text(explorer, "Open Tempo explorer")
    approval_link = f"<a href=\"/approvals/{esc(approval['id'])}\">Open approval record</a>"
    vikunja_link = link_or_text(task.get("url"), f"Open Vikunja task {task.get('task_id')}")
    calendar_link = link_or_text(calendar_feed_url, "Open delivery ICS feed")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentCart Proof</title>
  <style>
    :root {{ color-scheme: light; --ink:#1d252c; --muted:#5f6b73; --line:#d9e0e6; --panel:#f6f8f9; --brand:#0a6c60; --good:#0a6c60; --warn:#9b4d16; }}
    body {{ margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#fff; }}
    header {{ padding:24px 32px 18px; border-bottom:1px solid var(--line); background:#eef5f2; }}
    main {{ max-width:1120px; margin:0 auto; padding:0 24px 40px; }}
    h1 {{ margin:0 0 6px; font-size:26px; letter-spacing:0; }}
    h2 {{ margin:26px 0 10px; font-size:18px; letter-spacing:0; }}
    .topline {{ color:var(--muted); }}
    .grid {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); margin-top:16px; }}
    .step {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; min-height:92px; }}
    .proof-grid {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); margin:16px 0 8px; }}
    .proof-card {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; min-height:112px; }}
    .proof-card h3 {{ margin:0 0 8px; font-size:15px; letter-spacing:0; }}
    .proof-card p {{ margin:6px 0 0; color:var(--muted); }}
    .step b {{ display:block; margin-bottom:5px; }}
    .ok {{ color:var(--good); font-weight:700; }}
    .warn {{ color:var(--warn); font-weight:700; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
    th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ background:var(--panel); color:#3d4951; font-size:12px; text-transform:uppercase; }}
    tr:last-child td {{ border-bottom:0; }}
    code {{ background:#eef1f3; padding:2px 5px; border-radius:4px; word-break:break-all; }}
    a {{ color:var(--brand); }}
    .button {{ display:inline-block; border:1px solid var(--brand); background:var(--brand); color:#fff; border-radius:6px; padding:9px 12px; font-weight:650; text-decoration:none; margin-top:18px; }}
    @media (max-width:800px) {{ header {{ padding:22px 20px 16px; }} main {{ padding:0 16px 32px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Execution Proof</h1>
    <div class="topline">Order {esc(order['id'])} links the household reason, policy, human approval, MPP receipt, merchant order, task sync, delivery estimate, and audit trail.</div>
    <a class="button" href="/">Back to Dashboard</a>
  </header>
  <main>
    <section class="grid">
      <div class="step"><b>1. Quote</b><span class="ok">{esc(quote['id'])}</span><br>{esc(quote['reason'])}<br>{esc(money(quote['total_cents'], quote['currency']))}</div>
      <div class="step"><b>2. Policy</b><span class="ok">{esc(quote['policy_result']['decision'])}</span><br>{esc('; '.join(quote['policy_result']['reasons']))}</div>
      <div class="step"><b>3. Human Approval</b><span class="ok">{esc(approval['state'])}</span><br>{esc(approval.get('approver') or '')}<br>{esc(approval.get('decided_at') or '')}</div>
      <div class="step"><b>4. MPP Checkout</b><span class="ok">{esc(receipt.get('status'))}</span><br>Challenge {esc(receipt.get('challenge_id'))}<br>Receipt {esc(receipt.get('id'))}</div>
      <div class="step"><b>5. Tempo Proof</b><span class="{ 'ok' if proof.get('state') == 'succeeded' else 'warn' }">{esc(proof.get('state') or 'not attached')}</span><br>{esc(proof.get('provider') or '')} {esc(proof.get('network') or '')}<br>{'Explorer link available' if explorer else 'No explorer reference stored'}</div>
      <div class="step"><b>6. Aftercare</b>Merchant order {esc(order.get('merchant_order_id'))}<br>Vikunja {esc(task.get('state') or '')}<br>Merchant ETA {esc(delivery.get('earliest_date') or '')} to {esc(delivery.get('latest_date') or shipment.get('estimated_delivery') or '')}</div>
    </section>

    <h2>Presentation Links</h2>
    <section class="proof-grid">
      <article class="proof-card"><h3>WooCommerce Order</h3>{merchant_link or esc(order.get('merchant_order_id') or '')}<p>Status: {esc(merchant_order.get('status') or merchant_order.get('state') or '')}</p></article>
      <article class="proof-card"><h3>Tempo Transaction</h3>{tempo_link or esc(proof_status_label(order))}<p>{esc(proof.get('network') or '')} {esc(settlement_asset.get('asset') or '')} {esc(proof_reference(proof)[:18] + '...' if proof_reference(proof) else '')}</p></article>
      <article class="proof-card"><h3>Home Assistant Approval</h3>{approval_link}<p>{esc(approval.get('state'))} by {esc(approval.get('approver') or '')}</p><ul>{notify_results or '<li>notification not sent</li>'}</ul></article>
      <article class="proof-card"><h3>Vikunja Task</h3>{vikunja_link or esc(task.get('state') or '')}<p>{esc((task.get('matched_open_task') or {}).get('title') or '')}</p></article>
      <article class="proof-card"><h3>Delivery ETA</h3>{calendar_link or esc(calendar_event.get('state') or '')}<p>{esc(calendar_event.get('summary') or calendar_event.get('reason') or 'Merchant-estimated; no carrier tracking claimed.')}</p></article>
      <article class="proof-card"><h3>Refund Path</h3><a href="#refunds">Show refunds</a><p>{esc(str(len(refunds)))} refund records; rail verified: {esc(any(bool(refund.get('real_refund_verified')) for refund in refunds if isinstance(refund, dict)))}</p></article>
      <article class="proof-card"><h3>Audit Trail</h3><a href="#audit">Show audit rows</a><p>{esc(str(len(audit_events)))} recorded events for this quote</p></article>
    </section>

    <h2>Items</h2>
    <table><thead><tr><th>Item</th><th>Line Total</th><th>Category</th></tr></thead><tbody>{item_rows}</tbody></table>

    <h2>Payment Proof</h2>
    <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{proof_rows}</tbody></table>
    <p class="topline">MPPscan indexes public/registered MPP servers. This hackathon endpoint runs locally at <code>127.0.0.1</code>, so it is not expected to appear there unless exposed and registered. The Tempo receipt reference is the on-chain/testnet leg to show in the Tempo explorer when present.</p>

    <h2 id="refunds">Refund Demo</h2>
    {refund_action}
    <table><thead><tr><th>Refund</th><th>State</th><th>Amount</th><th>Rail</th><th>Real Rail Refund</th><th>Reason</th></tr></thead><tbody>{refund_rows or '<tr><td colspan="6">No refunds recorded yet.</td></tr>'}</tbody></table>

    <h2>Order Integrations</h2>
    <table><tbody>
      <tr><td>Merchant of record</td><td>{esc((order.get('merchant_of_record') or {}).get('name', 'unknown'))}</td></tr>
      <tr><td>Merchant order</td><td>{merchant_link or esc(order.get('merchant_order_id'))}</td></tr>
      <tr><td>Home Assistant approval</td><td>{esc(approval.get('state'))} by {esc(approval.get('approver') or '')}; {esc(approval_notification_summary(approval))}</td></tr>
      <tr><td>Vikunja task</td><td>{f"<a href='{esc(task.get('url'))}' target='_blank' rel='noreferrer'>{esc(task.get('url'))}</a>" if task.get('url') else esc(task.get('state') or '')}</td></tr>
      <tr><td>Delivery calendar</td><td>{calendar_link or esc(calendar_event.get('state') or '')}{(': ' + esc(calendar_event.get('reason'))) if calendar_event.get('reason') else ''}</td></tr>
      <tr><td>Delivery window</td><td>{esc(delivery.get('earliest_date') or '')} to {esc(delivery.get('latest_date') or shipment.get('estimated_delivery') or '')} ({esc(delivery.get('label') or shipment.get('status') or 'merchant-estimated')}; no carrier tracking claimed)</td></tr>
    </tbody></table>

    <h2 id="audit">Audit Trail</h2>
    <table><thead><tr><th>Time</th><th>Event</th><th>Actor</th><th>Reason</th></tr></thead><tbody>{audit_rows or '<tr><td colspan="4">No audit events found.</td></tr>'}</tbody></table>
  </main>
</body>
</html>"""


def render_approval_page(service: AgentCartService, approval_id: str, token: str) -> str:
    approval = service.get_approval(approval_id)
    quote = service.get_quote(approval["quote_id"])
    items = "".join(
        f"<li>{esc(item['quantity'])}x {esc(item['title'])} at {esc(money(item['line_total_cents'], item['currency']))}</li>"
        for item in quote["items"]
    )
    approved = approval["state"] == "approved"
    rejected = approval["state"] == "rejected"
    finish_button = (
        f"""<form method="post" action="/demo/checkout/{esc(approval_id)}"><button type="submit">Finish MPP Demo Checkout</button></form>"""
        if approved
        else ""
    )
    decision_forms = ""
    if approval["state"] == "pending":
        decision_forms = f"""
        <form method="post" action="/approvals/{esc(approval_id)}/approve">
          <input type="hidden" name="token" value="{esc(token)}">
          <button type="submit">Approve</button>
        </form>
        <form method="post" action="/approvals/{esc(approval_id)}/reject">
          <input type="hidden" name="token" value="{esc(token)}">
          <button class="danger" type="submit">Reject</button>
        </form>
        """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentCart Approval</title>
  <style>
    body {{ margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:#1d252c; background:#f6f8f9; }}
    main {{ max-width:720px; margin:32px auto; padding:24px; background:#fff; border:1px solid #d9e0e6; border-radius:8px; }}
    h1 {{ margin:0 0 10px; font-size:24px; letter-spacing:0; }}
    .state {{ display:inline-block; padding:4px 8px; border-radius:4px; background:#eef5f2; color:#0a6c60; font-weight:650; }}
    .danger {{ background:#9b1c1c; border-color:#9b1c1c; }}
    button, .button {{ border:1px solid #0a6c60; background:#0a6c60; color:#fff; border-radius:6px; padding:9px 12px; font-weight:650; cursor:pointer; text-decoration:none; }}
    .actions {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:18px; }}
    dl {{ display:grid; grid-template-columns:130px 1fr; gap:5px 12px; }}
    dt {{ color:#5f6b73; }}
    dd {{ margin:0; }}
    .ok {{ color:#0a6c60; font-weight:700; }}
    .bad {{ color:#9b1c1c; font-weight:700; }}
  </style>
</head>
<body>
  <main>
    <h1>Approve Purchase</h1>
    <p class="state">{esc(approval['state'])}</p>
    <dl>
      <dt>Quote</dt><dd>{esc(quote['id'])}</dd>
      <dt>Merchant</dt><dd>{esc(quote['merchant']['name'])}</dd>
      <dt>Total</dt><dd>{esc(money(quote['total_cents'], quote['currency']))}</dd>
      <dt>Reason</dt><dd>{esc(quote['reason'])}</dd>
      <dt>Policy</dt><dd>{esc('; '.join(quote['policy_result']['reasons']))}</dd>
    </dl>
    <h2>Items</h2>
    <ul>{items}</ul>
    {"<p class='ok'>Approved. You can now run the simulated MPP checkout.</p>" if approved else ""}
    {"<p class='bad'>Rejected. Checkout is blocked.</p>" if rejected else ""}
    <div class="actions">
      {decision_forms}
      {finish_button}
      <a class="button" href="/">Back to Dashboard</a>
    </div>
  </main>
</body>
</html>"""


class AgentCartServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], service: AgentCartService) -> None:
        super().__init__(server_address, AgentCartHandler)
        self.service = service


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the AgentCart MVP service.")
    parser.add_argument("--bind", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)
    config = Config.from_env()
    if args.bind:
        config = Config(**{**config.__dict__, "bind": args.bind})
    if args.port:
        config = Config(**{**config.__dict__, "port": args.port})
    service = AgentCartService(config)
    server = AgentCartServer((config.bind, config.port), service)
    print(f"AgentCart listening on http://{config.bind}:{config.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping AgentCart", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
