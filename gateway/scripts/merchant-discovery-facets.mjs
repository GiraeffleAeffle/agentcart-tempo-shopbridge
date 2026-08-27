import {
  concatHex,
  encodeFunctionData,
  getAddress,
  isAddress,
  keccak256,
  parseAbi,
  toBytes,
} from "viem";

import {
  merchantRegistryAbi,
  validateMerchantRegistryDeployment,
  verifyMerchantRegistryDeployment,
} from "./merchant-registry-enrollment.mjs";
import {
  assertControllerBoundIdentity,
  fetchRegistryRecord,
  normalizedDomain,
  registryRecordHash,
} from "./onchain-registry-indexer.mjs";

const ZERO_BYTES32 = `0x${"00".repeat(32)}`;
const CATEGORY_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MAX_CATEGORY_COUNT = 8;

export const merchantDiscoveryFacetsAbi = parseAbi([
  "function registry() view returns (address)",
  "function publish(bytes32 recordId, bytes32 expectedRecordHash, bytes32[] categoryHashes) returns (bytes32 categorySetHash, uint64 generation)",
  "function facetState(bytes32 recordId) view returns ((bytes32 recordHash, bytes32 categorySetHash, uint64 generation, uint8 categoryCount))",
]);

function bytes32(value, field) {
  const normalized = String(value || "").toLowerCase();
  if (!/^0x[0-9a-f]{64}$/.test(normalized)) throw new Error(`${field}_invalid`);
  return normalized;
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

function facetValues(state) {
  if (Array.isArray(state)) {
    return {
      recordHash: state[0],
      categorySetHash: state[1],
      generation: Number(state[2]),
      categoryCount: Number(state[3]),
    };
  }
  return {
    recordHash: state?.recordHash,
    categorySetHash: state?.categorySetHash,
    generation: Number(state?.generation || 0),
    categoryCount: Number(state?.categoryCount || 0),
  };
}

export function categoryCommitmentFromRecord(record) {
  const facets = record?.discovery_facets;
  if (!facets || typeof facets !== "object" || Array.isArray(facets)) {
    throw new Error("record_discovery_facets_missing");
  }
  if (
    facets.schema !== "agentcart.discovery_facets.v1" ||
    facets.taxonomy !== "woocommerce-product-category-slug-v1" ||
    facets.source !== "exposed_catalog_snapshot"
  ) {
    throw new Error("record_discovery_facets_metadata_invalid");
  }
  const categories = facets.categories;
  if (!Array.isArray(categories) || categories.length < 1 || categories.length > MAX_CATEGORY_COUNT) {
    throw new Error("record_discovery_facets_category_count_invalid");
  }
  if (
    categories.some((category) =>
      typeof category !== "string" ||
      category.length > 64 ||
      !CATEGORY_PATTERN.test(category)
    ) ||
    new Set(categories).size !== categories.length ||
    JSON.stringify(categories) !== JSON.stringify([...categories].sort())
  ) {
    throw new Error("record_discovery_facets_categories_not_canonical");
  }
  const categoryHashes = categories.map((category) => keccak256(toBytes(category))).sort();
  return {
    categories,
    categoryHashes,
    categorySetHash: keccak256(concatHex(categoryHashes)),
  };
}

export async function verifyDiscoveryFacetsDeployment(publicClient, deployment, options = {}) {
  validateMerchantRegistryDeployment(deployment);
  const descriptor = deployment.discovery_facets;
  if (!descriptor) throw new Error("deployment_discovery_facets_missing");
  const finalizedBlock = await verifyMerchantRegistryDeployment(publicClient, deployment, options);
  if (finalizedBlock.number < BigInt(descriptor.deployment_block)) {
    throw new Error("rpc_finalized_block_before_discovery_facets_deployment");
  }
  const [deploymentBlock, codeAtDeployment, codeBeforeDeployment, linkedRegistry] = await Promise.all([
    publicClient.getBlock({ blockNumber: BigInt(descriptor.deployment_block) }),
    publicClient.getBytecode({
      address: getAddress(descriptor.address),
      blockNumber: BigInt(descriptor.deployment_block),
    }),
    publicClient.getBytecode({
      address: getAddress(descriptor.address),
      blockNumber: BigInt(descriptor.deployment_block - 1),
    }),
    publicClient.readContract({
      address: getAddress(descriptor.address),
      abi: merchantDiscoveryFacetsAbi,
      functionName: "registry",
      blockNumber: finalizedBlock.number,
    }),
  ]);
  if (String(deploymentBlock?.hash || "").toLowerCase() !== descriptor.deployment_block_hash) {
    throw new Error("discovery_facets_deployment_block_hash_mismatch");
  }
  if (!codeAtDeployment || codeAtDeployment === "0x" || keccak256(codeAtDeployment) !== descriptor.runtime_code_hash) {
    throw new Error("discovery_facets_runtime_code_hash_mismatch");
  }
  if (codeBeforeDeployment && codeBeforeDeployment !== "0x") {
    throw new Error("discovery_facets_block_not_contract_creation_boundary");
  }
  if (!isAddress(linkedRegistry || "") || getAddress(linkedRegistry) !== getAddress(deployment.registry_address)) {
    throw new Error("discovery_facets_registry_binding_mismatch");
  }
  return finalizedBlock;
}

function planIdentity(plan, deployment) {
  const controller = plan?.identity?.controller;
  const recordId = bytes32(plan?.identity?.record_id, "plan_record_id");
  const recordHash = bytes32(plan?.record?.record_hash, "plan_record_hash");
  const recordUri = String(plan?.record?.record_uri || "");
  if (!isAddress(controller || "") || /^0x0{40}$/i.test(controller)) {
    throw new Error("plan_controller_invalid");
  }
  if (!recordUri.startsWith("https://")) throw new Error("plan_record_uri_invalid");
  if (
    plan?.deployment?.id !== deployment.id ||
    plan?.deployment?.chain_id !== deployment.caip2 ||
    String(plan?.deployment?.registry_address || "").toLowerCase() !== deployment.registry_address.toLowerCase()
  ) {
    throw new Error("plan_deployment_mismatch");
  }
  return { controller: getAddress(controller), recordId, recordHash, recordUri };
}

export async function prepareDiscoveryFacetsPublication({
  enrollmentPlan,
  deployment,
  publicClient,
  loadRecord = fetchRegistryRecord,
}) {
  const identity = planIdentity(enrollmentPlan, deployment);
  const finalizedBlock = await verifyDiscoveryFacetsDeployment(publicClient, deployment);
  const record = await loadRecord(identity.recordUri, identity.recordHash);
  if (`0x${await registryRecordHash(record)}` !== identity.recordHash) {
    throw new Error("discovery_facets_record_hash_mismatch");
  }
  const domain = normalizedDomain(record.domain);
  if (!domain) throw new Error("discovery_facets_record_domain_invalid");
  assertControllerBoundIdentity(record, {
    chainId: deployment.chain_id,
    controller: identity.controller,
    registryAddress: getAddress(deployment.registry_address),
    recordId: identity.recordId,
    domainHash: keccak256(toBytes(domain)),
  });
  const commitment = categoryCommitmentFromRecord(record);
  const registryAddress = getAddress(deployment.registry_address);
  const facetsAddress = getAddress(deployment.discovery_facets.address);
  const [storedRecordRaw, currentFacetsRaw] = await Promise.all([
    publicClient.readContract({
      address: registryAddress,
      abi: merchantRegistryAbi,
      functionName: "record",
      args: [identity.recordId],
      blockNumber: finalizedBlock.number,
    }),
    publicClient.readContract({
      address: facetsAddress,
      abi: merchantDiscoveryFacetsAbi,
      functionName: "facetState",
      args: [identity.recordId],
      blockNumber: finalizedBlock.number,
    }),
  ]);
  const stored = recordValues(storedRecordRaw);
  if (
    stored.status !== 1 ||
    String(stored.controller || "").toLowerCase() !== identity.controller.toLowerCase() ||
    String(stored.recordHash || "").toLowerCase() !== identity.recordHash
  ) {
    throw new Error("discovery_facets_registry_record_not_current");
  }
  const current = facetValues(currentFacetsRaw);
  const base = {
    schema: "agentcart.merchant_discovery_facets_plan.v1",
    deployment: {
      id: deployment.id,
      chain_id: deployment.caip2,
      registry_address: registryAddress,
      discovery_facets_address: facetsAddress,
      discovery_facets_deployment_block: deployment.discovery_facets.deployment_block,
      discovery_facets_deployment_block_hash: deployment.discovery_facets.deployment_block_hash,
      discovery_facets_runtime_code_hash: deployment.discovery_facets.runtime_code_hash,
    },
    identity: {
      controller: identity.controller,
      record_id: identity.recordId,
      record_hash: identity.recordHash,
    },
    categories: commitment.categories,
    category_hashes: commitment.categoryHashes,
    category_set_hash: commitment.categorySetHash,
    chain_snapshot: {
      block_tag: "finalized",
      block_number: Number(finalizedBlock.number),
      block_hash: finalizedBlock.hash,
    },
  };
  if (
    String(current.recordHash || "").toLowerCase() === identity.recordHash &&
    String(current.categorySetHash || "").toLowerCase() === commitment.categorySetHash &&
    current.categoryCount === commitment.categories.length &&
    current.generation > 0
  ) {
    return {
      ...base,
      ready: true,
      state: "finalized_current",
      generation: current.generation,
      transaction_request: null,
      wallet_request: null,
      required_ack: null,
    };
  }
  const data = encodeFunctionData({
    abi: merchantDiscoveryFacetsAbi,
    functionName: "publish",
    args: [identity.recordId, identity.recordHash, commitment.categoryHashes],
  });
  const transaction = {
    chainId: `0x${deployment.chain_id.toString(16)}`,
    from: identity.controller,
    to: facetsAddress,
    data,
    value: "0x0",
  };
  await publicClient.call({
    account: identity.controller,
    to: facetsAddress,
    data,
    value: 0n,
    blockNumber: finalizedBlock.number,
  });
  const requiredAck = [
    "publish-facets",
    deployment.caip2,
    facetsAddress.toLowerCase(),
    identity.recordId,
    identity.recordHash,
    commitment.categorySetHash,
  ].join(":");
  return {
    ...base,
    ready: true,
    state: "ready_to_publish",
    current_generation: current.generation,
    transaction_request: transaction,
    wallet_request: { method: "eth_sendTransaction", params: [transaction] },
    required_ack: requiredAck,
  };
}

export async function verifyDiscoveryFacetsState({ plan, deployment, publicClient }) {
  if (plan?.schema !== "agentcart.merchant_discovery_facets_plan.v1") {
    throw new Error("discovery_facets_plan_schema_invalid");
  }
  const finalizedBlock = await verifyDiscoveryFacetsDeployment(publicClient, deployment);
  const controller = plan.identity?.controller;
  if (!isAddress(controller || "")) throw new Error("plan_controller_invalid");
  const recordId = bytes32(plan.identity?.record_id, "plan_record_id");
  const expectedRecordHash = bytes32(plan.identity?.record_hash, "plan_record_hash");
  const [facetStateRaw, registryRecordRaw] = await Promise.all([
    publicClient.readContract({
      address: getAddress(deployment.discovery_facets.address),
      abi: merchantDiscoveryFacetsAbi,
      functionName: "facetState",
      args: [recordId],
      blockNumber: finalizedBlock.number,
    }),
    publicClient.readContract({
      address: getAddress(deployment.registry_address),
      abi: merchantRegistryAbi,
      functionName: "record",
      args: [recordId],
      blockNumber: finalizedBlock.number,
    }),
  ]);
  const state = facetValues(facetStateRaw);
  const registryRecord = recordValues(registryRecordRaw);
  const registryCurrent =
    registryRecord.status === 1 &&
    String(registryRecord.controller || "").toLowerCase() === controller.toLowerCase() &&
    String(registryRecord.recordHash || "").toLowerCase() === expectedRecordHash;
  const current = registryCurrent &&
    String(state.recordHash || "").toLowerCase() === expectedRecordHash &&
    String(state.categorySetHash || "").toLowerCase() === bytes32(plan.category_set_hash, "plan_category_set_hash") &&
    state.categoryCount === plan.category_hashes?.length &&
    state.generation > 0;
  return {
    schema: "agentcart.merchant_discovery_facets_verification.v1",
    ready: current,
    state: current ? "finalized_current" : "finalized_mismatch",
    record_id: plan.identity.record_id,
    record_hash: state.recordHash || ZERO_BYTES32,
    category_set_hash: state.categorySetHash || ZERO_BYTES32,
    category_count: state.categoryCount,
    generation: state.generation,
    registry_current: registryCurrent,
    finality: {
      block_tag: "finalized",
      block_number: Number(finalizedBlock.number),
      block_hash: finalizedBlock.hash,
    },
  };
}
