from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest import mock

from test_shopbridge_direct_skill import shopbridge_direct as direct, sample_quote
from test_agentcart import make_service


class MarketFairnessTests(unittest.TestCase):
    def discover(self, currencies=None, failed_stage=None, **args):
        records = [{"merchant_id": m, "domain": f"{m}.example"} for m in ("a", "b", "c")]
        calls = []

        def resolve(record, _args):
            calls.append(record["merchant_id"])
            if failed_stage == "proof" and len(calls) == 1:
                raise SystemExit("expired proof")
            return {"ok": True, "merchant": {"id": record["merchant_id"], "name": record["merchant_id"]},
                    "base_url": f"https://{record['domain']}", "verification": {"state": "verified"}}

        def catalog(call):
            if failed_stage == "catalog" and len(calls) == 1:
                raise SystemExit("unavailable")
            return {"products": [{"id": "tea", "title": "Tea", "shipping_regions": ["DE"]}]}

        def quote(call):
            if failed_stage == "quote" and len(calls) == 1:
                raise SystemExit("out of stock")
            merchant = call["base_url"].split("//")[1].split(".")[0]
            return sample_quote(id=f"quote-{merchant}", currency=(currencies or {}).get(merchant, "EUR"),
                                merchant={"id": merchant, "name": merchant})

        with mock.patch.object(direct, "registry_records_from_args", return_value=records), \
             mock.patch.object(direct, "resolve_record_for_discovery", side_effect=resolve), \
             mock.patch.object(direct, "command_catalog", side_effect=catalog), \
             mock.patch.object(direct, "command_quote", side_effect=quote), \
             mock.patch.object(direct, "command_checkout_preflight", return_value={
                 "ok": True, "issues": [], "available_payment_methods": [{"rail": "stripe-card-mpp"}]}):
            result = direct.command_discover_quotes({"query": "tea", "candidate_seed": "test", **args})
        return result, calls

    def test_mixed_currency_discovery_has_no_winner_until_buyer_selects_currency(self):
        result, _ = self.discover(currencies={"b": "GBP"})
        self.assertIsNone(result["winner"])
        self.assertTrue(result["comparison"]["choice_required"])
        self.assertEqual(len(result["other_offers"]), 3)
        result, _ = self.discover(currencies={"b": "GBP"}, comparison_currency="EUR")
        self.assertEqual(result["winner"]["currency"], "EUR")
        self.assertEqual([c["currency"] for c in result["other_offers"]], ["GBP"])

    def test_failed_proof_catalog_or_quote_backfills_without_expanding_contact_budget(self):
        for stage in ("proof", "catalog", "quote"):
            with self.subTest(stage=stage):
                result, calls = self.discover(failed_stage=stage, merchant_candidate_limit=1)
                self.assertIsNotNone(result["winner"])
                self.assertEqual(len(calls), 2)
                self.assertLessEqual(len(calls), result["market_design"]["candidate_selection"]["selected_count"])

    def test_default_nonce_is_unpredictable_but_stable_within_request(self):
        args = {"query": "tea"}
        seed = direct.merchant_candidate_seed(args)
        self.assertEqual(seed, direct.merchant_candidate_seed(args))
        self.assertNotEqual(seed, direct.merchant_candidate_seed({"query": "tea"}))

    def test_incompatible_physical_units_and_partial_baskets_never_compete(self):
        offers = [{"merchant_id": unit, "currency": "EUR", "total_cents": 100,
                   "unit_value": {"available": True, "normalized_unit": unit, "normalized_total_quantity": 100}} for unit in ("g", "ml", "unit")]
        comparable, other, state = direct.market.comparable_offers(offers, by_unit=True)
        self.assertFalse(comparable); self.assertTrue(state["choice_required"]); self.assertEqual(len(other), 3)
        comparable, _, _ = direct.market.comparable_offers(offers, by_unit=True, unit="g")
        self.assertEqual(comparable[0]["merchant_id"], "g")
        comparable, other, _ = direct.market.comparable_offers([{"currency": "EUR", "total_cents": 1, "full_basket": False}])
        self.assertFalse(comparable); self.assertEqual(other[0]["comparison_exclusion"], "partial_basket_requires_separate_buyer_choice")

    def test_delivered_unit_price_uses_total_and_unrounded_quantities(self):
        product = {"id": "tea", "title": "Tea 100 g", "unit_size": "100 g", "price_cents": 100}
        value = direct.unit_value_for_candidate(product, sample_quote(total_cents=1580), "tea")
        self.assertTrue(value["includes_shipping_and_tax"])
        self.assertEqual(value["cents_per_basis"], 1580)
        offer = {"total_cents": 1, "unit_value": {"normalized_total_quantity": "3"}}
        self.assertLess(direct.market.unit_price_key(offer), direct.market.unit_price_key({**offer, "total_cents": 2}))

    def test_common_owner_grouping_uses_verified_admissions_only(self):
        records = [{"merchant_id": str(i), "domain": f"{i}.example", "entity_id": "untrusted",
                    "onchain_identity": {"record_id": str(i)}} for i in range(3)]
        args = {"candidate_seed": "test", "merchant_candidate_limit": 3}
        selected, _ = direct.prequote_candidate_sample(records, args)
        self.assertEqual(len(selected), 3)
        args["_verified_admissions"] = {str(i): {"eligible": True, "entity_id": "shared" if i < 2 else "independent"} for i in range(3)}
        selected, _ = direct.prequote_candidate_sample(records, args)
        self.assertEqual(len(selected), 2)

    def test_many_brands_do_not_improve_an_admitted_owners_sampling_chance(self):
        def record(i):
            return {"merchant_id": str(i), "domain": f"{i}.example", "onchain_identity": {"record_id": str(i)}}
        admissions = {str(i): {"eligible": True, "entity_id": "independent" if i == 0 else "large-owner"} for i in range(102)}
        for seed in range(30):
            args = {"candidate_seed": str(seed), "merchant_candidate_limit": 1, "_verified_admissions": admissions}
            small, _ = direct.prequote_candidate_sample([record(0), record(1)], args)
            large, _ = direct.prequote_candidate_sample([record(i) for i in range(102)], args)
            owner = lambda selected: admissions[selected[0]["merchant_id"]]["entity_id"]
            self.assertEqual(owner(small), owner(large))

    def test_service_display_limit_does_not_stop_before_later_cheapest_merchant(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(pathlib.Path(tmp))
            catalog = service.search_catalog("sencha")
            # Make the cheapest fixture shop last, behind a larger catalog.
            catalog["products"].sort(key=lambda p: p.get("merchant_id") == "demo-tea-shop")
            with mock.patch.object(service, "search_catalog", return_value=catalog):
                result = service.quote_tournament({"query": "sencha", "max_candidates": 1, "candidate_seed": "test"})
            self.assertEqual(result["winner"]["merchant_id"], "demo-tea-shop")
            self.assertEqual(len(result["candidates"]), 1)

    def test_product_scheduling_is_permutation_invariant_and_keeps_shop_local_ids(self):
        products = [{"merchant_id": "large", "id": str(i)} for i in range(100)] + [{"merchant_id": "small", "id": "0"}]
        schedule = direct.market.diverse_products(products, "test", 10)
        self.assertEqual(schedule, direct.market.diverse_products(list(reversed(products)), "test", 10))
        self.assertEqual(len(schedule), 3)
        self.assertEqual({p["merchant_id"] for p in schedule[:2]}, {"large", "small"})

    def test_http_budget_covers_requests_bytes_and_deadline(self):
        budget = direct.safe_http.DiscoveryBudget(requests=1, response_bytes=10)
        _, allocation = budget.reserve(30, 100)
        self.assertEqual(allocation, 9)
        with self.assertRaises(direct.safe_http.SafeHttpError): budget.reserve(30, 1)
        expired = direct.safe_http.DiscoveryBudget(seconds=-1)
        with self.assertRaises(direct.safe_http.SafeHttpError): expired.reserve(30, 1)

    def test_pending_or_failed_refund_boolean_cannot_authorize_completion_claim(self):
        for status in ("pending", "requires_action", "failed", "canceled", ""):
            refund = {"real_refund_verified": True, "refund_status": status}
            messages = direct.buyer_aftercare_messages({"refund_state": "refunded"}, [refund], "EUR")
            self.assertFalse(messages["allowed_claims"]["refund_executed"])
            self.assertFalse(messages["allowed_claims"]["money_returned"])


if __name__ == "__main__":
    unittest.main()
