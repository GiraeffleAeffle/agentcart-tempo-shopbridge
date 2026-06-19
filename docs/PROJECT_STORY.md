# AgentCart

## Inspiration

AgentCart came from a real household setup: Home Assistant already knows when
something in the home needs attention, Vikunja already has our open shopping
tasks, and OpenClaw/local agents can already run inside a home lab. The missing
piece was commerce.

If my household agent knows that tea is running low, it should not need browser
automation or scraped checkout pages. It should be able to discover opt-in
shops, compare final quotes, ask me for approval on my phone/watch, pay through
an MPP-compatible checkout flow, create the merchant order, update my household
task board, and leave an audit trail.

## What It Does

AgentCart is a household-safe commerce bridge between personal agents and
opt-in merchants.

In the demo, I can ask:

> Please buy my favourite tea

The agent uses household context to understand that my usual tea is Hazel's
Chocolate Tea. It then:

1. Discovers matching products from multiple shops.
2. Requests final quotes with VAT, shipping, stock, delivery estimate, and
   merchant-of-record data.
3. Compares offers by local household policy, final price, delivery, and trust.
4. Requests explicit human approval through Home Assistant, chat, web, or API.
5. Completes an HTTP 402 / MPP-style checkout and attaches Tempo proof.
6. Creates a real WooCommerce order through the AgentCart ShopBridge plugin.
7. Updates Vikunja and the delivery calendar.
8. Shows an audit log explaining why the purchase happened.

The ranking is intentionally user-owned:

$$
winner = \arg\min_{quote \in eligible} (total\_price + delivery\_risk + policy\_penalty)
$$

No paid placement signal is used in the demo.

## How We Built It

The project has three main parts:

- **AgentCart Gateway**: merchant discovery, product search, household
  preference resolution, quote tournaments, policy checks, approvals, checkout,
  order proof, delivery calendar, and audit logs.
- **WooCommerce ShopBridge Plugin**: exposes a normal WooCommerce shop as an
  agent-readable merchant with catalog, quote, order, refund, and capability
  endpoints.
- **Household OS Integration**: connects Home Assistant, OpenClaw chat, Vikunja,
  Tempo MPP proof, and the demo dashboard.

The key design choice is that merchants opt in. AgentCart does not secretly buy
from existing shops. The merchant remains merchant of record and fulfills the
order.

## Challenges

The hard part was not just payment. MPP can prove a machine payment, but real
commerce needs more context:

- What product did the user actually mean?
- Which merchant has the best final price after VAT and shipping?
- Who is merchant of record?
- Is the product in stock?
- Which human approved the purchase?
- What refund path exists?
- How do we prove why the agent bought something?

We also hit a very real agent-safety bug: different spellings like
`favorite`/`favourite`, or direct tool calls using `favorite_tea`, could route to
the wrong merchant. We fixed this by adding an explicit household preference
resolver instead of relying on brittle string matching.

## What We Learned

Agent commerce needs more than payment rails. It needs product discovery,
quote integrity, merchant identity, buyer context, household policy, human
consent, delivery state, refund handling, and auditability.

Tempo MPP is useful as the payment/proof layer. AgentCart explores the practical
commerce layer around it, especially for ordinary WooCommerce merchants.

## What's Next

- Harden the WooCommerce plugin for production onboarding.
- Add production-grade Stripe/card and EUR-compatible settlement options.
- Define a public merchant discovery registry with privacy-preserving integrity
  anchors.
- Add real carrier tracking and verified refund flows.
- Package the household stack so a user can run Home Assistant, OpenClaw,
  Vikunja, and AgentCart on a small home server.
