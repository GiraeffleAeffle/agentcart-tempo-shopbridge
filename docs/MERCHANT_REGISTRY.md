# Merchant Registry And Discovery

> Status: architecture plan. The current repo exposes a demo registry document;
> production work should first implement the off-chain verifier described here,
> then swap the registry source to an onchain contract or append-only registry.


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
  "signature_alg": "eip-191-or-ed25519",
  "signature": "merchant-domain-or-wallet-signature",
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
10. Agent requests private catalog/quote data from the merchant endpoint.

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

## Suggested Alpha

Start off-chain. Implement a signed registry JSON or local file loader with the
same record shape as the future onchain contract. The verifier module should:

- load candidate records;
- fetch each manifest;
- canonicalize and hash the manifest;
- verify domain, hash, signature/proof, revocation, timestamp, payment
  recipient, and shipping country scope;
- expose `verification.state` and `verification.errors`;
- make quote tournament exclude unverified external merchants by default.

Once that interface is stable, the source of records can move from a signed JSON
feed to an onchain registry without changing buyer or merchant adapters.

## Open Questions

- Should registry updates be wallet-signed, DNS-based, or both?
- How should merchants rotate payment recipients?
- How should compromised manifests be revoked?
- Should there be a neutral allowlist for consumer-protection-compliant shops?
- How can small merchants stay discoverable without recreating ad-market
  dynamics?
