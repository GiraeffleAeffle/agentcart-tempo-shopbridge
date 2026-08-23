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
  --payment-profile talos-usd-staging \
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

## Status update (2026-08-23)

The production-shaped USD workload now runs in the Talos cluster from the
pinned GHCR digest. A new 1,578-cent Tempo testnet payment, live verifier-backed
refund, conflicting replay rejection, online SQLite backup, and pod-restart
persistence drill are recorded in
`attachments/talos-usd-verifier-live-drill-2026-08-23.md`. The alert webhook is
still unconfigured, so the alert-delivery evidence remains deliberately TODO.

The USD merchant also completed the Tempo Moderato register, revoke, and
recovery lifecycle. The packaged Direct Skill enforced each finalized state,
and dRPC plus Tenderly independently reproduced the hosted event history. The
redacted record is
`attachments/tempo-registry-lifecycle-2026-08-23.md`.

These results close the maintainer-run technical baseline; they do not replace
the non-maintainer buyer-agent run, external merchant walkthrough, support/SLA
sign-off, privacy-notice adoption, or independent security/governance review.
The evidence collector must continue to report those items as blockers.
