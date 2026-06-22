# Releases

> Status: alpha release process. The artifacts are installable ZIPs plus a
> machine-readable manifest, but releases are not signed yet.

## Artifacts

The release pipeline produces:

```text
dist/agentcart-shopbridge.zip
dist/shopbridge-direct-skill.zip
dist/agentcart-release.json
```

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

Or run the full gate:

```sh
./scripts/verify.sh
```

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

Keep the previous release ZIPs and release manifest before upgrading.

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

## Signing Gap

Production still needs signed release artifacts or a trusted update channel.
Until then, use the manifest checksums, git commit, and a trusted distribution
path together.
