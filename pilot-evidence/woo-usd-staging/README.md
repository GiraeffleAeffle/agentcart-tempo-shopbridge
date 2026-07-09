# Pilot Evidence: woo-usd-staging (beta pilot, staging merchant #1)

Evidence folder for the supervised external beta decision
([issue #21](https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/21)),
anchored on the maintainer-run staging merchant
`agentcart-usd-staging-shop` (`https://woo-usd.agentcart.eu`, plugin v1.11.1,
Tempo pathUSD **testnet** payment mode).

The planned second merchant is an external (non-maintainer) WooCommerce shop;
its onboarding evidence — including the required non-maintainer setup
walkthrough — gets recorded when that pilot session happens. Send
`docs/PILOT_MERCHANT_BRIEF.md` to the merchant first.

Generated initially with
`python3 scripts/collect-pilot-evidence.py --write-sample pilot-evidence/woo-usd-staging`
on 2026-07-05. Files still containing `TODO` are unfilled samples and are not
evidence (see `docs/PILOT_EXECUTION_PLAYBOOK.md` replacement rules).

## Status ledger (2026-07-05)

Real evidence recorded:

- `pilot/pilot-merchant-onboarding/live_woocommerce_smoke_result.md` —
  settlement rehearsal passed (exit 0, production-ready + real-refund
  assertions); transcript in `attachments/`.
- `pilot/pilot-merchant-onboarding/registry_record_or_bundle_url.md` — bundle,
  revocation, and manifest URLs verified live.
- `pilot/pilot-payment-mode/sample_payment_contract_hash.md` — hash-linked
  sample from the rehearsal.
- `pilot/pilot-rollback/*` — previous ZIP + manifests staged with checksums;
  revocation URL verified. One open sub-item: execute a rollback/revocation
  rehearsal once and append the transcript.

Drafts needing operator sign-off (marked DRAFT in the file):

- `pilot/pilot-payment-mode/payment_mode_decision_record.md`
- `pilot/pilot-payment-mode/refund_policy_statement.md`
- `pilot/pilot-support-channel/*` (confirm the monitored mailbox!)
- `pilot/pilot-safety-privacy/privacy_notice.md`

Still TODO (require running the actual pilot / ops work):

- Remaining `pilot/pilot-merchant-onboarding/*` items: install log, settings
  readiness snapshot, catalog preview, sandbox quote/checkout results,
  compatibility + variance profile results, and the **non-maintainer setup
  walkthrough notes** (external merchant session).
- `pilot/pilot-buyer-agent-setup/*` and all `buyer-agents/*` runtime evidence
  (service, direct skill, generic MCP client).
- `pilot/pilot-payment-mode/` ops pack: verifier health, metrics snapshot,
  SQLite replay backup/restore drill, alert delivery result, provider error
  review, production payment profile check.
- `pilot/pilot-safety-privacy/`: ops event redaction sample, rate-limit smoke,
  prompt-injection corpus result + review notes.

## Report command

```sh
python3 scripts/collect-pilot-evidence.py \
  --pilot-evidence-dir pilot-evidence/woo-usd-staging/pilot \
  --buyer-agent-evidence-dir pilot-evidence/woo-usd-staging/buyer-agents \
  --payment-env-file <production-shaped payment env file> \
  --report-out pilot-evidence-report.json
```

## Status update (2026-07-09)

The hardened Hetzner USD deployment, real Tempo MPP testnet settlement/refund,
SQLite migration and backup drill, live rate-limit probe, two merchant-variance
smokes, payment profile, verifier health/metrics, redaction test, and
prompt-injection review are now recorded. The evidence gate counts 28 of 39
pilot files as valid; production-payment-profile and WooCommerce-compatibility
gates pass.

The release decision remains blocked. Eleven pilot files still require external
or operational action: the non-maintainer setup walkthrough, the buyer-runtime
sessions and shared approval/audit artifacts, an alert-webhook delivery, a
confirmed support contact/SLA/incident owner, and adoption of the privacy
notice. All 24 per-runtime buyer-agent evidence files also remain invalid until
the three runtime sessions are actually executed. The generated
`pilot-evidence-report.json` records these blockers without treating templates
as evidence.
