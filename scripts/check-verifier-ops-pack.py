#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "VERIFIER_OPERATIONS_READINESS.md"
SOURCE_PATH = ROOT / "gateway" / "scripts" / "stripe-mpp-verifier.mjs"
SQLITE_SOURCE_PATH = ROOT / "gateway" / "scripts" / "verifier-sqlite-replay-store.mjs"
PILOT_CHECKLIST_PATH = ROOT / "gateway" / "config" / "pilot_beta_checklist.json"
ENV_OVERLAY_PATH = ROOT / "deploy" / "home-server" / ".env.production-payment.example"
ADR_PATH = ROOT / "docs" / "adr" / "0006-sqlite-verifier-replay-store-for-pilot.md"
PILOT_DOC_PATH = ROOT / "docs" / "PILOT_BETA_CHECKLIST.md"

EXPECTED_PILOT_EVIDENCE = {
    "verifier_health_or_fixture_result",
    "verifier_metrics_snapshot",
    "sqlite_replay_backup_restore_drill",
    "verifier_alert_delivery_result",
    "provider_error_review",
}

DOC_TOKENS = {
    "/health",
    "/metrics",
    "agentcart.verifierMetrics.v1",
    "agentcart.verifierEvent.v1",
    "agentcart.verifier_alert_notification.v1",
    "agentcart.verifierReplay.sqlite.v1",
    "replay_store_driver",
    "replay_store_writable",
    "replay_store_error",
    "rejections.replay_conflict",
    "provider_errors",
    "AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite",
    "AGENTCART_VERIFIER_REPLAY_STORE_PATH=/data/verifier/replay-store.sqlite",
    "AGENTCART_VERIFIER_REPLAY_JOURNAL_PATH=/data/verifier/replay-journal.jsonl",
    "AGENTCART_VERIFIER_ALERT_WEBHOOK_URL",
    "AGENTCART_VERIFIER_ALERT_MIN_SEVERITY",
    "AGENTCART_VERIFIER_ALERT_THROTTLE_SECONDS",
    "sqlite3 /data/verifier/replay-store.sqlite",
    "node gateway/scripts/verifier-sqlite-replay-store.mjs diagnostics",
    *{f"{evidence_id}.md" for evidence_id in EXPECTED_PILOT_EVIDENCE},
}

SOURCE_TOKENS = {
    'url.pathname === "/" || url.pathname === "/health"',
    'url.pathname === "/metrics" || url.pathname === "/metrics.json"',
    'schema: "agentcart.verifierMetrics.v1"',
    'schema: "agentcart.verifierEvent.v1"',
    'schema: "agentcart.verifier_alert_notification.v1"',
    "provider_errors",
    "replay_conflict",
    "replay_store",
    "replay_journal",
    "alerts",
}

SQLITE_SOURCE_TOKENS = {
    'schema: "agentcart.verifierReplay.sqlite.v1"',
    "sqliteReplayStoreDiagnostics",
    "sqliteReplayStoreWriteProbe",
}

ENV_TOKENS = {
    "AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite",
    "AGENTCART_VERIFIER_REPLAY_STORE_PATH=/data/verifier/replay-store.sqlite",
    "AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true",
    "AGENTCART_VERIFIER_REPLAY_JOURNAL_PATH=/data/verifier/replay-journal.jsonl",
}

ADR_TOKENS = {
    "/health",
    "/metrics",
    "provider error class counts",
    "alert delivery state",
    "back up the SQLite database and replay journal together",
}


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def require_tokens(label: str, haystack: str, tokens: set[str], errors: list[str]) -> None:
    for token in sorted(tokens):
        if token not in haystack:
            errors.append(f"{label} missing required reference: {token}")


def pilot_payment_evidence() -> set[str]:
    checklist = json.loads(PILOT_CHECKLIST_PATH.read_text(encoding="utf-8"))
    for gate in checklist.get("gates", []):
        if isinstance(gate, dict) and gate.get("id") == "pilot-payment-mode":
            evidence = gate.get("required_evidence")
            if isinstance(evidence, list):
                return {str(item) for item in evidence}
    return set()


def validate() -> list[str]:
    errors: list[str] = []
    doc = read(DOC_PATH)
    source = read(SOURCE_PATH)
    sqlite_source = read(SQLITE_SOURCE_PATH)
    env_overlay = read(ENV_OVERLAY_PATH)
    adr = read(ADR_PATH)
    pilot_doc = read(PILOT_DOC_PATH)

    require_tokens("verifier operations runbook", doc, DOC_TOKENS, errors)
    require_tokens("stripe verifier source", source, SOURCE_TOKENS, errors)
    require_tokens("sqlite replay store source", sqlite_source, SQLITE_SOURCE_TOKENS, errors)
    require_tokens("production payment env overlay", env_overlay, ENV_TOKENS, errors)
    require_tokens("sqlite replay-store ADR", adr, ADR_TOKENS, errors)
    require_tokens(
        "pilot checklist docs",
        pilot_doc,
        {
            "verifier metrics snapshot",
            "SQLite replay backup/restore drill",
            "verifier alert delivery result",
            "provider error review",
        },
        errors,
    )

    missing_evidence = EXPECTED_PILOT_EVIDENCE - pilot_payment_evidence()
    if missing_evidence:
        errors.append(
            "pilot-payment-mode required_evidence missing verifier ops files: "
            + ", ".join(sorted(missing_evidence))
        )

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"verifier ops pack check failed: {error}", file=sys.stderr)
        return 1
    print("verifier ops pack ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
