# Merchant Registry And Discovery

> Status: alpha implemented. The current gateway can load a signed off-chain
> registry JSON feed, verify manifest hash/domain/payment/shipping bindings,
> and exclude unverified external merchants from quote tournaments by default.
> The same verifier interface is intended to sit behind an onchain or
> append-only registry later.


AgentCart's registry should be an identity and integrity anchor, not an ad
marketplace and not a product catalog.

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
  "manifest_hash_alg": "sha-256",
  "manifest_hash": "abc123...",
  "supported_protocols": ["agentcart-shopbridge", "mpp-http-auth"],
  "payment_network": "tempo-testnet",
  "payment_recipient": "0x...",
  "ship_to_countries": ["DE", "AT"],
  "updated_at": "2026-06-18T00:00:00Z",
  "revoked_at": null,
  "revocation_url": "https://shop.example/.well-known/agentcart-revocations.json",
  "signature_alg": "hmac-sha256",
  "signature": "hmac-sha256:...",
  "proof": {
    "type": "onchain_registry_record",
    "chain_id": "tempo-testnet",
    "contract": "0x...",
    "record_id": "tea-shop.example"
  }
}
```

## On-Chain vs Off-Chain

Put on-chain or in a public append-only registry:

- merchant id
- domain
- manifest URL
- manifest hash
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
eligible merchants -> private quote requests -> local policy/price/delivery ranking
```

If a marketplace relay later supports auctions, the auction should be
buyer-intent based and private by default. A public registry can help find
eligible merchants, but final bidding should not leak household demand broadly.

## Integrity Flow

1. Merchant publishes `/.well-known/agentcart.json`.
2. Merchant signs or registers the canonical manifest hash.
3. Agent fetches the registry record from an allowlisted off-chain feed or
   onchain registry.
4. Agent rejects revoked or stale records.
5. Agent verifies that `manifest_url` host matches the registered domain.
6. Agent fetches the manifest from the merchant domain.
7. Agent canonicalizes the manifest JSON and verifies its hash.
8. Agent verifies the detached signature or onchain proof over the registry
   record.
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

`hmac-sha256` is an implementation shortcut for the alpha feed, not the desired
public trust model. Production should replace it with merchant wallet
signatures, DNS/DID proofs, or an onchain registry event while keeping the same
verified record shape for agents.

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
- fail closed when registry verification, manifest hash, quote hash, payment
  recipient, or verifier response do not match.

## Implemented Alpha

The gateway now:

- loads candidate records from `AGENTCART_MERCHANT_REGISTRY_PATH` or
  `AGENTCART_MERCHANT_REGISTRY_URL`;
- fetches each manifest, or reads `manifest_snapshot` for reproducible local
  tests;
- canonicalizes and hashes the manifest;
- verifies domain, hash, signature/proof, revocation, updated timestamp,
  payment recipient, and shipping country scope;
- rejects absolute catalog/quote endpoint URLs outside the registered merchant
  domain;
- exposes `verification.state`, `verification.errors`, and manifest source;
- makes quote tournament exclude unverified external merchants by default.

Once that interface is stable, the source of records can move from a signed JSON
feed to an onchain registry without changing buyer or merchant adapters.

## Open Questions

- Should registry updates be wallet-signed, DNS-based, or both?
- How should merchants rotate payment recipients?
- How should compromised manifests be revoked?
- Should there be a neutral allowlist for consumer-protection-compliant shops?
- How can small merchants stay discoverable without recreating ad-market
  dynamics?
