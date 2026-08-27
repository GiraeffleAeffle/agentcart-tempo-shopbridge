from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = (
    ROOT
    / "gateway"
    / "shopbridge-direct-skill"
    / "scripts"
    / "shopbridge_discovery_facets.py"
)
SPEC = importlib.util.spec_from_file_location("shopbridge_discovery_facets_test", MODULE_PATH)
facets = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = facets
SPEC.loader.exec_module(facets)


def record(record_id: str, categories: list[str], *, coverage: str = "complete") -> dict:
    truncated = coverage == "partial"
    return {
        "merchant_id": f"merchant-{record_id[-2:]}",
        "domain": f"{record_id[-2:]}.example",
        "onchain_identity": {
            "record_id": record_id,
            "chain_id": "eip155:42431",
            "registry_address": "0x" + "ab" * 20,
        },
        "discovery_facets": {
            "schema": facets.FACETS_SCHEMA,
            "taxonomy": facets.TAXONOMY,
            "source": facets.SOURCE_EXPOSED_CATALOG,
            "categories": categories,
            "category_count_total": len(categories) + (1 if truncated else 0),
            "coverage": coverage,
            "truncated": truncated,
        },
    }


class DiscoveryFacetsTests(unittest.TestCase):
    def test_derives_canonical_bounded_facets_by_product_frequency(self) -> None:
        result = facets.discovery_facets_from_category_counts(
            {" Tea ": 5, "coffee_beans": 3, "gift sets": 2, "ignored!": 50}
        )

        self.assertEqual(result["categories"], ["coffee-beans", "gift-sets", "tea"])
        self.assertEqual(result["coverage"], "complete")
        self.assertFalse(result["truncated"])
        self.assertEqual(facets.validate_discovery_facets(result), [])

    def test_caps_facets_and_marks_partial_coverage(self) -> None:
        result = facets.discovery_facets_from_category_counts(
            {f"category-{index}": 20 - index for index in range(10)}
        )

        self.assertEqual(len(result["categories"]), 8)
        self.assertEqual(result["category_count_total"], 10)
        self.assertEqual(result["coverage"], "partial")
        self.assertTrue(result["truncated"])

    def test_rejects_noncanonical_or_inconsistent_facets(self) -> None:
        invalid = {
            "schema": facets.FACETS_SCHEMA,
            "taxonomy": facets.TAXONOMY,
            "source": facets.SOURCE_EXPOSED_CATALOG,
            "categories": ["tea", "Coffee Beans", "tea"],
            "category_count_total": 3,
            "coverage": "complete",
            "truncated": False,
        }

        errors = facets.validate_discovery_facets(invalid)
        self.assertIn("discovery_facets_categories_not_canonical", errors)
        self.assertIn("discovery_facets_categories_duplicate", errors)
        self.assertIn("discovery_facets_categories_not_sorted", errors)

    def test_index_returns_routing_hints_but_requires_fallback_for_partial_coverage(self) -> None:
        tea_id = "0x" + "11" * 32
        coffee_id = "0x" + "22" * 32
        index = facets.build_discovery_index(
            [record(tea_id, ["beverages", "tea"]), record(coffee_id, ["coffee"], coverage="partial")],
            generated_at="2026-08-27T00:00:00Z",
        )

        hinted, diagnostics = facets.hinted_record_ids(
            index,
            ["find me some tea"],
            expected_chain_id="eip155:42431",
            expected_registry_address="0x" + "ab" * 20,
        )

        self.assertEqual(hinted, {tea_id})
        self.assertEqual(index["authority"], "routing_hint_only")
        self.assertTrue(diagnostics["fallback_required"])

    def test_index_hints_are_scoped_to_chain_and_registry(self) -> None:
        tea_id = "0x" + "44" * 32
        index = facets.build_discovery_index([record(tea_id, ["tea"])])

        hinted, _diagnostics = facets.hinted_record_ids(
            index,
            ["tea"],
            expected_chain_id="eip155:1",
            expected_registry_address="0x" + "ab" * 20,
        )

        self.assertEqual(hinted, set())

    def test_query_matching_handles_plural_terms(self) -> None:
        value = record("0x" + "33" * 32, ["gift-sets", "tea"])["discovery_facets"]
        self.assertEqual(facets.matching_categories(value, "show me teas"), ["tea"])


if __name__ == "__main__":
    unittest.main()
