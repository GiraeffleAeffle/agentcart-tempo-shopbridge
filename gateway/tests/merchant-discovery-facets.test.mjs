import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

import { keccak256, toBytes } from "viem";

import {
  categoryCommitmentFromRecord,
  prepareDiscoveryFacetsPublication,
  verifyDiscoveryFacetsState,
} from "../scripts/merchant-discovery-facets.mjs";
import { tempoModeratoDeployment } from "../scripts/merchant-registry-enrollment.mjs";
import { registryRecordHash } from "../scripts/onchain-registry-indexer.mjs";

const controller = "0x1111111111111111111111111111111111111111";
const recordId = `0x${"44".repeat(32)}`;
const domainHash = keccak256(toBytes("tea.example"));
const runtimeCode = "0x6000";
const registryRuntimeCode = "0x6001";
const finalizedHash = `0x${"aa".repeat(32)}`;
const deployment = Object.freeze({
  ...tempoModeratoDeployment,
  runtime_code_hash: keccak256(registryRuntimeCode),
  discovery_facets: Object.freeze({
    ...tempoModeratoDeployment.discovery_facets,
    runtime_code_hash: keccak256(runtimeCode),
  }),
});

function record() {
  return {
    merchant_id: "tea.example",
    name: "Tea Shop",
    domain: "tea.example",
    manifest_url: "https://tea.example/.well-known/agentcart.json",
    onchain_identity: {
      controller,
      chain_id: deployment.caip2,
      registry_address: deployment.registry_address,
      record_id: recordId,
    },
    discovery_facets: {
      schema: "agentcart.discovery_facets.v1",
      taxonomy: "woocommerce-product-category-slug-v1",
      source: "exposed_catalog_snapshot",
      categories: ["coffee", "tea"],
      category_count_total: 2,
      coverage: "complete",
      truncated: false,
    },
  };
}

function publicClient(recordHash, facetState = undefined) {
  const calls = [];
  return {
    calls,
    async getChainId() { return deployment.chain_id; },
    async getBlock({ blockTag, blockNumber }) {
      if (blockNumber === BigInt(deployment.deployment_block)) {
        return { number: blockNumber, hash: deployment.deployment_block_hash, timestamp: 1n };
      }
      if (blockNumber === BigInt(deployment.discovery_facets.deployment_block)) {
        return { number: blockNumber, hash: deployment.discovery_facets.deployment_block_hash, timestamp: 2n };
      }
      return {
        number: 33_000_000n,
        hash: finalizedHash,
        timestamp: BigInt(Math.floor(Date.now() / 1000) - 10),
      };
    },
    async getBytecode({ address, blockNumber }) {
      const normalized = address.toLowerCase();
      if (normalized === deployment.registry_address.toLowerCase()) {
        return blockNumber === BigInt(deployment.deployment_block - 1) ? "0x" : registryRuntimeCode;
      }
      if (normalized === deployment.discovery_facets.address.toLowerCase()) {
        return blockNumber === BigInt(deployment.discovery_facets.deployment_block - 1) ? "0x" : runtimeCode;
      }
      throw new Error("unexpected bytecode address");
    },
    async readContract({ address, functionName }) {
      calls.push(`read:${functionName}`);
      if (functionName === "registry") return deployment.registry_address;
      if (functionName === "record") {
        return {
          controller,
          recordHash,
          domainHash,
          status: 1,
        };
      }
      if (functionName === "facetState") {
        return facetState || {
          recordHash: `0x${"00".repeat(32)}`,
          categorySetHash: `0x${"00".repeat(32)}`,
          generation: 0,
          categoryCount: 0,
        };
      }
      throw new Error(`unexpected contract read ${address}:${functionName}`);
    },
    async call({ account, to, data, value }) {
      calls.push("call:publish");
      assert.equal(account, controller);
      assert.equal(to.toLowerCase(), deployment.discovery_facets.address.toLowerCase());
      assert.match(data, /^0x[0-9a-f]+$/);
      assert.equal(value, 0n);
    },
  };
}

test("category commitment hashes canonical slugs and sorts hashes for the contract", () => {
  const commitment = categoryCommitmentFromRecord(record());
  assert.deepEqual(commitment.categories, ["coffee", "tea"]);
  assert.deepEqual(commitment.categoryHashes, [
    keccak256(toBytes("coffee")),
    keccak256(toBytes("tea")),
  ].sort());
  assert.match(commitment.categorySetHash, /^0x[0-9a-f]{64}$/);
});

test("prepare derives one exact wallet request from the current committed record", async () => {
  const merchantRecord = record();
  const hash = `0x${await registryRecordHash(merchantRecord)}`;
  const client = publicClient(hash);
  const result = await prepareDiscoveryFacetsPublication({
    enrollmentPlan: {
      deployment: {
        id: deployment.id,
        chain_id: deployment.caip2,
        registry_address: deployment.registry_address,
      },
      identity: { controller, record_id: recordId },
      record: {
        record_hash: hash,
        record_uri: `https://tea.example/.well-known/agentcart-registry-records/${hash.slice(2)}.json`,
      },
    },
    deployment,
    publicClient: client,
    loadRecord: async () => merchantRecord,
  });

  assert.equal(result.state, "ready_to_publish");
  assert.equal(result.ready, true);
  assert.equal(result.wallet_request.method, "eth_sendTransaction");
  assert.equal(result.transaction_request.to.toLowerCase(), deployment.discovery_facets.address.toLowerCase());
  assert.match(result.required_ack, /^publish-facets:eip155:42431:/);
  assert.ok(client.calls.includes("call:publish"));
});

test("prepare is idempotent when the same category commitment is finalized", async () => {
  const merchantRecord = record();
  const hash = `0x${await registryRecordHash(merchantRecord)}`;
  const commitment = categoryCommitmentFromRecord(merchantRecord);
  const client = publicClient(hash, {
    recordHash: hash,
    categorySetHash: commitment.categorySetHash,
    generation: 3,
    categoryCount: 2,
  });
  const result = await prepareDiscoveryFacetsPublication({
    enrollmentPlan: {
      deployment: { id: deployment.id, chain_id: deployment.caip2, registry_address: deployment.registry_address },
      identity: { controller, record_id: recordId },
      record: { record_hash: hash, record_uri: `https://tea.example/record.json` },
    },
    deployment,
    publicClient: client,
    loadRecord: async () => merchantRecord,
  });
  assert.equal(result.state, "finalized_current");
  assert.equal(result.generation, 3);
  assert.equal(result.transaction_request, null);
  assert.equal(client.calls.includes("call:publish"), false);
});

test("finalized facet verification fails closed on a changed record generation", async () => {
  const merchantRecord = record();
  const hash = `0x${await registryRecordHash(merchantRecord)}`;
  const commitment = categoryCommitmentFromRecord(merchantRecord);
  const result = await verifyDiscoveryFacetsState({
    plan: {
      schema: "agentcart.merchant_discovery_facets_plan.v1",
      identity: { controller, record_id: recordId, record_hash: hash },
      category_hashes: commitment.categoryHashes,
      category_set_hash: commitment.categorySetHash,
    },
    deployment,
    publicClient: publicClient(hash, {
      recordHash: `0x${"99".repeat(32)}`,
      categorySetHash: commitment.categorySetHash,
      generation: 4,
      categoryCount: 2,
    }),
  });
  assert.equal(result.ready, false);
  assert.equal(result.state, "finalized_mismatch");
});

test("finalized facet verification also requires the registry record to remain current", async () => {
  const merchantRecord = record();
  const hash = `0x${await registryRecordHash(merchantRecord)}`;
  const commitment = categoryCommitmentFromRecord(merchantRecord);
  const client = publicClient(hash, {
    recordHash: hash,
    categorySetHash: commitment.categorySetHash,
    generation: 2,
    categoryCount: 2,
  });
  const originalRead = client.readContract;
  client.readContract = async (args) => {
    if (args.functionName === "record") {
      return {
        controller,
        recordHash: `0x${"88".repeat(32)}`,
        domainHash,
        status: 1,
      };
    }
    return originalRead(args);
  };
  const result = await verifyDiscoveryFacetsState({
    plan: {
      schema: "agentcart.merchant_discovery_facets_plan.v1",
      identity: { controller, record_id: recordId, record_hash: hash },
      category_hashes: commitment.categoryHashes,
      category_set_hash: commitment.categorySetHash,
    },
    deployment,
    publicClient: client,
  });
  assert.equal(result.ready, false);
  assert.equal(result.registry_current, false);
});

test("facets operator exposes only plan-bound publication commands", () => {
  const help = spawnSync(process.execPath, ["scripts/onchain-discovery-facets-operator.mjs", "--help"], {
    cwd: new URL("..", import.meta.url),
    encoding: "utf8",
  });
  assert.equal(help.status, 0, help.stderr);
  assert.match(help.stdout, /prepare --enrollment-plan/);
  assert.doesNotMatch(help.stdout, /publish --record-id/);
});
