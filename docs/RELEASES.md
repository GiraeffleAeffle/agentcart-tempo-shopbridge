# Releases

> Status: alpha release process. The artifacts are installable ZIPs plus a
> machine-readable manifest. The repo supports optional detached manifest
> signatures for private/self-hosted release channels.

## Artifacts

The release pipeline produces and uploads these files to a GitHub Release:

```text
dist/agentcart-shopbridge.zip
dist/shopbridge-direct-skill.zip
dist/agentcart-release.json
dist/agentcart-release.sig   # optional, only when signing a release
```

`semantic-release` is the public release driver for this repo. It reads
conventional commits on `main`, calculates the next version, stamps that version
into the shipped surfaces, runs the package builders, creates the release
manifest, and publishes the ZIPs plus manifest as GitHub Release assets.

Version stamping updates the release workspace before packaging:

- `gateway/package.json` and `gateway/package-lock.json`;
- WooCommerce plugin `Version:` header;
- WordPress plugin `readme.txt` `Stable tag`;
- direct skill `version:` frontmatter.

The generated ZIPs and manifest stay out of git. Git tags and GitHub Release
assets are the distribution channel.

## Automated GitHub Releases

The release workflow is `.github/workflows/release.yml`.

It runs on pushes to `main` and manual dispatch. The job:

1. installs root semantic-release tooling, gateway Node dependencies, and
   WordPress coding standards tooling;
2. runs `scripts/verify.sh` with strict WordPress official gates;
3. runs `npm run release`;
4. lets semantic-release create the Git tag, release notes, and GitHub Release
   assets.

Use conventional commits to control releases:

```text
fix: patch release
feat: minor release
feat!: major release
```

You can also add a `BREAKING CHANGE:` footer for a major release.

Local config check:

```sh
npm ci
npm run release:config-check
```

Semantic-release dry runs still verify GitHub push permission for tag creation,
so they need a token or CI credentials:

```sh
GITHUB_TOKEN=... npm run release:dry-run
```

Dry runs do not publish assets. To exercise the artifact preparation locally
without GitHub credentials, pass an explicit version and source commit:

```sh
scripts/prepare-semantic-release.sh 0.3.0 "$(git rev-parse HEAD)"
```

That command modifies versioned source files in the working tree. Use it in a
throwaway branch or reset the changes afterward unless you intend to inspect
the exact release workspace.

The WooCommerce ZIP includes the plugin entrypoint, WordPress `readme.txt`, and
`uninstall.php`. Uninstall removes ShopBridge settings and ephemeral state, but
preserves WooCommerce orders, refunds, cancellation history, payment
verification metadata, and product-level AgentCart metadata for auditability.

`agentcart-release.json` records:

- gateway release version from `gateway/package.json`;
- WooCommerce plugin version from the plugin header;
- direct skill version from `gateway/shopbridge-direct-skill/SKILL.md`;
- artifact file names, byte sizes, and SHA-256 checksums;
- the source git commit used to build the artifacts when
  `AGENTCART_RELEASE_SOURCE_COMMIT` is supplied.

Build everything:

```sh
./scripts/package-woocommerce-plugin.sh
./scripts/package-shopbridge-direct-skill.sh
python3 scripts/build-release-manifest.py
```

To embed a source commit in a published release manifest:

```sh
AGENTCART_RELEASE_SOURCE_COMMIT="$(git rev-parse HEAD)" python3 scripts/build-release-manifest.py
```

## Sign A Release

For a private/self-hosted release channel, create a detached manifest signature
with a secret release signing key:

```sh
export AGENTCART_RELEASE_SIGNING_KEY="replace-with-random-release-channel-key"
export AGENTCART_RELEASE_SIGNING_KEY_ID="home-release-2026-q2"
python3 scripts/build-release-manifest.py --signature-out dist/agentcart-release.sig
```

The signature sidecar signs the SHA-256 of `dist/agentcart-release.json`. It
does not hide artifact contents or secrets; it lets a buyer/merchant host verify
that the manifest came from the expected private release channel before trusting
the artifact checksums. Rotate the signing key if it is exposed.

Or run the full gate:

```sh
./scripts/verify.sh
```

`verify.sh` is the development/release-artifact gate. It validates the checked-in
pilot schemas and the checked-in production-payment env overlay shape, but it
does not claim that an external beta has recorded evidence unless you explicitly
enable the beta gate:

```sh
AGENTCART_BETA_RELEASE_GATE=1 \
AGENTCART_PILOT_EVIDENCE_DIR=pilot-evidence/example-shop/pilot \
AGENTCART_BUYER_AGENT_EVIDENCE_DIR=pilot-evidence/example-shop/buyer-agents \
AGENTCART_PAYMENT_ENV_FILE=deploy/home-server/.env \
AGENTCART_PILOT_EVIDENCE_REPORT_OUT=pilot-evidence-report.json \
./scripts/verify.sh
```

Set `AGENTCART_WOO_COMPATIBILITY_SMOKE=1` to include the Docker-backed
WooCommerce compatibility smoke in that release evidence report. Use
`AGENTCART_WOO_COMPATIBILITY_ENTRY=<matrix-id>` to run one matrix entry.

For a running WooCommerce merchant, add the live smoke target. Production-ready
mode fails if the ShopBridge setup guide still has production-required blockers:

```sh
AGENTCART_WOO_SMOKE_BASE_URL=https://shop.example.com \
AGENTCART_WOO_SMOKE_REQUIRE_SHIPPING=1 \
AGENTCART_WOO_SMOKE_REQUIRE_VAT_LINES=1 \
AGENTCART_WOO_SMOKE_REQUIRE_PRODUCTION_READY=1 \
./scripts/verify.sh
```

You can also run the stricter gate directly:

```sh
python3 scripts/collect-pilot-evidence.py \
  --pilot-evidence-dir pilot-evidence/example-shop/pilot \
  --buyer-agent-evidence-dir pilot-evidence/example-shop/buyer-agents \
  --payment-env-file deploy/home-server/.env \
  --report-out pilot-evidence-report.json
```

Start a new evidence folder with:

```sh
python3 scripts/collect-pilot-evidence.py --write-sample pilot-evidence/example-shop
```

The full gate includes a Python 3.11 compile check for runtime files. If local
`python3.11` is unavailable, it uses Docker `python:3.11-slim` when Docker is
available. The gateway Docker smoke image also uses Python 3.11. This protects
the homelab/systemd deployment path from syntax that a newer local Python
accepts but the deployed runtime rejects.

## Verify Artifacts

Inspect the manifest:

```sh
cat dist/agentcart-release.json
```

Verify a checksum manually:

```sh
shasum -a 256 dist/agentcart-shopbridge.zip
shasum -a 256 dist/shopbridge-direct-skill.zip
```

The checksums should match the corresponding `sha256` values in
`dist/agentcart-release.json`.

Or verify the full manifest and all listed artifacts:

```sh
python3 scripts/verify-release.py
```

Verify a signed release:

```sh
AGENTCART_RELEASE_SIGNING_KEY="replace-with-release-channel-key" \
python3 scripts/verify-release.py \
  --signature dist/agentcart-release.sig \
  --trusted-signature-key-id home-release-2026-q2 \
  --require-signature
```

If you received the manifest checksum over a trusted channel, pin it:

```sh
python3 scripts/verify-release.py \
  --expected-manifest-sha256 "replace-with-trusted-manifest-sha256"
```

If a published release embeds `source_git_commit`, pin that too:

```sh
python3 scripts/verify-release.py \
  --expected-source-commit "replace-with-trusted-source-commit"
```

## Upgrade

WooCommerce plugin:

1. Download or build `dist/agentcart-shopbridge.zip`.
2. Back up current WordPress/WooCommerce settings.
3. In WordPress, open `Plugins -> Add New -> Upload Plugin`.
4. Upload the ZIP and replace the existing plugin when prompted.
5. Open `WooCommerce -> AgentCart` and confirm readiness checks.
6. Smoke test `/.well-known/agentcart.json` and `/wp-json/agentcart/v1/catalog`.

Direct buyer skill:

1. Download or build `dist/shopbridge-direct-skill.zip`.
2. Back up the installed `shopbridge-direct-skill` folder.
3. Replace the installed skill folder or reinstall the ZIP in the buyer agent.
4. Run a read-only readiness command against a known ShopBridge merchant.

AgentCart service:

1. Pull the target git commit.
2. Review `.env` changes before restarting.
3. Run `./scripts/verify.sh` on the host when possible.
4. Restart the home-server compose stack.

## Rollback

Keep the previous release ZIPs and release manifest before upgrading. For a
merchant or pilot incident, follow `docs/MERCHANT_ROLLBACK_RUNBOOK.md`; this
section is the artifact-level quick reference.

Rollback WooCommerce:

1. Disable AgentCart checkout exposure if orders are failing.
2. Reinstall the previous `agentcart-shopbridge.zip`.
3. Confirm settings in `WooCommerce -> AgentCart`.
4. Re-test manifest, catalog, quote, and a non-production checkout path.

Rollback direct skill:

1. Replace the installed skill folder with the previous copy.
2. Re-run `readiness`, `catalog`, and `quote` commands.
3. Do not retry checkout from a new skill version against an old approval packet;
   create a fresh approval packet because quote/payment destinations are bound.

## Signing Limits

The current signature format is `hmac-sha256`, intended for private release
channels where the verifier already has the release-channel key through a
separate trusted path. Public distribution should eventually use asymmetric
signatures or a standard signed update channel so verifiers do not need the
publisher's signing secret.

Use the signature, manifest checksums, optional manifest checksum pin, optional
source commit pin, and a trusted distribution path together. Checksums detect
accidental or local tampering; the detached signature proves the manifest came
from whoever controls the configured release-channel key.
