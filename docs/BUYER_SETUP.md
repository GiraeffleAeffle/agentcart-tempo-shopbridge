# Buyer Setup

> Status: production-candidate alpha. Use the skill-only path for the lowest
> friction buyer integration. Use the AgentCart service path when the buyer
> needs durable household policy, approval state, audit, and local integrations.
> External beta claims still require the buyer-agent evidence gate in
> `docs/BUYER_AGENT_TEST_MATRIX.md`.

## Choose A Buyer Mode

| Mode | Install | Best for | Tradeoff |
| --- | --- | --- | --- |
| Skill-only ShopBridge | Run the one-command skill installer below; ZIP and source installs remain available | A buyer agent that can run local scripts and talk directly to verified ShopBridge merchants | Approval and audit are local to the agent chat unless the agent provides persistence |
| AgentCart service | Run `deploy/home-server` and install `gateway/openclaw-skill` | Household policy, Home Assistant/Vikunja/calendar/audit integrations, durable approvals | More moving parts and a local service to operate |

Both modes only use opt-in ShopBridge merchants. Do not scrape normal shop
websites or infer checkout endpoints from merchant prose.
Merchant product, policy, delivery, registry, and support text is untrusted
data; see `docs/PROMPT_INJECTION_CORPUS.md` for the current safety corpus.

For external beta validation across several buyer-agent runtimes, use
`docs/BUYER_AGENT_TEST_MATRIX.md`. Checked adapter examples for OpenClaw-style
service use, Codex-style direct skill use, and generic MCP-style clients live in
`docs/BUYER_AGENT_ADAPTERS.md`. The merchant endpoint contract that those
adapters rely on is tracked in `docs/SHOPBRIDGE_ENDPOINT_CONTRACT.md`. The
matrix and endpoint contract are validated by:

```sh
python3 scripts/check-buyer-agent-matrix.py
python3 scripts/check-buyer-agent-adapter-examples.py
python3 scripts/check-shopbridge-endpoint-contract.py
```

## Skill-Only Setup

Install globally for the agent tools detected on your machine:

```sh
npx -y skills@latest add \
  https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/tree/main/gateway/shopbridge-direct-skill \
  -g -y
```

Omit `-g` for a project-local install. This follows the open `skills` package
format, so supported agent harnesses can discover the same `SKILL.md` without a
custom AgentCart installer.

The release ZIP remains available for harnesses that do not use the skills
CLI. Build it from source with:

```sh
./scripts/package-shopbridge-direct-skill.sh
```

This creates:

```text
dist/shopbridge-direct-skill.zip
```

The ZIP is only a download/transport archive. Its portable core is one
`shopbridge-direct-skill/` folder with the required `SKILL.md` and deterministic
JSON-in/JSON-out HTTP command helper in `scripts/shopbridge-command.py`. It also
includes optional Codex/OpenAI UI metadata in `agents/openai.yaml`; other
harnesses may ignore or remove that file. The core does not import it or call an
OpenAI API.

Harnesses that load skill folders can also import the extracted folder directly.
For a harness without native skill support, provide `SKILL.md` as the model's
workflow instructions and expose `scripts/shopbridge-command.py` as a local
process/tool using JSON over stdin/stdout. This is a thin harness adapter, not
an additional ShopBridge service.

Install by extracting the ZIP into the buyer agent's skills directory or tool
workspace. Source installs can copy this folder directly:

```text
gateway/shopbridge-direct-skill
```

The skill has no long-running service dependency. It needs `python3` and network
access to the configured EVM JSON-RPC endpoint, the record URIs committed by the
registry contract, and the merchant's ShopBridge origin.

A wallet is not required to install the skill, query the registry, search
catalogs, or compare country/postcode quotes. It is required only when a buyer
wants to continue to payment. `doctor.ok=true` therefore means discovery is
ready; it does not mean the machine has a wallet. The doctor reports that
separate state under `purchase_readiness`.

Its bundled HTTP transport rejects redirects and private/non-global DNS targets
for public URLs, pins each connection to the validated DNS result, and bounds
JSON responses. This applies to RPC, record, manifest, proof, catalog, quote,
checkout, and status requests.

For a known single merchant in local development, set:

```sh
export SHOPBRIDGE_BASE_URL=http://127.0.0.1:8098
export SHOPBRIDGE_ALLOW_PRIVATE_ORIGIN=1
```

Normal multi-merchant discovery needs no configuration. The buyer skill queries
the registry smart contract directly using:

```text
RPC: https://rpc.moderato.tempo.xyz
Chain: eip155:42431
Contract: 0x0965961617c5B0898167AA4034C5511dB0EfcA07
Deployment block: 30731101
```

It requests the RPC `finalized` head, reads the eligibility-changing contract
logs from the deployment block, and reconstructs current lifecycle state. It
then chooses a bounded set of active candidates and fetches only each selected
record's current `recordURI`; historical record documents do not have to remain
online. The skill checks the committed hash, controller/domain binding,
lifecycle projection, and the contract's current storage views at the verified
boundary. Only after that does it verify the merchant domain proof, manifest,
payment binding, freshness, and revocation document. Revoked, suspended,
incomplete, wrong-chain, wrong-contract, or unfinalized state fails closed.

To use a different deployment or RPC:

```sh
export SHOPBRIDGE_ONCHAIN_RPC_URL=https://rpc.example
export SHOPBRIDGE_ONCHAIN_CHAIN_ID=42431
export SHOPBRIDGE_ONCHAIN_REGISTRY_ADDRESS=0x...
export SHOPBRIDGE_ONCHAIN_FROM_BLOCK=30731101
# Optional for a standard historical RPC; mandatory with Myotis
export SHOPBRIDGE_ONCHAIN_DEPLOYMENT_BLOCK_HASH=0x...
export SHOPBRIDGE_ONCHAIN_RPC_PROFILE=auto
# Optional override; defaults: Ethereum 1800, Gnosis/Tempo 600 seconds
export SHOPBRIDGE_ONCHAIN_FINALITY_MAX_AGE_SECONDS=600
```

### Verified light-client RPC with Myotis

For a future registry deployment on Ethereum mainnet or Gnosis, the skill has a
fail-closed [Myotis](https://github.com/biafra23/myotis) transport profile so a
buyer can use a local verified light client instead of a hosted RPC or full
node. Myotis exposes the Ethereum JSON-RPC methods the skill needs and, on its
Rust engine, maintains an opt-in receipt-root-verified `eth_getLogs` index for
selected contracts.

There is one upstream blocker in Myotis commit
`1cc9f09a854846c20b0ca03b517f0ac6a0712ebd`: the Rust adapter parses
`finalizedBlockNumber`, but `RustChainHandle.beaconStatus()` currently exports
`executionBlockNumber` as `0`. The ShopBridge profile intentionally rejects
that with `myotis_finalized_block_unavailable`; it will not substitute the
optimistic head and call it finalized. The minimal Myotis fix is to populate
that `BeaconStatus` field from `s.finalizedBlockNumber()`. The latest inspected
pre-release, v0.1.7, also predates the generic log-index build commands below,
so pin a later fixed commit or release before treating this as usable.

Once that field is fixed, Myotis must know the exact registry contract and its
deployment block, and its log-index backfill must finish before discovery can
succeed. Following the current main-branch daemon interface, prepare Gnosis and
start the Rust daemon in one terminal:

```sh
./gradlew refreshCheckpoint -Pnetwork=gnosis
./gradlew :app:run -Pnetwork=gnosis -Pengine=rust
```

In a second terminal, build the index locally and wait for coverage to reach the
deployment block:

```sh
./gradlew :app:run -Pnetwork=gnosis \
  -Pargs="build-logindex 0xREGISTRY_CONTRACT --from DEPLOYMENT_BLOCK"
./gradlew :app:run -Pnetwork=gnosis -Pargs=logindex-status
```

Then configure the skill on the same machine:

```sh
export SHOPBRIDGE_ONCHAIN_RPC_URL=http://127.0.0.1:8546
export SHOPBRIDGE_ALLOW_PRIVATE_RPC=1
export SHOPBRIDGE_ONCHAIN_RPC_PROFILE=myotis
export SHOPBRIDGE_ONCHAIN_CHAIN_ID=100
export SHOPBRIDGE_ONCHAIN_REGISTRY_ADDRESS=0xREGISTRY_CONTRACT
export SHOPBRIDGE_ONCHAIN_FROM_BLOCK=DEPLOYMENT_BLOCK
export SHOPBRIDGE_ONCHAIN_DEPLOYMENT_BLOCK_HASH=0xINDEPENDENTLY_RECORDED_BLOCK_HASH
# Gnosis default: 600 seconds
export SHOPBRIDGE_ONCHAIN_FINALITY_MAX_AGE_SECONDS=600
```

For Ethereum mainnet, use Myotis network `mainnet`, loopback port `8545`, chain
id `1`, and the default 1800-second finalized-block age bound. The default
`auto` profile also detects Myotis, but explicitly setting `myotis` makes a
wrong local endpoint fail immediately. Myotis currently supports Ethereum
mainnet, Sepolia, and Gnosis, not Tempo; the current Moderato registry therefore
still uses its HTTPS RPC.

The deployment block hash is mandatory with Myotis. Record it independently
from the successful deployment receipt—ideally in an immutable deployment
manifest—before the block leaves Myotis's short historical-header window. For
an older deployment, verify it through an independent archival source. At run
time the skill does not ask Myotis for the ancient header: it matches the
pinned hash against the receipt-root-verified constructor
`OwnershipTransferred(address(0), owner)` log and requires log-index coverage
from that exact block.

The skill gets the actual finalized execution height from
`myotis_beaconStatus`, queries the verified log index only through that height,
and verifies current contract views at Myotis's newer verified head. A newer
revoke, suspension, controller change, or record update causes a conservative
failure until it finalizes; a newly registered merchant is simply omitted
until finality. Incomplete log-index coverage is an error, never an empty
merchant list.

This removes the trusted hosted-RPC/full-node requirement, not all local work:
Myotis still runs a P2P light client and stores a per-contract log index whose
size grows with that contract's logs. The HTTPS `recordURI` documents and
merchant endpoints remain offchain and must still be reachable. Pin and test a
specific Myotis release or commit before production because the project is
still evolving. Build the log index locally for the trustless path; do not treat
an imported portable snapshot as independently verified provenance.
Myotis binds its unauthenticated RPC to loopback intentionally. If the buyer
agent runs inside a container, `127.0.0.1` must be in the same network namespace
or connected through a narrowly scoped local bridge; do not expose the raw RPC
on a public interface.

To deliberately use a trusted hosted compatibility feed instead of querying a
contract:

```sh
export SHOPBRIDGE_REGISTRY_URL=https://registry.example/agentcart.json
```

If a local demo registry itself uses a private address or plain HTTP, set
`SHOPBRIDGE_ALLOW_PRIVATE_ORIGIN=1` as an explicit opt-in. Leave it unset for
normal public discovery.

For local/self-hosted testing without a public registry:

```sh
export SHOPBRIDGE_REGISTRY_PATH=/path/to/merchant-registry.json
```

For a deliberately offline run with no default RPC source, set
`SHOPBRIDGE_DISABLE_DEFAULT_REGISTRY=1`.

The prior hosted finalized-event format remains available as a compatibility
source:

```sh
export SHOPBRIDGE_ONCHAIN_REGISTRY_EVENTS_URL=https://registry.example/onchain-events.json
# or, for local tests:
export SHOPBRIDGE_ONCHAIN_REGISTRY_EVENTS_PATH=/path/to/onchain-events.json
```

Remote compatibility snapshots must be fresh, complete
`agentcart.onchain_registry_rpc_indexer.v1` documents capped at an RPC
`finalized` block. The direct skill validates record commitments and binds the
full `registry_record` to the snapshot chain, registry, controller, and record
ID, then applies the normal domain-proof, manifest, payment, freshness, and
revocation checks. Hosted snapshot generation has a 600-second default window,
configurable with `SHOPBRIDGE_ONCHAIN_REGISTRY_MAX_AGE_SECONDS`. Direct RPC
finality uses a separate chain policy: 1800 seconds on Ethereum mainnet and 600
seconds on Gnosis and Tempo, overridable per deployment with
`SHOPBRIDGE_ONCHAIN_FINALITY_MAX_AGE_SECONDS`. This prevents a frozen RPC from
keeping a revoked merchant eligible while still accepting Ethereum's normally
older finalized head. A finalized timestamp more than five minutes in the
future also fails closed.

The direct skill rejects records with missing/invalid timestamps, records dated
more than 10 minutes in the future, and records older than
`SHOPBRIDGE_REGISTRY_MAX_AGE_DAYS` days. The default is `180`; use `0` only for
local fixtures where you intentionally want to disable the freshness window.

If a merchant advertises the `signed-http-ready` profile and requires signed
requests, configure either the HMAC secret provided by that merchant or the RSA
private key whose public key was registered with the merchant. Use the profile's
`active_signer` value when it is present. The plugin only accepts legacy generic
signer labels for one-key private/demo installs; rotated or multi-key merchants
require the published signer id. Prefer RSA for public or multi-merchant setups
because the merchant never receives the buyer-side private key.

```sh
export SHOPBRIDGE_SIGNED_REQUEST_SECRET=replace-with-shopbridge-signing-secret
# or:
export SHOPBRIDGE_SIGNED_REQUEST_PRIVATE_KEY="$(cat /secure/path/agentcart-signer.pem)"
export SHOPBRIDGE_SIGNED_REQUEST_SIGNER=sig_active_signer_from_profile
```

Check the skill install and configuration first. This is read-only. It queries
the contract and committed record URI but does not call merchant manifest,
catalog, quote, or checkout endpoints unless verification/probing is requested:

```sh
python3 gateway/shopbridge-direct-skill/scripts/shopbridge-command.py <<'JSON'
{"command":"doctor","args":{"format":"toon"}}
JSON
```

If the buyer intends to order, inspect the payment side before promising a
checkout or asking for approval:

```sh
python3 gateway/shopbridge-direct-skill/scripts/shopbridge-command.py <<'JSON'
{"command":"payment_readiness","args":{"payment_rail":"tempo-mpp","format":"toon"}}
JSON
```

This command never invokes `npx`, `mppx`, a wallet, or a provider. An installed
launcher or `SHOPBRIDGE_MPP_ACCOUNT` label does not prove a wallet exists. If
the buyer already has a configured payment account, use that account. With
`SHOPBRIDGE_MPP_ACCOUNT` omitted, the demo adapter leaves account selection to
the payment client's existing default. Never create a wallet, install payment
software, switch accounts, or import/export keys without explicit buyer
permission.

Smoke test a known merchant:

```sh
python3 gateway/shopbridge-direct-skill/scripts/shopbridge-command.py <<'JSON'
{"command":"readiness","args":{"base_url":"http://127.0.0.1:8098","format":"toon"}}
JSON
```

For a configured registry, verify merchant domain proofs before discovery:

```sh
python3 gateway/shopbridge-direct-skill/scripts/shopbridge-command.py <<'JSON'
{"command":"doctor","args":{"verify_merchants":true,"format":"toon"}}
JSON
```

Quote and approval packet:

```sh
python3 gateway/shopbridge-direct-skill/scripts/shopbridge-command.py <<'JSON'
{"command":"quote","args":{"base_url":"http://127.0.0.1:8098","product_id":"woo_10","quantity":1}}
JSON
```

For groceries, prefer whole-basket discovery:

```sh
python3 gateway/shopbridge-direct-skill/scripts/shopbridge-command.py <<'JSON'
{"command":"discover_basket_quotes","args":{"basket":[{"query":"tea","quantity":1},{"query":"filters","quantity":2}],"country":"DE","postal_code":"10115","payment_rail":"stripe-card-mpp","format":"toon"}}
JSON
```

That command uses direct onchain discovery by default. Alternatively, configure
`SHOPBRIDGE_REGISTRY_URL` or `SHOPBRIDGE_REGISTRY_PATH`, or pass
`registry_records`, `registry_url`, or `registry_path` in the command args for
explicit compatibility/offline tests. Those sources can be a feed with
`entries[]`, a single registry record, or a ShopBridge registry bundle from:

```text
https://shop.example/.well-known/agentcart-registry-bundle.json
```

Discovery sends only country/postcode to candidate merchants. Its winning
quote is therefore a comparison quote and returns `approval_ready:false` until
the full delivery address is present. After selecting a merchant, ask the buyer
for the missing delivery fields and request a fresh quote from only that
verified origin. Never invent a recipient name or street address, and never
reuse the comparison quote's approval hash after refreshing it.

Checkout safety:

- Always create or inspect an `approval_packet` before checkout.
- Do not request approval when `approval_ready:false`. Refresh the selected
  merchant's quote with the complete delivery address first.
- Inspect `financial_readiness` and show the tax lines. A quote whose
  tax-inclusion metadata does not reconcile with its total must be refreshed;
  the agent must not silently add or discard tax.
- Run `payment_readiness` before requesting approval. Discovery readiness and
  merchant checkout readiness do not prove that the buyer has a usable wallet
  or payment provider.
- Do not call `checkout` until the human approves the exact merchant, items,
  total, delivery window, quote hash, and payment destination.
- Store the returned `approval_record`/`approval_record_hash` when the buyer
  agent supports durable memory. In skill-only mode this is the portable proof
  of the approval contract that was shown to the human.
- After approval, call `payment_handoff` to get the structured payment request
  for the wallet, payment-capable agent, or provider. The request is not a
  secret and does not move money; it says exactly which rail, amount, currency,
  quote hash, approval record, and merchant profile/recipient the resulting
  receipt must bind.
- Pass only the resulting quote-bound `payment_receipt` to `checkout`.
- Preserve the checkout `audit_packet` when available. It hash-links the
  approval decision, payment receipt, and checkout payload for later household
  audit import.
- The direct skill rejects underspecified supplied receipts. Do not rely on the
  skill to fill amount, currency, quote hash, destination, or transaction
  reference from the quote.
- Treat aftercare actions such as refund or cancellation as request drafts
  unless the buyer is using a trusted AgentCart gateway with merchant
  authorization. ShopBridge cancellation changes Woo order state only; paid
  orders still need a separate rail-verified refund.
- Production checkout must supply a verifier/payment receipt explicitly bound
  to amount, currency, quote hash, merchant recipient/profile, and transaction
  reference or credential.
- The Tempo demo proof is sandbox/testnet proof, not production EUR settlement.

Audit import into an AgentCart service:

If the buyer later runs the AgentCart service, import the skill-only checkout
packet through the direct skill:

```sh
printf '%s\n' '{"command":"audit_import","args":{"checkout_payload":{...}}}' \
  | AGENTCART_URL=http://localhost:8099 \
    AGENTCART_TOKEN=replace-with-random-agentcart-token \
    python3 gateway/shopbridge-direct-skill/scripts/shopbridge-command.py
```

The command extracts `checkout_payload.audit_packet`, verifies
`audit_packet_hash` locally, and posts it to `/v1/audit/import`. The service
also verifies the hash and ignores duplicate imports with the same packet hash.

The imported trail is then visible in the dashboard audit table and can be
exported as JSON with:

```sh
curl -sS "$AGENTCART_URL/v1/audit/<quote_id>/export" \
  -H "X-AgentCart-Token: $AGENTCART_TOKEN"
```

Skill-only production sequence:

```text
resolve_merchant -> catalog/quote -> approval_packet -> human approval
  -> store approval_record -> payment_handoff -> external payment receipt
  -> checkout/audit_packet -> order_status
```

`resolve_merchant` must reject stale records, failed domain proofs, off-domain
endpoints, and matching merchant-hosted revocation documents. Direct discovery
uses a bounded query-seeded sample before merchant HTTP calls; use
`merchant_domain` or the public onchain `record_id` for an exact lookup when a
merchant is not in the current sample.

## AgentCart Service Setup

Use the home-server package when the buyer wants durable state and integrations:

```sh
cd deploy/home-server
cp .env.example .env
docker-compose up -d --build
```

Open:

```text
http://localhost:8099/auth/login
http://localhost:8088/chat
```

Submit the `AGENTCART_TOKEN` value from `.env` through the login form. The
browser receives a derived HttpOnly session cookie rather than the service
token.

Install the service-backed agent skill from:

```text
gateway/openclaw-skill
```

Configure the agent environment:

```sh
AGENTCART_URL=http://localhost:8099
AGENTCART_TOKEN=replace-with-random-agentcart-token
```

For OpenClaw-style deployments, the helper also reads:

```text
/etc/openclaw/agentcart.env
```

## Local Merchant For Independent Testing

A tester can run the optional WooCommerce demo shop without your homelab:

```sh
scripts/woocommerce-demo-smoke.sh
```

That command starts the demo WooCommerce stack, seeds products/tax/shipping, and
verifies the public ShopBridge manifest, catalog, and WooCommerce-backed quote
totals. Manual startup is also available:

```sh
cd deploy/home-server
cp .env.example .env
docker-compose --profile woocommerce-demo up -d --build
docker-compose --profile woocommerce-demo run --rm woocommerce-seed
```

Then install or activate the packaged plugin:

```text
dist/agentcart-shopbridge.zip
```

Open the local ShopBridge endpoints:

```text
http://localhost:8098/.well-known/agentcart.json
http://localhost:8098/wp-json/agentcart/v1/catalog
```

## Network Notes

Defaults bind to `127.0.0.1`. For LAN or Tailscale testing, change the relevant
`*_HOST_BIND` values in `deploy/home-server/.env` to `0.0.0.0` or a specific
interface. Do not expose the demo stack publicly without a real payment
verifier, TLS, host-level rate limits, and merchant legal review.
