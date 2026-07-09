# previous_plugin_zip

- Scope: `pilot_gate`
- Owner id: `pilot-rollback`
- Recorded at: 2026-07-05
- Operator: Max (GiraeffleAeffle), recorded via Claude Code session
- Command or source: `gh release download v1.11.0 --pattern '*' --dir pilot-evidence/woo-usd-staging/attachments/rollback/v1.11.0`

## Evidence

Previous-release plugin ZIP staged locally for instant rollback from the
current pilot release v1.11.1:

- `attachments/rollback/v1.11.0/agentcart-shopbridge.zip`
  sha256 `6df6a26409aa2f8f54d68ec8377f55679199818ebc08d0e76f8dd1de07070dca`
- `attachments/rollback/v1.11.0/shopbridge-direct-skill.zip`
  sha256 `dbded3a067ea168692bfa548ab7a7dbeeb30650fb77ef9fd180091b71d1a2dfd`

ZIP binaries are gitignored (`*.zip`), so they live only in the local working
copy; they are re-obtainable at any time with the command above from the
GitHub release
https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/releases/tag/v1.11.0
and can be integrity-checked against the checksums in that release's
`agentcart-release.json` (see `release_manifest.md`).
