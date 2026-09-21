# Supervised staging onboarding (1.24.0)

Start with a staging copy containing synthetic customers and products, a named
maintainer, and one buyer using the ShopBridge Direct Skill. Keep production
provider credentials out of this environment. The initial payment profile is
Tempo testnet and optionally Stripe test mode; the preflight deliberately does
not approve x402 pilots yet. Passing is a configuration check, not a security
certification or proof of business legitimacy.

## Install and configure

Use the plugin, verifier image, charts and skill ZIPs from the same release.
Download the four ZIPs and `agentcart-release.json` from the GitHub release into
`dist/` inside the corresponding source checkout. The manifest checks detect
mixed or damaged artifacts; they do not independently authenticate a publisher.
Use a trusted release page/source commit to obtain them.

For the Helm shop, enable the verifier and pin its published image digest.
Configure `store.checkoutMode: external_verifier_only`,
`store.signedRequestMode: require_all_sensitive`, `store.stockHoldMode: hard`,
`store.environmentType: staging`, and `store.tempoNetwork: testnet`.
Configure the recipient, testnet settlement verification, test-only refund
wallet, registry identity, and distinct strong secrets as described in the
chart and payment documentation. `verifier.allowedTempoNetworks: [testnet]`
limits the verifier; never add mainnet for these sessions.

The chart enables `scheduler.enabled` and `verifier.reconciliationEnabled`.
The scheduler runs due WordPress jobs every minute in the storefront pod and
sets `DISABLE_WP_CRON` and `AGENTCART_EXTERNAL_SCHEDULER`. With another hosting
setup, arrange an external scheduler to run `wp cron event run --due-now` every
minute, then set those constants only after it is working. A configuration
flag alone does not make a healthy heartbeat. Turning off the chart scheduler
restores normal traffic-triggered WP-Cron; it will fail this unattended staging
preflight. Inspect the scheduler container readiness and manager diagnostics
if its heartbeat stops.

## Run the preflight

Download a fresh support diagnostics bundle from the ShopBridge settings page
as a WooCommerce manager. Save a fresh JSON response from the verifier's
`/health` endpoint through your operator access path. These are read-only
exports. Do not post the source exports publicly: they contain operational
identifiers even though credentials are redacted. The generated preflight
report contains only fixed check names, pass/fail values and remediation text.

From the release source checkout:

```sh
python3 scripts/tester-preflight.py \
  --shop-diagnostics /tmp/shop-diagnostics.json \
  --verifier-health /tmp/verifier-health.json \
  --release-root . --manifest dist/agentcart-release.json
```

Exit status 0 means all checks passed; 1 means stop and address the listed
failures. Export both reports within five minutes of running it. Registry
health must also be fresh. A bonded admission must remain eligible and
unexpired. For an explicitly maintainer-curated **v1 test registry** only, add
`--curated-v1-pilot`. This is an operator declaration about the test scope, not
business verification; it cannot override an expired v2 admission.

The command performs no network calls, sends no credentials, creates no quotes,
and makes no payments. It checks artifact hashes and versions, staging/HTTPS,
strong separated credentials, signed mutations, verifier enforcement, allowed
networks, native stock holds, encrypted/transactional recovery, durable verifier
storage, both scheduler heartbeats and outstanding operations. It does not
prove DNS/RPC independence, provider account ownership, backup restorability,
refund wallet funding, shipping accuracy or compatibility with other plugins.
Complete an observed purchase/refund exercise before inviting an unattended
tester. Never treat a saved successful report as ongoing monitoring.

## Recovery behavior and stop procedure

Checkout retries use the original persisted request and stop after three
automatic attempts. The periodic scan excludes exhausted and future-due cases
before selecting its ten-order batch, for both legacy storage and HPOS.
`compensation_required` always needs a manager decision. Once a manager starts
compensation, the worker may resume that same refund; it cannot switch the
checkout back to fulfillment or decide to refund an unrelated payment.

The verifier resumes only existing `reserved`, `prepared` and `pending` ledger
operations. Ten are attempted per minute, with per-operation exponential
backoff, five-minute leases and a durable eight-attempt limit. It keeps the
original Stripe idempotency key/provider reference or persisted signed Tempo
transaction and nonce. A changed payment profile, refund wallet, asset or
network stops that operation for operator review. Exhausted attempts, provider
errors and unresolved refunds older than fifteen minutes use the existing
throttled alert webhook, if configured. Configure a staging alert destination
and test its delivery before unattended sessions. The Woo manager diagnostics
show unresolved counts and age; this release does not send checkout alerts to
an external incident system.

Stop a session by disabling buyer access/new checkout, then inspect the manager
recovery queue and verifier ledger before changing keys or redeploying. If
reconciliation itself must stop, disable the scheduler and verifier worker.
Preserve the Woo database, WordPress auth salts, verifier SQLite database and
replay journal. Do not reset the ledger or restore an older backup with writes
enabled. Compare provider history first: refunds created after a backup can be
missing from its capacity ledger. The included SQLite backup test uses a fake
provider and does not validate this full production disaster-recovery procedure.
