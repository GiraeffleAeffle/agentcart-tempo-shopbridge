# Merchant Registry And Discovery

> Status: alpha implemented. A read-only public discovery feed is live for the
> two staging merchants and advertises a finalized Tempo Moderato event feed.
> The USD staging merchant is active through an onchain record commitment; the
> EUR staging merchant remains curated/offchain. Gateway and Direct Skill use
> the same claim/domain/payment/shipping/revocation and onchain lifecycle checks
> before admitting a merchant.

AgentCart's registry should be an identity and integrity anchor, not an ad
marketplace and not a product catalog.

Standards direction: this off-chain record shape should stay compatible with a
future ERC-8004-style registration file for ShopBridge merchants or hosted
service providers. The registry should identify and validate merchant endpoints;
it should not require public registration of a household's private shopping
agent.

## Public Pilot Deployment

The public pilot discovery plane is available at:

```text
https://registry.agentcart.eu/v1/registry/records
```

It is a small, stateless, read-only deployment of
`charts/agentcart-shopbridge-registry/`. It currently publishes the EUR and USD
staging merchants and accepts only `GET` and `HEAD`. The buyer skill verifies
each record against the merchant's HTTPS manifest, domain proof, and revocation
document before using it. Merchant enrollment during this phase is a reviewed,
maintainer-curated chart update; there is no public self-service submission API.

The same hostname continues to serve the OCI Distribution registry at `/v2/`.
The ShopBridge chart owns only `/`, `/registry`, and `/v1/registry...`, so the
two registry meanings remain separate at the ingress boundary.

This deployment intentionally does not claim stronger trust than it provides:

- it has no database or durable append-only transparency log;
- the curated feed itself is not signed; every record is checked against
  merchant-hosted proof and revocation material, and only the USD record is
  additionally committed to the Tempo testnet contract;
- Tempo Moderato is a trusted-operator testnet pilot, not production governance;
- Ethereum remains `not_deployed`, while `/v1/registry/onchain` reports the
  Moderato contract as `testnet_only` with its finalized event URL.

The controller-bound proof, fail-closed indexer, immutable archive,
register/revoke/recover drill, and opt-in independent-RPC comparison/alert
mechanism are complete. Before any production deployment, activate that
mechanism with an independently operated full-history witness and real alert
receiver, complete source publication and independent security review, collect
non-maintainer pilots, and make the chain/upgrade/governance decision in ADRs
0007 and 0008.

## Goals

- Let agents discover shops that support AgentCart ShopBridge.
- Let shops publish a stable manifest URL.
- Let agents verify that a manifest has not been silently swapped.
- Avoid publishing household demand, addresses, private shopping tasks, or live
  catalog data on-chain.
- Keep merchant-provided product and support text as untrusted data. A registry
  can prove identity and integrity, but it cannot make catalog text safe to
  follow as instructions.

## Registry Record

```json
{
  "merchant_id": "tea-shop.example",
  "domain": "shop.example",
  "manifest_url": "https://shop.example/.well-known/agentcart.json",
  "registry_claim_hash_alg": "sha-256",
  "registry_claim_hash": "abc123...",
  "supported_protocols": ["agentcart-shopbridge", "mpp-http-auth"],
  "protocol_profile_ids": ["agentcart-shopbridge", "mpp-http-auth", "erc8004-ready"],
  "onchain_identity": {
    "standard": "ERC-8004",
    "controller": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "chain_id": "eip155:8453",
    "registry_address": "0x2222222222222222222222222222222222222222",
    "record_id": "0x4444444444444444444444444444444444444444444444444444444444444444",
    "agent_id": "agentcart:tea-shop.example",
    "registration_uri": "https://shop.example/.well-known/agentcart.json"
  },
  "payment_network": "tempo-testnet",
  "payment_recipient": "0x...",
  "ship_to_countries": ["DE", "AT"],
  "updated_at": "2026-06-18T00:00:00Z",
  "revoked_at": null,
  "revocation_url": "https://shop.example/.well-known/agentcart-registry-revocations.json",
  "signature_alg": "https-domain-proof",
  "signature": "",
  "proof": {
    "type": "https-well-known",
    "url": "https://shop.example/.well-known/agentcart-registry-proof.json"
  }
}
```

## On-Chain vs Off-Chain

Put on-chain or in a public append-only registry:

- merchant id
- domain
- manifest URL
- registry claim hash
- payment network/recipient
- update timestamp
- revocation pointer

Keep off-chain:

- products
- stock
- prices
- quotes
- delivery estimates
- buyer intent
- household location
- shopping tasks

The executable adapter contract for this boundary lives at
`docs/fixtures/registry/onchain-adapter-contract.json`, with a prose explainer in
`docs/ONCHAIN_MERCHANT_REGISTRY_ADAPTER.md`. The gateway-hosted registry remains
an alpha indexer/cache and monitor for this shape; it should not become the
final source of truth for public discovery.

## Ranking Rules

The registry should not rank by advertising spend. Ranking belongs to the
buyer-side agent and should be explainable:

```text
eligible merchants -> private quote requests -> payment readiness -> local policy/price/delivery ranking
```

If a marketplace relay later supports auctions, the auction should be
buyer-intent based and private by default. A public registry can help find
eligible merchants, but final bidding should not leak household demand broadly.

## Integrity Flow

1. Merchant publishes `/.well-known/agentcart.json`.
2. Merchant signs or publishes a proof for the canonical registry record and
   stable registry claim hash.
3. Agent fetches the registry record from an allowlisted off-chain feed or
   onchain registry.
4. Agent rejects stale records, records with `revoked_at`, or records listed in
   the merchant-hosted revocation document.
5. Agent verifies that `manifest_url` host matches the registered domain.
6. Agent fetches the manifest from the merchant domain.
7. Agent canonicalizes the stable registry claim inside the manifest and
   verifies its hash. Legacy records can still bind the full manifest hash.
8. If optional `onchain_identity` metadata is present, the agent validates its
   ERC-8004-style mapping shape and verifies that the manifest registry claim
   binds the same metadata.
9. Agent verifies the detached signature, merchant-domain proof, or future
   onchain proof over the registry record.
10. Agent verifies that payment recipient/network in the manifest matches the
    registry record.
11. Agent verifies that absolute catalog/quote endpoint URLs stay on the
    registered merchant domain.
12. Agent requests private catalog/quote data from the merchant endpoint.

The shared trust contract for these checks is
`agentcart.registry_trust_contract.v1`. Its reproducible fixture set lives in
`docs/fixtures/registry/trust-fixtures.json` and is consumed by the gateway
service, the ShopBridge Direct Skill, and the registry record CLI tool.

## Alpha Configuration

The local alpha supports an off-chain JSON registry source:

```env
AGENTCART_MERCHANT_REGISTRY_PATH=/data/merchant-registry.json
AGENTCART_MERCHANT_REGISTRY_URL=
AGENTCART_ONCHAIN_REGISTRY_EVENTS_PATH=
AGENTCART_ONCHAIN_REGISTRY_EVENTS_URL=
AGENTCART_ALLOW_PRIVATE_REGISTRY_URLS=false
AGENTCART_MERCHANT_REGISTRY_HMAC_SECRET=replace-with-shared-registry-secret
AGENTCART_REQUIRE_VERIFIED_REGISTRY=true
AGENTCART_MERCHANT_REGISTRY_MAX_AGE_DAYS=180
AGENTCART_HOSTED_REGISTRY_ENABLED=true
AGENTCART_HOSTED_REGISTRY_PATH=/data/hosted-merchant-registry.json
AGENTCART_REGISTRY_SUBMIT_TOKEN=replace-with-distinct-submit-token
AGENTCART_REGISTRY_FEED_PROOF_PRIVATE_KEY=
AGENTCART_REGISTRY_FEED_PROOF_SIGNER=agentcart-registry
AGENTCART_REGISTRY_FEED_PROOF_PUBLIC_KEY_URL=
AGENTCART_REGISTRY_FEED_PROOF_ANCHOR_URL=
AGENTCART_REGISTRY_FEED_PROOF_ANCHOR_CHAIN_ID=
AGENTCART_REGISTRY_FEED_PROOF_RETIRING_SIGNERS=
AGENTCART_REGISTRY_FEED_PROOF_ROTATION_DUE_AT=
AGENTCART_REGISTRY_MONITOR_INTERVAL_SECONDS=0
AGENTCART_REGISTRY_MONITOR_HISTORY_LIMIT=50
AGENTCART_REGISTRY_ALERT_WEBHOOK_URL=
AGENTCART_REGISTRY_ALERT_WEBHOOK_TOKEN=
AGENTCART_REGISTRY_ALERT_HOMEASSISTANT_ENABLED=false
AGENTCART_REGISTRY_ALERT_EMAIL_TO=
AGENTCART_REGISTRY_ALERT_EMAIL_FROM=
AGENTCART_REGISTRY_ALERT_SMTP_HOST=
AGENTCART_REGISTRY_ALERT_SMTP_PORT=587
AGENTCART_REGISTRY_ALERT_SMTP_USERNAME=
AGENTCART_REGISTRY_ALERT_SMTP_PASSWORD=
AGENTCART_REGISTRY_ALERT_SMTP_STARTTLS=true
AGENTCART_REGISTRY_ALERT_MIN_SEVERITY=warning
AGENTCART_REGISTRY_ALERT_INCLUDE_RESOLVED=true
```

`GET /v1/registry/records` exposes the raw hosted record feed plus revocations.
`POST /v1/registry/records` accepts ShopBridge admin submit/revoke requests,
strips any local snapshot documents from the submitted record, fetches the live
merchant manifest/proof/revocation URLs, verifies them with the same
domain-proof and manifest checks, stores the verified record, and refreshes the
agent-facing `GET /v1/registry` view. Embedded manifest/proof/revocation
snapshots are accepted only for local file feeds and reproducible fixture tests;
they are not a public hosted-registry trust source.
Each accepted submit, refresh, or revoke appends a hash-chained transparency
event. `GET /v1/registry/transparency` exports that log with sequence numbers,
previous event hashes, event hashes, source request hashes, record hashes, and
chain verification status so agents can audit registry continuity without
trusting mutable feed state alone.
`GET /v1/registry/feed-proof` returns a compact canonical payload hash over the
active record hashes, revoked record hashes, and current transparency-log head.
Operators and buyer agents can pin that hash between runs today. When
`AGENTCART_REGISTRY_FEED_PROOF_PRIVATE_KEY` is configured, the proof also
includes an RSA-SHA256 signature over a canonical signature payload. Optional
`AGENTCART_REGISTRY_FEED_PROOF_ANCHOR_URL` and
`AGENTCART_REGISTRY_FEED_PROOF_ANCHOR_CHAIN_ID` fields let operators publish the
same payload hash and transparency head as an external or onchain anchor without
putting catalog, quote, buyer, order, or payment data into the registry.
The response also includes `governance`, a machine-readable signer operations
block with the active signer, retiring signer ids from
`AGENTCART_REGISTRY_FEED_PROOF_RETIRING_SIGNERS`, optional
`AGENTCART_REGISTRY_FEED_PROOF_ROTATION_DUE_AT`, public-key/anchor publication
state, and stable `operator_actions` ids such as
`publish_feed_proof_public_key`, `publish_feed_proof_anchor`, and
`complete_feed_proof_key_rotation`.
`GET /v1/registry/health` summarizes verifier states, source errors, hosted
record/revocation counts, stale records, endpoint failures, and suggested
operator actions.
`POST /v1/registry/monitor/run` persists a health snapshot and computes
new/resolved alert deltas; `GET /v1/registry/monitor` returns the retained
snapshot history. The optional `AGENTCART_REGISTRY_MONITOR_INTERVAL_SECONDS`
scheduler can run the same monitor automatically.

Hosted registry submissions use `AGENTCART_REGISTRY_SUBMIT_TOKEN`
(`AGENTCART_HOSTED_REGISTRY_TOKEN` remains accepted as a legacy alias). When the
gateway binds outside loopback, startup fails unless this submit token is set
and distinct from the broad `AGENTCART_TOKEN`.

Monitor alert delivery is opt-in. When `AGENTCART_REGISTRY_ALERT_WEBHOOK_URL`
is set, AgentCart posts an `agentcart.registry_alert_notification.v1` JSON event
for new alerts and, by default, resolved alerts. The payload includes the
snapshot id, registry/health/monitor URLs, summary state, new alert objects, and
resolved alert objects. `AGENTCART_REGISTRY_ALERT_WEBHOOK_TOKEN` is sent as a
Bearer token. Set `AGENTCART_REGISTRY_ALERT_MIN_SEVERITY` to `info`, `warning`,
or `critical` to control noise, and set
`AGENTCART_REGISTRY_ALERT_INCLUDE_RESOLVED=false` if only new alerts should
notify.

If `AGENTCART_REGISTRY_ALERT_HOMEASSISTANT_ENABLED=true`, AgentCart also sends a
compact Home Assistant notification through the configured `HOMEASSISTANT_URL`,
`HOMEASSISTANT_TOKEN`, and `HA_NOTIFY_SERVICES`.

If `AGENTCART_REGISTRY_ALERT_EMAIL_TO`,
`AGENTCART_REGISTRY_ALERT_EMAIL_FROM`, and
`AGENTCART_REGISTRY_ALERT_SMTP_HOST` are set, AgentCart sends the same new and
resolved alert summary through SMTP. `AGENTCART_REGISTRY_ALERT_EMAIL_TO` accepts
a comma-separated recipient list. SMTP username/password and STARTTLS are
optional so pilots can use either an authenticated provider or a local relay.
The email body contains public merchant registry metadata only.

The monitor JSON, registry page, and ShopBridge WordPress admin registry health
panel show whether alert delivery was skipped, sent, partial, or failed. The
monitor JSON also exposes `alert_delivery_metrics` with delivery counts by
state, per-sink sent/failed counters, the latest delivery summary, and a
`consecutive_problem_count`/`needs_attention` signal for failed or partial alert
delivery streaks.

`hmac-sha256` remains available for private/local feeds, but it is an
implementation shortcut. Public trust should use a merchant-owned proof such as
`https-domain-proof`, merchant wallet signatures, DNS/DID proofs, or an onchain
registry event while keeping the same verified record shape for agents.

## Merchant-Owned Domain Proof

The dependency-light production step is `signature_alg:
https-domain-proof`. The registry record points to a proof document hosted on
the registered merchant domain under `/.well-known/`:

```json
{
  "merchant_id": "tea-shop.example",
  "domain": "shop.example",
  "manifest_url": "https://shop.example/.well-known/agentcart.json",
  "registry_claim_hash": "abc123...",
  "payment_network": "tempo-testnet",
  "payment_recipient": "0x...",
  "updated_at": "2026-06-18T00:00:00Z",
  "revocation_url": "https://shop.example/.well-known/agentcart-registry-revocations.json",
  "controller": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "chain_id": "eip155:8453",
  "registry_address": "0x2222222222222222222222222222222222222222",
  "record_id": "0x4444444444444444444444444444444444444444444444444444444444444444",
  "record_hash": "def456..."
}
```

`record_hash` is the canonical JSON hash of the registry record, excluding
runtime-only fields such as `signature`, `verification`, and local test
snapshots. AgentCart requires the proof URL to be HTTPS, to stay on the
registered merchant domain, and to use a `/.well-known/` path. It rejects
mismatched record hashes. If the record claims an onchain registry identity,
the proof must also bind the domain to the onchain `controller`, `chain_id`,
`registry_address`, and `record_id`; this prevents a public merchant bundle
from being copied and registered under an attacker's controller. This proves
control of the shop domain without adding a crypto dependency to the gateway.
Wallet signatures can be added later as another verifier behind the same proof
seam.

The WooCommerce ShopBridge plugin exposes this proof at
`/.well-known/agentcart-registry-proof.json`. It automatically maintains the
claim hash, record hash, `updated_at` timestamp, and revocation URL from stable
settings, so merchants do not paste registry hashes during normal onboarding.
When configured with `AGENTCART_REGISTRY_ONCHAIN_CONTROLLER`,
`AGENTCART_REGISTRY_ONCHAIN_CHAIN_ID`, `AGENTCART_REGISTRY_ONCHAIN_ADDRESS`,
and `AGENTCART_REGISTRY_ONCHAIN_RECORD_ID`, the plugin also publishes the
controller-bound onchain identity fields in both the registry claim and proof.
The admin page also provides a manual refresh action for the generated registry
metadata and a public endpoint check that fetches the manifest, proof,
revocation document, and registry bundle before a merchant asks a registry to
ingest the shop.

The plugin also publishes `/.well-known/agentcart-registry-bundle.json`, which
contains the same `registry_record`, `record_hash`, expected proof document,
empty revocation document, and a one-entry `registry_feed`. A central registry,
self-hosted registry, or local buyer-agent test can ingest that bundle directly
instead of asking the merchant to run a helper script.

## Merchant-Owned Revocation

When a registry record includes `revocation_url`, AgentCart requires that URL to
be HTTPS, on the registered merchant domain, and under `/.well-known/`. The
current ShopBridge plugin publishes an empty revocation document by default:

```json
{
  "type": "agentcart-registry-revocations",
  "merchant_id": "tea-shop.example",
  "domain": "shop.example",
  "updated_at": "2026-06-18T00:00:00Z",
  "revocations": []
}
```

To revoke a bad or compromised record, the document can include the canonical
record hash:

```json
{
  "type": "agentcart-registry-revocations",
  "merchant_id": "tea-shop.example",
  "domain": "shop.example",
  "updated_at": "2026-06-18T01:00:00Z",
  "revocations": [
    {
      "record_hash": "def456...",
      "revoked_at": "2026-06-18T01:00:00Z"
    }
  ]
}
```

Buyer verifiers fail closed when the revocation pointer is invalid, unreachable,
off-domain, or lists the current record hash. Existing local/test records can
omit `revocation_url`, but public records should include it.

## Registry Record Helper

For current ShopBridge merchants, the lowest-friction path is to consume the
merchant's bundle:

```sh
curl https://shop.example/.well-known/agentcart-registry-bundle.json
```

The registry operator can also build records from the merchant manifest instead
of asking merchants to hand-write JSON or copy hashes. The helper uses the same
canonical JSON hashing and verifier code as the gateway:

```sh
python3 gateway/scripts/registry_record.py build \
  --manifest-url https://shop.example/.well-known/agentcart.json \
  --format bundle
```

The output contains:

- `registry_record`: the record to add to the public registry feed.
- `merchant_action`: whether the merchant needs to do anything. For current
  ShopBridge manifests this should be `none` because the plugin already
  publishes a matching proof.
- `proof_document_expected`: the proof document the shop should already publish.
- `legacy_merchant_settings`: paste-back settings only for legacy/non-ShopBridge
  manifests that do not publish an auto-managed registry claim.

To inspect the compact smart-contract-facing projection for the same merchant,
emit the onchain adapter shape:

```sh
python3 gateway/scripts/registry_record.py build \
  --manifest-url https://shop.example/.well-known/agentcart.json \
  --format onchain
```

If the registry record was already built or fetched from the merchant bundle,
project that existing record instead:

```sh
python3 gateway/scripts/registry_record.py project-onchain \
  --record-file merchant-registry-record.json
```

For append-only/onchain registry dry runs, write compact events to a JSONL
ledger and rebuild the index from that event stream:

```sh
python3 gateway/scripts/registry_record.py append-onchain \
  --ledger-file onchain-registry.jsonl \
  --operation upsert \
  --record-file merchant-registry-record.json

python3 gateway/scripts/registry_record.py index-onchain \
  --ledger-file onchain-registry.jsonl
```

The ledger stores the contract-facing projection and revoke events only; it does
not store products, prices, quotes, buyer demand, order payloads, or payment
receipts.

For smart-contract event dry runs, use the minimal interface fixture and replay
contract logs into the same indexed adapter shape:

```sh
python3 gateway/scripts/registry_record.py index-contract-events \
  --events-file docs/fixtures/registry/onchain-contract-events.json
```

The event fixture mirrors
`contracts/interfaces/IAgentCartMerchantRegistry.sol` and covers register,
attest, event-only flag, suspend, and unsuspend flows. The indexer fails closed
when a `MerchantRegistered` or `MerchantUpdated` log does not match the fetched
offchain record projection.

Production-facing event feeds use
`gateway/scripts/onchain-registry-indexer.mjs`. It reads only through the RPC
`finalized` block, records the finalized block hash and indexed range, fetches
record URIs without redirects or private-network access, verifies the record
commitment and controller-bound identity, and fails closed on any incomplete
event. The public records feed advertises the same-origin snapshot at
`onchain_events_url`; buyer skills consume it automatically.

The Direct Skill and gateway registry adapter use the portable
`shopbridge_safe_http.py` boundary for those public JSON requests. It rejects
redirects and non-global DNS results, pins connections to validated addresses,
and enforces bounded request/response sizes. Local/private targets require an
explicit development opt-in.

The public registry chart can produce that snapshot continuously with
`registry.onchainEvents.source=rpc_indexer`. Each pod runs an unprivileged
sidecar with no service-account token, validates the RPC chain against the
selected deployment descriptor, and atomically replaces the pod-local event
file only after a complete finalized replay. Transient failures preserve the
last good file; remote buyers reject it after 600 seconds. Static documents are
retained for fixtures and one-shot drills, not as the live operating mode.

Optional witness mode takes a second HTTPS RPC URL either directly or from an
existing Kubernetes Secret. The sidecar reconstructs both paths, compares
chain and registry identity, equal-height finalized block hashes, finality-time
lag, and canonical event hashes through the common finalized block, and
publishes only that independently matched range. Witness failure or divergence
preserves the prior snapshot. An optional Secret-backed webhook receives
redacted, throttled firing and resolved events; neither RPC URL is published.
The Helm values are documented in
`charts/agentcart-shopbridge-registry/README.md`.

The recurring indexer is deliberately full-replay for the supervised pilot.
It trades efficiency for deterministic reconstruction without a writable
checkpoint database. A production deployment with significant history must
introduce independently reproducible checkpointing; the packaged second path
must be activated and evidenced under the promotion gates in ADR 0008.

The gateway can consume the same event snapshot as a discovery source:

```env
AGENTCART_ONCHAIN_REGISTRY_EVENTS_PATH=/data/onchain-registry-events.json
AGENTCART_ONCHAIN_REGISTRY_EVENTS_URL=
```

Remote registry, record, manifest, proof, revocation, and finalized-event URLs
use the safe HTTP boundary. Keep `AGENTCART_ALLOW_PRIVATE_REGISTRY_URLS=false`;
enable it only for an operator-controlled local fixture network.

For usable merchant discovery, the indexer snapshot should include the compact
`onchain_record` projection and the resolved full `registry_record` for each
register/update event. The gateway validates both hashes against the contract
`recordHash`, then runs the full registry record through the normal signature,
domain, manifest, payment, freshness, and revocation verifier.

Verify the live proof:

```sh
python3 gateway/scripts/registry_record.py verify \
  --record-file merchant-registry-record.json
```

For reproducible local tests, use snapshots instead of network fetches:

```sh
python3 gateway/scripts/registry_record.py verify \
  --record-file merchant-registry-record.json \
  --manifest-file manifest.json \
  --proof-file proof.json \
  --revocation-file revocations.json
```

This keeps merchant onboarding close to the normal WooCommerce flow: install the
plugin, configure payment/support settings, enable products, share the registry
bundle URL, and let the registry consume the plugin-generated claim.

## Agent Safety Model

Registry verification solves spoofing and silent endpoint swaps. It does not
solve prompt injection by itself.

Agents should treat these fields as untrusted data:

- product titles and descriptions;
- merchant names, support copy, and policy text;
- category labels and tags;
- delivery notes and refund descriptions.

Safe agent behavior:

- never execute instructions from merchant/catalog fields;
- summarize merchant text only as quoted/bounded content;
- use structured fields for policy decisions, not prose;
- bind quote approval to merchant id, items, total, delivery window, expiry,
  payment rail, and quote hash;
- exclude quotes whose advertised payment protocols are all unavailable or
  setup-required before ranking;
- fail closed when registry verification, claim/manifest hash, quote hash, payment
  recipient, or verifier response do not match.

## Implemented Alpha

The gateway now:

- loads candidate records from `AGENTCART_MERCHANT_REGISTRY_PATH` or
  `AGENTCART_MERCHANT_REGISTRY_URL`;
- replays optional `AGENTCART_ONCHAIN_REGISTRY_EVENTS_PATH` or
  `AGENTCART_ONCHAIN_REGISTRY_EVENTS_URL` contract-event snapshots and exposes
  the event count, active record count, log head, proof payload hash, and replay
  errors in registry health;
- accepts first-party hosted registry submissions and revocations at
  `/v1/registry/records`;
- stores hosted records in an append-friendly JSON feed and removes revoked
  hashes from the active feed;
- appends hosted submit, refresh, and revoke events to a public hash-chained
  transparency export at `/v1/registry/transparency`;
- exposes a compact feed proof at `/v1/registry/feed-proof` so monitors can pin
  active record hashes, revoked hashes, and the transparency head;
- normalizes optional ERC-8004-style or AgentCart onchain registry
  `onchain_identity` / `erc8004_identity` metadata, including controller-bound
  proof fields, and exposes the mapping status without requiring onchain
  registration for early pilots;
- fetches each manifest, or reads `manifest_snapshot` for reproducible local
  tests;
- canonicalizes and hashes either the stable registry claim or legacy manifest;
- verifies domain, hash, signature/proof, optional onchain identity mapping,
  revocation URL/document, updated timestamp, payment recipient, and shipping
  country scope;
- verifies `hmac-sha256` private-feed records and `https-domain-proof`
  merchant-owned records;
- rejects absolute catalog/quote endpoint URLs outside the registered merchant
  domain;
- exposes `verification.state`, `verification.errors`, and manifest source;
- exposes `GET /v1/registry/health` for aggregate registry health, freshness
  warnings, source errors, and operator action items;
- persists authenticated registry monitor snapshots and new/resolved alert
  deltas, with an optional in-process scheduler;
- keeps the shared registry trust fixtures in
  `docs/fixtures/registry/trust-fixtures.json` so service, Direct Skill, and
  registry tool verifier behavior stays aligned;
- makes quote tournament exclude unverified external merchants by default.

Once that interface is stable, the source of records can move from local JSON or
a signed hosted feed to an onchain/append-only registry without changing buyer
or merchant adapters.

## Deferred Policy And Pilot Questions

- Registry identity updates are controller-authorized onchain changes paired
  with a new immutable HTTPS record and controller-bound domain proof. The
  remaining question is how much of that transaction flow should be sponsored
  for small merchants.
- Payment-recipient rotation uses the same new-record update and invalidates
  prior attestation state. A real merchant rotation and rollback still need to
  be captured as pilot evidence.
- Should there be a neutral allowlist for consumer-protection-compliant shops?
- How can small merchants stay discoverable without recreating ad-market
  dynamics?
