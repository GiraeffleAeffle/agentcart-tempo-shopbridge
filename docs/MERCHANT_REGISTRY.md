# Merchant Registry And Discovery

AgentCart's registry should be an identity and integrity anchor, not an ad
marketplace and not a product catalog.

## Goals

- Let agents discover shops that support AgentCart ShopBridge.
- Let shops publish a stable manifest URL.
- Let agents verify that a manifest has not been silently swapped.
- Avoid publishing household demand, addresses, private shopping tasks, or live
  catalog data on-chain.

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
  "signature": "merchant-domain-or-wallet-signature"
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
2. Merchant signs or registers the manifest hash.
3. Agent fetches registry record.
4. Agent fetches manifest from merchant domain.
5. Agent verifies hash/signature.
6. Agent requests private quote from the merchant endpoint.

## Open Questions

- Should registry updates be wallet-signed, DNS-based, or both?
- How should merchants rotate payment recipients?
- How should compromised manifests be revoked?
- Should there be a neutral allowlist for consumer-protection-compliant shops?
- How can small merchants stay discoverable without recreating ad-market
  dynamics?
