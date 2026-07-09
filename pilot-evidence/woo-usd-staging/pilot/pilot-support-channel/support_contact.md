# support_contact

- Scope: `pilot_gate`
- Owner id: `pilot-support-channel`
- Recorded at: 2026-07-05 (DRAFT — pending operator confirmation)
- Operator: drafted via Claude Code session for Max (GiraeffleAeffle)
- Command or source: staging manifest `merchant_of_record.support_email`; repo issue tracker

## Evidence

Decision (2026-07-07): no dedicated support mailbox is stood up for the pilot.
A monitored channel is what the gate requires, not a new inbox. For a
supervised beta the operator's existing channels are sufficient.

Pilot support channels:

- Primary: the operator's own monitored email — `______` (Max to fill with the
  address he actually reads day-to-day; personal is fine for a supervised
  pilot).
- Secondary (technical, public):
  https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues
- During scheduled pilot sessions: direct chat/call channel agreed with the
  merchant (record the concrete channel here once chosen).

Note: this is the *pilot operator* channel (merchant → Max). It is separate
from the merchant's own buyer-facing support email on their shop, which the
external merchant owns and must keep working as their merchant-of-record
contact.

What testers should send: see
`pilot/pilot-support-channel/diagnostic_collection_steps.md`.

### Operator sign-off

- Channel confirmed monitored by: ______ (name, date)
