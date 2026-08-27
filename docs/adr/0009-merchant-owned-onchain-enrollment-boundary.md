# ADR 0009: Merchant-Owned Onchain Enrollment Boundary

## Status

Accepted for the supervised testnet merchant pilot.

## Context

The registry contract already supports deterministic merchant records,
controller-only updates, and controller-only revocation. The remaining merchant
journey was fragmented: WordPress could publish a mutable onboarding bundle but
could not retain an immutable record URI, public onchain identity was available
only through deployment constants, and the operator required raw hashes and
contract identifiers. WordPress also treated local HTTPS proof as registry
readiness even when no finalized contract record existed.

Putting a controller private key in WordPress would make installation look
simple while moving registry authority into the largest and most exposed
merchant runtime. Making AgentCart the controller for every merchant would
remove merchant ownership. Treating a hosted-registry HTTP response as onchain
registration would conflate a compatibility service with the contract source of
truth established by ADR 0007.

## Decision

Split enrollment into four explicit authorities:

1. The ShopBridge Plugin owns public merchant metadata. It publishes the
   current onboarding bundle and retains every Registry Record at the
   content-addressed merchant path
   `/.well-known/agentcart-registry-records/<sha256>.json`.
2. The enrollment operator owns deterministic preparation and finalized
   verification. It accepts a deployment id, bundle URL, and public controller
   address rather than merchant-computed hashes or calldata.
3. The Registry Controller owns transaction approval and signing in an external
   wallet or isolated operator signer. Its private key, seed phrase, wallet
   session, and signature never enter WordPress, a registry service, a plan, or
   support diagnostics.
4. The Hosted Registry remains a cache, archive, monitor, and compatibility
   surface. Its submission response is not proof of contract inclusion.

Enrollment is a two-phase prepare flow. The first prepare call derives the
domain hash and either computes the first-registration record id or reads the
existing stable domain mapping, then returns four public WordPress
settings: controller, CAIP-2 chain id, registry contract, and record id. After
the merchant saves those settings, the record hash changes to bind that public
identity. The second prepare call verifies the merchant-hosted immutable record,
reads the finalized contract state, selects `register` or `update`, simulates the
write, and emits a secret-free `eth_sendTransaction` request.

Mutation plans are valid for 30 minutes. Their typed acknowledgement includes
an intent hash over the pinned deployment and runtime hash, controller, domain,
record id, record hash/URI or revoke reason, exact zero-value calldata,
finalized current-state precondition, and expiry. Execution recomputes that
intent, rechecks deployment code at the creation boundary and finalized head,
re-fetches the immutable record, and rechecks the finalized domain mapping,
controller, status, and current hash immediately before signing. The operator
has no free-form register/update/revoke commands. Its isolated signer writes a
mode-0600 transaction-hash journal immediately after broadcast and treats every
later error as `submitted_unverified`, which must be verified rather than
blindly retried.

A saved plan may prepare controller revocation even when the shop is offline.
`verify` requires the external-wallet transaction hash and proves its successful
canonical finalized receipt, sender, target, zero value, exact plan calldata,
and resulting registry state. WooCommerce may display `Finalized` only after
its pinned read-only RPC verifier captures one fresh finalized block hash and
uses EIP-1898 `requireCanonical` selectors for every state read. It checks the
deployment block and creation boundary, runtime code, Ethereum Keccak hash of
the normalized shop hostname, controller, stable domain-mapped record id,
record hash, active status, and non-revocation. The
result removes dependence on the Hosted Registry but still trusts the pinned
Tempo RPC. Hosted health and event documents remain explicitly labeled operator
snapshots and cannot set public discovery readiness. A merchant-id-only match,
local domain proof, or successful hosted submission is insufficient.

The Tempo Moderato deployment descriptor pins chain `eip155:42431`, contract
`0x0965961617c5B0898167AA4034C5511dB0EfcA07`, deployment block `30731101`, and
deployment block hash
`0x8646ecbbb11ac5cf6195dd7e288acb2541f02ef0d580e3bc9afa2e42045edd26`.
The descriptor also pins runtime bytecode hash
`0x6ef95b4471732ea43ea30a6a6f40117e117357a7291587e66b13d824f83509a4`,
requires code at the deployment block and no code at the preceding block, and
rejects a stale or future-dated finalized head.
Production-network mutation remains governed by ADR 0008 and is not approved by
this decision.

The Registry Controller, merchant Payment Recipient, and buyer Payment Wallet
are distinct roles even when a pilot operator temporarily controls more than
one of them.

## Consequences

Positive consequences:

- a merchant can complete public identity configuration from WordPress without
  editing `wp-config.php`;
- historical contract events remain replayable after merchant settings change;
- register and update use the same high-level preparation command;
- revocation remains possible from a retained plan during a shop incident;
- WordPress and the Hosted Registry cannot claim finalized inclusion from
  weaker evidence;
- an external wallet can review the exact chain, contract, controller, domain,
  hash, URI, and calldata before signing.

Costs and limitations:

- the first pilot is supervised because the generic EIP-1193 request still
  needs a compatible wallet or isolated signer adapter;
- uninstalling or disabling the plugin can make merchant-hosted historical
  records unavailable, so a separately operated append-only archive remains a
  production availability requirement;
- a merchant metadata change requires an onchain update and another finalized
  health check;
- controller backup, rotation, and recovery need explicit merchant operations;
- the current testnet contract lacks atomic expected-current-hash mutation
  methods, so pilot operations must serialize writes per controller; a
  production successor must enforce the expected state in the transaction;
- this does not approve a production chain, production governance, or real-money
  payment rail.

## Alternatives Considered

### Store the controller key in WordPress

Rejected because plugin or WordPress compromise would become registry-control
compromise, and ordinary support exports or backups could expose the key.

### Let AgentCart control every merchant record

Rejected because the merchant could not independently update or revoke its
identity and AgentCart would become a custodial registry gatekeeper.

### Keep the mutable onboarding bundle as `recordURI`

Rejected because old event commitments would no longer resolve to the committed
record after any stable merchant setting changed.

### Treat hosted submission as registration

Rejected because an HTTP acceptance response says nothing about contract
execution, finality, controller identity, or the current committed hash.

### Require merchants to compute raw hashes and calldata

Rejected because it is error-prone, difficult to audit, and needlessly exposes
contract internals in the normal merchant journey.

## References

- [ADR 0007](0007-onchain-registry-source-of-truth.md)
- [ADR 0008](0008-registry-network-and-governance-rollout.md)
- [Merchant setup walkthrough](../MERCHANT_SETUP_WALKTHROUGH.md)
- [Merchant registry](../MERCHANT_REGISTRY.md)
