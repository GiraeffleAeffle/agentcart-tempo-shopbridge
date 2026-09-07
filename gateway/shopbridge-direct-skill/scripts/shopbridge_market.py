"""Buyer-side comparison and bounded, order-independent candidate scheduling."""
from __future__ import annotations

import hashlib
import re
from fractions import Fraction
from typing import Any


def tie_key(nonce: str, candidate: dict[str, Any]) -> str:
    identity = f"{candidate.get('merchant_id', '')}\0{candidate.get('product_id', '')}"
    return hashlib.sha256(f"{nonce}\0{identity}".encode()).hexdigest()


def comparable_offers(candidates: list[dict[str, Any]], *, currency: str = "", unit: str = "", by_unit: bool = False):
    """Keep incompatible offers visible, without giving them a numeric rank."""
    currencies = sorted({str(c.get("currency") or "").upper() for c in candidates})
    selected_currency = currency.strip().upper() or (currencies[0] if len(currencies) == 1 else "")
    units = sorted({str((c.get("unit_value") or {}).get("normalized_unit") or "") for c in candidates
                    if str(c.get("currency") or "").upper() == selected_currency
                    and (c.get("unit_value") or {}).get("available")})
    selected_unit = unit.strip() or (units[0] if len(units) == 1 else "")
    comparable, other = [], []
    for candidate in candidates:
        reason = ""
        if not re.fullmatch(r"[A-Z]{3}", str(candidate.get("currency") or "").upper()):
            reason = "invalid_currency"
        elif not selected_currency:
            reason = "choose_comparison_currency"
        elif str(candidate.get("currency") or "").upper() != selected_currency:
            reason = "different_currency_no_fx_conversion"
        elif candidate.get("full_basket") is False:
            reason = "partial_basket_requires_separate_buyer_choice"
        elif by_unit:
            value = candidate.get("unit_value") or {}
            if not value.get("available"):
                reason = "unit_value_unavailable"
            elif not selected_unit:
                reason = "choose_comparable_unit"
            elif value.get("normalized_unit") != selected_unit:
                reason = "incompatible_unit"
        if reason:
            other.append({**{k: v for k, v in candidate.items() if not k.startswith("_")},
                          "comparison_exclusion": reason, "rank": None, "winner": False})
        else:
            comparable.append(candidate)
    return comparable, other, {
        "currency": selected_currency or None, "available_currencies": currencies,
        "unit": selected_unit if by_unit else None, "available_units": units if by_unit else [],
        "choice_required": bool(candidates) and (not selected_currency or (by_unit and not selected_unit)),
        "fx_conversion": False, "scope": "valid offers from contacted merchants; buyer must confirm product equivalence",
    }


def unit_price_key(candidate: dict[str, Any]) -> Fraction:
    # Compare exact delivered cost per quantity, without rounded display prices.
    return Fraction(int(candidate["total_cents"])) / Fraction(str(candidate["unit_value"]["normalized_total_quantity"]))


def diverse_products(products: list[dict[str, Any]], nonce: str, merchant_limit: int, products_per_merchant: int = 2):
    groups: dict[str, dict[str, dict[str, Any]]] = {}
    for product in products:
        merchant = str(product.get("merchant_id") or "")
        product_id = str(product.get("id") or product.get("product_id") or "")
        if merchant and product_id:
            groups.setdefault(merchant, {}).setdefault(product_id, product)
    merchants = sorted(groups, key=lambda m: tie_key(nonce, {"merchant_id": m}))[:merchant_limit]
    queues = [sorted(groups[m].values(), key=lambda p: tie_key(nonce, {**p, "product_id": p.get("id") or p.get("product_id")}))[:products_per_merchant] for m in merchants]
    return [queue[index] for index in range(products_per_merchant) for queue in queues if len(queue) > index]
