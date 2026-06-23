# AgentCart Repo Strategy

## Recommendation

Use a clean public monorepo for the hackathon, then split if the plugin survives
the event.

Do not publish `<private-source-repo>` directly. It contains unrelated
private infrastructure state, local topology, and potentially sensitive operational context.

## Hackathon Monorepo

Suggested public repo: `agentcart`

```text
agentcart/
  gateway/                  # AgentCart API, quote tournament, approval, audit
  woocommerce-shopbridge/   # WordPress/WooCommerce plugin
  demo/                     # Docker compose, seed products, demo runbook
  docs/                     # MPP compatibility, protocol field map, pitch notes
```

Why this is best for the hackathon:

- one URL for reviewers;
- one README and one demo script;
- easier to explain how the household agent and merchant plugin fit together;
- less coordination overhead during the final polish.

## Production Split

If this continues after the hackathon, split into two repos:

```text
agentcart
agentcart-shopbridge-woocommerce
```

`agentcart` should contain the gateway, household adapters, quote tournament,
policy engine, audit surfaces, and demo integrations.

`agentcart-shopbridge-woocommerce` should contain only the WordPress plugin,
installation docs, screenshots, WordPress tests/linting, release ZIP workflow,
and examples for Tempo, Stripe/card, and custom verifier configuration.

## Plugin Independence Requirements

The WooCommerce plugin should not require Home Assistant, OpenClaw, Vikunja, or
AgentCart's household demo to be useful. A store owner should be able to:

1. Install WooCommerce.
2. Install AgentCart ShopBridge.
3. Configure support email, allowed shipping countries, merchant-of-record
   terms, payment verifier URL, settlement method, and gateway token.
4. Publish `/.well-known/agentcart.json`.
5. Let agents discover products, request final quotes, and create paid orders
   through the plugin API.

The household AgentCart gateway is one possible buyer-side client. Telegram,
Signal, another local agent, a cloud agent, or a marketplace relay should be able
to call the same merchant profile.

## What To Exclude From Public Release

- real tokens, passwords, wallet keys, Stripe keys, MPP secrets;
- private IPs unless clearly marked as local demo examples;
- Home Assistant long-lived access tokens;
- Vikunja tokens;
- local order/customer data;
- unrelated infrastructure dashboards, validator files, or personal automations;
- demo state files with real addresses or phone identifiers.
