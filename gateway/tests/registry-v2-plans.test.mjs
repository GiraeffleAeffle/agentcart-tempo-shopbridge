import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { decodeFunctionData, decodeFunctionResult, encodeAbiParameters, keccak256, parseAbi, toBytes } from "viem";
import { registryRecordHash } from "../scripts/onchain-registry-indexer.mjs";
import { prepareRegistryV2Operation, registryV2Abi } from "../scripts/registry-v2-plans.mjs";

const hash = byte => `0x${byte.repeat(64)}`;
const actor = `0x${"11".repeat(20)}`;
const validator = `0x${"22".repeat(20)}`;
const token = `0x${"33".repeat(20)}`;
const registry = `0x${"44".repeat(20)}`;
const recordId = hash("5");
const zero = hash("0");
const domainHash = keccak256(toBytes("shop.example"));
const now = 1_800_000_000_000;
const runtime = "0x6000";
const deployment = {
  schema: "agentcart.onchain_registry_deployment.v1", registry_version: 2, id: "v2-fixture",
  rpc_url: "https://primary.example", witness_rpc_url: "https://witness.example",
  network_class: "testnet", chain_id: 42431, caip2: "eip155:42431", registry_address: registry,
  deployment_block: 100, deployment_block_hash: hash("a"), runtime_code_hash: keccak256(runtime),
  finality: { block_tag: "finalized", max_age_seconds: 600, max_future_skew_seconds: 120 }, mutation_policy: "pilot_enabled",
};
const document = { merchant_id: "shop.example", name: "Shop", domain: "shop.example", manifest_url: "https://shop.example/.well-known/agentcart.json",
  onchain_identity: { controller: actor, chain_id: deployment.caip2, registry_address: registry, record_id: recordId } };
const documentHash = `0x${await registryRecordHash(document)}`;
const recordUri = `https://shop.example/.well-known/agentcart-registry-records/${documentHash.slice(2)}.json`;

test("the shared registry ABI decodes the contract's full uint64 attestation generation", () => {
  const data = encodeAbiParameters([{ type: "address" }, { type: "bytes32" }, { type: "bytes32" },
    { type: "uint64" }, { type: "uint64" }, { type: "uint64" }, { type: "uint64" }, { type: "uint16" }, { type: "uint8" }],
    [actor, documentHash, domainHash, 1n, 0n, 0n, 2n ** 40n, 2, 1]);
  assert.equal(decodeFunctionResult({ abi: registryV2Abi, functionName: "record", data }).attestationGeneration, 2n ** 40n);
});

function fixture(options = {}) {
  const calls = [];
  const stored = { controller: actor, recordHash: documentHash, domainHash, status: 1 };
  const client = {
    async getChainId() { return options.chainId || 42431; },
    async getBlock({ blockNumber }) { return { number: blockNumber ?? 200n, hash: blockNumber === 100n ? hash("a") : hash("b"), timestamp: BigInt(now / 1000 - 30) }; },
    async getBytecode({ blockNumber }) { return blockNumber === 99n ? "0x" : options.runtime || runtime; },
    async readContract(call) {
      assert.equal(call.blockNumber, 200n);
      calls.push(call);
      const responses = {
        recordIdForDomain: options.existingId || zero, computeRecordId: recordId, record: stored,
        bondToken: token, minimumBond: 1000000n, allowance: options.allowance || 0n, balanceOf: options.balance ?? 10000000n,
        admission: [options.admitted !== false, hash("6"), BigInt(now / 1000 + 86400)],
        eligibility: [options.admitted !== false, hash("6"), BigInt(now / 1000 + 86400), 1000000n],
        bondExitAt: 0n, sanctions: [zero, zero, actor, 0n, 0n, false],
        validatorActionHash: hash("7"), attestationThresholdActionHash: hash("8"),
        supersession: { ...stored, controller: actor },
      };
      if (!Object.hasOwn(responses, call.functionName)) throw new Error(`unexpected_read:${call.functionName}`);
      return responses[call.functionName];
    },
    async simulateContract(call) {
      assert.equal(call.blockNumber, 200n);
      calls.push(call);
      if (options.revert) throw new Error(options.revert);
      return { result: options.approveResult ?? true };
    },
  };
  const prepare = (operation, parameters = {}, overrides = {}) => prepareRegistryV2Operation({
    deployment, publicClient: client, now: () => now, loadRecord: async () => document,
    request: { operation, actor, parameters }, ...overrides,
  });
  return { prepare, calls };
}

test("v2 identity preparation returns public settings without simulating a transaction", async () => {
  const { prepare, calls } = fixture();
  const plan = await prepare("identity", { domain: "shop.example" });
  assert.equal(plan.wordpress_settings.record_id, recordId);
  assert.equal(plan.domain_hash, domainHash);
  assert.equal(plan.wallet_request, null);
  assert.equal(calls.some(call => call.account), false);
  const existing = await fixture({ existingId: recordId }).prepare("identity", { domain: "shop.example" });
  assert.equal(existing.supersession_required, false);
});

test("v2 plans reject unknown deployments, code changes, arbitrary targets and unsafe amounts", async () => {
  const { prepare } = fixture();
  await assert.rejects(prepare("withdrawBond", { record_id: recordId }, { deployment: { ...deployment, registry_version: 1 } }), /v2_deployment/);
  await assert.rejects(fixture({ runtime: "0x6001" }).prepare("withdrawBond", { record_id: recordId }), /runtime_code_hash_mismatch/);
  await assert.rejects(prepare("transfer", {}), /unsupported/);
  await assert.rejects(prepare("approveBond", { to: actor }), /unexpected_operation_parameter/);
  await assert.rejects(prepare("proposeSlash", { record_id: recordId, amount_base_units: 9007199254740992, beneficiary: actor, case_hash: hash("7"), evidence_uri: "https://cases.example/1" }), /decimal_string/);
  await assert.rejects(prepare("identity", { domain: "shop.example" }, { deployment: { ...deployment, chain_id: 100 } }), /production_chain_mislabeled/);
});

test("status separates finalized eligibility, remaining bond and pending sanction without a wallet request", async () => {
  const { prepare, calls } = fixture({ admitted: false });
  const status = await prepare("status", { record_id: recordId });
  assert.equal(status.admission.eligible, false);
  assert.equal(status.admission.bond_base_units, "1000000");
  assert.equal(status.sanction.ready_at, "0");
  assert.equal(status.snapshot.block_number, "200");
  assert.equal(status.wallet_request, null);
  assert.equal(calls.some(call => call.account), false);
});

test("bond approval is limited to the registry's actual collateral requirement", async () => {
  const plan = await fixture().prepare("approveBond");
  const decoded = decodeFunctionData({ abi: parseAbi(["function approve(address spender, uint256 amount) returns (bool)"]), data: plan.transaction_request.data });
  assert.equal(plan.transaction_request.to, token);
  assert.deepEqual(decoded.args, [registry, 1000000n]);
  assert.equal(plan.evidence.bond.approval_base_units, "1000000");
  assert.equal(plan.transaction_request.value, "0x0");
  assert.equal(plan.required_ack.endsWith(plan.intent_hash), true);
  assert.equal(Date.parse(plan.expires_at) - Date.parse(plan.prepared_at), 1800000);
  const reset = await fixture({ allowance: 1n }).prepare("approveBond");
  assert.equal(reset.evidence.bond.approval_base_units, "0");
  await assert.rejects(fixture({ balance: 999999n }).prepare("approveBond"), /insufficient_bond_balance/);
  await assert.rejects(fixture({ allowance: 1000000n }).prepare("approveBond"), /already_sufficient/);
  await assert.rejects(fixture({ approveResult: false }).prepare("approveBond"), /approval_rejected/);
});

test("validator admission binds the public immutable document and includes no invented business verdict", async () => {
  const parameters = { domain_hash: domainHash, controller: actor, record_hash: documentHash, entity_id: hash("6"),
    expires_at: String(now / 1000 + 86400), evidence_hash: hash("7"), record_uri: recordUri };
  const { prepare, calls } = fixture();
  const plan = await prepare("voteAdmission", parameters, { request: { operation: "voteAdmission", actor: validator, parameters } });
  const decoded = decodeFunctionData({ abi: registryV2Abi, data: plan.transaction_request.data });
  assert.equal(decoded.functionName, "voteAdmission");
  assert.equal(decoded.args.length, 6);
  assert.equal(decoded.args[1], actor);
  assert.equal(plan.evidence.document.immutable_uri_verified, true);
  assert.equal(calls.at(-1).account, validator);
  assert.equal(plan.evidence.admission, undefined); // One vote does not assert quorum or business honesty.
  await assert.rejects(prepare("voteAdmission", { ...parameters, controller: validator }), /controller_mismatch/);
  await assert.rejects(prepare("voteAdmission", { ...parameters, record_uri: recordUri.replace("shop.example", "lookalike.example") }), /domain_or_uri_mismatch/);
  await assert.rejects(prepare("voteAdmission", { ...parameters, record_hash: hash("9") }), /hash_mismatch/);
});

test("registration requires both an unclaimed domain and current quorum admission", async () => {
  const parameters = { domain_hash: domainHash, record_hash: documentHash, record_uri: recordUri };
  const plan = await fixture().prepare("register", parameters);
  assert.equal(decodeFunctionData({ abi: registryV2Abi, data: plan.transaction_request.data }).functionName, "register");
  assert.equal(plan.evidence.admission.entity_id, hash("6"));
  await assert.rejects(fixture({ admitted: false }).prepare("register", parameters), /fresh_quorum/);
  await assert.rejects(fixture({ existingId: recordId }).prepare("register", parameters), /already_registered/);
  await assert.rejects(fixture({ revert: "BondUnavailable" }).prepare("register", parameters), /BondUnavailable/);
});

test("renewal checks the unchanged record's approval and preserves its identity", async () => {
  const plan = await fixture({ existingId: recordId }).prepare("renewAdmission", { record_id: recordId });
  assert.deepEqual(decodeFunctionData({ abi: registryV2Abi, data: plan.transaction_request.data }).args, [recordId]);
  await assert.rejects(fixture({ admitted: false }).prepare("renewAdmission", { record_id: recordId }), /fresh_quorum/);
});

test("case, amount, beneficiary and appeal evidence are explicit in each unsigned operation", async () => {
  const parameters = { record_id: recordId, amount_base_units: "600000", beneficiary: actor, case_hash: hash("8"), evidence_uri: "https://cases.example/42" };
  const { prepare } = fixture();
  const plan = await prepare("proposeSlash", parameters);
  assert.deepEqual(decodeFunctionData({ abi: registryV2Abi, data: plan.transaction_request.data }).args,
    [recordId, 600000n, actor, hash("8"), "https://cases.example/42"]);
  for (const operation of ["reviewAppeal", "executeSlash", "withdrawBond", "unsuspend"]) {
    const next = await prepare(operation, { record_id: recordId });
    assert.equal(decodeFunctionData({ abi: registryV2Abi, data: next.transaction_request.data }).functionName, operation);
  }
  const appeal = await prepare("appealSlash", { record_id: recordId, evidence_hash: hash("9") });
  assert.deepEqual(decodeFunctionData({ abi: registryV2Abi, data: appeal.transaction_request.data }).args, [recordId, hash("9")]);
  await assert.rejects(fixture({ revert: "InvalidSanction" }).prepare("executeSlash", { record_id: recordId }), /InvalidSanction/);
});

test("governance preparation computes exact scheduled actions and still simulates delayed execution", async () => {
  const { prepare } = fixture();
  const schedule = await prepare("scheduleValidator", { validator, enabled: true });
  assert.deepEqual(decodeFunctionData({ abi: registryV2Abi, data: schedule.transaction_request.data }), { functionName: "scheduleGovernanceAction", args: [hash("7")] });
  const pause = await prepare("schedulePause", { paused: true });
  assert.equal(pause.evidence.governance.action_hash, keccak256(encodeAbiParameters([{ type: "string" }, { type: "bool" }], ["pause", true])));
  await assert.rejects(fixture({ revert: "GovernanceActionNotReady" }).prepare("setValidator", { validator, enabled: true }), /GovernanceActionNotReady/);
});

test("the v2 CLI only prepares unsigned typed operations", () => {
  const help = spawnSync(process.execPath, ["scripts/registry-v2-operator.mjs", "--help"], { encoding: "utf8" });
  assert.equal(help.status, 0);
  assert.match(help.stdout, /never signs or broadcasts/);
  const execute = spawnSync(process.execPath, ["scripts/registry-v2-operator.mjs", "execute"], { encoding: "utf8" });
  assert.notEqual(execute.status, 0);
  assert.match(execute.stderr, /only prepare/);
});


test("identity exports WordPress bytecode pins from verified runtime without exposing them in merchant settings", async () => {
  const plan = await fixture().prepare("identity", { domain: "shop.example" });
  assert.equal(plan.wordpress_deployment.registry_version, 2);
  assert.equal(plan.wordpress_deployment.runtime_code_sha256, "f3df0a62b10f205b0f29768aa3d69e777154caaa179f64aabb0a4899c666b017");
  assert.equal(plan.wordpress_deployment.witness_rpc_url, deployment.witness_rpc_url);
  assert.equal(plan.wordpress_deployment.max_finality_age_seconds, 600);
  assert.deepEqual(Object.keys(plan.wordpress_settings).sort(), ["chain_id", "controller", "record_id", "registry_address"]);
});

test("WordPress deployment export rejects absent, unsafe or same-host witness endpoints", async () => {
  for (const url of [undefined, "http://witness.example", "https://primary.example/another", "https://127.0.0.1", "https://user:pass@witness.example", "https://witness.example:8443", "https://witness.example#",
    "https://@witness.example", "https://bad_host.example", "https://xn--bcher-kva.example"]) {
    await assert.rejects(fixture().prepare("identity", { domain: "shop.example" }, {
      deployment: { ...deployment, witness_rpc_url: url },
    }), /wordpress_(public_https_rpc_required|distinct_witness_required)/);
  }
});


test("WordPress export rejects finality policies outside the merchant verifier bounds", async () => {
  for (const finality of [{ ...deployment.finality, max_age_seconds: 601 },
    { ...deployment.finality, max_future_skew_seconds: 301 }]) {
    await assert.rejects(fixture().prepare("identity", { domain: "shop.example" }, {
      deployment: { ...deployment, finality },
    }), /wordpress_finality_policy_invalid/);
  }
});
