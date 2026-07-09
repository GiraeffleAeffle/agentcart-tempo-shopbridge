# plugin_zip_install_screenshot_or_log

- Scope: `pilot_gate`
- Owner id: `pilot-merchant-onboarding`
- Recorded at: 2026-07-09T20:24Z
- Operator: Codex deployment session authorized by Max (GiraeffleAeffle)
- Command or source: `deploy/hetzner-staging/ansible/usd-shop.yml` rollout transcript

## Evidence

The maintained Hetzner staging shop uses a deployment-managed read-only plugin
mount rather than an uploaded ZIP. Before mutation, the operator created a
root-only rollback archive. Ansible then copied the current ShopBridge source,
rendered the hardened Compose configuration, recreated WordPress, and ran the
seed command; the existing `agentcart-shopbridge` plugin remained activated.
The play recap reported 24 successful tasks, 11 changes, and zero failures.
The post-deployment capability document exposed the new verifier trust fields,
proving the updated plugin code was active. This covers the maintainer staging
installation only; the external merchant still needs a separate release-ZIP
installation log and non-maintainer walkthrough.
