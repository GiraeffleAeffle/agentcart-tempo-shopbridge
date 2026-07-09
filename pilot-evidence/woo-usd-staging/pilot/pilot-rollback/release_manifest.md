# release_manifest

- Scope: `pilot_gate`
- Owner id: `pilot-rollback`
- Recorded at: 2026-07-05
- Operator: Max (GiraeffleAeffle), recorded via Claude Code session
- Command or source: `gh release download v1.11.1 --pattern '*'` and `shasum -a 256`

## Evidence

Release manifests with artifact checksums staged for both the pilot release
and the rollback target:

- Current pilot release **v1.11.1** (published 2026-07-03):
  `attachments/rollback/v1.11.1/agentcart-release.json`
  sha256 `07bda405f7de87f8fa1f8f06832497a1154a670d18901259fcd045fd78a8c5fc`
  - plugin ZIP sha256
    `3eaea200f428b38e5462a116c75923027d9fd0d449c3d7a285b84a505c25c04b`
  - direct-skill ZIP sha256
    `0a601825ec44a2107b6d668ab564af8c9d5eec430e6aaf098e5c5c01a1cb6da2`
- Rollback target **v1.11.0**:
  `attachments/rollback/v1.11.0/agentcart-release.json`
  sha256 `ede801d7ee09ea6836b4488e0f2ab233f32a6a7cd6f8e45e20b9a79c247ccc85`

Source: https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/releases
