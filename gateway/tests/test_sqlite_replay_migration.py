from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT_DIR / "gateway" / "scripts" / "verifier-sqlite-replay-store.mjs"


@unittest.skipUnless(shutil.which("sqlite3") and shutil.which("node"), "node and sqlite3 are required")
class SQLiteReplayMigrationTest(unittest.TestCase):
    def run_tool(self, *args: str) -> dict[str, object]:
        completed = subprocess.run(
            ["node", str(TOOL), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(completed.stdout)

    def test_legacy_json_import_is_idempotent_and_preserves_conflict_detection(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = pathlib.Path(raw_tmp)
            source = tmp / "replay-store.json"
            database = tmp / "replay-store.sqlite"
            metadata = {
                "provider": "tempo_mpp",
                "rail": "tempo-mpp",
                "amount_cents": 1490,
                "currency": "USD",
                "quote_hash": "a" * 64,
                "payment_contract_hash": "b" * 64,
            }
            source.write_text(
                json.dumps(
                    {
                        "schema": "agentcart.verifierReplay.v1",
                        "payments": {
                            "tempo_tx_legacy_001": {
                                **metadata,
                                "first_seen_at": "2026-07-01T10:00:00Z",
                                "last_seen_at": "2026-07-01T10:05:00Z",
                                "replay_count": 2,
                            }
                        },
                        "refund_requests": {},
                        "refunds": {},
                    }
                ),
                encoding="utf-8",
            )

            first = self.run_tool(
                "import-json",
                "--source",
                str(source),
                "--db",
                str(database),
            )
            second = self.run_tool(
                "import-json",
                "--source",
                str(source),
                "--db",
                str(database),
            )
            diagnostics = self.run_tool("diagnostics", "--db", str(database))
            same = self.run_tool(
                "claim",
                "--db",
                str(database),
                "--bucket",
                "payments",
                "--reference",
                "tempo_tx_legacy_001",
                "--metadata-json",
                json.dumps(metadata),
            )
            conflict = self.run_tool(
                "claim",
                "--db",
                str(database),
                "--bucket",
                "payments",
                "--reference",
                "tempo_tx_legacy_001",
                "--metadata-json",
                json.dumps({**metadata, "amount_cents": 1590}),
            )

        self.assertEqual(1, first["imported"])
        self.assertEqual(0, first["skipped"])
        self.assertEqual(0, second["imported"])
        self.assertEqual(1, second["skipped"])
        self.assertEqual({"payments": 1, "refund_requests": 0, "refunds": 0}, diagnostics["counts"])
        self.assertTrue(same["idempotentReplay"])
        self.assertEqual("conflict", conflict["status"])


if __name__ == "__main__":
    unittest.main()
