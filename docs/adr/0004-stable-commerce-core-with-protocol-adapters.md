# ADR 0004: Stable Commerce Core With Protocol Adapters

## Status

Accepted

## Context

Agent commerce protocols and ecosystems are moving quickly: x402, MPP, Stripe/card MPP, ERC-8004, ERC-8128, ERC-8183, AP2, ACP, UCP, MCP, A2A, and agent skills all touch the product surface differently.

## Decision

AgentCart keeps a stable commerce core and maps protocols into or out of it through adapters. Merchant, Manifest, Registry Record, Final Quote, Approval Record, Payment Requirements, Order, Aftercare, and Audit Packet remain AgentCart concepts.

## Consequences

- New standards work should not pivot the product around one protocol.
- Protocol profiles should be configured-only and machine-readable.
- Native protocol runtimes should be added only after a concrete conformance target and auth/task lifecycle story are selected.
- Tests should assert mapping invariants without claiming compliance before runtime support exists.

