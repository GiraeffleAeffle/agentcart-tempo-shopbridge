// Read-only preparation. A wallet must review and submit each transaction.
import { createHash } from "node:crypto";
import { isIP } from "node:net";
import { encodeAbiParameters, encodeFunctionData, getAddress, keccak256, parseAbi, toBytes } from "viem";
import { merchantRegistryAbi, verifyMerchantRegistryDeployment } from "./merchant-registry-enrollment.mjs";
import { assertControllerBoundIdentity, fetchRegistryRecord, normalizedDomain, registryRecordHash } from "./onchain-registry-indexer.mjs";

export const registryV2Abi = [...merchantRegistryAbi, ...parseAbi([
  "function bondToken() view returns (address)",
  "function minimumBond() view returns (uint256)",
  "function admission(bytes32 domainHash, address controller, bytes32 recordHash) view returns (bool approved, bytes32 entity, uint64 expiresAt)",
  "function eligibility(bytes32 recordId) view returns (bool eligible, bytes32 entity, uint64 expiresAt, uint256 bond)",
  "function bondExitAt(bytes32 recordId) view returns (uint64)",
  "function sanctions(bytes32 recordId) view returns (bytes32 action, bytes32 reason, address beneficiary, uint256 amount, uint64 readyAt, bool appealed)",
  "function voteAdmission(bytes32 domainHash, address controller, bytes32 recordHash, bytes32 entity, uint64 expiresAt, bytes32 evidenceHash) returns (bytes32)",
  "function renewAdmission(bytes32 recordId)",
  "function setController(bytes32 recordId, address newController, bytes32 newRecordHash, string recordURI)",
  "function withdrawBond(bytes32 recordId)",
  "function proposeSlash(bytes32 recordId, uint256 amount, address beneficiary, bytes32 reason, string evidenceURI)",
  "function appealSlash(bytes32 recordId, bytes32 evidenceHash)",
  "function reviewAppeal(bytes32 recordId)",
  "function executeSlash(bytes32 recordId)",
  "function restoreEntity(bytes32 entity, bytes32 reason)",
  "function suspend(bytes32 recordId, bytes32 reasonHash)",
  "function unsuspend(bytes32 recordId)",
  "function requestSupersession(bytes32 domainHash, bytes32 recordHash, bytes32 reasonHash, string recordURI, string evidenceURI) returns (bytes32, uint64)",
  "function approveSupersession(bytes32 pendingRecordId, bytes32 recordHash, string evidenceURI) returns (uint64)",
  "function cancelSupersession(bytes32 pendingRecordId, bytes32 reasonHash)",
  "function activateSupersession(bytes32 pendingRecordId, string recordURI)",
  "function supersession(bytes32 pendingRecordId) view returns ((address controller, bytes32 domainHash, bytes32 previousRecordId, bytes32 recordHash, bytes32 reasonHash, uint64 requestedAt, address approvedBy, uint64 approvedAt))",
  "function validatorActionHash(address validator, bool enabled) view returns (bytes32)",
  "function attestationThresholdActionHash(uint16 threshold) view returns (bytes32)",
  "function scheduleGovernanceAction(bytes32 actionHash) returns (uint64)",
  "function cancelGovernanceAction(bytes32 actionHash)",
  "function setValidator(address validator, bool enabled)",
  "function setAttestationThreshold(uint16 threshold)",
  "function setWritesPaused(bool paused)",
  "function transferOwnership(address newOwner)",
  "function acceptOwnership()",
])];
const tokenAbi = parseAbi([
  "function allowance(address owner, address spender) view returns (uint256)",
  "function balanceOf(address account) view returns (uint256)",
  "function approve(address spender, uint256 amount) returns (bool)",
]);
const ZERO = `0x${"00".repeat(32)}`;
// Fields are in contract argument order. No arbitrary calldata, target, or value.
const operations = {
  identity: "domain:domain",
  status: "record_id:hash",
  voteAdmission: "domain_hash:hash controller:address record_hash:hash entity_id:hash expires_at:uint64 evidence_hash:hash record_uri:uri",
  register: "domain_hash:hash record_hash:hash record_uri:uri",
  update: "record_id:hash record_hash:hash record_uri:uri",
  setController: "record_id:hash new_controller:address record_hash:hash record_uri:uri",
  renewAdmission: "record_id:hash",
  revoke: "record_id:hash reason_hash:hash",
  approveBond: "",
  withdrawBond: "record_id:hash",
  proposeSlash: "record_id:hash amount_base_units:uint256 beneficiary:address case_hash:hash evidence_uri:uri",
  appealSlash: "record_id:hash evidence_hash:hash",
  reviewAppeal: "record_id:hash",
  executeSlash: "record_id:hash",
  restoreEntity: "entity_id:hash reason_hash:hash",
  suspend: "record_id:hash reason_hash:hash",
  unsuspend: "record_id:hash",
  requestSupersession: "domain_hash:hash record_hash:hash reason_hash:hash record_uri:uri evidence_uri:uri",
  approveSupersession: "record_id:hash record_hash:hash evidence_uri:uri",
  cancelSupersession: "record_id:hash reason_hash:hash",
  activateSupersession: "record_id:hash record_uri:uri",
  scheduleValidator: "validator:address enabled:bool",
  setValidator: "validator:address enabled:bool",
  scheduleThreshold: "threshold:uint16",
  setAttestationThreshold: "threshold:uint16",
  schedulePause: "paused:bool",
  setWritesPaused: "paused:bool",
  scheduleOwnership: "new_owner:address",
  transferOwnership: "new_owner:address",
  acceptOwnership: "",
  cancelGovernanceAction: "action_hash:hash",
};

export function registryV2Operations() { return { ...operations }; }
function field(value, type, key) {
  if (type === "domain") {
    if (typeof value !== "string" || !normalizedDomain(value)) throw new Error(`${key}_invalid`);
    return normalizedDomain(value);
  }
  if (type === "hash") {
    if (!/^0x[0-9a-fA-F]{64}$/.test(value || "") || value.toLowerCase() === ZERO) throw new Error(`${key}_invalid`);
    return value.toLowerCase();
  }
  if (type === "address") {
    const result = getAddress(value);
    if (/^0x0{40}$/i.test(result)) throw new Error(`${key}_invalid`);
    return result;
  }
  if (type === "bool") {
    if (typeof value !== "boolean") throw new Error(`${key}_invalid`);
    return value;
  }
  if (type.startsWith("uint")) {
    // Decimal strings avoid silent JSON precision loss for token amounts.
    if (typeof value !== "string" || !/^[1-9][0-9]*$/.test(value)) throw new Error(`${key}_must_be_positive_decimal_string`);
    const result = BigInt(value);
    if (result >= 2n ** BigInt(type.slice(4))) throw new Error(`${key}_out_of_range`);
    return result;
  }
  if (type === "uri") {
    const url = new URL(value);
    if (typeof value !== "string" || Buffer.byteLength(value) > 4096 || url.protocol !== "https:" || url.username || url.password) throw new Error(`${key}_invalid`);
    return value;
  }
  throw new Error("unsupported_field_type");
}
const serializable = value => JSON.parse(JSON.stringify(value, (_, item) => typeof item === "bigint" ? item.toString() : item));
const recordValues = stored => Array.isArray(stored)
  ? { controller: stored[0], recordHash: stored[1], domainHash: stored[2], status: Number(stored[8]) } : stored;

async function checkedDocument({ uri, hash, controller, domainHash, allowedIds, deployment, loadRecord }) {
  const document = await loadRecord(uri, hash);
  if (`0x${await registryRecordHash(document)}` !== hash) throw new Error("immutable_record_hash_mismatch");
  const domain = normalizedDomain(document.domain);
  const url = new URL(uri);
  if (!domain || keccak256(toBytes(domain)) !== domainHash || normalizedDomain(url.hostname) !== domain
    || url.port || url.search || url.hash || url.pathname !== `/.well-known/agentcart-registry-records/${hash.slice(2)}.json`) {
    throw new Error("immutable_record_domain_or_uri_mismatch");
  }
  const id = String(document.onchain_identity?.record_id || "").toLowerCase();
  if (!allowedIds.includes(id) || id === ZERO) throw new Error("immutable_record_identity_mismatch");
  assertControllerBoundIdentity(document, {
    chainId: deployment.chain_id, registryAddress: deployment.registry_address,
    controller, recordId: id, domainHash,
  });
  return { record_id: id, domain, record_hash: hash, record_uri: uri, immutable_uri_verified: true };
}

// Export only deployment configuration; this is never part of public merchant metadata.
async function wordpressDeployment(deployment, publicClient, snapshot) {
  if (deployment.deployment_block <= 0 || deployment.finality.max_age_seconds > 600
    || deployment.finality.max_future_skew_seconds > 300) throw new Error("wordpress_finality_policy_invalid");
  const host = value => {
    let url;
    try { url = new URL(value); } catch { throw new Error("wordpress_public_https_rpc_required"); }
    const authority = String(value).match(/^https:\/\/([^/?#]*)/);
    const labels = url.hostname.split(".");
    if (!authority || authority[1].includes("@") || String(value).includes("#")
      || url.protocol !== "https:" || url.username || url.password || url.hash || url.port
      || labels.length < 2 || url.hostname.length > 253 || isIP(url.hostname) || url.hostname.endsWith(".localhost")
      || labels.some(label => label.startsWith("xn--") || label.length > 63
        || !/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label))) {
      throw new Error("wordpress_public_https_rpc_required");
    }
    return url.hostname;
  };
  if (host(deployment.rpc_url) === host(deployment.witness_rpc_url)) throw new Error("wordpress_distinct_witness_required");
  const runtime = await publicClient.getBytecode({ address: getAddress(deployment.registry_address), blockNumber: snapshot.number });
  if (!runtime || keccak256(runtime).toLowerCase() !== deployment.runtime_code_hash.toLowerCase()) {
    throw new Error("registry_runtime_code_hash_mismatch");
  }
  return {
    registry_version: 2, id: deployment.id, chain_id: deployment.chain_id, caip2: deployment.caip2,
    registry_address: deployment.registry_address.toLowerCase(), deployment_block: deployment.deployment_block,
    deployment_block_hash: deployment.deployment_block_hash.toLowerCase(),
    runtime_code_sha256: createHash("sha256").update(Buffer.from(runtime.slice(2), "hex")).digest("hex"),
    rpc_url: deployment.rpc_url, witness_rpc_url: deployment.witness_rpc_url,
    max_finality_age_seconds: deployment.finality.max_age_seconds,
    max_future_skew_seconds: deployment.finality.max_future_skew_seconds,
  };
}

export async function prepareRegistryV2Operation({ request, deployment, publicClient, loadRecord = fetchRegistryRecord, now = () => Date.now() }) {
  if (deployment?.registry_version !== 2 || !["mainnet", "testnet"].includes(deployment.network_class)) throw new Error("registry_v2_deployment_required");
  if ([1, 100, 4217].includes(deployment.chain_id) && deployment.network_class !== "mainnet") throw new Error("production_chain_mislabeled");
  if (!request || Object.keys(request).some(key => !["operation", "actor", "parameters"].includes(key))) throw new Error("operation_request_invalid");
  if (!Object.hasOwn(operations, request.operation)) throw new Error("unsupported_registry_v2_operation");
  const actor = field(request.actor, "address", "actor");
  const specs = operations[request.operation].split(" ").filter(Boolean).map(item => item.split(":"));
  const parameters = request.parameters || {};
  if (typeof parameters !== "object" || Array.isArray(parameters)
    || Object.keys(parameters).some(key => !specs.some(([name]) => key === name))) throw new Error("unexpected_operation_parameter");
  const values = Object.fromEntries(specs.map(([key, type]) => [key, field(parameters[key], type, key)]));
  const preparedAt = now();
  const snapshot = await verifyMerchantRegistryDeployment(publicClient, deployment, { now: () => preparedAt });
  const registry = getAddress(deployment.registry_address);
  const read = (functionName, args = [], address = registry, abi = registryV2Abi) => publicClient.readContract({ address, abi, functionName, args, blockNumber: snapshot.number });
  const deploymentEvidence = { id: deployment.id, registry_version: 2, chain_id: deployment.chain_id, registry_address: registry,
    deployment_block: deployment.deployment_block, deployment_block_hash: deployment.deployment_block_hash, runtime_code_hash: deployment.runtime_code_hash };
  const boundary = { block_number: snapshot.number.toString(), block_hash: snapshot.hash, block_tag: "finalized" };
  if (request.operation === "status") {
    const [record, eligibility, exitAt, sanction] = await Promise.all([
      read("record", [values.record_id]), read("eligibility", [values.record_id]),
      read("bondExitAt", [values.record_id]), read("sanctions", [values.record_id]),
    ]);
    return serializable({ schema: "agentcart.registry_v2_status.v1", state: "finalized_snapshot", deployment: deploymentEvidence,
      record_id: values.record_id, record: recordValues(record),
      admission: { eligible: eligibility[0], entity_id: eligibility[1], expires_at: eligibility[2], bond_base_units: eligibility[3] },
      bond_exit_at: exitAt, sanction: { action_hash: sanction[0], case_hash: sanction[1], beneficiary: sanction[2], amount_base_units: sanction[3], ready_at: sanction[4], appealed: sanction[5] },
      snapshot: boundary, transaction_request: null, wallet_request: null });
  }
  if (request.operation === "identity") {
    const domainHash = keccak256(toBytes(values.domain));
    const currentId = await read("recordIdForDomain", [domainHash]);
    const current = currentId !== ZERO ? recordValues(await read("record", [currentId])) : null;
    const sameController = current && String(current.controller).toLowerCase() === actor.toLowerCase();
    const recordId = sameController ? currentId : await read("computeRecordId", [domainHash, actor]);
    return {
      schema: "agentcart.registry_v2_identity_plan.v1", state: "store_identity_required", ready: false,
      domain: values.domain, domain_hash: domainHash, supersession_required: currentId !== ZERO && !sameController,
      wordpress_settings: { controller: actor.toLowerCase(), chain_id: deployment.caip2, registry_address: registry.toLowerCase(), record_id: recordId },
      wordpress_deployment: await wordpressDeployment(deployment, publicClient, snapshot),
      deployment: deploymentEvidence, snapshot: boundary,
      next_step: "Have the operator install wordpress_deployment in wp-config or Helm. Store wordpress_settings in WooCommerce and publish its immutable registry bundle before requesting validator admission.",
      transaction_request: null, wallet_request: null,
    };
  }
  let functionName = request.operation;
  let args = Object.values(values);
  let target = registry;
  let abi = registryV2Abi;
  const evidence = {};

  if (["voteAdmission", "register", "requestSupersession"].includes(functionName)) {
    const controller = values.controller || actor;
    const [currentId, derivedId] = await Promise.all([
      read("recordIdForDomain", [values.domain_hash]), read("computeRecordId", [values.domain_hash, controller]),
    ]);
    evidence.document = await checkedDocument({ uri: values.record_uri, hash: values.record_hash, controller,
      domainHash: values.domain_hash, allowedIds: functionName === "voteAdmission" ? [currentId, derivedId] : [derivedId], deployment, loadRecord });
    if (functionName === "register" && currentId !== ZERO) throw new Error("domain_already_registered");
    if (functionName === "voteAdmission") args = args.slice(0, 6);
  } else if (["update", "setController"].includes(functionName)) {
    const stored = recordValues(await read("record", [values.record_id]));
    if (String(stored.controller).toLowerCase() !== actor.toLowerCase() || Number(stored.status) !== 1) throw new Error("active_controller_required");
    evidence.document = await checkedDocument({ uri: values.record_uri, hash: values.record_hash,
      controller: values.new_controller || actor, domainHash: stored.domainHash,
      allowedIds: [values.record_id], deployment, loadRecord });
  } else if (functionName === "activateSupersession") {
    const stored = await read("supersession", [values.record_id]);
    const pending = Array.isArray(stored) ? { controller: stored[0], domainHash: stored[1], recordHash: stored[3] } : stored;
    if (String(pending.controller).toLowerCase() !== actor.toLowerCase()) throw new Error("successor_controller_required");
    evidence.document = await checkedDocument({ uri: values.record_uri, hash: pending.recordHash,
      controller: actor, domainHash: pending.domainHash, allowedIds: [values.record_id], deployment, loadRecord });
  } else if (functionName === "approveBond") {
    const [token, minimum] = await Promise.all([read("bondToken"), read("minimumBond")]);
    target = field(token, "address", "bond_token");
    const [allowance, balance] = await Promise.all([
      read("allowance", [actor, registry], target, tokenAbi), read("balanceOf", [actor], target, tokenAbi),
    ]);
    if (minimum <= 0n || balance < minimum) throw new Error("insufficient_bond_balance");
    if (allowance >= minimum) throw new Error("bond_allowance_already_sufficient");
    // Some tokens require resetting a non-zero allowance before increasing it.
    const amount = allowance > 0n ? 0n : minimum;
    evidence.bond = { token: target, spender: registry, minimum_base_units: minimum, allowance_base_units: allowance,
      approval_base_units: amount, next_step: amount === 0n ? "Finalize this reset, then prepare approveBond again." : "Finalize approval, then prepare register or activateSupersession." };
    abi = tokenAbi;
    functionName = "approve";
    args = [registry, amount];
  } else if (functionName.startsWith("schedule")) {
    let action;
    if (functionName === "scheduleValidator") action = await read("validatorActionHash", args);
    else if (functionName === "scheduleThreshold") action = await read("attestationThresholdActionHash", args);
    else if (functionName === "schedulePause") action = keccak256(encodeAbiParameters([{ type: "string" }, { type: "bool" }], ["pause", values.paused]));
    else if (functionName === "scheduleOwnership") action = keccak256(encodeAbiParameters([{ type: "string" }, { type: "address" }], ["owner", values.new_owner]));
    evidence.governance = { action_hash: action, execution_requires_fresh_plan_after_delay: true };
    functionName = "scheduleGovernanceAction";
    args = [action];
  }
  if (["register", "update", "setController", "renewAdmission"].includes(functionName)) {
    const stored = values.record_id ? recordValues(await read("record", [values.record_id])) : null;
    const admission = await read("admission", [values.domain_hash || stored.domainHash, values.new_controller || actor, values.record_hash || stored.recordHash]);
    if (admission[0] !== true) throw new Error("fresh_quorum_admission_required");
    evidence.admission = { entity_id: admission[1], expires_at: admission[2] };
  }
  // Simulate at the exact reviewed finalized boundary, including role, bond,
  // quorum, case, and delay checks. A vote can succeed without reaching quorum.
  const simulated = await publicClient.simulateContract({ account: actor, address: target, abi, functionName, args, blockNumber: snapshot.number });
  if (functionName === "approve" && simulated.result !== true) throw new Error("bond_token_approval_rejected");
  const transaction = { chainId: `0x${deployment.chain_id.toString(16)}`, from: actor.toLowerCase(), to: target.toLowerCase(),
    data: encodeFunctionData({ abi, functionName, args }), value: "0x0" };
  const plan = serializable({
    schema: "agentcart.registry_v2_wallet_plan.v1", state: "ready_for_wallet_review", operation: request.operation,
    request: { operation: request.operation, actor, parameters: values },
    deployment: deploymentEvidence, snapshot: boundary,
    prepared_at: new Date(preparedAt).toISOString(), expires_at: new Date(preparedAt + 30 * 60 * 1000).toISOString(),
    evidence, transaction_request: transaction, wallet_request: { method: "eth_sendTransaction", params: [transaction] },
  });
  plan.intent_hash = keccak256(toBytes(JSON.stringify(plan)));
  plan.required_ack = `registry-v2:${deployment.chain_id}:${registry.toLowerCase()}:${actor.toLowerCase()}:${request.operation}:${plan.intent_hash}`;
  return plan;
}
