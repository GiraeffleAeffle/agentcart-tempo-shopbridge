# privacy_notice

- Scope: `pilot_gate`
- Owner id: `pilot-safety-privacy`
- Recorded at: 2026-07-05 (DRAFT — review before sharing externally; this is not legal advice)
- Operator: drafted via Claude Code session for Max (GiraeffleAeffle)
- Command or source: `docs/PILOT_BETA_CHECKLIST.md` pilot-safety-privacy gate; repo non-negotiables in `CONTEXT.md`

## Evidence

### AgentCart ShopBridge Pilot Privacy Notice (draft)

**Who we are.** AgentCart ShopBridge is an open-source agent-commerce bridge
for WooCommerce, maintained by Max (GiraeffleAeffle). Contact:
`merchant@agentcart.eu`.

**Scope.** This notice covers the supervised external beta pilot on staging
shops only. Pilot shops process test orders with testnet payments; no real
customer traffic and no real money are involved.

**What we collect during the pilot:**

- Public merchant metadata the merchant chooses to publish: shop domain,
  manifest, exposed catalog entries, terms/returns/support URLs, registry
  record and revocation pointer.
- Test transaction evidence: quotes, approval hashes, testnet payment and
  refund references, order lifecycle states, smoke-test transcripts.
- Setup observation notes: timestamps, screenshots of admin screens, friction
  and help-log entries from the merchant setup walkthrough.

**What we do not collect or publish:**

- No real customer names, delivery addresses, or order histories (staging
  shops with test products only).
- No payment credentials, private keys, or bearer tokens in evidence files or
  ops notifications; ShopBridge diagnostics and ops events are redacted by
  design.
- The public registry stores merchant identity/integrity records only — never
  household demand, private shopping tasks, buyer addresses, or live catalog
  data.
- Merchant-provided prose (product text, policies, notes) is treated as
  untrusted display data by buyer agents and is never executed as
  instructions.

**Where pilot data lives.** Evidence artifacts are stored in the project
repository's pilot-evidence folder to support the beta release decision.
Staging server logs stay on the staging host.

**Your choices.** A pilot merchant can stop at any time: the registry record
can be revoked, the plugin can be deactivated without deleting WooCommerce
data, and the merchant can request removal of their evidence artifacts from
the repository.

### Operator sign-off

- Notice reviewed and adopted by: ______ (name, date)
