#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:?usage: scripts/prepare-semantic-release.sh <version> [source-commit]}"
SOURCE_COMMIT="${2:-$(git -C "$ROOT_DIR" rev-parse HEAD)}"

cd "$ROOT_DIR"

python3 scripts/stamp-release-version.py "$VERSION"
scripts/package-woocommerce-plugin.sh
scripts/package-shopbridge-direct-skill.sh

if [ -n "${AGENTCART_RELEASE_SIGNING_KEY:-}" ]; then
  AGENTCART_RELEASE_SOURCE_COMMIT="$SOURCE_COMMIT" \
    python3 scripts/build-release-manifest.py \
      --signature-out dist/agentcart-release.sig
  python3 scripts/verify-release.py \
    --manifest dist/agentcart-release.json \
    --root "$ROOT_DIR" \
    --expected-source-commit "$SOURCE_COMMIT" \
    --signature dist/agentcart-release.sig \
    --trusted-signature-key-id "${AGENTCART_RELEASE_SIGNING_KEY_ID:-}" \
    --require-signature >/dev/null
else
  AGENTCART_RELEASE_SOURCE_COMMIT="$SOURCE_COMMIT" \
    python3 scripts/build-release-manifest.py
  python3 scripts/verify-release.py \
    --manifest dist/agentcart-release.json \
    --root "$ROOT_DIR" \
    --expected-source-commit "$SOURCE_COMMIT" >/dev/null
fi
