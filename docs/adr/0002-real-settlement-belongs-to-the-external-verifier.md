# ADR 0002: Real Settlement Belongs To The External Verifier

## Status

Accepted

## Context

The repo supports demos, testnet proofs, MPP-shaped flows, x402-compatible requirements, and Stripe/card MPP fixtures. Production order creation and refunds need rail-specific proof, provider credentials, replay protection, and operational monitoring.

## Decision

Real payment and refund claims require External Verifier evidence. Token-authenticated checkout remains local/private mode. Public production checkout should use `external_verifier_only` and must not mark orders paid or refunded from demo proof or merchant token trust alone.

## Consequences

- Payment and refund verifier contracts are production-critical interfaces.
- Each payment rail should live behind the verifier seam instead of changing catalog, quote, approval, order, delivery, and audit flow.
- Refund claims must preserve verifier-backed provider references.
- Production verifier work needs managed replay storage, provider dashboards, alerting, and operational runbooks.

