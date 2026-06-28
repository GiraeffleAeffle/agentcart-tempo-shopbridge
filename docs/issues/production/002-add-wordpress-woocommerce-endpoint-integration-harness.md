# Add WordPress/WooCommerce endpoint integration harness

## What to build

Add a repeatable integration test harness that boots the local WordPress/WooCommerce stack and exercises the ShopBridge manifest, catalog, quote, checkout, status, refund, cancellation, and rate-limit surfaces through HTTP.

## Acceptance criteria

- [ ] Harness can run locally from a documented command.
- [ ] Quote totals are compared against WooCommerce cart totals.
- [ ] Checkout rejects expired quotes and quote hash mismatch.
- [ ] Refund endpoint requires idempotency and verifier evidence.
- [ ] Cancellation endpoint never claims refund execution.
- [ ] The harness can be gated separately from fast source-level tests.

## Blocked by

None - can start immediately.

## Slice metadata

Type: AFK
Source: `docs/PRODUCTION_ISSUE_SLICES.md`

