# incident_owner

- Scope: `pilot_gate`
- Owner id: `pilot-support-channel`
- Recorded at: 2026-07-05 (DRAFT — pending operator confirmation)
- Operator: drafted via Claude Code session for Max (GiraeffleAeffle)
- Command or source: `docs/PILOT_BETA_CHECKLIST.md` pilot-support-channel gate

## Evidence

- Incident owner for the pilot window: **Max (GiraeffleAeffle)** — sole
  maintainer; owns triage, mitigation, and the follow-up issues.
- Mitigation authority: the incident owner can immediately
  - disable public checkout on a pilot shop,
  - revoke the shop's registry record (merchant admin action or revocation
    document),
  - roll back the plugin or gateway release per
    `docs/MERCHANT_ROLLBACK_RUNBOOK.md` — WooCommerce orders and audit
    evidence are preserved through deactivation/rollback.
- The merchant can independently deactivate the plugin and revoke their
  registry record at any time without maintainer involvement.

### Operator sign-off

- Confirmed by: ______ (name, date)
