# response_sla

- Scope: `pilot_gate`
- Owner id: `pilot-support-channel`
- Recorded at: 2026-07-05 (DRAFT — pending operator confirmation)
- Operator: drafted via Claude Code session for Max (GiraeffleAeffle)
- Command or source: `docs/PILOT_BETA_CHECKLIST.md` pilot-support-channel gate

## Evidence

Response targets for the pilot window (single-maintainer project — targets,
not a contractual SLA):

- **P0** (unsafe payment/product/privacy state, or a pilot shop serving wrong
  totals): acknowledge same day; immediate mitigation is to disable public
  checkout or revoke the registry record per
  `docs/MERCHANT_ROLLBACK_RUNBOOK.md`, then diagnose.
- **P1** (setup blocked, endpoint down, smoke failing): acknowledge within 1
  business day.
- **P2** (confusing docs/UI, cosmetic issues): acknowledge within 3 business
  days; collected into follow-up issues.

Coverage: weekdays (Europe/Berlin); best effort on weekends. Scheduled pilot
sessions are supervised live, so in-session issues are handled immediately.

### Operator sign-off

- Targets confirmed by: ______ (name, date)
