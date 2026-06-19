# Household OS Demo Bridge

This folder contains the optional household-side demo bridge used by AgentCart.
It connects a household chat surface to Vikunja tasks, Home Assistant approval
notifications, and the AgentCart API.

It is intentionally demo infrastructure, not the core merchant product. The
core merchant artifact is the WooCommerce ShopBridge plugin in
`woocommerce-shopbridge/`.

## Components

- `/chat`: shared household-agent chat UI.
- `/api/command`: task, Home Assistant, and AgentCart command bridge.
- Vikunja integration: reads shopping tasks and creates/updates order tasks.
- Home Assistant integration: sends actionable approval notifications.
- Calendar feeds: optional delivery/task calendar feeds for the demo.

## Public Demo Defaults

Use generic local hostnames or your own LAN names in `.env`:

```env
VIKUNJA_WEB_URL=http://vikunja.local:3456/
HOMEASSISTANT_URL=http://homeassistant.local:8123
OPENCLAW_GATEWAY_URL=http://openclaw.local:18789
AGENTCART_URL=http://agentcart.local:8099
HA_NOTIFY_SERVICES=notify.mobile_app_demo_phone
```

Create a normal Vikunja user such as `demo` and use that account for the chat
login. Do not publish real household usernames, task exports, phone notification
service names, LAN IPs, or Home Assistant entity ids.

## Demo Prompt

```text
Please buy my favourite tea. Discover shops, choose the best final quote, and
ask me for approval before checkout.
```

The expected path is:

1. Household OS recognizes the shopping intent.
2. AgentCart resolves the favorite tea preference.
3. AgentCart compares opt-in merchant quotes.
4. The household user approves the exact quote.
5. AgentCart checks out through the MPP-shaped payment path.
6. Vikunja receives a `Tea ordered` task and the order proof shows the delivery
   estimate and audit trail.
