# Quote Reliability

AgentCart treats a Final Quote as the checkout contract. A country/postcode-only
Comparison Quote is for private merchant ranking and cannot be approved or
paid. The selected merchant must issue a fresh Final Quote whose hash binds
merchant identity, items, the complete buyer-supplied delivery address,
shipping, included VAT, total, currency, expiry, stock-hold metadata, merchant
policy, and payment profile.

At checkout, ShopBridge now revalidates four layers before creating the order:

1. **Replay and concurrency:** the buyer must provide an idempotency key, checkout
   is locked by idempotency key, and each `merchant_quote_id` is consumed once.
2. **Delivery completeness:** every country-specific required address field must
   be present in the stored quote before payment verification. Checkout input
   cannot replace the quote-bound address.
3. **Availability:** products must still be enabled, inside quantity limits,
   shippable to the quoted country, and in stock after active quote holds.
4. **Money drift:** WooCommerce recalculates the stored quote basket before
   payment verification. If item prices, subtotal, shipping amount/method, VAT
   lines, total, or currency no longer match, checkout fails closed with a
   machine-readable recovery hint.

Recovery errors include `recovery.recreate_quote_required=true`, the quote
endpoint to call, the original `merchant_quote_id`, and a reason such as
`quote_expired`, `stock_changed`, `price_changed`, `shipping_changed`, or
`tax_changed`. Buyer agents should discard the old approval/payment attempt,
request a fresh final quote, and ask the buyer to approve the new amount.

The checked contract is in
`gateway/config/quote_reliability_matrix.json` and is validated by
`scripts/check-quote-reliability-matrix.py --verify-test-refs`.
