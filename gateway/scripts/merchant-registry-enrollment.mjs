import {
  encodeFunctionData,
  getAddress,
  isAddress,
  keccak256,
  parseAbi,
  toBytes,
} from "viem";

import {
  assertControllerBoundIdentity,
  fetchRegistryRecord,
  normalizedDomain,
  registryRecordHash,
} from "./onchain-registry-indexer.mjs";

const ZERO_BYTES32 = `0x${"00".repeat(32)}`;
const MERCHANT_PLAN_TTL_MS = 30 * 60 * 1000;
const MAX_FINALITY_AGE_SECONDS = 600;
const MAX_FINALITY_FUTURE_SKEW_SECONDS = 120;

export const merchantRegistryAbi = parseAbi([
  "function writesPaused() view returns (bool)",
  "function recordIdForDomain(bytes32 domainHash) view returns (bytes32)",
  "function computeRecordId(bytes32 domainHash, address controller) view returns (bytes32)",
  "function revokedRecordHashes(bytes32 recordHash) view returns (bool)",
  "function record(bytes32 recordId) view returns ((address controller, bytes32 recordHash, bytes32 domainHash, uint64 updatedAt, uint64 attestedAt, uint64 attestationExpiresAt, uint32 attestationGeneration, uint16 attestationCount, uint8 status))",
  "function register(bytes32 domainHash, bytes32 recordHash, string recordURI) returns (bytes32 recordId)",
  "function update(bytes32 recordId, bytes32 recordHash, string recordURI)",
  "function revoke(bytes32 recordId, bytes32 reasonHash)",
]);

export const tempoModeratoDeployment = Object.freeze({
  schema: "agentcart.onchain_registry_deployment.v1",
  id: "tempo-moderato",
  network_class: "testnet",
  chain_id: 42431,
  caip2: "eip155:42431",
  registry_address: "0x0965961617c5b0898167aa4034c5511db0efca07",
  deployment_block: 30731101,
  deployment_block_hash: "0x8646ecbbb11ac5cf6195dd7e288acb2541f02ef0d580e3bc9afa2e42045edd26",
  runtime_code_hash: "0x6ef95b4471732ea43ea30a6a6f40117e117357a7291587e66b13d824f83509a4",
  rpc_url: "https://rpc.moderato.tempo.xyz",
  discovery_facets: Object.freeze({
    address: "0x693de216d208ADC933365bD6F4FCbC062BB8Afe5",
    deployment_block: 32721088,
    deployment_block_hash: "0xc3742bb0f7b5db034ccb36f8fdd252be4b8aeacb17018b374d77c0cf5fdcc8dd",
    runtime_code_hash: "0x3a5d6e537b74546d91a80f3fa728acff2b9f217efea0cbf22a848ae43af27d12",
  }),
  finality: Object.freeze({
    block_tag: "finalized",
    max_age_seconds: MAX_FINALITY_AGE_SECONDS,
    max_future_skew_seconds: MAX_FINALITY_FUTURE_SKEW_SECONDS,
  }),
  mutation_policy: "pilot_enabled",
});

export const merchantRegistryDeployments = new Map([
  [tempoModeratoDeployment.id, tempoModeratoDeployment],
]);

function normalizeBytes32(value, field) {
  const normalized = String(value || "").toLowerCase();
  if (!/^0x[0-9a-f]{64}$/.test(normalized)) {
    throw new Error(`${field}_invalid`);
  }
  return normalized;
}

function normalizedHash(value, field) {
  return normalizeBytes32(String(value || "").startsWith("0x") ? value : `0x${value}`, field);
}

function publicBundleUrl(value, domain) {
  let parsed;
  try {
    parsed = new URL(String(value || ""));
  } catch {
    throw new Error("bundle_url_invalid");
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    parsed.port ||
    normalizedDomain(parsed.hostname) !== domain
  ) {
    throw new Error("bundle_url_must_use_merchant_https_domain");
  }
  return parsed.toString();
}

function immutableRecordUri(value, domain, recordHash) {
  let parsed;
  try {
    parsed = new URL(String(value || ""));
  } catch {
    throw new Error("record_uri_invalid");
  }
  const expectedPath = `/.well-known/agentcart-registry-records/${recordHash.slice(2)}.json`;
  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    parsed.port ||
    normalizedDomain(parsed.hostname) !== domain ||
    parsed.pathname !== expectedPath ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error("record_uri_not_merchant_content_addressed");
  }
  return parsed.toString();
}

function recordValues(record) {
  if (Array.isArray(record)) {
    return {
      controller: record[0],
      recordHash: record[1],
      domainHash: record[2],
      status: Number(record[8]),
    };
  }
  return {
    controller: record?.controller,
    recordHash: record?.recordHash,
    domainHash: record?.domainHash,
    status: Number(record?.status || 0),
  };
}

export function validateMerchantRegistryDeployment(deployment) {
  if (deployment?.schema !== "agentcart.onchain_registry_deployment.v1") {
    throw new Error("deployment_schema_invalid");
  }
  if (!Number.isSafeInteger(deployment.chain_id) || deployment.chain_id <= 0) {
    throw new Error("deployment_chain_id_invalid");
  }
  if (deployment.caip2 !== `eip155:${deployment.chain_id}`) {
    throw new Error("deployment_caip2_mismatch");
  }
  if (!isAddress(deployment.registry_address || "")) {
    throw new Error("deployment_registry_address_invalid");
  }
  if (!Number.isSafeInteger(deployment.deployment_block) || deployment.deployment_block < 0) {
    throw new Error("deployment_block_invalid");
  }
  normalizeBytes32(deployment.deployment_block_hash, "deployment_block_hash");
  normalizeBytes32(deployment.runtime_code_hash, "runtime_code_hash");
  if (deployment.discovery_facets !== undefined) {
    const facets = deployment.discovery_facets;
    if (!isAddress(facets?.address || "")) {
      throw new Error("deployment_discovery_facets_address_invalid");
    }
    if (!Number.isSafeInteger(facets.deployment_block) || facets.deployment_block < deployment.deployment_block) {
      throw new Error("deployment_discovery_facets_block_invalid");
    }
    normalizeBytes32(facets.deployment_block_hash, "deployment_discovery_facets_block_hash");
    normalizeBytes32(facets.runtime_code_hash, "deployment_discovery_facets_runtime_code_hash");
  }
  if (
    deployment.finality?.block_tag !== "finalized" ||
    !Number.isSafeInteger(deployment.finality?.max_age_seconds) ||
    deployment.finality.max_age_seconds <= 0 ||
    !Number.isSafeInteger(deployment.finality?.max_future_skew_seconds) ||
    deployment.finality.max_future_skew_seconds < 0
  ) {
    throw new Error("deployment_finality_policy_invalid");
  }
  if (deployment.network_class === "mainnet" && deployment.mutation_policy !== "approved") {
    throw new Error("mainnet_deployment_not_approved_for_mutation");
  }
  return deployment;
}

export async function verifyMerchantRegistryDeployment(
  publicClient,
  deployment,
  { now = () => Date.now() } = {},
) {
  validateMerchantRegistryDeployment(deployment);
  const [chainId, finalizedBlock, deploymentBlock] = await Promise.all([
    publicClient.getChainId(),
    publicClient.getBlock({ blockTag: "finalized" }),
    publicClient.getBlock({ blockNumber: BigInt(deployment.deployment_block) }),
  ]);
  if (chainId !== deployment.chain_id) throw new Error("rpc_chain_id_mismatch");
  if (!finalizedBlock?.hash || finalizedBlock.number === null || finalizedBlock.number === undefined) {
    throw new Error("rpc_finalized_block_unavailable");
  }
  if (finalizedBlock.number < BigInt(deployment.deployment_block)) {
    throw new Error("rpc_finalized_block_before_deployment");
  }
  const finalizedTimestamp = Number(finalizedBlock.timestamp);
  const referenceTimestamp = Number(now());
  if (!Number.isSafeInteger(finalizedTimestamp) || !Number.isFinite(referenceTimestamp)) {
    throw new Error("rpc_finalized_block_time_invalid");
  }
  const finalizedTimeMs = finalizedTimestamp * 1000;
  if (finalizedTimeMs > referenceTimestamp + deployment.finality.max_future_skew_seconds * 1000) {
    throw new Error("rpc_finalized_block_time_future");
  }
  if (finalizedTimeMs < referenceTimestamp - deployment.finality.max_age_seconds * 1000) {
    throw new Error("rpc_finalized_block_time_stale");
  }
  if (String(deploymentBlock?.hash || "").toLowerCase() !== deployment.deployment_block_hash.toLowerCase()) {
    throw new Error("deployment_block_hash_mismatch");
  }
  const registryAddress = getAddress(deployment.registry_address);
  const [deploymentBytecode, previousBytecode, finalizedBytecode] = await Promise.all([
    publicClient.getBytecode({
      address: registryAddress,
      blockNumber: BigInt(deployment.deployment_block),
    }),
    deployment.deployment_block > 0
      ? publicClient.getBytecode({
          address: registryAddress,
          blockNumber: BigInt(deployment.deployment_block - 1),
        })
      : Promise.resolve("0x"),
    publicClient.getBytecode({
      address: registryAddress,
      blockNumber: finalizedBlock.number,
    }),
  ]);
  if (!deploymentBytecode || deploymentBytecode === "0x") {
    throw new Error("registry_code_missing_at_deployment_block");
  }
  if (previousBytecode && !["0x", "0x0", "0x00"].includes(previousBytecode.toLowerCase())) {
    throw new Error("deployment_block_not_contract_creation_boundary");
  }
  if (!finalizedBytecode || finalizedBytecode === "0x") throw new Error("registry_contract_code_missing");
  if (
    keccak256(deploymentBytecode).toLowerCase() !== deployment.runtime_code_hash.toLowerCase() ||
    keccak256(finalizedBytecode).toLowerCase() !== deployment.runtime_code_hash.toLowerCase()
  ) {
    throw new Error("registry_runtime_code_hash_mismatch");
  }
  return finalizedBlock;
}

function isoTime(timestampMs) {
  return new Date(timestampMs).toISOString().replace(".000Z", "Z");
}

function basePlan({
  bundle,
  bundleUrl,
  controller,
  deployment,
  domain,
  domainHash,
  recordId,
  finalizedBlock,
  preparedAt,
}) {
  return {
    schema: "agentcart.merchant_onchain_plan.v1",
    ready: false,
    state: "not_ready",
    operation: "none",
    deployment: {
      id: deployment.id,
      network_class: deployment.network_class,
      chain_id: deployment.caip2,
      registry_address: deployment.registry_address.toLowerCase(),
      deployment_block: deployment.deployment_block,
      deployment_block_hash: deployment.deployment_block_hash.toLowerCase(),
      runtime_code_hash: deployment.runtime_code_hash.toLowerCase(),
    },
    merchant: {
      merchant_id: String(bundle.merchant_id || bundle.registry_record?.merchant_id || ""),
      domain,
      bundle_url: bundleUrl,
    },
    identity: {
      controller: controller.toLowerCase(),
      domain_hash: domainHash,
      record_id: recordId.toLowerCase(),
    },
    chain_snapshot: {
      block_tag: "finalized",
      block_number: Number(finalizedBlock.number),
      block_hash: finalizedBlock.hash,
      block_time: finalizedBlock.timestamp === undefined
        ? ""
        : new Date(Number(finalizedBlock.timestamp) * 1000).toISOString().replace(".000Z", "Z"),
    },
    prepared_at: isoTime(preparedAt),
    expires_at: isoTime(preparedAt + MERCHANT_PLAN_TTL_MS),
    precondition: null,
    intent_hash: "",
    record: null,
    transaction_request: null,
    wallet_request: null,
    blockers: [],
    warnings: [],
  };
}

/**
 * Hash the complete reviewed wallet intent using a fixed-position payload.
 * Any change to the target, calldata, public record, snapshot precondition, or
 * expiry therefore changes the acknowledgement the merchant must type.
 */
export function merchantPlanIntentHash(plan) {
  const transaction = plan?.transaction_request || {};
  const precondition = plan?.precondition || {};
  const payload = [
    "agentcart.merchant_onchain_intent.v1",
    String(plan?.operation || ""),
    String(plan?.deployment?.id || ""),
    String(plan?.deployment?.network_class || ""),
    String(plan?.deployment?.chain_id || ""),
    String(plan?.deployment?.registry_address || "").toLowerCase(),
    String(plan?.deployment?.deployment_block ?? ""),
    String(plan?.deployment?.deployment_block_hash || "").toLowerCase(),
    String(plan?.deployment?.runtime_code_hash || "").toLowerCase(),
    String(plan?.merchant?.merchant_id || ""),
    String(plan?.merchant?.domain || ""),
    String(plan?.merchant?.bundle_url || ""),
    String(plan?.identity?.controller || "").toLowerCase(),
    String(plan?.identity?.domain_hash || "").toLowerCase(),
    String(plan?.identity?.record_id || "").toLowerCase(),
    String(plan?.record?.record_hash || "").toLowerCase(),
    String(plan?.record?.record_uri || ""),
    String(plan?.reason_hash || "").toLowerCase(),
    String(plan?.chain_snapshot?.block_number ?? ""),
    String(plan?.chain_snapshot?.block_hash || "").toLowerCase(),
    String(precondition.writes_paused ?? ""),
    String(precondition.domain_record_id || "").toLowerCase(),
    String(precondition.current_status || ""),
    String(precondition.current_record_hash || "").toLowerCase(),
    String(transaction.chainId || ""),
    String(transaction.from || "").toLowerCase(),
    String(transaction.to || "").toLowerCase(),
    String(transaction.data || "").toLowerCase(),
    String(transaction.value || ""),
    String(plan?.prepared_at || ""),
    String(plan?.expires_at || ""),
  ];
  return keccak256(toBytes(JSON.stringify(payload)));
}

function finalizeMutationPlan(plan) {
  plan.intent_hash = merchantPlanIntentHash(plan);
  plan.required_ack = [
    plan.operation,
    plan.deployment.chain_id,
    plan.deployment.registry_address,
    plan.identity.record_id,
    plan.intent_hash,
  ].join(":");
  return plan;
}

/**
 * Prepare a secret-free merchant enrollment plan from the shop's public bundle.
 *
 * The first call returns public WordPress identity settings. Once the merchant
 * stores those settings and refreshes the bundle, the second call verifies the
 * immutable record and emits a transaction request for an external wallet.
 */
export async function prepareMerchantEnrollment({
  bundle,
  bundleUrl,
  controller,
  deployment,
  publicClient,
  loadRecord = fetchRegistryRecord,
  now = () => Date.now(),
}) {
  validateMerchantRegistryDeployment(deployment);
  if (!isAddress(controller || "") || /^0x0{40}$/i.test(controller)) {
    throw new Error("controller_address_invalid");
  }
  if (!bundle || typeof bundle !== "object" || Array.isArray(bundle)) {
    throw new Error("registry_bundle_invalid");
  }
  const registryRecord = bundle.registry_record;
  if (!registryRecord || typeof registryRecord !== "object" || Array.isArray(registryRecord)) {
    throw new Error("registry_bundle_record_missing");
  }
  const domain = normalizedDomain(registryRecord.domain);
  if (!domain) throw new Error("registry_record_domain_invalid");
  const normalizedBundleUrl = publicBundleUrl(bundleUrl, domain);
  const normalizedController = getAddress(controller);
  const registryAddress = getAddress(deployment.registry_address);
  const preparedAt = Number(now());
  if (!Number.isFinite(preparedAt)) throw new Error("merchant_plan_time_invalid");
  const finalizedBlock = await verifyMerchantRegistryDeployment(publicClient, deployment, {
    now: () => preparedAt,
  });
  const domainHash = keccak256(toBytes(domain));
  const currentRecordId = normalizeBytes32(
    await publicClient.readContract({
      address: registryAddress,
      abi: merchantRegistryAbi,
      functionName: "recordIdForDomain",
      args: [domainHash],
      blockNumber: finalizedBlock.number,
    }),
    "domain_record_id",
  );
  // A controller rotation intentionally preserves the record id. Derive a
  // new id only for an unregistered domain; otherwise the domain mapping is
  // the stable identity anchor.
  const recordId = currentRecordId === ZERO_BYTES32
    ? normalizeBytes32(await publicClient.readContract({
      address: registryAddress,
      abi: merchantRegistryAbi,
      functionName: "computeRecordId",
      args: [domainHash, normalizedController],
      blockNumber: finalizedBlock.number,
    }), "record_id")
    : currentRecordId;
  const plan = basePlan({
    bundle,
    bundleUrl: normalizedBundleUrl,
    controller: normalizedController,
    deployment,
    domain,
    domainHash,
    recordId,
    finalizedBlock,
    preparedAt,
  });
  const identity = registryRecord.onchain_identity;
  if (!identity || typeof identity !== "object" || Array.isArray(identity) || Object.keys(identity).length === 0) {
    plan.state = "store_identity_required";
    plan.wordpress_settings = {
      controller: normalizedController.toLowerCase(),
      chain_id: deployment.caip2,
      registry_address: deployment.registry_address.toLowerCase(),
      record_id: recordId,
    };
    return plan;
  }

  assertControllerBoundIdentity(registryRecord, {
    chainId: deployment.chain_id,
    controller: normalizedController,
    registryAddress,
    recordId,
    domainHash,
  });

  const computedRecordHash = `0x${await registryRecordHash(registryRecord)}`;
  const bundleRecordHash = normalizedHash(bundle.record_hash, "bundle_record_hash");
  if (computedRecordHash !== bundleRecordHash) throw new Error("bundle_record_hash_mismatch");
  const recordUri = immutableRecordUri(bundle.record_uri, domain, computedRecordHash);
  const loadedRecord = await loadRecord(recordUri, computedRecordHash);
  if (`0x${await registryRecordHash(loadedRecord)}` !== computedRecordHash) {
    throw new Error("immutable_record_hash_mismatch");
  }
  assertControllerBoundIdentity(loadedRecord, {
    chainId: deployment.chain_id,
    controller: normalizedController,
    registryAddress,
    recordId,
    domainHash,
  });
  plan.record = {
    record_hash: computedRecordHash,
    record_uri: recordUri,
    immutable_uri_verified: true,
  };

  const writesPaused = await publicClient.readContract({
      address: registryAddress,
      abi: merchantRegistryAbi,
      functionName: "writesPaused",
      blockNumber: finalizedBlock.number,
    });
  plan.chain_snapshot.writes_paused = Boolean(writesPaused);
  plan.chain_snapshot.domain_record_id = currentRecordId;
  if (writesPaused) throw new Error("registry_writes_paused");

  let functionName;
  let args;
  const normalizedCurrentRecordId = currentRecordId;
  if (normalizedCurrentRecordId === ZERO_BYTES32) {
    functionName = "register";
    args = [domainHash, computedRecordHash, recordUri];
    plan.precondition = {
      writes_paused: false,
      domain_record_id: ZERO_BYTES32,
      current_status: "unregistered",
      current_record_hash: ZERO_BYTES32,
    };
  } else {
    if (normalizedCurrentRecordId !== recordId) throw new Error("domain_registered_to_different_record_id");
    const stored = recordValues(
      await publicClient.readContract({
        address: registryAddress,
        abi: merchantRegistryAbi,
        functionName: "record",
        args: [recordId],
        blockNumber: finalizedBlock.number,
      }),
    );
    if (String(stored.controller || "").toLowerCase() !== normalizedController.toLowerCase()) {
      throw new Error("onchain_record_controller_mismatch");
    }
    if (String(stored.domainHash || "").toLowerCase() !== domainHash.toLowerCase()) {
      throw new Error("onchain_record_domain_mismatch");
    }
    if (stored.status !== 1) throw new Error("onchain_record_not_active");
    plan.chain_snapshot.current_record_hash = String(stored.recordHash || "").toLowerCase();
    plan.chain_snapshot.current_status = "active";
    if (String(stored.recordHash || "").toLowerCase() === computedRecordHash) {
      plan.state = "finalized_current";
      plan.ready = true;
      return plan;
    }
    functionName = "update";
    args = [recordId, computedRecordHash, recordUri];
    plan.precondition = {
      writes_paused: false,
      domain_record_id: recordId,
      current_status: "active",
      current_record_hash: String(stored.recordHash || "").toLowerCase(),
    };
  }

  await publicClient.simulateContract({
    account: normalizedController,
    address: registryAddress,
    abi: merchantRegistryAbi,
    functionName,
    args,
  });
  const data = encodeFunctionData({ abi: merchantRegistryAbi, functionName, args });
  const transaction = {
    chainId: `0x${deployment.chain_id.toString(16)}`,
    from: normalizedController.toLowerCase(),
    to: deployment.registry_address.toLowerCase(),
    data,
    value: "0x0",
  };
  plan.operation = functionName;
  plan.state = `ready_to_${functionName}`;
  plan.ready = true;
  plan.transaction_request = transaction;
  plan.wallet_request = { method: "eth_sendTransaction", params: [transaction] };
  return finalizeMutationPlan(plan);
}

function validatedSavedPlan(plan, deployment) {
  if (plan?.schema !== "agentcart.merchant_onchain_plan.v1") {
    throw new Error("merchant_plan_schema_invalid");
  }
  if (plan.deployment?.id !== deployment.id) throw new Error("merchant_plan_deployment_mismatch");
  if (plan.deployment?.chain_id !== deployment.caip2) throw new Error("merchant_plan_chain_id_mismatch");
  if (String(plan.deployment?.registry_address || "").toLowerCase() !== deployment.registry_address.toLowerCase()) {
    throw new Error("merchant_plan_registry_address_mismatch");
  }
  if (
    Number(plan.deployment?.deployment_block) !== deployment.deployment_block ||
    String(plan.deployment?.deployment_block_hash || "").toLowerCase() !== deployment.deployment_block_hash.toLowerCase() ||
    String(plan.deployment?.runtime_code_hash || "").toLowerCase() !== deployment.runtime_code_hash.toLowerCase()
  ) {
    throw new Error("merchant_plan_deployment_evidence_mismatch");
  }
  if (!isAddress(plan.identity?.controller || "")) throw new Error("merchant_plan_controller_invalid");
  const domainHash = normalizeBytes32(plan.identity?.domain_hash, "merchant_plan_domain_hash");
  const recordId = normalizeBytes32(plan.identity?.record_id, "merchant_plan_record_id");
  const recordHash = normalizedHash(plan.record?.record_hash, "merchant_plan_record_hash");
  return {
    controller: getAddress(plan.identity.controller),
    domainHash,
    recordId,
    recordHash,
  };
}

function walletTransaction(deployment, controller, data) {
  return {
    chainId: `0x${deployment.chain_id.toString(16)}`,
    from: controller.toLowerCase(),
    to: deployment.registry_address.toLowerCase(),
    data,
    value: "0x0",
  };
}

export async function prepareMerchantRevocation({
  plan,
  reason,
  deployment,
  publicClient,
  now = () => Date.now(),
}) {
  validateMerchantRegistryDeployment(deployment);
  const allowedReasons = new Set(["merchant_admin_revoke", "compromised_store", "pilot_complete"]);
  if (!allowedReasons.has(reason)) throw new Error("merchant_revoke_reason_invalid");
  const saved = validatedSavedPlan(plan, deployment);
  const registryAddress = getAddress(deployment.registry_address);
  const preparedAt = Number(now());
  if (!Number.isFinite(preparedAt)) throw new Error("merchant_plan_time_invalid");
  const finalizedBlock = await verifyMerchantRegistryDeployment(publicClient, deployment, {
    now: () => preparedAt,
  });
  const [writesPaused, currentRecordId, stored] = await Promise.all([
    publicClient.readContract({
      address: registryAddress,
      abi: merchantRegistryAbi,
      functionName: "writesPaused",
      blockNumber: finalizedBlock.number,
    }),
    publicClient.readContract({
      address: registryAddress,
      abi: merchantRegistryAbi,
      functionName: "recordIdForDomain",
      args: [saved.domainHash],
      blockNumber: finalizedBlock.number,
    }),
    publicClient.readContract({
      address: registryAddress,
      abi: merchantRegistryAbi,
      functionName: "record",
      args: [saved.recordId],
      blockNumber: finalizedBlock.number,
    }),
  ]);
  if (writesPaused) throw new Error("registry_writes_paused");
  if (normalizeBytes32(currentRecordId, "domain_record_id") !== saved.recordId) {
    throw new Error("merchant_plan_record_not_active_for_domain");
  }
  const values = recordValues(stored);
  if (String(values.controller || "").toLowerCase() !== saved.controller.toLowerCase()) {
    throw new Error("merchant_plan_controller_mismatch");
  }
  if (String(values.recordHash || "").toLowerCase() !== saved.recordHash) {
    throw new Error("merchant_plan_record_hash_stale");
  }
  if (String(values.domainHash || "").toLowerCase() !== saved.domainHash || values.status !== 1) {
    throw new Error("merchant_plan_record_not_active");
  }
  const reasonHash = keccak256(toBytes(`agentcart.registry.revoke.reason.v1:${reason}`));
  const args = [saved.recordId, reasonHash];
  await publicClient.simulateContract({
    account: saved.controller,
    address: registryAddress,
    abi: merchantRegistryAbi,
    functionName: "revoke",
    args,
  });
  const transaction = walletTransaction(
    deployment,
    saved.controller,
    encodeFunctionData({ abi: merchantRegistryAbi, functionName: "revoke", args }),
  );
  const revokePlan = {
    ...plan,
    deployment: {
      id: deployment.id,
      network_class: deployment.network_class,
      chain_id: deployment.caip2,
      registry_address: deployment.registry_address.toLowerCase(),
      deployment_block: deployment.deployment_block,
      deployment_block_hash: deployment.deployment_block_hash.toLowerCase(),
      runtime_code_hash: deployment.runtime_code_hash.toLowerCase(),
    },
    ready: true,
    state: "ready_to_revoke",
    operation: "revoke",
    reason,
    reason_hash: reasonHash,
    chain_snapshot: {
      block_tag: "finalized",
      block_number: Number(finalizedBlock.number),
      block_hash: finalizedBlock.hash,
      block_time: finalizedBlock.timestamp === undefined
        ? ""
        : new Date(Number(finalizedBlock.timestamp) * 1000).toISOString().replace(".000Z", "Z"),
      writes_paused: false,
      domain_record_id: saved.recordId,
      current_record_hash: saved.recordHash,
      current_status: "active",
    },
    prepared_at: isoTime(preparedAt),
    expires_at: isoTime(preparedAt + MERCHANT_PLAN_TTL_MS),
    precondition: {
      writes_paused: false,
      domain_record_id: saved.recordId,
      current_status: "active",
      current_record_hash: saved.recordHash,
    },
    record: { ...plan.record, record_hash: saved.recordHash },
    transaction_request: transaction,
    wallet_request: { method: "eth_sendTransaction", params: [transaction] },
    blockers: [],
  };
  return finalizeMutationPlan(revokePlan);
}

export async function verifyMerchantPlanFinality({
  plan,
  expectedState = "active",
  deployment,
  publicClient,
  now = () => Date.now(),
}) {
  if (!["active", "revoked"].includes(expectedState)) throw new Error("expected_state_invalid");
  validateMerchantRegistryDeployment(deployment);
  const saved = validatedSavedPlan(plan, deployment);
  const registryAddress = getAddress(deployment.registry_address);
  const finalizedBlock = await verifyMerchantRegistryDeployment(publicClient, deployment, { now });
  const [currentRecordId, stored, revokedHash] = await Promise.all([
    publicClient.readContract({
      address: registryAddress,
      abi: merchantRegistryAbi,
      functionName: "recordIdForDomain",
      args: [saved.domainHash],
      blockNumber: finalizedBlock.number,
    }),
    publicClient.readContract({
      address: registryAddress,
      abi: merchantRegistryAbi,
      functionName: "record",
      args: [saved.recordId],
      blockNumber: finalizedBlock.number,
    }),
    publicClient.readContract({
      address: registryAddress,
      abi: merchantRegistryAbi,
      functionName: "revokedRecordHashes",
      args: [saved.recordHash],
      blockNumber: finalizedBlock.number,
    }),
  ]);
  const values = recordValues(stored);
  const commonMatches = String(values.controller || "").toLowerCase() === saved.controller.toLowerCase()
    && String(values.domainHash || "").toLowerCase() === saved.domainHash
    && String(values.recordHash || "").toLowerCase() === saved.recordHash;
  const currentId = normalizeBytes32(currentRecordId, "domain_record_id");
  const ready = expectedState === "active"
    ? commonMatches && values.status === 1 && currentId === saved.recordId && !revokedHash
    : commonMatches && values.status === 2 && currentId === ZERO_BYTES32 && Boolean(revokedHash);
  return {
    schema: "agentcart.merchant_onchain_finality.v1",
    ready,
    state: ready
      ? expectedState === "active" ? "finalized_current" : "finalized_revoked"
      : "finalized_state_mismatch",
    expected_state: expectedState,
    deployment: {
      id: deployment.id,
      chain_id: deployment.caip2,
      registry_address: deployment.registry_address.toLowerCase(),
    },
    identity: {
      controller: saved.controller.toLowerCase(),
      domain_hash: saved.domainHash,
      record_id: saved.recordId,
    },
    record: {
      record_hash: saved.recordHash,
      status: values.status,
      domain_record_id: currentId,
      revoked_hash: Boolean(revokedHash),
    },
    finality: {
      block_tag: "finalized",
      block_number: Number(finalizedBlock.number),
      block_hash: finalizedBlock.hash,
      block_time: finalizedBlock.timestamp === undefined
        ? ""
        : new Date(Number(finalizedBlock.timestamp) * 1000).toISOString().replace(".000Z", "Z"),
    },
  };
}
