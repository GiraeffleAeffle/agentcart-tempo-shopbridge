# rollback_command_or_runbook

- Scope: `pilot_gate`
- Owner id: `pilot-rollback`
- Recorded at: 2026-07-05
- Operator: Max (GiraeffleAeffle), recorded via Claude Code session
- Command or source: `docs/MERCHANT_ROLLBACK_RUNBOOK.md`

## Evidence

The pilot uses the checked-in runbook `docs/MERCHANT_ROLLBACK_RUNBOOK.md` as
the incident procedure. Concrete rollback paths staged for this pilot:

1. **Plugin rollback on a pilot shop**: deactivate `AgentCart ShopBridge` in
   WordPress admin (orders, audit hashes, and WooCommerce data are preserved),
   then `Plugins -> Add New -> Upload Plugin` with
   `attachments/rollback/v1.11.0/agentcart-shopbridge.zip` (checksum in
   `previous_plugin_zip.md`).
2. **Remove a pilot merchant from discovery**: revoke the registry record from
   the merchant admin Registry Proof section, or publish the revocation in
   `/.well-known/agentcart-registry-revocations.json` (URL evidence in
   `registry_revocation_url.md`); buyer paths verify revocation documents.
3. **Disable public checkout immediately**: switch the shop out of public
   checkout in the AgentCart admin (mitigation named in
   `pilot/pilot-support-channel/incident_owner.md`).
4. **Gateway/staging rollback**: redeploy the previous release artifacts per
   `docs/RELEASES.md`; staging stacks are recreated by the Ansible playbooks
   under `deploy/hetzner-staging/`.

Open item for the pilot window: run one rehearsal of step 1 or 2 on the
staging shop and append the transcript/screenshot here, so the runbook has
executed — not just written — evidence.
