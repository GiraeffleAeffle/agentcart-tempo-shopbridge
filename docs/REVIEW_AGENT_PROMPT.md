# AgentCart Independent Review Prompt

Use this prompt with a separate review agent before the hackathon presentation.

```text
You are reviewing AgentCart, an MPP Hackathon project. Be critical and do not
rubber-stamp the design.

Goal:
Verify whether AgentCart makes accurate claims, follows the official MPP
protocol boundary, and demonstrates a real gap for household agents buying from
opt-in merchants.

Primary local repo paths:
- /Users/max/Code/homelab/home-ops/agentcart
- /Users/max/Code/homelab/home-ops/agentcart/woocommerce-plugin

Official protocol sources to check:
- https://mpp.dev/llms-full.txt
- https://mpp.dev/protocol/
- https://mpp.dev/advanced/discovery
- https://mpp.dev/payment-methods/stripe/
- https://mpp.dev/payment-methods/tempo/

Review questions:
1. MPP compliance:
   - Does /openapi.json use canonical x-payment-info.offers[]?
   - Does checkout use 402, WWW-Authenticate: Payment, Authorization: Payment,
     and Payment-Receipt consistently?
   - Are challenge ids, expiry, idempotency keys, and request body digests used
     to prevent replay or accidental side effects?
   - Are we incorrectly claiming that product/VAT/delivery/order fields are
     part of MPP?

2. AgentCart ShopBridge boundary:
   - Are product, quote, tax, shipping, merchant-of-record, approval, order,
     delivery, and audit fields clearly described as AgentCart-specific?
   - Is the WooCommerce plugin usable without Home Assistant, OpenClaw, or
     Vikunja?
   - Does the plugin expose enough machine-readable data for an agent to quote
     and create an order from products already managed in WooCommerce?

3. Payment and currency truthfulness:
   - Does the demo clearly say the WooCommerce quote is EUR?
   - Does it clearly say the current Tempo testnet proof is pathUSD and not real
     EUR merchant settlement?
   - Are Stripe/card or EUR-compatible settlement described as future production
     options rather than completed features?
   - Does AGENTCART_PAYMENT_VERIFIER_URL make sense as the verifier boundary for
     quote-bound payment proofs?

4. WooCommerce plugin security:
   - Are public catalog/quote endpoints safe for opt-in use?
   - Is order creation protected by a token or verifier?
   - Is quote_hash bound to items, totals, shipping, delivery country, and expiry?
   - Are transaction references replay-protected?
   - Does the plugin avoid collecting unnecessary IP/device data?
   - Are guest checkout and delivery address handling explicit enough?

5. Demo proof:
   - Can the live demo show two shops for Hazel's Chocolate Tea and choose the
     better final offer?
   - Can the demo show approval, order creation, Tempo proof/explorer link,
     Vikunja task, delivery estimate/calendar, and audit trail?
   - Are fake/demo-only parts labeled clearly?

6. Legal and payment risk:
   - Are VAT, refunds, chargebacks, consumer rights, merchant-of-record,
     shipping, data protection, KYC, and sanctions handled by the merchant/PSP
     in the production story?
   - Are we avoiding browser automation or proxy-buying from non-opt-in shops?

7. Repo hygiene:
   - Are secrets, local passwords, tokens, private IP assumptions, and unrelated
     homelab files excluded from any public repo?
   - Should this be a monorepo for the hackathon or split into:
     a) agentcart gateway/demo
     b) agentcart-shopbridge-woocommerce plugin?

Output:
- Start with findings ordered by severity.
- Include exact file paths and line references.
- Then list protocol inaccuracies, missing tests, and demo risks.
- End with a concise recommendation: proceed, proceed with caveats, or pivot.
```
