# Pilot Evidence Folder Example

This folder documents the expected evidence layout for an external beta release
decision. Do not attach this README as evidence by itself. Generate a working
template with:

```sh
python3 scripts/collect-pilot-evidence.py --write-sample pilot-evidence/example-shop
```

Then replace every generated `TODO` with real transcripts, command output,
screenshot references, hashes, URLs, or decision records.
The operator workflow and replacement rules live in
`docs/PILOT_EXECUTION_PLAYBOOK.md`.

## Release Decision Command

```sh
python3 scripts/collect-pilot-evidence.py \
  --pilot-evidence-dir pilot-evidence/example-shop/pilot \
  --buyer-agent-evidence-dir pilot-evidence/example-shop/buyer-agents \
  --payment-env-file deploy/home-server/.env \
  --report-out pilot-evidence-report.json
```

Attach `pilot-evidence-report.json` to the release decision. It contains the
gate ids, missing evidence paths, WooCommerce compatibility result, payment
profile result, and pass/fail summary.

## Pilot Evidence Paths

Pilot checklist evidence lives under:

```text
pilot/<gate-id>/<evidence-id>.md
```

Important examples:

```text
pilot/pilot-merchant-onboarding/plugin_zip_install_screenshot_or_log.md
pilot/pilot-merchant-onboarding/live_woocommerce_smoke_result.md
pilot/pilot-merchant-onboarding/woocommerce_compatibility_matrix_result.md
pilot/pilot-buyer-agent-setup/buyer_agent_test_matrix_result.md
pilot/pilot-payment-mode/production_payment_profile_check_result.md
pilot/pilot-payment-mode/verifier_metrics_snapshot.md
pilot/pilot-payment-mode/sqlite_replay_backup_restore_drill.md
pilot/pilot-payment-mode/verifier_alert_delivery_result.md
pilot/pilot-payment-mode/provider_error_review.md
pilot/pilot-safety-privacy/prompt_injection_corpus_result.md
```

## Buyer-Agent Evidence Paths

Buyer-agent runtime evidence lives under:

```text
buyer-agents/<runtime-id>/<evidence-id>.md
```

Expected transcript files:

```text
buyer-agents/agentcart-service-openclaw/merchant_discovery_transcript.md
buyer-agents/agentcart-service-openclaw/quote_comparison_transcript.md
buyer-agents/shopbridge-direct-skill/merchant_discovery_transcript.md
buyer-agents/shopbridge-direct-skill/quote_comparison_transcript.md
buyer-agents/generic-mcp-client/merchant_discovery_transcript.md
buyer-agents/generic-mcp-client/quote_creation_transcript.md
```

The runner also expects each runtime's setup, health, approval, checkout,
aftercare, and audit evidence files from
`gateway/config/buyer_agent_test_matrix.json`.
