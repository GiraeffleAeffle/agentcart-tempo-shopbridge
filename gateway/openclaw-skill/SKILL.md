---
name: agentcart
description: Buy demo household products through AgentCart with merchant discovery, quote tournaments, portable human approval, HTTP 402 payment-auth checkout, orders, and audit logs.
metadata:
  openclaw:
    requires:
      bins:
        - python3
---

# AgentCart Skill

Use this skill when the household user asks the household agent to search for household goods,
quote a small opt-in merchant purchase, check policy, request approval, or
complete an AgentCart demo checkout.

Always call AgentCart instead of scraping or automating third-party shop
websites. AgentCart keeps the merchant as merchant of record and records the
reason, policy result, approval, payment receipt, order, and Vikunja sync state.

The command helper reads `AGENTCART_URL` and `AGENTCART_TOKEN` from the
environment. If they are not already set, it loads `/etc/openclaw/agentcart.env`.

Command helper:

```sh
python3 {baseDir}/scripts/agentcart-command.py <<'JSON'
{"command":"search_catalog","args":{"q":"tea"}}
JSON
```

Available commands:

- `health` with `{}`.
- `capabilities` with `{}`.
- `integration_status` with `{}` to report whether Home Assistant, Vikunja,
  Tempo MPP proof, AgentCash proof, and the payment provider are configured.
- `list_open_tasks` with optional `limit`; returns open Vikunja tasks when
  Vikunja is configured.
- `search_catalog` with optional `q`.
- `registry` with `{}` to list opt-in merchant manifest anchors.
- `quote_tournament` with optional `q`, `country`, `postal_code`, and
  `quantity`. Use this before purchase when the household user asks for the best price or
  asks to buy a product by intent.
- `get_product` with `product_id`.
- `get_quote` with `quote_id`.
- `create_quote` with `items`, `reason`, optional `ship_to`, and optional
  `agent_id`.
- `create_approval` with `quote_id`, optional `channel`, and optional
  `delivery_channels`. Approval is portable: render `consent_request` in chat,
  or use `decision_url` for web/mobile/Home Assistant approval.
- `approval_status` with `approval_id`.
- `approve_purchase` with `approval_url`, or with `approval_id` and
  `token`/`decision_token`. Use only after the household user explicitly approves in chat.
- `reject_purchase` with `approval_url`, or with `approval_id` and
  `token`/`decision_token`. Use only after the household user explicitly rejects in chat.
- `approve_and_checkout` with `approval_url`, or with `approval_id` and
  `token`/`decision_token`. This records the human approval and then runs the
  demo HTTP 402 payment-auth checkout. Use only when the household user explicitly asks to approve and
  continue checkout.
- `checkout` with `quote_id`, `approval_id`, optional `idempotency_key`, and
  optional `simulate_payment`. If `simulate_payment` is true, the helper follows
  AgentCart's demo 402 challenge and retries with `Authorization: Payment`.
- `order_status` with `order_id`.
- `audit` with `purchase_id`.
- `start_demo_purchase` or `buy_tea_demo` with optional `q`, `product_id`,
  `quantity`, `reason`, `ship_to`, `use_tournament`, `wait_for_approval`,
  `wait_seconds`, and `poll_interval`. By default this runs a private quote
  tournament, fetches the winning final quote, requests human approval, and
  returns the approval URL. It does not complete checkout unless
  `wait_for_approval` is true and the human approves before the timeout.
- `buy_favorite_tea` with optional `quantity`, `reason`, `ship_to`,
  `wait_for_approval`, `wait_seconds`, and `poll_interval`. This resolves the
  household favorite tea to Hazel's Chocolate Tea, discovers matching opt-in
  shops, picks the best final quote, then follows the same approval flow.
- `energy_surplus` with `{}`. This reads configured Home Assistant solar,
  battery, grid import/export, and house-output sensors and returns a read-only
  decision about whether energy is offerable. It does not sell or settle energy.
- `resume_checkout` with `approval_id` and optional `quote_id`. Use this after
  the human approval is complete. It verifies the approval state and then runs
  the demo HTTP 402 payment-auth checkout.
- `demo_low_tea` with `{}` to trigger the Home Assistant tea-low demo path.
- `demo_woo_tea` with `{}` to trigger the opt-in WooCommerce tea demo path.

Preferred tea purchase flow:

```sh
python3 {baseDir}/scripts/agentcart-command.py <<'JSON'
{"command":"buy_favorite_tea","args":{}}
JSON
```

Tell the human the returned approval URL or wait for the Home Assistant
notification. After the human approves through the approval page:

```sh
python3 {baseDir}/scripts/agentcart-command.py <<'JSON'
{"command":"resume_checkout","args":{"approval_id":"approval_..."}}
JSON
```

If the household user approves over chat instead, use the approval URL/token from the pending
request:

```sh
python3 {baseDir}/scripts/agentcart-command.py <<'JSON'
{"command":"approve_and_checkout","args":{"approval_url":"http://.../approvals/approval_...?token=..."}}
JSON
```

Safety rules:

- Do not buy from non-opt-in websites.
- Do not bypass policy or approval.
- Do not treat the agent's own purchase proposal as approval. Approval must be
  an explicit human message, Home Assistant action, approval page action, or
  external UI decision posted to AgentCart's approval API.
- Do not create orders unless the quote is approved.
- Treat `demo` payment receipts as HTTP 402 Payment-auth simulation, not real settlement.
- Treat Tempo testnet proof receipts as payment-protocol proof artifacts, not
  settled physical-goods checkout.
- For real-money variants, require explicit human confirmation and verify the
  merchant, tax, refund, and support path before checkout.
