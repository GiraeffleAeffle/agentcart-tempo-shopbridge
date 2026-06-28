# ADR 0001: WooCommerce Remains The Merchant System Of Record

## Status

Accepted

## Context

AgentCart ShopBridge exposes agent-readable commerce surfaces for WooCommerce merchants. The product must support catalog, quote, checkout, status, cancellation, refund, and fulfillment without replacing merchant operations.

## Decision

WooCommerce remains the system of record for products, stock, tax, shipping, fulfillment, refunds, support, and order history. The ShopBridge Plugin is an adapter around WooCommerce, not a replacement commerce backend.

## Consequences

- Final Quote and Order behavior must flow through WooCommerce calculations and order state.
- Production readiness depends on WordPress/WooCommerce integration coverage, not only source-level contract tests.
- Product controls and aftercare policy should be merchant-admin configurable in WooCommerce.
- AgentCart docs and buyer agents must not imply that AgentCart is merchant of record.

