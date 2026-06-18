from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.parse


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "agentcart.py"
SPEC = importlib.util.spec_from_file_location("agentcart", MODULE_PATH)
agentcart = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["agentcart"] = agentcart
SPEC.loader.exec_module(agentcart)


def make_service(tmp: pathlib.Path, **overrides: object) -> object:
    config = agentcart.Config(
        bind="127.0.0.1",
        port=8099,
        timezone="Europe/Berlin",
        public_url="http://agentcart.test",
        agentcart_token="test-token",
        state_path=tmp / "state.json",
        audit_log_path=tmp / "audit.jsonl",
        policy_path=None,
        homeassistant_url="",
        homeassistant_token="",
        ha_notify_services=(),
        homeassistant_calendar_entity_id="",
        energy_solar_power_entity="sensor.solar_power",
        energy_battery_level_entity="sensor.battery_level",
        energy_battery_power_entity="sensor.battery_power",
        energy_grid_export_entity="sensor.grid_export",
        energy_grid_import_entity="sensor.grid_import",
        energy_house_output_entity="sensor.house_output",
        energy_min_export_w=100.0,
        energy_min_battery_percent=70.0,
        vikunja_api_url="",
        vikunja_web_url="",
        vikunja_token="",
        vikunja_project_id=None,
        default_ship_country="DE",
        default_ship_postal_code="15344",
        woocommerce_mode="mock",
        woocommerce_base_url="",
        woocommerce_consumer_key="",
        woocommerce_consumer_secret="",
        woocommerce_agentcart_token="",
        woocommerce_merchant_id="woocommerce-demo-tea",
        woocommerce_merchant_name="Woo Demo Tea Shop",
        payment_provider="demo",
        agentcash_proof_url="",
        agentcash_command="",
        agentcash_proof_required=False,
        agentcash_timeout_seconds=5,
        tempo_mpp_endpoint="",
        tempo_mpp_proof_url="",
        tempo_mpp_command="npx mppx",
        tempo_mpp_network="testnet",
        tempo_mpp_account="agentcart-test",
        tempo_mpp_proof_required=False,
        tempo_mpp_timeout_seconds=5,
        tempo_mpp_recipient_address="",
        delivery_calendar_enabled=False,
        delivery_calendar_token="",
    )
    if overrides:
        config = agentcart.Config(**{**config.__dict__, **overrides})
    return agentcart.AgentCartService(config)


class AgentCartTests(unittest.TestCase):
    def test_catalog_search_returns_demo_tea_products(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            result = service.search_catalog("tea")
            self.assertEqual(result["merchant"]["id"], "demo-tea-shop")
            self.assertGreaterEqual(len(result["products"]), 5)
            self.assertEqual(result["products"][0]["category"], "grocery.tea")
            self.assertIn("woocommerce-demo-tea", {merchant["id"] for merchant in result["merchants"]})

    def test_discovery_documents_advertise_checkout_payment_info(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            openapi = service.openapi_document()
            self.assertEqual(openapi["openapi"], "3.1.0")
            checkout = openapi["paths"]["/v1/checkout"]["post"]
            self.assertIn("x-payment-info", checkout)
            offer = checkout["x-payment-info"]["offers"][0]
            self.assertEqual(offer["method"], "demo")
            self.assertEqual(offer["intent"], "charge")
            self.assertIsNone(offer["amount"])
            self.assertEqual(offer["currency"], "EUR")
            self.assertIn("x-service-info", openapi)
            self.assertIn("/v1/registry", openapi["paths"])
            self.assertIn("/v1/quote-tournament", openapi["paths"])
            self.assertIn("/openapi.json", service.llms_text())

    def test_registry_document_is_identity_anchor_not_ad_marketplace(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(
                pathlib.Path(raw_tmp),
                public_url="http://agentcart.example",
                woocommerce_base_url="http://woo.example",
                tempo_mpp_recipient_address="0x1111111111111111111111111111111111111111",
            )

            registry = service.registry_document()

            self.assertTrue(registry["registry"]["public_data_only"])
            self.assertTrue(registry["registry"]["no_catalog_prices_or_household_demand_onchain"])
            self.assertEqual(registry["market_design"]["ranking"], "user-owned policy; no hidden sponsored ranking")
            entries = {entry["merchant_id"]: entry for entry in registry["entries"]}
            self.assertIn("demo-tea-shop", entries)
            self.assertIn("woocommerce-demo-tea", entries)
            self.assertEqual(entries["demo-tea-shop"]["ranking"]["role"], "identity_anchor_only")
            self.assertFalse(entries["demo-tea-shop"]["ranking"]["paid_placement"])
            self.assertEqual(entries["woocommerce-demo-tea"]["manifest_url"], "http://woo.example/.well-known/agentcart.json")
            self.assertRegex(entries["demo-tea-shop"]["manifest_hash"], r"^[0-9a-f]{64}$")
            self.assertIn("DE", entries["demo-tea-shop"]["delivery"]["ship_to_countries"])

    def test_quote_tournament_ranks_final_quotes_without_paid_placement(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))

            result = service.quote_tournament({"q": "sencha", "country": "DE", "postal_code": "15344"})

            self.assertEqual(result["market_design"]["registry_role"], "public identity anchor")
            self.assertEqual(result["market_design"]["ranking"], "local user policy, total price, delivery window; no paid placement")
            self.assertGreaterEqual(len(result["candidates"]), 2)
            self.assertIsNotNone(result["winner"])
            winner = result["winner"]
            self.assertEqual(winner["rank"], 1)
            self.assertEqual(winner["merchant_id"], "demo-tea-shop")
            self.assertEqual(winner["total_cents"], 1339)
            self.assertFalse(winner["registry"]["paid_placement"])
            self.assertIn("no paid ranking signal used", winner["rank_reasons"])
            totals = [candidate["total_cents"] for candidate in result["candidates"]]
            self.assertEqual(totals, sorted(totals))
            self.assertTrue(all(candidate["quote_id"].startswith("quote_") for candidate in result["candidates"]))

    def test_favorite_tea_tournament_uses_normalized_intent_and_can_select_woo(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))

            result = service.quote_tournament({"q": "buy my favorite tea", "country": "DE", "postal_code": "15344"})

            self.assertEqual(result["query"], "buy my favorite tea")
            self.assertEqual(result["catalog_query"], "Hazel's Chocolate Tea")
            merchants = {candidate["merchant_id"] for candidate in result["candidates"]}
            self.assertIn("demo-tea-shop", merchants)
            self.assertIn("woocommerce-demo-tea", merchants)
            self.assertEqual(result["winner"]["merchant_id"], "woocommerce-demo-tea")
            self.assertEqual(result["winner"]["product_id"], "woo_203")
            self.assertEqual(result["winner"]["total_cents"], 1480)
            self.assertEqual(result["winner"]["payment_summary"]["quote_currency"], "EUR")
            self.assertEqual(result["winner"]["payment_summary"]["methods"], ["mpp"])
            self.assertIn("payment_requirements", result["winner"])

    def test_approval_is_portable_and_home_assistant_is_optional(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(
                pathlib.Path(raw_tmp),
                homeassistant_url="http://ha.test",
                homeassistant_token="ha-token",
                ha_notify_services=("notify.mobile_app_test",),
            )
            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "buy via chat approval",
                    "items": [{"product_id": "woo_203", "quantity": 1}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )

            approval = service.create_approval(
                {"quote_id": quote["id"], "channel": "agent_chat", "delivery_channels": ["chat", "web", "api"]}
            )

            self.assertEqual(approval["channel"], "agent_chat")
            self.assertIn("chat", approval["delivery_channels"])
            self.assertEqual(approval["notification"]["state"], "skipped")
            self.assertIn("/v1/approvals/", approval["decision_api"]["url"])
            self.assertEqual(approval["decision_api"]["token_transport"], "json_body.token")
            self.assertEqual(approval["consent_request"]["kind"], "purchase_approval")
            self.assertIn("chat", approval["consent_request"]["renderable_by"])
            self.assertIn("decision_token", approval)

    def test_mppx_include_output_extracts_payment_receipt_reference(self) -> None:
        receipt = agentcart.b64url_json(
            {
                "method": "tempo",
                "status": "success",
                "timestamp": "2026-06-17T15:18:21.749Z",
                "reference": "0x419813a47925f1533762a2af1a63fa45820b761821268ad0262566fac02b43da",
            }
        )
        output = (
            "HTTP/1.1 402 Payment Required\n"
            "www-authenticate: Payment id=\"chal\"\n\n"
            "HTTP/1.1 200 OK\n"
            f"payment-receipt: {receipt}\n"
            "content-type: application/json\n\n"
            '{"ok": true, "amount": "0.01"}\n'
        )

        parsed = agentcart.parse_mppx_output(output, network="testnet")

        self.assertEqual(parsed["body"]["amount"], "0.01")
        self.assertEqual(parsed["payment_receipt"]["method"], "tempo")
        self.assertEqual(
            parsed["transaction_reference"],
            "0x419813a47925f1533762a2af1a63fa45820b761821268ad0262566fac02b43da",
        )
        self.assertEqual(
            parsed["explorer_url"],
            "https://explore.testnet.tempo.xyz/tx/0x419813a47925f1533762a2af1a63fa45820b761821268ad0262566fac02b43da",
        )

    def test_integration_status_reports_configured_services(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(
                pathlib.Path(raw_tmp),
                homeassistant_url="http://ha.test",
                homeassistant_token="ha-token",
                ha_notify_services=("notify.mobile_app_test",),
                homeassistant_calendar_entity_id="calendar.household_deliveries",
                vikunja_api_url="http://vikunja.test/api/v1",
                vikunja_token="vikunja-token",
                vikunja_project_id=123,
                agentcash_proof_url="mock://agentcash/success",
                tempo_mpp_proof_url="mock://tempo/success",
                tempo_mpp_recipient_address="0x1111111111111111111111111111111111111111",
                delivery_calendar_enabled=True,
                delivery_calendar_token="calendar-token",
            )
            status = service.integration_status()
            self.assertTrue(status["home_assistant"]["approval_notifications_ready"])
            self.assertTrue(status["home_assistant"]["delivery_calendar_write_ready"])
            self.assertTrue(status["vikunja"]["configured"])
            self.assertTrue(status["vikunja"]["open_tasks_ready"])
            self.assertTrue(status["agentcash"]["proof_configured"])
            self.assertTrue(status["tempo_mpp"]["proof_configured"])
            self.assertTrue(status["tempo_mpp"]["recipient_configured"])
            self.assertTrue(status["delivery_calendar"]["ics_enabled"])

    def test_energy_surplus_is_read_only_and_thresholded(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(
                pathlib.Path(raw_tmp),
                homeassistant_url="http://ha.test",
                homeassistant_token="ha-token",
                energy_min_export_w=100.0,
                energy_min_battery_percent=70.0,
            )
            states = {
                "sensor.solar_power": ("80", "W"),
                "sensor.battery_level": ("54", "%"),
                "sensor.battery_power": ("120", "W"),
                "sensor.grid_export": ("43", "W"),
                "sensor.grid_import": ("0", "W"),
                "sensor.house_output": ("100", "W"),
            }

            def fake_http_json(url: str, **_kwargs: object) -> object:
                entity_id = url.rsplit("/", 1)[-1].replace("%2E", ".")
                value, unit = states[entity_id]
                return {"entity_id": entity_id, "state": value, "attributes": {"unit_of_measurement": unit}}

            service.http_json = fake_http_json  # type: ignore[method-assign]
            result = service.energy_surplus()
            self.assertEqual(result["state"], "no_surplus")
            self.assertFalse(result["offerable"])
            self.assertEqual(result["scope"], "read_only_detection_only_no_settlement")
            self.assertIn("below 100 W threshold", result["reasons"][0])
            self.assertIn("below 70% threshold", result["reasons"][1])

    def test_energy_offer_create_and_accept_is_demo_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(
                pathlib.Path(raw_tmp),
                homeassistant_url="http://ha.test",
                homeassistant_token="ha-token",
                tempo_mpp_proof_url="mock://tempo/success",
                tempo_mpp_recipient_address="0x1111111111111111111111111111111111111111",
            )
            states = {
                "sensor.solar_power": ("900", "W"),
                "sensor.battery_level": ("92", "%"),
                "sensor.battery_power": ("120", "W"),
                "sensor.grid_export": ("600", "W"),
                "sensor.grid_import": ("0", "W"),
                "sensor.house_output": ("180", "W"),
            }

            def fake_http_json(url: str, **_kwargs: object) -> object:
                entity_id = url.rsplit("/", 1)[-1].replace("%2E", ".")
                value, unit = states[entity_id]
                return {"entity_id": entity_id, "state": value, "attributes": {"unit_of_measurement": unit}}

            service.http_json = fake_http_json  # type: ignore[method-assign]
            offer = service.create_energy_offer({"price_cents_per_kwh": 18})
            self.assertEqual(offer["state"], "open")
            self.assertEqual(offer["telemetry_snapshot"]["offer_basis"], "battery_backed_solar_reserve")
            self.assertEqual(offer["legal_scope"]["prototype_scope"], "demo_discovery_and_payment_proof_only")
            self.assertFalse(offer["legal_scope"]["physical_delivery"])
            self.assertLess(offer["price_cents_per_kwh"], offer["market_reference_cents_per_kwh"])

            result = service.accept_energy_offer(offer["id"], {"buyer_id": "neighbor-test"})
            accepted_offer = result["offer"]
            settlement = result["settlement"]
            self.assertEqual(accepted_offer["state"], "accepted")
            self.assertEqual(settlement["state"], "demo_settled")
            self.assertFalse(settlement["legal_settlement"])
            self.assertFalse(settlement["physical_delivery"])
            proof = settlement["payment_receipt"]["external_value_proof"]
            self.assertEqual(proof["provider"], "tempo_mpp")
            self.assertEqual(proof["state"], "succeeded")
            dashboard = service.dashboard_state()
            self.assertEqual(dashboard["energy_offers"][-1]["id"], offer["id"])

    def test_catalog_search_matches_agent_style_phrases(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            result = service.search_catalog("buy woo tea")
            product_ids = {product["id"] for product in result["products"]}
            self.assertIn("woo_201", product_ids)
            self.assertIn("woo_202", product_ids)

    def test_favorite_tea_alias_resolves_to_hazels_chocolate(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            result = service.search_catalog("buy my favorite tea")
            self.assertEqual(result["catalog_query"], "Hazel's Chocolate Tea")
            self.assertEqual(result["products"][0]["id"], "woo_203")
            self.assertEqual(result["products"][0]["merchant_id"], "woocommerce-demo-tea")
            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "buy my favorite tea",
                    "items": [{"product_id": result["products"][0]["id"], "quantity": 1}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )
            self.assertEqual(quote["merchant_id"], "woocommerce-demo-tea")
            self.assertEqual(quote["items"][0]["product_id"], "woo_203")
            self.assertEqual(quote["items"][0]["title"], "Hazel's Chocolate Tea")
            self.assertEqual(quote["total_cents"], 1480)

    def test_quote_includes_shipping_vat_policy_and_merchant_of_record(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "tea stock is low",
                    "items": [{"product_id": "tea_sencha_100g", "quantity": 1}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )
            self.assertEqual(quote["subtotal_cents"], 849)
            self.assertEqual(quote["shipping"]["amount_cents"], 490)
            self.assertEqual(quote["total_cents"], 1339)
            self.assertEqual(quote["policy_result"]["decision"], "requires_approval")
            self.assertEqual(quote["merchant_of_record"]["name"], "Futura Demo Tea Shop GmbH")
            self.assertEqual({line["rate_bps"] for line in quote["vat_lines"]}, {700, 1900})
            self.assertEqual(quote["delivery_window"]["source"], "merchant_quote")
            self.assertRegex(quote["delivery_window"]["earliest_date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertRegex(quote["delivery_window"]["latest_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_woocommerce_mock_quote_uses_woo_merchant(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "buy from opt-in Woo tea shop",
                    "items": [{"product_id": "woo_201", "quantity": 1}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )
            self.assertEqual(quote["merchant_id"], "woocommerce-demo-tea")
            self.assertEqual(quote["merchant"]["name"], "Woo Demo Tea Shop")
            self.assertEqual(quote["items"][0]["source_product_id"], 201)
            self.assertEqual(quote["total_cents"], 1689)
            self.assertEqual(quote["policy_result"]["decision"], "requires_approval")

    def test_policy_blocks_quote_above_order_limit(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "oversized order",
                    "items": [{"product_id": "tea_assam_250g", "quantity": 3}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )
            self.assertEqual(quote["policy_result"]["decision"], "deny")
            with self.assertRaises(agentcart.Forbidden):
                service.create_approval({"quote_id": quote["id"]})

    def test_checkout_is_mpp_shaped_and_has_no_order_side_effect_before_payment(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "tea stock is low",
                    "items": [{"product_id": "tea_sencha_100g", "quantity": 1}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )
            approval = service.create_approval({"quote_id": quote["id"]})
            service.decide_approval(
                approval["id"],
                {"decision": "approved", "token": approval["decision_token"], "approver": "max"},
            )

            payload = {
                "quote_id": quote["id"],
                "approval_id": approval["id"],
                "idempotency_key": "test-checkout-1",
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            status, headers, body = service.checkout(payload, {"idempotency-key": "test-checkout-1"}, raw_body)
            self.assertEqual(status, 402)
            self.assertIn("WWW-Authenticate", headers)
            self.assertEqual(service.state["orders"], {})
            self.assertTrue(body["demo_authorization"].startswith("Payment demo:chal_"))

            status, headers, body = service.checkout(
                payload,
                {
                    "idempotency-key": "test-checkout-1",
                    "authorization": body["demo_authorization"],
                },
                raw_body,
            )
            self.assertEqual(status, 201)
            self.assertIn("Payment-Receipt", headers)
            order = body["order"]
            self.assertEqual(order["state"], "accepted")
            self.assertEqual(order["vikunja_task"]["state"], "skipped")
            self.assertEqual(order["calendar_event"]["state"], "skipped")
            self.assertEqual(order["shipment"]["status"], "not_shipped")
            self.assertIn("delivery_window", order)
            self.assertEqual(service.state["stock"]["tea_sencha_100g"], 11)
            calendar = service.render_delivery_calendar()
            self.assertIn("BEGIN:VCALENDAR", calendar)
            self.assertIn("X-WR-CALNAME:AgentCart Deliveries", calendar)
            self.assertIn("SUMMARY:Delivery: 1x Sencha Daily Green Tea", calendar)

            status, _headers, replay = service.checkout(payload, {"idempotency-key": "test-checkout-1"}, raw_body)
            self.assertEqual(status, 200)
            self.assertTrue(replay["idempotent_replay"])
            self.assertEqual(replay["order"]["id"], order["id"])

    def test_refund_order_records_demo_refund_without_claiming_real_rail_refund(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "tea stock is low",
                    "items": [{"product_id": "tea_sencha_100g", "quantity": 1}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )
            approval = service.create_approval({"quote_id": quote["id"]})
            service.decide_approval(
                approval["id"],
                {"decision": "approved", "token": approval["decision_token"], "approver": "max"},
            )
            payload = {
                "quote_id": quote["id"],
                "approval_id": approval["id"],
                "idempotency_key": "test-refund-order",
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            status, _headers, body = service.checkout(payload, {"idempotency-key": "test-refund-order"}, raw_body)
            self.assertEqual(status, 402)
            status, _headers, body = service.checkout(
                payload,
                {
                    "idempotency-key": "test-refund-order",
                    "authorization": body["demo_authorization"],
                },
                raw_body,
            )
            self.assertEqual(status, 201)
            order_id = body["order"]["id"]

            result = service.refund_order(order_id, {"reason": "customer changed their mind"})

            refund = result["refund"]
            self.assertEqual(refund["order_id"], order_id)
            self.assertEqual(refund["amount_cents"], 1339)
            self.assertEqual(refund["state"], "demo_refund_recorded")
            self.assertFalse(refund["real_refund_verified"])
            self.assertEqual(result["order"]["refund_state"], "demo_refund_recorded")
            self.assertEqual(result["order"]["refunds"][0]["id"], refund["id"])

    def test_agentcash_mock_value_proof_is_attached_to_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp), agentcash_proof_url="mock://agentcash/success")
            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "tea stock is low",
                    "items": [{"product_id": "tea_sencha_100g", "quantity": 1}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )
            approval = service.create_approval({"quote_id": quote["id"]})
            service.decide_approval(
                approval["id"],
                {"decision": "approved", "token": approval["decision_token"], "approver": "max"},
            )
            payload = {
                "quote_id": quote["id"],
                "approval_id": approval["id"],
                "idempotency_key": "test-agentcash-proof",
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            status, _headers, body = service.checkout(payload, {"idempotency-key": "test-agentcash-proof"}, raw_body)
            self.assertEqual(status, 402)
            status, _headers, body = service.checkout(
                payload,
                {
                    "idempotency-key": "test-agentcash-proof",
                    "authorization": body["demo_authorization"],
                },
                raw_body,
            )
            self.assertEqual(status, 201)
            proof = body["payment_receipt"]["external_value_proof"]
            self.assertEqual(proof["provider"], "agentcash_x402")
            self.assertEqual(proof["state"], "succeeded")

    def test_home_assistant_calendar_event_is_created_after_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(
                pathlib.Path(raw_tmp),
                homeassistant_url="http://ha.test",
                homeassistant_token="ha-token",
                homeassistant_calendar_entity_id="calendar.household_deliveries",
            )
            calls = []

            def fake_http_json(url: str, **kwargs: object) -> object:
                calls.append({"url": url, **kwargs})
                return [{"context": {"id": "ctx-calendar"}}]

            service.http_json = fake_http_json  # type: ignore[method-assign]
            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "tea stock is low",
                    "items": [{"product_id": "tea_sencha_100g", "quantity": 1}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )
            approval = service.create_approval({"quote_id": quote["id"]})
            service.decide_approval(
                approval["id"],
                {"decision": "approved", "token": approval["decision_token"], "approver": "max"},
            )
            payload = {
                "quote_id": quote["id"],
                "approval_id": approval["id"],
                "idempotency_key": "test-calendar-checkout",
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            status, _headers, body = service.checkout(payload, {"idempotency-key": "test-calendar-checkout"}, raw_body)
            self.assertEqual(status, 402)
            status, _headers, body = service.checkout(
                payload,
                {
                    "idempotency-key": "test-calendar-checkout",
                    "authorization": body["demo_authorization"],
                },
                raw_body,
            )
            self.assertEqual(status, 201)
            calendar_event = body["order"]["calendar_event"]
            self.assertEqual(calendar_event["state"], "created")
            self.assertEqual(calendar_event["entity_id"], "calendar.household_deliveries")
            self.assertEqual(calls[-1]["url"], "http://ha.test/api/services/calendar/create_event")
            payload_sent = calls[-1]["payload"]
            self.assertEqual(payload_sent["entity_id"], "calendar.household_deliveries")
            self.assertEqual(payload_sent["summary"], "Delivery: 1x Sencha Daily Green Tea")

    def test_list_open_vikunja_tasks_filters_done_and_adds_links(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(
                pathlib.Path(raw_tmp),
                vikunja_api_url="http://vikunja.test/api/v1",
                vikunja_web_url="http://vikunja.test",
                vikunja_token="vikunja-token",
                vikunja_project_id=5,
            )
            requested_urls = []

            def fake_http_json(url: str, **_kwargs: object) -> object:
                requested_urls.append(url)
                return [
                    {"id": 1, "title": "Buy tea", "done": False, "due_date": "0001-01-01T00:00:00Z"},
                    {"id": 2, "title": "Done task", "done": True, "due_date": "2026-06-19T18:00:00+02:00"},
                ]

            service.http_json = fake_http_json  # type: ignore[method-assign]
            result = service.list_open_vikunja_tasks(limit=10)
            self.assertEqual(result["state"], "ok")
            self.assertIn("/projects/5/tasks?", requested_urls[0])
            self.assertEqual([task["title"] for task in result["tasks"]], ["Buy tea"])
            self.assertIsNone(result["tasks"][0]["due_date"])
            self.assertEqual(result["tasks"][0]["url"], "http://vikunja.test/tasks/1")

    def test_match_open_purchase_task_prefers_matching_product_task(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))

            def fake_open_tasks(*, limit: int = 20) -> dict[str, object]:
                return {
                    "state": "ok",
                    "tasks": [
                        {
                            "id": 32,
                            "title": "Buy Hazel's Chocolate tea",
                            "url": "http://vikunja.test/tasks/32",
                        },
                        {
                            "id": 40,
                            "title": "Buy Morning Coffee Beans",
                            "url": "http://vikunja.test/tasks/40",
                        },
                    ],
                }

            service.list_open_vikunja_tasks = fake_open_tasks  # type: ignore[method-assign]
            order = {
                "items": [
                    {
                        "title": "Morning Coffee Beans",
                        "sku": "AGENT-COFFEE-1",
                        "category": "woocommerce.coffee",
                    }
                ]
            }

            matched = service.match_open_purchase_task(order)

            self.assertIsNotNone(matched)
            self.assertEqual(matched["id"], 40)
            self.assertEqual(matched["match"], "product_purchase_intent")

    def test_tempo_mpp_mock_value_proof_takes_precedence_over_agentcash(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(
                pathlib.Path(raw_tmp),
                tempo_mpp_proof_url="mock://tempo/success",
                agentcash_proof_url="mock://agentcash/success",
            )
            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "tea stock is low",
                    "items": [{"product_id": "tea_sencha_100g", "quantity": 1}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )
            approval = service.create_approval({"quote_id": quote["id"]})
            service.decide_approval(
                approval["id"],
                {"decision": "approved", "token": approval["decision_token"], "approver": "max"},
            )
            payload = {
                "quote_id": quote["id"],
                "approval_id": approval["id"],
                "idempotency_key": "test-tempo-proof",
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            status, _headers, body = service.checkout(payload, {"idempotency-key": "test-tempo-proof"}, raw_body)
            self.assertEqual(status, 402)
            status, _headers, body = service.checkout(
                payload,
                {
                    "idempotency-key": "test-tempo-proof",
                    "authorization": body["demo_authorization"],
                },
                raw_body,
            )
            self.assertEqual(status, 201)
            proof = body["payment_receipt"]["external_value_proof"]
            self.assertEqual(proof["provider"], "tempo_mpp")
            self.assertEqual(proof["state"], "succeeded")

    def test_non_demo_payment_provider_fails_closed_before_order_creation(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp), payment_provider="tempo_mpp")
            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "tea stock is low",
                    "items": [{"product_id": "tea_sencha_100g", "quantity": 1}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )
            approval = service.create_approval({"quote_id": quote["id"]})
            service.decide_approval(
                approval["id"],
                {"decision": "approved", "token": approval["decision_token"], "approver": "max"},
            )
            payload = {
                "quote_id": quote["id"],
                "approval_id": approval["id"],
                "idempotency_key": "test-tempo-disabled",
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            with self.assertRaises(agentcart.PaymentProviderUnavailable):
                service.checkout(payload, {"idempotency-key": "test-tempo-disabled"}, raw_body)
            self.assertEqual(service.state["orders"], {})

    def test_woocommerce_mock_checkout_creates_woo_order_reference(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "tea stock is low",
                    "items": [{"product_id": "woo_201", "quantity": 1}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )
            approval = service.create_approval({"quote_id": quote["id"]})
            service.decide_approval(
                approval["id"],
                {"decision": "approved", "token": approval["decision_token"], "approver": "max"},
            )

            payload = {
                "quote_id": quote["id"],
                "approval_id": approval["id"],
                "idempotency_key": "test-woo-checkout-1",
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            status, _headers, body = service.checkout(payload, {"idempotency-key": "test-woo-checkout-1"}, raw_body)
            self.assertEqual(status, 402)
            status, _headers, body = service.checkout(
                payload,
                {
                    "idempotency-key": "test-woo-checkout-1",
                    "authorization": body["demo_authorization"],
                },
                raw_body,
            )
            self.assertEqual(status, 201)
            order = body["order"]
            self.assertEqual(order["merchant_id"], "woocommerce-demo-tea")
            self.assertEqual(order["merchant_order"]["platform"], "woocommerce-mock")
            self.assertTrue(order["merchant_order_id"].startswith("WOO-MOCK-"))
            self.assertEqual(service.state["stock"]["woo_201"], 8)

    def test_woocommerce_plugin_quote_and_checkout_use_plugin_order_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(
                pathlib.Path(raw_tmp),
                woocommerce_mode="plugin",
                woocommerce_base_url="http://woo.test",
                woocommerce_agentcart_token="merchant-token",
                woocommerce_merchant_id="woocommerce-demo-shop",
                woocommerce_merchant_name="AgentCart Demo Shop",
            )
            adapter = service.adapters["woocommerce-demo-shop"]
            calls = []
            product = {
                "id": "woo_701",
                "product_id": "woo_701",
                "source_product_id": 701,
                "merchant_id": "woocommerce-demo-shop",
                "sku": "AGENT-SHAVER-1",
                "title": "Travel Electric Shaver",
                "description": "Compact shaver exposed through the AgentCart WooCommerce plugin.",
                "category": "woocommerce.personal-care",
                "brand": "AgentCart Demo Shop",
                "unit_size": "1 unit",
                "image_urls": [],
                "price_cents": 1990,
                "currency": "EUR",
                "vat_rate_bps": 1900,
                "stock": 4,
                "availability": "in_stock",
                "shipping_regions": ["DE"],
                "eligible_for_agent_checkout": True,
            }

            def fake_plugin_json(url: str, *, method: str, payload: dict[str, object] | None = None, **_kwargs: object) -> object:
                calls.append({"url": url, "method": method, "payload": payload})
                parsed = urllib.parse.urlparse(url)
                query = urllib.parse.parse_qs(parsed.query)
                route = query.get("rest_route", [""])[0]
                if route == "/agentcart/v1/catalog":
                    return {"products": [product]}
                if route == "/agentcart/v1/products/701":
                    return product
                if route == "/agentcart/v1/quote":
                    self.assertEqual(method, "POST")
                    self.assertEqual(payload["items"][0]["product_id"], "woo_701")  # type: ignore[index]
                    return {
                        "id": "woo_quote_701",
                        "merchant": adapter.merchant,
                        "merchant_of_record": adapter.merchant["merchant_of_record"],
                        "items": [
                            {
                                "product_id": "woo_701",
                                "source_product_id": 701,
                                "sku": "AGENT-SHAVER-1",
                                "title": "Travel Electric Shaver",
                                "quantity": 1,
                                "unit_price_cents": 1990,
                                "line_total_cents": 1990,
                                "currency": "EUR",
                                "category": "woocommerce.personal-care",
                                "vat_rate_bps": 1900,
                            }
                        ],
                        "subtotal_cents": 1990,
                        "shipping": {"amount_cents": 490, "currency": "EUR", "method": "woocommerce-demo-standard", "vat_rate_bps": 1900},
                        "vat_lines": [{"rate_bps": 1900, "taxable_gross_cents": 2480, "vat_cents": 396, "currency": "EUR", "included_in_price": True}],
                        "total_cents": 2480,
                        "currency": "EUR",
                        "delivery_estimate": {"min_days": 2, "max_days": 4, "label": "2-4 business days"},
                        "stock_reservation": {"state": "not_reserved", "rechecked_before_order_creation": True},
                        "quote_hash": "hash-woo-701",
                        "payment_requirements": {
                            "amount_cents": 2480,
                            "currency": "EUR",
                            "protocols": [{"id": "tempo-mpp", "network": "testnet"}],
                        },
                        "terms_url": "http://woo.test/terms",
                        "returns_url": "http://woo.test/returns",
                    }
                if route == "/agentcart/v1/orders":
                    self.assertEqual(method, "POST")
                    self.assertEqual(payload["payment_receipt"]["method"], "demo")  # type: ignore[index]
                    self.assertEqual(payload["quote_hash"], "hash-woo-701")
                    return {
                        "platform": "woocommerce-agentcart-plugin",
                        "state": "created",
                        "id": 9001,
                        "number": "9001",
                        "status": "processing",
                        "payment_method": "tempo_mpp",
                        "url": "http://woo.test/wp-admin/post.php?post=9001&action=edit",
                        "status_url": "http://woo.test/wp-json/agentcart/v1/orders/9001/status",
                        "status_token": "status-token",
                        "fulfillment": {
                            "state": "preparing",
                            "carrier": None,
                            "tracking_number": None,
                            "tracking_url": None,
                            "source": "woocommerce_order_meta",
                        },
                        "payment_verification": {"state": "verified", "mode": "trusted_agentcart_token"},
                    }
                raise AssertionError(f"unexpected plugin call: {method} {url}")

            adapter.plugin_json = fake_plugin_json  # type: ignore[method-assign]
            service.state["stock"]["woo_701"] = 0
            search = service.search_catalog("shaver")
            self.assertEqual(search["products"][0]["title"], "Travel Electric Shaver")
            self.assertEqual(search["products"][0]["stock"], 4)
            self.assertEqual(search["products"][0]["availability"], "in_stock")

            quote = service.create_quote(
                {
                    "agent_id": "test-agent",
                    "reason": "buy a shaver from the opt-in WooCommerce demo shop",
                    "items": [{"product_id": "woo_701", "quantity": 1}],
                    "ship_to": {"country": "DE", "postal_code": "15344"},
                }
            )
            self.assertEqual(quote["merchant_quote_id"], "woo_quote_701")
            self.assertEqual(quote["quote_hash"], "hash-woo-701")
            self.assertEqual(quote["stock_reservation"]["state"], "not_reserved")
            self.assertEqual(quote["total_cents"], 2480)
            self.assertEqual(quote["policy_result"]["decision"], "requires_approval")

            approval = service.create_approval({"quote_id": quote["id"]})
            service.decide_approval(
                approval["id"],
                {"decision": "approved", "token": approval["decision_token"], "approver": "max"},
            )
            payload = {
                "quote_id": quote["id"],
                "approval_id": approval["id"],
                "idempotency_key": "test-woo-plugin-checkout",
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            status, _headers, body = service.checkout(payload, {"idempotency-key": "test-woo-plugin-checkout"}, raw_body)
            self.assertEqual(status, 402)
            status, _headers, body = service.checkout(
                payload,
                {
                    "idempotency-key": "test-woo-plugin-checkout",
                    "authorization": body["demo_authorization"],
                },
                raw_body,
            )
            self.assertEqual(status, 201)
            order = body["order"]
            self.assertEqual(order["merchant_order"]["platform"], "woocommerce-agentcart-plugin")
            self.assertEqual(order["merchant_order_id"], "9001")
            self.assertEqual(order["merchant_order"]["payment_verification"]["state"], "verified")
            self.assertEqual(order["shipment"]["status"], "preparing")
            self.assertTrue(any(urllib.parse.parse_qs(urllib.parse.urlparse(call["url"]).query).get("rest_route") == ["/agentcart/v1/orders"] for call in calls))

    def test_approval_token_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            quote = service.create_quote(
                {
                    "items": [{"product_id": "tea_rooibos_150g", "quantity": 1}],
                    "reason": "tea stock is low",
                }
            )
            approval = service.create_approval({"quote_id": quote["id"]})
            with self.assertRaises(agentcart.Forbidden):
                service.decide_approval(
                    approval["id"],
                    {"decision": "approved", "token": "wrong", "approver": "max"},
                )

    def test_dashboard_marks_stale_pending_approvals_expired(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            quote = service.create_quote(
                {
                    "items": [{"product_id": "tea_rooibos_150g", "quantity": 1}],
                    "reason": "tea stock is low",
                }
            )
            approval = service.create_approval({"quote_id": quote["id"]})
            service.state["approvals"][approval["id"]]["expires_at"] = agentcart.isoformat(
                agentcart.utcnow() - agentcart.dt.timedelta(seconds=1)
            )

            dashboard = service.dashboard_state()

            expired = [item for item in dashboard["approvals"] if item["id"] == approval["id"]][0]
            self.assertEqual(expired["state"], "expired")

    def test_dashboard_orders_are_sorted_by_creation_time(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp))
            service.state["orders"] = {
                "order_z": {"id": "order_z", "created_at": "2026-06-17T10:00:00Z"},
                "order_a": {"id": "order_a", "created_at": "2026-06-17T12:00:00Z"},
            }

            dashboard = service.dashboard_state()

            self.assertEqual([order["id"] for order in dashboard["orders"]], ["order_z", "order_a"])

    def test_order_proof_page_shows_explorer_link(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = make_service(pathlib.Path(raw_tmp), tempo_mpp_proof_url="mock://tempo/success")
            quote = service.create_quote(
                {
                    "items": [{"product_id": "tea_rooibos_150g", "quantity": 1}],
                    "reason": "tea stock is low",
                }
            )
            approval = service.create_approval({"quote_id": quote["id"]})
            service.decide_approval(approval["id"], {"decision": "approved", "token": approval["decision_token"]})
            checkout = service.demo_finish_checkout(approval["id"])
            order = checkout["order"]
            order["payment_receipt"]["external_value_proof"] = {
                "provider": "tempo_mpp",
                "state": "succeeded",
                "network": "testnet",
                "transaction_reference": "0x419813a47925f1533762a2af1a63fa45820b761821268ad0262566fac02b43da",
                "body": {"amount": "0.01"},
            }

            html = agentcart.render_order_proof_page(service, order["id"])

            self.assertIn("Execution Proof", html)
            self.assertIn("https://explore.testnet.tempo.xyz/tx/0x419813a47925f1533762a2af1a63fa45820b761821268ad0262566fac02b43da", html)


if __name__ == "__main__":
    unittest.main()
