from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import sys
import unittest
from zoneinfo import ZoneInfo


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "household_os.py"
SPEC = importlib.util.spec_from_file_location("household_os", MODULE_PATH)
household_os = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["household_os"] = household_os
SPEC.loader.exec_module(household_os)

IMPORTER_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "import_household_board.py"
IMPORTER_SPEC = importlib.util.spec_from_file_location("import_household_board", IMPORTER_PATH)
import_household_board = importlib.util.module_from_spec(IMPORTER_SPEC)
assert IMPORTER_SPEC and IMPORTER_SPEC.loader
sys.modules["import_household_board"] = import_household_board
IMPORTER_SPEC.loader.exec_module(import_household_board)


class HouseholdOsTests(unittest.TestCase):
    def test_parse_bool(self) -> None:
        self.assertIs(household_os.parse_bool("open"), False)
        self.assertIs(household_os.parse_bool("completed"), True)
        self.assertIsNone(household_os.parse_bool(""))

    def test_parse_datetime_handles_vikunja_zero_time(self) -> None:
        self.assertIsNone(household_os.parse_datetime("0001-01-01T00:00:00Z"))
        parsed = household_os.parse_datetime("2026-05-31T10:30:00Z")
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.tzinfo, dt.timezone.utc)

    def test_filter_tasks_by_project_done_and_due_date(self) -> None:
        tasks = [
            {
                "id": 1,
                "title": "Due soon",
                "project_id": 7,
                "done": False,
                "due_date": "2026-06-01T00:00:00Z",
                "updated": "2026-05-30T00:00:00Z",
            },
            {
                "id": 2,
                "title": "Other project",
                "project_id": 8,
                "done": False,
                "due_date": "2026-06-01T00:00:00Z",
                "updated": "2026-05-30T00:00:00Z",
            },
            {
                "id": 3,
                "title": "Done",
                "project_id": 7,
                "done": True,
                "due_date": "2026-05-31T00:00:00Z",
                "updated": "2026-05-30T00:00:00Z",
            },
        ]
        filtered = household_os.filter_tasks(
            tasks,
            project_id=7,
            done=False,
            due_before=dt.date(2026, 6, 2),
        )
        self.assertEqual([task["id"] for task in filtered], [1])

    def test_filter_stale_tasks(self) -> None:
        tasks = [
            {
                "id": 1,
                "title": "Stale",
                "project_id": 1,
                "done": False,
                "updated": "2026-04-01T00:00:00Z",
            },
            {
                "id": 2,
                "title": "Fresh",
                "project_id": 1,
                "done": False,
                "updated": "2026-05-30T00:00:00Z",
            },
        ]
        filtered = household_os.filter_tasks(
            tasks,
            stale_days=30,
            now=dt.datetime(2026, 5, 31, tzinfo=dt.timezone.utc),
        )
        self.assertEqual([task["id"] for task in filtered], [1])

    def test_description_to_vikunja_html(self) -> None:
        html = household_os.description_to_vikunja_html(
            "**Owners:** max\n\n## Notes\n\nDo the thing.\n\n## Checklist\n\n- [ ] First\n- [x] Done"
        )
        self.assertIn("<strong>Owners:</strong>", html)
        self.assertIn("<h3>Notes</h3>", html)
        self.assertIn('<ul data-type="taskList">', html)
        self.assertIn('data-checked="false"', html)
        self.assertIn('data-checked="true"', html)
        self.assertNotIn("##", html)

    def test_importer_normalizes_labels_to_broad_taxonomy(self) -> None:
        labels = import_household_board.normalize_task_labels(
            ["shopping", "clothes", "personal-care", "done", "home-assistant", "lights"]
        )
        self.assertEqual(labels, ["shopping", "health", "home-automation"])

    def test_agentcart_demo_intent_detection_is_narrow(self) -> None:
        self.assertTrue(household_os.is_agentcart_demo_message("Use AgentCart to buy my favorite tea"))
        self.assertTrue(household_os.is_agentcart_demo_message("Please buy my favourite tea"))
        self.assertTrue(household_os.is_agentcart_demo_message("Please buy my fav tea"))
        self.assertTrue(household_os.is_agentcart_demo_message("Please buy my favourit tea"))
        self.assertTrue(household_os.is_agentcart_demo_message("Please order our usual tea"))
        self.assertTrue(household_os.is_agentcart_demo_message("Can we sell excess energy?"))
        self.assertTrue(household_os.is_agentcart_demo_message("Order Hazel's Chocolate"))
        self.assertTrue(household_os.is_agentcart_demo_message("Buy a shaver from the WooCommerce shop"))
        self.assertFalse(household_os.is_agentcart_demo_message("What are our chores today?"))

    def test_agentcart_checkout_summary_includes_delivery_and_payment_proof(self) -> None:
        summary = household_os.format_agentcart_checkout_summary(
            {
                "order": {
                    "id": "order_1",
                    "quote_id": "quote_1",
                    "merchant_order_id": "FTS-1",
                    "total_cents": 1580,
                    "currency": "EUR",
                    "items": [{"quantity": 1, "title": "Hazel's Chocolate Tea"}],
                    "delivery_window": {
                        "earliest_date": "2026-06-19",
                        "latest_date": "2026-06-23",
                        "label": "2-4 business days",
                    },
                    "merchant_of_record": {"name": "Futura Demo Tea Shop GmbH"},
                    "vikunja_task": {"url": "http://vikunja/tasks/33"},
                    "calendar_event": {"state": "skipped"},
                },
                "payment_receipt": {
                    "id": "pay_1",
                    "external_value_proof": {
                        "provider": "tempo_mpp",
                        "state": "succeeded",
                        "network": "testnet",
                        "value_transfer": True,
                        "real_settlement": False,
                        "body": {"amount": "0.01"},
                        "transaction_reference": "0x419813a47925f1533762a2af1a63fa45820b761821268ad0262566fac02b43da",
                        "explorer_url": "https://explore.testnet.tempo.xyz/tx/0x419813a47925f1533762a2af1a63fa45820b761821268ad0262566fac02b43da",
                    },
                },
            }
        )
        self.assertIn("Hazel's Chocolate Tea", summary)
        self.assertIn("15.80 EUR", summary)
        self.assertIn("2026-06-19 to 2026-06-23", summary)
        self.assertIn("tempo_mpp", summary)
        self.assertIn("value_transfer=true", summary)
        self.assertIn("explore.testnet.tempo.xyz", summary)

    def test_agentcart_energy_trade_summary_keeps_demo_scope_visible(self) -> None:
        summary = household_os.format_agentcart_energy_trade(
            {
                "offer": {
                    "id": "energy_offer_1",
                    "quantity_kwh": 0.3,
                    "price_cents_per_kwh": 18,
                    "telemetry_snapshot": {"net_export_w": 600},
                },
                "settlement": {
                    "state": "demo_settled",
                    "amount_cents": 5,
                    "currency": "EUR",
                    "payment_receipt": {
                        "external_value_proof": {
                            "provider": "tempo_mpp",
                            "state": "succeeded",
                            "network": "testnet",
                            "value_transfer": True,
                            "real_settlement": False,
                            "transaction_reference": "0x419813a47925f1533762a2af1a63fa45820b761821268ad0262566fac02b43da",
                            "explorer_url": "https://explore.testnet.tempo.xyz/tx/0x419813a47925f1533762a2af1a63fa45820b761821268ad0262566fac02b43da",
                        }
                    },
                },
            }
        )
        self.assertIn("energy_offer_1", summary)
        self.assertIn("0.3 kWh", summary)
        self.assertIn("tempo_mpp", summary)
        self.assertIn("demo only", summary)
        self.assertIn("no grid delivery", summary)

    def test_daily_summary_groups_due_tasks(self) -> None:
        tz = ZoneInfo("Europe/Berlin")
        today = dt.datetime.now(tz).date()
        tasks = [
            {"id": 1, "title": "Overdue", "project_id": 7, "done": False, "due_date": (today - dt.timedelta(days=1)).isoformat()},
            {"id": 2, "title": "Today", "project_id": 7, "done": False, "due_date": today.isoformat()},
            {"id": 3, "title": "Tomorrow", "project_id": 7, "done": False, "due_date": (today + dt.timedelta(days=1)).isoformat()},
            {"id": 4, "title": "Soon", "project_id": 7, "done": False, "due_date": (today + dt.timedelta(days=3)).isoformat()},
        ]

        class FakeVikunja(household_os.VikunjaClient):
            def list_projects(self) -> list[dict[str, object]]:
                return [{"id": 7, "title": "This Week / Active"}]

            def list_tasks(self, **_kwargs: object) -> list[dict[str, object]]:
                return [household_os.normalize_task(task) for task in tasks]

        client = FakeVikunja(
            household_os.Config(
                bind="127.0.0.1",
                port=8088,
                timezone="Europe/Berlin",
                household_token="",
                audit_log_path=pathlib.Path("/tmp/audit.jsonl"),
                chat_history_path=pathlib.Path("/tmp/chat.jsonl"),
                session_path=pathlib.Path("/tmp/sessions.json"),
                vikunja_api_url="http://vikunja:3456/api/v1",
                vikunja_web_url="http://vikunja.example",
                vikunja_token="token",
                homeassistant_url="http://ha.example",
                homeassistant_token="ha-token",
                openclaw_gateway_url="",
                openclaw_gateway_token="",
                notify_services=(),
                shopping_todo_entity="todo.shopping",
                co2_entity_ids=(),
                window_entity_ids=(),
                co2_threshold_ppm=1000,
                allowed_script_ids=(),
                cycle_calendar_enabled=False,
                cycle_calendar_token="",
                cycle_calendar_start_date="",
                cycle_calendar_length_days=28,
                cycle_calendar_period_days=5,
                cycle_calendar_months_ahead=6,
                task_calendar_enabled=False,
                task_calendar_token="",
                task_calendar_days_past=14,
                task_calendar_days_ahead=180,
                task_calendar_event_minutes=30,
            )
        )
        summary = client.daily_summary("Europe/Berlin", days=3)
        self.assertEqual(summary["counts"]["overdue"], 1)
        self.assertEqual(summary["counts"]["today"], 1)
        self.assertEqual(summary["counts"]["tomorrow"], 1)
        self.assertEqual(summary["counts"]["upcoming"], 1)
        self.assertIn("Household task digest", summary["text"])

    def test_cycle_support_events_for_28_day_cycle(self) -> None:
        events = household_os.cycle_support_events(
            start_date=dt.date(2026, 6, 4),
            cycle_length_days=28,
            period_days=5,
            months_ahead=1,
            today=dt.date(2026, 6, 4),
        )
        by_kind = {event["uid"].split("@")[0].rsplit("-", 1)[1]: event for event in events[:6]}
        self.assertEqual(by_kind["rest"]["start"], dt.date(2026, 6, 4))
        self.assertEqual(by_kind["rest"]["end"], dt.date(2026, 6, 9))
        self.assertEqual(by_kind["planning"]["start"], dt.date(2026, 6, 9))
        self.assertEqual(by_kind["planning"]["end"], dt.date(2026, 6, 17))
        self.assertEqual(by_kind["ovulation"]["start"], dt.date(2026, 6, 12))
        self.assertEqual(by_kind["ovulation"]["end"], dt.date(2026, 6, 19))
        self.assertEqual(by_kind["sensitive"]["start"], dt.date(2026, 6, 25))
        self.assertEqual(by_kind["sensitive"]["end"], dt.date(2026, 7, 2))
        self.assertEqual(by_kind["next"]["start"], dt.date(2026, 7, 2))
        self.assertEqual(by_kind["next"]["end"], dt.date(2026, 7, 3))

    def test_render_cycle_calendar_outputs_ics(self) -> None:
        config = household_os.Config(
            bind="127.0.0.1",
            port=8088,
            timezone="Europe/Berlin",
            household_token="",
            audit_log_path=pathlib.Path("/tmp/audit.jsonl"),
            chat_history_path=pathlib.Path("/tmp/chat.jsonl"),
            session_path=pathlib.Path("/tmp/sessions.json"),
            vikunja_api_url="http://vikunja:3456/api/v1",
            vikunja_web_url="http://vikunja.example",
            vikunja_token="token",
            homeassistant_url="http://ha.example",
            homeassistant_token="ha-token",
            openclaw_gateway_url="",
            openclaw_gateway_token="",
            notify_services=(),
            shopping_todo_entity="todo.shopping",
            co2_entity_ids=(),
            window_entity_ids=(),
            co2_threshold_ppm=1000,
            allowed_script_ids=(),
            cycle_calendar_enabled=True,
            cycle_calendar_token="secret",
            cycle_calendar_start_date="2026-06-04",
            cycle_calendar_length_days=28,
            cycle_calendar_period_days=5,
            cycle_calendar_months_ahead=1,
            task_calendar_enabled=False,
            task_calendar_token="",
            task_calendar_days_past=14,
            task_calendar_days_ahead=180,
            task_calendar_event_minutes=30,
        )
        calendar = household_os.render_cycle_calendar(
            config,
            now=dt.datetime(2026, 6, 4, 10, 0, tzinfo=dt.timezone.utc),
        )
        self.assertIn("BEGIN:VCALENDAR", calendar)
        self.assertIn("X-WR-CALNAME:Cycle Support", calendar)
        self.assertIn("DTSTART;VALUE=DATE:20260604", calendar)
        self.assertIn("DTEND;VALUE=DATE:20260609", calendar)
        self.assertIn("SUMMARY:Cycle support - rest window", calendar)
        self.assertIn("DESCRIPTION:Check in gently", calendar)

    def test_render_task_calendar_outputs_open_due_tasks(self) -> None:
        config = household_os.Config(
            bind="127.0.0.1",
            port=8088,
            timezone="Europe/Berlin",
            household_token="",
            audit_log_path=pathlib.Path("/tmp/audit.jsonl"),
            chat_history_path=pathlib.Path("/tmp/chat.jsonl"),
            session_path=pathlib.Path("/tmp/sessions.json"),
            vikunja_api_url="http://vikunja:3456/api/v1",
            vikunja_web_url="http://vikunja.example",
            vikunja_token="token",
            homeassistant_url="http://ha.example",
            homeassistant_token="ha-token",
            openclaw_gateway_url="",
            openclaw_gateway_token="",
            notify_services=(),
            shopping_todo_entity="todo.shopping",
            co2_entity_ids=(),
            window_entity_ids=(),
            co2_threshold_ppm=1000,
            allowed_script_ids=(),
            cycle_calendar_enabled=False,
            cycle_calendar_token="",
            cycle_calendar_start_date="",
            cycle_calendar_length_days=28,
            cycle_calendar_period_days=5,
            cycle_calendar_months_ahead=6,
            task_calendar_enabled=True,
            task_calendar_token="secret",
            task_calendar_days_past=14,
            task_calendar_days_ahead=180,
            task_calendar_event_minutes=30,
        )
        tasks = [
            {
                "id": 31,
                "title": "Buy wedding card",
                "project_id": 9,
                "done": False,
                "due_date": "2026-06-05T18:00:00+02:00",
                "labels": [{"title": "shopping"}],
                "assignees": [{"username": "max"}],
                "description": "<p>Print the card.</p>",
            },
            {
                "id": 99,
                "title": "Done task",
                "project_id": 9,
                "done": True,
                "due_date": "2026-06-05T18:00:00+02:00",
            },
        ]
        calendar = household_os.render_task_calendar(
            config,
            tasks,
            {9: "This Week / Active"},
            now=dt.datetime(2026, 6, 4, 10, 0, tzinfo=dt.timezone.utc),
        )
        self.assertIn("X-WR-CALNAME:Household Tasks", calendar)
        self.assertIn("UID:vikunja-task-31-due@household-os", calendar)
        self.assertIn("SUMMARY:Task due: Buy wedding card", calendar)
        self.assertIn("DTSTART;TZID=Europe/Berlin:20260605T180000", calendar)
        self.assertIn("DTEND;TZID=Europe/Berlin:20260605T183000", calendar)
        self.assertIn("Project: This Week / Active", calendar)
        self.assertIn("URL:http://vikunja.example/tasks/31", calendar)
        self.assertNotIn("Done task", calendar)


if __name__ == "__main__":
    unittest.main()
