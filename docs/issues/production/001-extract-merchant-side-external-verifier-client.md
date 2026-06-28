# Extract merchant-side External Verifier client

## What to build

Move ShopBridge payment/refund verifier request construction, redirect-safe HTTP calls, response validation, and redacted error handling into a dedicated merchant-side module while preserving the current REST endpoint behavior.

## Acceptance criteria

- [ ] Payment and refund endpoints still pass the existing verifier contract tests.
- [ ] Verifier HTTP redirects remain rejected.
- [ ] Error responses remain redacted and structured.
- [ ] Existing positive and negative verifier fixtures still validate.
- [ ] A focused module-level test covers payment success, refund success, replay conflict, and redacted verifier failure.

## Blocked by

None - can start immediately.

## Slice metadata

Type: AFK
Source: `docs/PRODUCTION_ISSUE_SLICES.md`

