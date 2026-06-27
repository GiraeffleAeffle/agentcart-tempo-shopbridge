# Demo Recording Plan

Target length: **3 minutes maximum**.

## 3-Minute Structure

| Time | Shot | What to say |
| --- | --- | --- |
| 0:00-0:20 | Opening slide | "Tempo MPP can handle machine payment. AgentCart solves the missing shop bridge: product discovery, final quote, approval, order, delivery, refund metadata, and audit." |
| 0:20-0:45 | Architecture page | "The agent does not scrape websites. It calls AgentCart, gets opt-in merchant manifests and quotes, applies household policy, then uses an MPP-shaped checkout." |
| 0:45-1:15 | WooCommerce admin plugin | "A normal WooCommerce shop installs ShopBridge, configures support, shipping countries, Tempo or Stripe verifier settings, and stays merchant of record." |
| 1:15-2:20 | Live order flow | Ask: `Please buy my favourite tea. Discover shops, choose the best final quote, and ask me for approval before checkout.` Show quote comparison, approval, checkout, and proof page. |
| 2:20-2:45 | WooCommerce order | Show the paid WooCommerce order with product, shipping, total, and `Tempo MPP via AgentCart`. |
| 2:45-3:00 | Close / limits | "This is testnet/demo settlement. Production needs verifier-backed real settlement/refunds, carrier tracking, legal terms, and a fair discovery registry." |

## Tabs To Prepare

- `http://agentcart.local:8099/presentation.html`
- `http://agentcart.local:8099/demo`
- `http://agentcart.local:8099/architecture.html`
- WooCommerce `WooCommerce -> AgentCart`
- `http://household-os.local:8088/chat` or `http://agentcart.local:8099/agent`
- Latest AgentCart order proof page
- WooCommerce order detail page

## Must Show

1. The shop opts in with the WooCommerce plugin.
2. The agent compares at least two offers and chooses the best final quote.
3. The user approves before checkout.
4. The proof page shows approval, Tempo proof/explorer reference, merchant order, delivery ETA, Vikunja/calendar/audit state.
5. WooCommerce shows the merchant-side order.

## Skip If Time Is Tight

- Energy sale demo.
- Local GPU model details.
- Refund click-through.
- Full protocol field page.
- Long market/protocol background.
