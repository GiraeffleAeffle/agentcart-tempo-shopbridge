"""Bounded merchant-category routing hints for ShopBridge discovery.

Discovery Facets are coarse, public categories committed by a Registry Record's
onchain ``recordHash``.  They narrow which records a buyer resolves before
catalog requests.  They never establish merchant eligibility, product
availability, or ranking; the caller still verifies the record and queries the
merchant's current catalog.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


FACETS_SCHEMA = "agentcart.discovery_facets.v1"
INDEX_SCHEMA = "agentcart.registry_discovery_index.v1"
TAXONOMY = "woocommerce-product-category-slug-v1"
SOURCE_EXPOSED_CATALOG = "exposed_catalog_snapshot"
ALLOWED_SOURCES = {SOURCE_EXPOSED_CATALOG}
MAX_CATEGORIES = 8
MAX_INDEX_ENTRIES = 5_000
CATEGORY_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
RECORD_ID_PATTERN = re.compile(r"0x[0-9a-f]{64}")
ADDRESS_PATTERN = re.compile(r"0x[0-9a-f]{40}")
CHAIN_ID_PATTERN = re.compile(r"eip155:[1-9][0-9]*")
QUERY_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
QUERY_STOP_WORDS = {
    "a",
    "an",
    "and",
    "buy",
    "deliver",
    "delivered",
    "delivery",
    "find",
    "for",
    "from",
    "looking",
    "me",
    "near",
    "of",
    "or",
    "please",
    "selling",
    "shop",
    "some",
    "store",
    "that",
    "the",
    "to",
    "want",
    "with",
}


def normalized_category(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text or len(text) > 64 or not CATEGORY_PATTERN.fullmatch(text):
        return ""
    return text


def discovery_facets_from_category_counts(
    category_counts: Mapping[Any, Any] | Iterable[Any],
    *,
    source: str = SOURCE_EXPOSED_CATALOG,
    max_categories: int = MAX_CATEGORIES,
) -> dict[str, Any]:
    """Create canonical facets from exposed-product category occurrence counts."""

    if max_categories < 1 or max_categories > MAX_CATEGORIES:
        raise ValueError(f"max_categories must be 1..{MAX_CATEGORIES}")
    raw_items = category_counts.items() if isinstance(category_counts, Mapping) else (
        (value, 1) for value in category_counts
    )
    counts: dict[str, int] = {}
    for raw_category, raw_count in raw_items:
        category = normalized_category(raw_category)
        if not category:
            continue
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        if count < 1:
            continue
        counts[category] = counts.get(category, 0) + count
    if not counts:
        return {}
    ranked = sorted(counts, key=lambda category: (-counts[category], category))
    selected = sorted(ranked[:max_categories])
    truncated = len(ranked) > len(selected)
    return {
        "schema": FACETS_SCHEMA,
        "taxonomy": TAXONOMY,
        "source": source,
        "categories": selected,
        "category_count_total": len(ranked),
        "coverage": "partial" if truncated else "complete",
        "truncated": truncated,
    }


def validate_discovery_facets(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, dict):
        return ["discovery_facets_must_be_object"]
    errors: list[str] = []
    if value.get("schema") != FACETS_SCHEMA:
        errors.append("discovery_facets_schema_unsupported")
    if value.get("taxonomy") != TAXONOMY:
        errors.append("discovery_facets_taxonomy_unsupported")
    if value.get("source") not in ALLOWED_SOURCES:
        errors.append("discovery_facets_source_unsupported")
    categories = value.get("categories")
    if not isinstance(categories, list):
        return [*errors, "discovery_facets_categories_must_be_array"]
    if not categories or len(categories) > MAX_CATEGORIES:
        errors.append("discovery_facets_category_count_invalid")
    normalized = [normalized_category(category) for category in categories]
    if any(not category for category in normalized):
        errors.append("discovery_facets_category_invalid")
    if normalized != categories:
        errors.append("discovery_facets_categories_not_canonical")
    if len(set(normalized)) != len(normalized):
        errors.append("discovery_facets_categories_duplicate")
    if normalized != sorted(normalized):
        errors.append("discovery_facets_categories_not_sorted")
    total = value.get("category_count_total")
    if isinstance(total, bool) or not isinstance(total, int) or total < len(categories) or total > 256:
        errors.append("discovery_facets_category_count_total_invalid")
        total = len(categories)
    truncated = value.get("truncated")
    coverage = value.get("coverage")
    if not isinstance(truncated, bool):
        errors.append("discovery_facets_truncated_invalid")
    if coverage not in {"complete", "partial"}:
        errors.append("discovery_facets_coverage_invalid")
    elif coverage == "complete" and (truncated is not False or total != len(categories)):
        errors.append("discovery_facets_coverage_inconsistent")
    elif coverage == "partial" and (truncated is not True or total <= len(categories)):
        errors.append("discovery_facets_coverage_inconsistent")
    return list(dict.fromkeys(errors))


def query_terms(value: Any) -> set[str]:
    terms = {
        token
        for token in QUERY_TOKEN_PATTERN.findall(str(value or "").lower())
        if len(token) > 1 and token not in QUERY_STOP_WORDS
    }
    singular = {
        token[:-1]
        for token in terms
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss")
    }
    return terms | singular


def category_terms(category: Any) -> set[str]:
    normalized = normalized_category(category)
    if not normalized:
        return set()
    parts = set(normalized.split("-"))
    return query_terms(normalized) | parts | {normalized}


def matching_categories(facets: Any, query: Any) -> list[str]:
    if not isinstance(facets, dict) or validate_discovery_facets(facets):
        return []
    terms = query_terms(query)
    if not terms:
        return []
    return [
        category
        for category in facets["categories"]
        if terms.intersection(category_terms(category))
    ]


def _onchain_identity(record: dict[str, Any]) -> dict[str, str]:
    identity = record.get("onchain_identity")
    if not isinstance(identity, dict):
        return {}
    record_id = str(identity.get("record_id") or "").strip().lower()
    chain_id = str(identity.get("chain_id") or "").strip().lower()
    registry_address = str(identity.get("registry_address") or "").strip().lower()
    if (
        not RECORD_ID_PATTERN.fullmatch(record_id)
        or record_id == "0x" + "0" * 64
        or not CHAIN_ID_PATTERN.fullmatch(chain_id)
        or not ADDRESS_PATTERN.fullmatch(registry_address)
        or registry_address == "0x" + "0" * 40
    ):
        return {}
    return {
        "record_id": record_id,
        "chain_id": chain_id,
        "registry_address": registry_address,
    }


def build_discovery_index(records: Iterable[dict[str, Any]], *, generated_at: str = "") -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        facets = record.get("discovery_facets")
        identity = _onchain_identity(record)
        if not identity or validate_discovery_facets(facets):
            continue
        entries.append(
            {
                **identity,
                "merchant_id": str(record.get("merchant_id") or ""),
                "domain": str(record.get("domain") or ""),
                "categories": list(facets["categories"]),
                "coverage": str(facets["coverage"]),
            }
        )
    entries.sort(key=lambda entry: entry["record_id"])
    return {
        "schema": INDEX_SCHEMA,
        "generated_at": generated_at,
        "authority": "routing_hint_only",
        "taxonomy": TAXONOMY,
        "entry_count": len(entries),
        "entries": entries,
    }


def hinted_record_ids(
    document: Any,
    queries: Iterable[Any],
    *,
    require_all_queries: bool = False,
    expected_chain_id: str = "",
    expected_registry_address: str = "",
) -> tuple[set[str], dict[str, Any]]:
    """Read untrusted index hints; callers must verify every returned id onchain."""

    query_list = [str(query or "").strip() for query in queries if str(query or "").strip()]
    diagnostics = {
        "schema": INDEX_SCHEMA,
        "authority": "routing_hint_only",
        "usable": False,
        "entry_count": 0,
        "matched_entry_count": 0,
        "require_all_queries": require_all_queries,
        "expected_chain_id": str(expected_chain_id or "").lower(),
        "expected_registry_address": str(expected_registry_address or "").lower(),
        "fallback_required": True,
        "errors": [],
    }
    if not isinstance(document, dict) or document.get("schema") != INDEX_SCHEMA:
        diagnostics["errors"] = ["discovery_index_schema_invalid"]
        return set(), diagnostics
    if document.get("taxonomy") != TAXONOMY or document.get("authority") != "routing_hint_only":
        diagnostics["errors"] = ["discovery_index_contract_invalid"]
        return set(), diagnostics
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_INDEX_ENTRIES:
        diagnostics["errors"] = ["discovery_index_entries_invalid"]
        return set(), diagnostics
    diagnostics["usable"] = True
    diagnostics["entry_count"] = len(entries)
    matched: set[str] = set()
    partial_coverage_seen = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        record_id = str(entry.get("record_id") or "").lower()
        chain_id = str(entry.get("chain_id") or "").lower()
        registry_address = str(entry.get("registry_address") or "").lower()
        categories = entry.get("categories")
        if (
            not RECORD_ID_PATTERN.fullmatch(record_id)
            or record_id == "0x" + "0" * 64
            or not CHAIN_ID_PATTERN.fullmatch(chain_id)
            or not ADDRESS_PATTERN.fullmatch(registry_address)
            or registry_address == "0x" + "0" * 40
            or not isinstance(categories, list)
            or not 1 <= len(categories) <= MAX_CATEGORIES
            or [normalized_category(category) for category in categories] != categories
            or len(set(categories)) != len(categories)
            or categories != sorted(categories)
            or entry.get("coverage") not in {"complete", "partial"}
        ):
            continue
        if expected_chain_id and chain_id != str(expected_chain_id).lower():
            continue
        if expected_registry_address and registry_address != str(expected_registry_address).lower():
            continue
        category_tokens = set().union(*(category_terms(category) for category in categories))
        query_matches = [bool(query_terms(query).intersection(category_tokens)) for query in query_list]
        matches = all(query_matches) if require_all_queries else any(query_matches)
        if matches and query_matches:
            matched.add(record_id)
        if entry.get("coverage") != "complete":
            partial_coverage_seen = True
    diagnostics["matched_entry_count"] = len(matched)
    diagnostics["partial_coverage_seen"] = partial_coverage_seen
    diagnostics["fallback_required"] = True
    return matched, diagnostics
