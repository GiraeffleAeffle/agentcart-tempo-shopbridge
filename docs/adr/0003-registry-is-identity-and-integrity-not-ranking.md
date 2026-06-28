# ADR 0003: Registry Is Identity And Integrity, Not Ranking

## Status

Accepted

## Context

Buyer agents need a way to discover opt-in ShopBridge merchants and verify merchant-owned manifests. Publishing household demand, live catalog data, or ad-driven ranking would undermine the privacy and trust model.

## Decision

The Merchant Registry anchors identity and integrity only. It binds merchant id, domain, manifest URL, registry claim hash, payment destination, freshness, proof, and revocation state. Product search, private quotes, and ranking remain buyer-side.

## Consequences

- Registry records must not include household demand, delivery addresses, private shopping tasks, or live catalog data.
- Buyer ranking should be explainable from eligible merchants, private Final Quotes, payment readiness, local policy, price, and delivery.
- Registry health and transparency should help agents explain inclusion or exclusion, not advertise merchants.
- Future onchain or append-only registry work should preserve the same minimal public record shape.

