# AgentCart Hackathon Demo Runbook

This is the practical demo path for Futura Camp MPP Hackathon.

## What To Show

AgentCart is a household-safe commerce bridge. It does not claim to replace MPP
or x402. It shows what a small merchant and a household agent need around the
payment:

- machine-readable catalog
- final quote with VAT, shipping, delivery window, stock, and merchant of record
- household policy check
- explicit Home Assistant human approval
- HTTP 402 payment-auth checkout plus Tempo MPP testnet proof
- demo merchant order
- Vikunja task update
- audit log and delivery calendar feed

## Demo Surfaces

- AgentCart dashboard: `http://192.168.178.146:8099/`
- Pitch deck: `http://192.168.178.146:8099/presentation.html`
- Architecture: `http://192.168.178.146:8099/architecture.html`
- Buyer/shop onboarding: `http://192.168.178.146:8099/onboarding.html`
- Protocol field map: `http://192.168.178.146:8099/protocol-fields.html`
- Payment/refund options: `http://192.168.178.146:8099/payment-options.html`
- Two-shop quote tournament:
  `http://192.168.178.146:8099/registry?q=Hazel%27s%20Chocolate%20Tea&country=DE&postal_code=15344`
- Agent console fallback: `http://192.168.178.146:8099/agent`
- OpenClaw gateway: `http://192.168.178.146:18789`
- Vikunja: `http://192.168.178.150:3456`
- Household OS chat: `http://192.168.178.150:8088/chat`

## Preflight

From the Mac:

```sh
cd /Users/max/Code/homelab/home-ops/agentcart
./scripts/hackathon-preflight.sh
```

Expected:

- `agentcart.service`: active
- `agentcart-mpp-smoke.service`: active
- `openclaw-gateway.service`: active
- Home Assistant notifications: ready
- Vikunja: configured and open tasks returned
- Tempo MPP proof: configured
- energy surplus: readable
- local Ollama endpoint: the preflight wakes the PC through Home Assistant if
  needed, then checks the local model path

## Primary Gateway Prompts

Use these prompts in Household OS Chat at `http://192.168.178.150:8088/chat`.
For AgentCart-specific prompts, Household OS now uses a narrow AgentCart bridge
instead of relying on generic model text. That means the chat can run merchant
discovery, compare final quotes, create a portable approval request, complete
checkout after explicit approval, and return the delivery/payment/order summary.

### 1. Household Context

```text
Use the AgentCart skill. First list our open household shopping tasks, then
check whether we currently have excess energy to sell. Do not create a quote,
do not create an approval, and do not buy anything. Give me a concise summary.
```

Expected story:

- Vikunja open tasks are visible.
- Energy telemetry is visible.
- Current energy result may be `no_surplus`; that is fine. The point is that
  household state can inform commerce decisions.

### 2. Buy Favorite Tea

```text
Use AgentCart to buy my favorite tea, Hazel's Chocolate. Discover matching
shops, get the best final quote, and ask me for approval before ordering.
```

Then approve from the same chat:

```text
Approve it and continue checkout.
```

Expected flow:

1. AgentCart normalizes `my favorite tea` to `Hazel's Chocolate Tea`.
2. AgentCart discovers the demo shop and WooCommerce ShopBridge merchant.
3. Private quote tournament selects WooCommerce at `14.80 EUR`.
4. The tournament also shows the settlement boundary: WooCommerce quote is EUR,
   while the current Tempo proof is pathUSD testnet.
5. Policy requires human approval.
6. Approval can be given in chat, Home Assistant, or the approval URL.
7. AgentCart completes the HTTP 402 payment-auth checkout.
8. Tempo MPP testnet proof is attached as `external_value_proof`.
9. WooCommerce admin shows the merchant order.
10. Vikunja gets `Tea ordered: 1x Hazel's Chocolate Tea`.
11. Delivery estimate is attached to the order and proof page.

### Optional Refund Demo

On the latest order proof page, click `Record Demo Refund`. Expected result:

- AgentCart calls the WooCommerce ShopBridge refund endpoint.
- WooCommerce records a refund object against the order.
- AgentCart stores a refund record and writes an `order.refund_recorded` audit
  event.
- The proof page shows `real_refund_verified=false` unless a production payment
  verifier confirmed a Stripe/card or Tempo/stablecoin refund.

### Proof To Show

Open the AgentCart dashboard at `http://192.168.178.146:8099/`, then click the
latest order id. The order proof page shows:

- quote id, reason, product, final price, VAT/shipping-inclusive total
- policy decision and human-approval reason
- Home Assistant approver and approval timestamp
- HTTP 402 payment challenge and AgentCart payment receipt
- Tempo MPP testnet proof from `mppx`
- merchant order id
- Vikunja task link
- delivery window
- audit events for the purchase

For orders created after the proof-page update, AgentCart captures the raw MPP
`Payment-Receipt` header. When the receipt contains a Tempo reference, the proof
page links to the Tempo testnet explorer. Older orders still show the successful
`mppx` proof body but cannot retroactively show the receipt reference because
that header was not stored yet.

MPPscan is useful for public or registered MPP servers. The hackathon smoke
endpoint currently runs on `127.0.0.1`, so it is not expected to appear on
MPPscan unless the API is exposed and registered.

### 3. Explain What Happened

```text
Show me the AgentCart audit for the tea purchase and explain why the purchase
was allowed, who approved it, what payment proof was attached, and when the tea
is expected to arrive.
```

## Deterministic Fallback

If OpenClaw's cloud-backed agent is quota-limited or unstable, run the same
demo through the AgentCart skill helper. This uses the same API, policy engine,
Home Assistant approval, Tempo MPP proof, merchant order, Vikunja sync, and
audit log.

### Context Check

```sh
ssh pve 'pct exec 104 -- runuser -u openclaw -- bash -lc '"'"'
cd /home/openclaw/workspace/skills/agentcart
python3 scripts/agentcart-command.py << "JSON"
{"command":"list_open_tasks","args":{"limit":8}}
JSON
python3 scripts/agentcart-command.py << "JSON"
{"command":"energy_surplus","args":{}}
JSON
'"'"''
```

### Purchase With Phone Approval

If you want the first chat message to wait for the phone/watch approval instead
of using the two-step chat approval, include "wait for my approval" in the
prompt.

Start this command, then approve the Home Assistant notification on phone/watch:

```sh
ssh pve 'pct exec 104 -- runuser -u openclaw -- bash -lc '"'"'
cd /home/openclaw/workspace/skills/agentcart
python3 scripts/agentcart-command.py << "JSON"
{
  "command": "buy_favorite_tea",
  "args": {
    "channel": "home_assistant",
    "wait_for_approval": true,
    "wait_seconds": 180,
    "reason": "Hackathon demo: household agent was asked to buy Max favorite tea"
  }
}
JSON
'"'"''
```

This returns the final order after approval. It is the best fallback because it
still demonstrates the real human approval and checkout sequence.

## Phone And Apple Watch Approval

AgentCart sends Home Assistant actionable notifications through:

- `notify.mobile_app_maximilians_iphone`
- `notify.mobile_app_iphone_paula`

Apple Watch behavior depends on iPhone notification mirroring and whether the
Companion App action buttons are shown on the watch. If the watch does not show
the action buttons, approve from the iPhone notification or open the approval
URL. The backend flow is the same.

## Local GPU Model

The desktop GPU host can be woken through Home Assistant and used by OpenClaw's
`ollama-test` profile. The current default local profile uses
`ollama/gemma4:e2b` with a 32k context window because the full OpenClaw embedded
agent prompt is too large for the old 8k profile.

Verified path:

```sh
ssh pve 'pct exec 104 -- bash -lc '"'"'
runuser -u openclaw -- env HOME=/home/openclaw OLLAMA_API_KEY=ollama-local \
  openclaw --profile ollama-test infer model run \
    --local \
    --model ollama/gemma4:e2b \
    --thinking off \
    --prompt "Reply with exactly: pong" \
    --json
'"'"''
```

Use this as a secondary point: local models can participate, and the full local
OpenClaw agent smoke test now works with `gemma4:e2b`. Keep the deterministic
AgentCart bridge as the primary checkout path because it avoids model/tool-loop
variance during the live payment demo.

Optional full local-agent smoke:

```sh
AGENTCART_PREFLIGHT_LOCAL_AGENT=1 ./scripts/hackathon-preflight.sh
```

## What Not To Claim

- Do not claim a real tea merchant fulfilled the order.
- Do not claim real EUR settlement occurred.
- Say explicitly: WooCommerce quotes in EUR; the Tempo testnet proof is a
  pathUSD proof artifact. Production needs FX handling, Stripe/card settlement,
  or an EUR-compatible MPP payment method.
- Do not claim the WooCommerce Refund button moves money in the demo. Say:
  WooCommerce records the order/refund workflow; production must execute refunds
  through the original rail, for example Stripe refund API or a Tempo/stablecoin
  verifier refund transfer.
- Do not claim AgentCart extends core MPP. Say: MPP handles payment challenge,
  credential, and receipt fields. AgentCart adds a commerce and household safety
  profile around MPP.
- Do not claim the local model reliably runs the full tool-agent flow.
- Do not claim energy sales are implemented. The energy branch is read-only
  surplus detection only.

## Pitch Close

The practical gap is not "can an agent pay?" Tempo MPP already covers that. The
gap is the bridge that lets a normal household agent safely discover a product,
get a real quote, apply household policy, collect human consent, pay through an
MPP-aware path, create a merchant order, and leave an audit trail.
