# ADR 0005: Skill-First Buyer Path With Optional Service

## Status

Accepted

## Context

Buyers need a low-friction way to use ShopBridge, while some households need durable policy, audit, approval, calendar/task integrations, and local automation.

## Decision

The Direct Skill is the default low-friction buyer path. The AgentCart Service remains optional and is used when durable household policy, approval, audit, registry monitoring, Home Assistant, Vikunja, or richer local workflow state is required.

## Consequences

- The Direct Skill must preserve approval and audit packets because it has no durable household memory by default.
- The AgentCart Service must be able to import skill-only audit evidence idempotently.
- Buyer-agent runtime tests must cover service-backed, skill-only, and generic MCP-style clients.
- Product docs should not require the AgentCart Service for a simple known-merchant purchase.

