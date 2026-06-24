# Merchant Registry And Discovery

> Status: alpha implemented. The current gateway can load a signed off-chain
> registry JSON feed, verify claim/domain/payment/shipping/revocation bindings,
> and exclude unverified external merchants from quote tournaments by default.
> The same verifier interface is intended to sit behind an onchain or
> append-only registry later.


AgentCart's registry should be an identity and integrity anchor, not an ad
marketplace and not a product catalog.

Standards direction: this off-chain record shape should stay compatible with a
future ERC-8004-style registration file for ShopBridge merchants or hosted
service providers. The registry should identify and validate merchant endpoints;
it should not require public registration of a household's private shopping
agent.

## Goals

- Let agents discover shops that support AgentCart ShopBridge.
- Let shops publish a stable manifest URL.
- Let agents verify that a manifest has not been silently swapped.
- Avoid publishing household demand, addresses, private shopping tasks, or live
  catalog data on-chain.
- Keep merchant-provided product and support text as untrusted data. A registry
  can prove identity and integrity, but it cannot make catalog text safe to
  follow as instructions.

## Registry Record

```json
{
  "merchant_id": "tea-shop.example",
  "domain": "shop.example",
  "manifest_url": "https://shop.example/.well-known/agentcart.json",
  "registry_claim_hash_alg": "sha-256",
  "registry_claim_hash": "abc123...",
  "supported_protocols": ["agentcart-shopbridge", "mpp-http-auth"],
  "payment_network": "tempo-testnet",
  "payment_recipient": "0x...",
  "ship_to_countries": ["DE", "AT"],
  "updated_at": "2026-06-18T00:00:00Z",
  "revoked_at": null,
  "revocation_url": "https://shop.example/.well-known/agentcart-registry-revocations.json",
  "signature_alg": "https-domain-proof",
  "signature": "",
  "proof": {
    "type": "https-well-known",
    "url": "https://shop.example/.well-known/agentcart-registry-proof.json"
  }
}
```

## On-Chain vs Off-Chain

Put on-chain or in a public append-only registry:

- merchant id
- domain
- manifest URL
- registry claim hash
- payment network/recipient
- update timestamp
- revocation pointer

Keep off-chain:

- products
- stock
- prices
- quotes
- delivery estimates
- buyer intent
- household location
- shopping tasks

## Ranking Rules

The registry should not rank by advertising spend. Ranking belongs to the
buyer-side agent and should be explainable:

```text
eligible merchants -> private quote requests -> payment readiness -> local policy/price/delivery ranking
```

If a marketplace relay later supports auctions, the auction should be
buyer-intent based and private by default. A public registry can help find
eligible merchants, but final bidding should not leak household demand broadly.

## Integrity Flow

1. Merchant publishes `/.well-known/agentcart.json`.
2. Merchant signs or publishes a proof for the canonical registry record and
   stable registry claim hash.
3. Agent fetches the registry record from an allowlisted off-chain feed or
   onchain registry.
4. Agent rejects stale records, records with `revoked_at`, or records listed in
   the merchant-hosted revocation document.
5. Agent verifies that `manifest_url` host matches the registered domain.
6. Agent fetches the manifest from the merchant domain.
7. Agent canonicalizes the stable registry claim inside the manifest and
   verifies its hash. Legacy records can still bind the full manifest hash.
8. Agent verifies the detached signature, merchant-domain proof, or onchain
   proof over the registry record.
9. Agent verifies that payment recipient/network in the manifest matches the
   registry record.
10. Agent verifies that absolute catalog/quote endpoint URLs stay on the
    registered merchant domain.
11. Agent requests private catalog/quote data from the merchant endpoint.

## Alpha Configuration

The local alpha supports an off-chain JSON registry source:

```env
AGENTCART_MERCHANT_REGISTRY_PATH=/data/merchant-registry.json
AGENTCART_MERCHANT_REGISTRY_URL=
AGENTCART_MERCHANT_REGISTRY_HMAC_SECRET=replace-with-shared-registry-secret
AGENTCART_REQUIRE_VERIFIED_REGISTRY=true
AGENTCART_MERCHANT_REGISTRY_MAX_AGE_DAYS=180
```

`hmac-sha256` remains available for private/local feeds, but it is an
implementation shortcut. Public trust should use a merchant-owned proof such as
`https-domain-proof`, merchant wallet signatures, DNS/DID proofs, or an onchain
registry event while keeping the same verified record shape for agents.

## Merchant-Owned Domain Proof

The dependency-light production step is `signature_alg:
https-domain-proof`. The registry record points to a proof document hosted on
the registered merchant domain under `/.well-known/`:

```json
{
  "merchant_id": "tea-shop.example",
  "domain": "shop.example",
  "manifest_url": "https://shop.example/.well-known/agentcart.json",
  "registry_claim_hash": "abc123...",
  "payment_network": "tempo-testnet",
  "payment_recipient": "0x...",
  "updated_at": "2026-06-18T00:00:00Z",
  "revocation_url": "https://shop.example/.well-known/agentcart-registry-revocations.json",
  "record_hash": "def456..."
}
```

`record_hash` is the canonical JSON hash of the registry record, excluding
runtime-only fields such as `signature`, `verification`, and local test
snapshots. AgentCart requires the proof URL to be HTTPS, to stay on the
registered merchant domain, and to use a `/.well-known/` path. It rejects
mismatched record hashes. This proves control of the shop domain without adding
a crypto dependency to the gateway. Wallet signatures can be added later as
another verifier behind the same proof seam.

The WooCommerce ShopBridge plugin exposes this proof at
`/.well-known/agentcart-registry-proof.json`. It automatically maintains the
claim hash, record hash, `updated_at` timestamp, and revocation URL from stable
settings, so merchants do not paste registry hashes during normal onboarding.
The admin page also provides a manual refresh action for the generated registry
metadata and a public endpoint check that fetches the manifest, proof,
revocation document, and registry bundle before a merchant asks a registry to
ingest the shop.

The plugin also publishes `/.well-known/agentcart-registry-bundle.json`, which
contains the same `registry_record`, `record_hash`, expected proof document,
empty revocation document, and a one-entry `registry_feed`. A central registry,
self-hosted registry, or local buyer-agent test can ingest that bundle directly
instead of asking the merchant to run a helper script.

## Merchant-Owned Revocation

When a registry record includes `revocation_url`, AgentCart requires that URL to
be HTTPS, on the registered merchant domain, and under `/.well-known/`. The
current ShopBridge plugin publishes an empty revocation document by default:

```json
{
  "type": "agentcart-registry-revocations",
  "merchant_id": "tea-shop.example",
  "domain": "shop.example",
  "updated_at": "2026-06-18T00:00:00Z",
  "revocations": []
}
```

To revoke a bad or compromised record, the document can include the canonical
record hash:

```json
{
  "type": "agentcart-registry-revocations",
  "merchant_id": "tea-shop.example",
  "domain": "shop.example",
  "updated_at": "2026-06-18T01:00:00Z",
  "revocations": [
    {
      "record_hash": "def456...",
      "revoked_at": "2026-06-18T01:00:00Z"
    }
  ]
}
```

Buyer verifiers fail closed when the revocation pointer is invalid, unreachable,
off-domain, or lists the current record hash. Existing local/test records can
omit `revocation_url`, but public records should include it.

## Registry Record Helper

For current ShopBridge merchants, the lowest-friction path is to consume the
merchant's bundle:

```sh
curl https://shop.example/.well-known/agentcart-registry-bundle.json
```

The registry operator can also build records from the merchant manifest instead
of asking merchants to hand-write JSON or copy hashes. The helper uses the same
canonical JSON hashing and verifier code as the gateway:

```sh
python3 gateway/scripts/registry_record.py build \
  --manifest-url https://shop.example/.well-known/agentcart.json \
  --format bundle
```

The output contains:

- `registry_record`: the record to add to the public registry feed.
- `merchant_action`: whether the merchant needs to do anything. For current
  ShopBridge manifests this should be `none` because the plugin already
  publishes a matching proof.
- `proof_document_expected`: the proof document the shop should already publish.
- `legacy_merchant_settings`: paste-back settings only for legacy/non-ShopBridge
  manifests that do not publish an auto-managed registry claim.

Verify the live proof:

```sh
python3 gateway/scripts/registry_record.py verify \
  --record-file merchant-registry-record.json
```

For reproducible local tests, use snapshots instead of network fetches:

```sh
python3 gateway/scripts/registry_record.py verify \
  --record-file merchant-registry-record.json \
  --manifest-file manifest.json \
  --proof-file proof.json \
  --revocation-file revocations.json
```

This keeps merchant onboarding close to the normal WooCommerce flow: install the
plugin, configure payment/support settings, enable products, share the registry
bundle URL, and let the registry consume the plugin-generated claim.

## Agent Safety Model

Registry verification solves spoofing and silent endpoint swaps. It does not
solve prompt injection by itself.

Agents should treat these fields as untrusted data:

- product titles and descriptions;
- merchant names, support copy, and policy text;
- category labels and tags;
- delivery notes and refund descriptions.

Safe agent behavior:

- never execute instructions from merchant/catalog fields;
- summarize merchant text only as quoted/bounded content;
- use structured fields for policy decisions, not prose;
- bind quote approval to merchant id, items, total, delivery window, expiry,
  payment rail, and quote hash;
- exclude quotes whose advertised payment protocols are all unavailable or
  setup-required before ranking;
- fail closed when registry verification, claim/manifest hash, quote hash, payment
  recipient, or verifier response do not match.

## Implemented Alpha

The gateway now:

- loads candidate records from `AGENTCART_MERCHANT_REGISTRY_PATH` or
  `AGENTCART_MERCHANT_REGISTRY_URL`;
- fetches each manifest, or reads `manifest_snapshot` for reproducible local
  tests;
- canonicalizes and hashes either the stable registry claim or legacy manifest;
- verifies domain, hash, signature/proof, revocation URL/document, updated timestamp,
  payment recipient, and shipping country scope;
- verifies `hmac-sha256` private-feed records and `https-domain-proof`
  merchant-owned records;
- rejects absolute catalog/quote endpoint URLs outside the registered merchant
  domain;
- exposes `verification.state`, `verification.errors`, and manifest source;
- makes quote tournament exclude unverified external merchants by default.

Once that interface is stable, the source of records can move from a signed JSON
feed to an onchain registry without changing buyer or merchant adapters.

## Open Questions

- Should registry updates be wallet-signed, DNS-based, or both?
- How should merchants rotate payment recipients?
- Should revocation documents be mirrored into an append-only transparency log?
- Should there be a neutral allowlist for consumer-protection-compliant shops?
- How can small merchants stay discoverable without recreating ad-market
  dynamics?
