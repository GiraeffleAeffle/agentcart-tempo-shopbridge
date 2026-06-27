# AgentCart Repository Strategy

## Current Shape

Keep this repo as a production-candidate monorepo while the merchant plugin,
buyer skill, registry, verifier contract, and local development stack are still
changing together.

The repo has three release surfaces:

- `woocommerce-shopbridge/`: the WordPress/WooCommerce merchant plugin and ZIP.
- `gateway/`: the AgentCart buyer gateway, hosted registry, verifier-facing
  tools, roadmap pages, and local development UI.
- `gateway/shopbridge-direct-skill/`: the service-free buyer skill for agents
  that can call ShopBridge merchants directly.

The local WooCommerce shop, home-server stack, Household OS bridge, and demo
pages are development and validation fixtures. They are useful for smoke tests
and onboarding, but they must not be required for a merchant to install
ShopBridge or for a buyer agent to use the direct skill.

## Production Direction

The merchant plugin should become independently releasable first. A store owner
should be able to:

1. Install WooCommerce.
2. Upload and activate `agentcart-shopbridge.zip`.
3. Configure merchant identity, support contact, product exposure, tax/shipping,
   payment verifier, signed-request policy, and registry publication from
   `WooCommerce -> AgentCart`.
4. Publish the well-known manifest, registry proof, revocation document, and
   registry bundle over the shop domain.
5. Let buyer agents discover products, request final quotes, and create paid
   orders through the plugin API.

The buyer side should support two paths:

- direct skill path for lowest-friction buyer setup;
- AgentCart gateway path for households that want local policy, approval,
  registry monitoring, delivery calendar, and audit aggregation.

## Split Criteria

Split into separate repositories only after the plugin release surface is stable:

```text
agentcart
agentcart-shopbridge-woocommerce
agentcart-shopbridge-direct-skill
```

Do not split yet if changes still regularly cross the plugin, buyer skill,
verifier contract, and registry fixtures. A premature split would increase
coordination cost without improving merchant safety.

Ready-to-split signals:

- the WooCommerce ZIP can be built, checked, and released without gateway code;
- plugin tests no longer need gateway fixtures except protocol JSON examples;
- direct skill uses versioned manifest/verifier contracts rather than importing
  assumptions from the gateway implementation;
- release manifests can track artifact versions independently;
- WordPress.org submission assets and update process are managed from the
  plugin release surface.

## Public Release Hygiene

Do not publish:

- real tokens, passwords, wallet keys, Stripe keys, MPP secrets, or verifier
  bearer tokens;
- private IPs unless clearly marked as local examples;
- Home Assistant or Vikunja access tokens;
- local order/customer data;
- unrelated infrastructure state;
- demo state files with real addresses or phone identifiers.

Public entry docs should describe the product as a production-candidate alpha,
not as an event submission. Historical demo and presentation notes can remain in
`docs/`, but they should not be the primary install path.

Generated release outputs under `dist/` are build artifacts. Keep them out of
source control and attach them to release channels instead. The canonical source
of truth is the plugin source, direct skill source, packaging scripts, and
release verification scripts.
