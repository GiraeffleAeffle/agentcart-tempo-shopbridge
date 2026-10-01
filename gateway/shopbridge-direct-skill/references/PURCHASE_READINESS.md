# Purchase Readiness

Read this file for any request that may continue from discovery to approval,
payment, or checkout.

## Keep the gates separate

1. **Discovery Readiness** means the agent can query the onchain registry,
   verify merchants, read catalogs, and request comparison quotes. It never
   implies that a buyer wallet exists.
2. **Final Quote Readiness** means one selected merchant returned a financially
   consistent quote bound to the complete buyer-supplied delivery address.
3. **Payment Readiness** means an existing buyer-approved wallet or provider can
   satisfy the Final Quote's selected payment rail.
4. **Approval** happens only after gates 2 and 3. Payment and checkout happen
   only after the human explicitly approves the final approval hash.

## Compare with a coarse destination

Use only the buyer's real country and postcode while comparing merchants. Ask
for them if unknown; do not choose a destination merely because a merchant
supports it. Do not send a complete delivery address to every candidate.

A discovery winner based on country/postcode is a **Comparison Quote**. Its
approval packet reports `approval_ready:false` and
`incomplete_delivery_address`. It may be shown as a price comparison, not as an
approval request.

After selecting one verified merchant, ask the buyer for the fields listed in
`delivery_readiness.missing_delivery_fields`. Never invent a recipient name,
street address, city, state, or contact detail. Request a fresh quote from only
the selected merchant's verified origin. Pass `winner.quote_trust` unchanged
(or `quote_trust` from a successful `resolve_merchant`) and keep the selected
`payment_rail`:

```json
{"command":"quote","args":{"base_url":"https://shop.example","quote_trust":{...},"payment_rail":"stripe-card-mpp","product_id":"woo_10","quantity":1,"ship_to":{"first_name":"<buyer supplied>","last_name":"<buyer supplied>","address_1":"<buyer supplied>","city":"<buyer supplied>","state":"<buyer supplied when required>","postcode":"<buyer supplied>","country":"<buyer supplied>"}}}
```

The refreshed quote has new quote, payment-contract, and approval hashes. Never
reuse the Comparison Quote's approval packet.

The carried `quote_trust` binds the origin and registry record hash to the
record's Tempo network/recipient and Stripe profile. The refreshed quote must
match the selected rail's commitment; `payment_destination_mismatch` blocks
ranking, approval, payment handoff and checkout. Missing/empty commitments
fail closed, including x402 (which has no binding in the current registry
schema). Do not refresh with only `base_url`: that is unverified single-merchant
mode, not a continuation of verified discovery.
For Stripe, compare `stripe_profile_id`/`network_id`, not the protocol-profile
label `profile_id`. Choose the binding by the selected protocol's `id`/`method`;
a merchant-provided `rail` cannot redirect the binding check to another rail.

The calling agent must preserve this trust metadata. It is hash-linked, not
authenticated against a compromised agent; agent tampering is out of scope.

## Reconcile money before approval

Require `financial_readiness.financially_consistent:true`. Show subtotal,
shipping, structured tax lines, total, and currency. Quote item and shipping
amounts are gross; VAT lines with `included_in_total:true` explain tax already
inside those amounts.

If tax metadata says an amount is excluded but the total omits it, or the total
otherwise does not reconcile, reject the quote and request a refreshed one. Do
not guess whether to add or discard tax.

## Check the buyer payment side without executing it

Run:

```json
{"command":"payment_readiness","args":{"quote":{...},"payment_rail":"tempo-mpp","format":"toon"}}
```

The command never invokes `npx`, `mppx`, a wallet, or a provider. It is safe to
run before approval. An available launcher, an account label, or
`configured_unverified` does not prove that a usable wallet exists.

Reuse an existing buyer-approved wallet or provider when available. With
`SHOPBRIDGE_MPP_ACCOUNT` omitted, the sandbox adapter leaves account selection
to the payment client's existing default. An explicit account override must be
confirmed as belonging to the buyer. Ask before creating a wallet, changing
accounts, installing payment tooling, or importing/exporting keys.

If no payment capability exists, discovery and comparison can still finish.
Tell the buyer exactly what is missing and stop before approval, payment, and
checkout.

## Approval and execution order

Continue only when all of these are true:

- `approval_packet.approval_ready:true`;
- `checkout_preflight.ok:true`;
- the selected normalized rail has exactly one protocol entry, with
  `available` not false and `setup_required` not true (duplicate aliases cause
  `duplicate_payment_rail` and require a corrected merchant quote);
- an existing wallet/provider is confirmed for the approved destination; and
- the human explicitly approves the exact `approval_hash`.

Then call `payment_handoff`. It does not move money. Let the confirmed
wallet/provider satisfy its `receipt_requirements`, verify the returned receipt,
and only then call `checkout`.
