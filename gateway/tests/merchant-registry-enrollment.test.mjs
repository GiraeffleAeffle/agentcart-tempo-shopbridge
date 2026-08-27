import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

import { encodeFunctionData, keccak256, toBytes } from "viem";

import {
  merchantPlanIntentHash,
  prepareMerchantRevocation,
  prepareMerchantEnrollment,
  merchantRegistryAbi,
  tempoModeratoDeployment,
  verifyMerchantRegistryDeployment,
  verifyMerchantPlanFinality,
} from "../scripts/merchant-registry-enrollment.mjs";
import { registryRecordHash } from "../scripts/onchain-registry-indexer.mjs";
import {
  executeMerchantPlan,
  verifyMerchantTransactionInclusion,
  waitForReceiptFinality,
} from "../scripts/onchain-registry-operator.mjs";

const controller = "0x1111111111111111111111111111111111111111";
const registryAddress = "0x0965961617c5b0898167aa4034c5511db0efca07";
const recordId = `0x${"44".repeat(32)}`;
const zeroBytes32 = `0x${"00".repeat(32)}`;
const finalizedHash = `0x${"bb".repeat(32)}`;
const deploymentHash = "0x8646ecbbb11ac5cf6195dd7e288acb2541f02ef0d580e3bc9afa2e42045edd26";
const domain = "tea.example";
const domainHash = keccak256(toBytes(domain));
const runtimeBytecode = "0x6000";
const testDeployment = Object.freeze({
  ...tempoModeratoDeployment,
  runtime_code_hash: keccak256(runtimeBytecode),
});

function client({ existingId = zeroBytes32, recordHash = zeroBytes32, status = 0 } = {}) {
  const calls = [];
  let liveRecordHash = recordHash;
  let liveExistingId = existingId;
  let liveStatus = status;
  return {
    calls,
    setRegistryState(next) {
      if (next.recordHash !== undefined) liveRecordHash = next.recordHash;
      if (next.existingId !== undefined) liveExistingId = next.existingId;
      if (next.status !== undefined) liveStatus = next.status;
    },
    async getChainId() {
      calls.push("getChainId");
      return 42431;
    },
    async getBlock({ blockTag, blockNumber }) {
      calls.push(`getBlock:${blockTag}`);
      if (blockNumber === 30731101n) {
        return { number: blockNumber, hash: deploymentHash, timestamp: 1_787_000_000n };
      }
      return {
        number: 32_200_000n,
        hash: finalizedHash,
        timestamp: BigInt(Math.floor(Date.now() / 1000) - 30),
      };
    },
    async getBytecode({ address, blockNumber }) {
      calls.push(`getBytecode:${address}:${blockNumber}`);
      return blockNumber === 30731100n ? "0x" : runtimeBytecode;
    },
    async readContract({ functionName }) {
      calls.push(`read:${functionName}`);
      if (functionName === "computeRecordId") return recordId;
      if (functionName === "recordIdForDomain") return liveExistingId;
      if (functionName === "revokedRecordHashes") return liveStatus === 2;
      if (functionName === "writesPaused") return false;
      if (functionName === "record") {
        return {
          controller,
          recordHash: liveRecordHash,
          domainHash,
          updatedAt: 1n,
          attestedAt: 0n,
          attestationExpiresAt: 0n,
          attestationGeneration: 0,
          attestationCount: 0,
          status: liveStatus,
        };
      }
      throw new Error(`unexpected read: ${functionName}`);
    },
    async simulateContract({ functionName, account }) {
      calls.push(`simulate:${functionName}:${account}`);
      return { request: {} };
    },
  };
}

function baseRecord(identity = undefined) {
  const record = {
    merchant_id: "tea.example",
    name: "Tea Shop",
    domain,
    manifest_url: "https://tea.example/.well-known/agentcart.json",
  };
  if (identity) record.onchain_identity = identity;
  return record;
}

async function bundleFor(record) {
  const hash = await registryRecordHash(record);
  return {
    type: "agentcart-registry-onboarding-bundle",
    version: "0.1",
    merchant_id: record.merchant_id,
    registry_record: record,
    record_hash: hash,
    record_uri: `https://tea.example/.well-known/agentcart-registry-records/${hash}.json`,
  };
}

test("first prepare returns only the public identity settings and never simulates", async () => {
  const publicClient = client();
  let recordLoads = 0;
  const plan = await prepareMerchantEnrollment({
    bundle: await bundleFor(baseRecord()),
    bundleUrl: "https://tea.example/.well-known/agentcart-registry-bundle.json",
    controller,
    deployment: testDeployment,
    publicClient,
    loadRecord: async () => {
      recordLoads += 1;
      throw new Error("record must not be loaded during identity preparation");
    },
  });

  assert.equal(plan.state, "store_identity_required");
  assert.equal(plan.ready, false);
  assert.deepEqual(plan.wordpress_settings, {
    controller,
    chain_id: "eip155:42431",
    registry_address: registryAddress,
    record_id: recordId,
  });
  assert.equal(recordLoads, 0);
  assert.equal(publicClient.calls.some((call) => call.startsWith("simulate:")), false);
});

test("second prepare verifies the immutable record and emits a register wallet request", async () => {
  const identity = {
    controller,
    chain_id: "eip155:42431",
    registry_address: registryAddress,
    record_id: recordId,
    standard: "AgentCart-Onchain-Registry-v1",
  };
  const record = baseRecord(identity);
  const bundle = await bundleFor(record);
  const publicClient = client();
  const plan = await prepareMerchantEnrollment({
    bundle,
    bundleUrl: "https://tea.example/.well-known/agentcart-registry-bundle.json",
    controller,
    deployment: testDeployment,
    publicClient,
    loadRecord: async (uri, hash) => {
      assert.equal(uri, bundle.record_uri);
      assert.equal(hash, `0x${bundle.record_hash}`);
      return record;
    },
  });

  assert.equal(plan.state, "ready_to_register");
  assert.equal(plan.operation, "register");
  assert.equal(plan.ready, true);
  assert.equal(plan.record.immutable_uri_verified, true);
  assert.equal(plan.chain_snapshot.block_tag, "finalized");
  assert.deepEqual(plan.wallet_request, {
    method: "eth_sendTransaction",
    params: [
      {
        chainId: "0xa5bf",
        from: controller,
        to: registryAddress,
        data: plan.transaction_request.data,
        value: "0x0",
      },
    ],
  });
  assert.ok(publicClient.calls.includes("simulate:register:0x1111111111111111111111111111111111111111"));
});

test("prepare chooses update for the controller's active record with a different hash", async () => {
  const identity = {
    controller,
    chain_id: "eip155:42431",
    registry_address: registryAddress,
    record_id: recordId,
  };
  const record = baseRecord(identity);
  const bundle = await bundleFor(record);
  const publicClient = client({ existingId: recordId, recordHash: `0x${"99".repeat(32)}`, status: 1 });
  const plan = await prepareMerchantEnrollment({
    bundle,
    bundleUrl: "https://tea.example/.well-known/agentcart-registry-bundle.json",
    controller,
    deployment: testDeployment,
    publicClient,
    loadRecord: async () => record,
  });

  assert.equal(plan.state, "ready_to_update");
  assert.equal(plan.operation, "update");
  assert.equal(publicClient.calls.includes("read:computeRecordId"), false);
  assert.ok(publicClient.calls.includes(`simulate:update:${controller}`));
});

test("prepare reports the exact finalized record as current without another transaction", async () => {
  const identity = {
    controller,
    chain_id: "eip155:42431",
    registry_address: registryAddress,
    record_id: recordId,
  };
  const record = baseRecord(identity);
  const bundle = await bundleFor(record);
  const publicClient = client({ existingId: recordId, recordHash: `0x${bundle.record_hash}`, status: 1 });
  const plan = await prepareMerchantEnrollment({
    bundle,
    bundleUrl: "https://tea.example/.well-known/agentcart-registry-bundle.json",
    controller,
    deployment: testDeployment,
    publicClient,
    loadRecord: async () => record,
  });

  assert.equal(plan.state, "finalized_current");
  assert.equal(plan.operation, "none");
  assert.equal(plan.ready, true);
  assert.equal(plan.transaction_request, null);
  assert.equal(publicClient.calls.includes("read:computeRecordId"), false);
  assert.equal(publicClient.calls.some((call) => call.startsWith("simulate:")), false);
});

test("a public identity mismatch fails before immutable loading or simulation", async () => {
  const wrongIdentity = {
    controller: "0x2222222222222222222222222222222222222222",
    chain_id: "eip155:42431",
    registry_address: registryAddress,
    record_id: recordId,
  };
  const publicClient = client();
  let loaded = false;
  await assert.rejects(
    prepareMerchantEnrollment({
      bundle: await bundleFor(baseRecord(wrongIdentity)),
      bundleUrl: "https://tea.example/.well-known/agentcart-registry-bundle.json",
      controller,
      deployment: testDeployment,
      publicClient,
      loadRecord: async () => {
        loaded = true;
      },
    }),
    /controller_proof_controller_mismatch/,
  );
  assert.equal(loaded, false);
  assert.equal(publicClient.calls.some((call) => call.startsWith("simulate:")), false);
});

test("a saved enrollment plan can prepare emergency revocation while the shop is offline", async () => {
  const recordHash = `0x${"77".repeat(32)}`;
  const publicClient = client({ existingId: recordId, recordHash, status: 1 });
  const savedPlan = {
    schema: "agentcart.merchant_onchain_plan.v1",
    deployment: {
      id: "tempo-moderato",
      chain_id: "eip155:42431",
      registry_address: registryAddress,
      deployment_block: testDeployment.deployment_block,
      deployment_block_hash: testDeployment.deployment_block_hash,
      runtime_code_hash: testDeployment.runtime_code_hash,
    },
    identity: { controller, domain_hash: domainHash, record_id: recordId },
    record: { record_hash: recordHash },
  };
  const plan = await prepareMerchantRevocation({
    plan: savedPlan,
    reason: "merchant_admin_revoke",
    deployment: testDeployment,
    publicClient,
  });

  assert.equal(plan.state, "ready_to_revoke");
  assert.equal(plan.operation, "revoke");
  assert.equal(plan.ready, true);
  assert.equal(plan.record.record_hash, recordHash);
  assert.equal(plan.wallet_request.method, "eth_sendTransaction");
  assert.ok(publicClient.calls.includes(`simulate:revoke:${controller}`));
});

test("finality verification distinguishes active and revoked plans", async () => {
  const recordHash = `0x${"77".repeat(32)}`;
  const plan = {
    schema: "agentcart.merchant_onchain_plan.v1",
    deployment: {
      id: "tempo-moderato",
      chain_id: "eip155:42431",
      registry_address: registryAddress,
      deployment_block: testDeployment.deployment_block,
      deployment_block_hash: testDeployment.deployment_block_hash,
      runtime_code_hash: testDeployment.runtime_code_hash,
    },
    identity: { controller, domain_hash: domainHash, record_id: recordId },
    record: { record_hash: recordHash },
  };

  const active = await verifyMerchantPlanFinality({
    plan,
    expectedState: "active",
    deployment: testDeployment,
    publicClient: client({ existingId: recordId, recordHash, status: 1 }),
  });
  assert.equal(active.state, "finalized_current");
  assert.equal(active.ready, true);

  const revoked = await verifyMerchantPlanFinality({
    plan,
    expectedState: "revoked",
    deployment: testDeployment,
    publicClient: client({ existingId: zeroBytes32, recordHash, status: 2 }),
  });
  assert.equal(revoked.state, "finalized_revoked");
  assert.equal(revoked.ready, true);
});

test("mutation completion waits for finalized inclusion and checks canonical block identity", async () => {
  let finalizedReads = 0;
  const receipt = { blockNumber: 120n, blockHash: `0x${"aa".repeat(32)}` };
  const result = await waitForReceiptFinality(
    {
      async getBlock({ blockTag, blockNumber }) {
        if (blockTag === "finalized") {
          finalizedReads += 1;
          return {
            number: finalizedReads === 1 ? 119n : 121n,
            hash: `0x${"bb".repeat(32)}`,
            timestamp: 1_787_680_000n,
          };
        }
        assert.equal(blockNumber, 120n);
        return { number: blockNumber, hash: receipt.blockHash };
      },
    },
    receipt,
    { wait: async () => {}, timeoutMs: 1000 },
  );

  assert.equal(finalizedReads, 2);
  assert.equal(result.block_tag, "finalized");
  assert.equal(result.block_number, 121);
  assert.equal(result.receipt_included, true);
});

test("deployment verification pins runtime code, creation boundary, and fresh finality", async () => {
  const valid = client();
  await verifyMerchantRegistryDeployment(valid, testDeployment);
  assert.ok(valid.calls.some((call) => call.endsWith(":30731101")));
  assert.ok(valid.calls.some((call) => call.endsWith(":30731100")));

  const preexisting = client();
  preexisting.getBytecode = async () => runtimeBytecode;
  await assert.rejects(
    verifyMerchantRegistryDeployment(preexisting, testDeployment),
    /deployment_block_not_contract_creation_boundary/,
  );

  const stale = client();
  const originalGetBlock = stale.getBlock;
  stale.getBlock = async ({ blockTag, blockNumber }) => {
    if (blockTag === "finalized") {
      return {
        number: 32_200_000n,
        hash: finalizedHash,
        timestamp: BigInt(Math.floor(Date.now() / 1000) - 601),
      };
    }
    return originalGetBlock({ blockTag, blockNumber });
  };
  await assert.rejects(
    verifyMerchantRegistryDeployment(stale, testDeployment),
    /rpc_finalized_block_time_stale/,
  );
});

test("the public operator CLI exposes no free-form mutation command", () => {
  const help = spawnSync(process.execPath, ["scripts/onchain-registry-operator.mjs", "--help"], {
    cwd: new URL("..", import.meta.url),
    encoding: "utf8",
  });
  assert.equal(help.status, 0, help.stderr);
  assert.doesNotMatch(help.stdout, /register --rpc-url|update --rpc-url|revoke --rpc-url/);

  const rawRegister = spawnSync(
    process.execPath,
    ["scripts/onchain-registry-operator.mjs", "register"],
    { cwd: new URL("..", import.meta.url), encoding: "utf8" },
  );
  assert.equal(rawRegister.status, 1);
  assert.match(rawRegister.stderr, /unsupported command: register/);
});

test("the supervised signer executes only an acknowledged prepared plan and verifies finality", async () => {
  const identity = {
    controller,
    chain_id: "eip155:42431",
    registry_address: registryAddress,
    record_id: recordId,
  };
  const record = baseRecord(identity);
  const bundle = await bundleFor(record);
  const recordHash = `0x${bundle.record_hash}`;
  const priorRecordHash = `0x${"77".repeat(32)}`;
  const transactionHash = `0x${"88".repeat(32)}`;
  const receiptHash = `0x${"99".repeat(32)}`;
  const receiptBlock = 32_199_900n;
  const publicClient = client({ existingId: recordId, recordHash: priorRecordHash, status: 1 });
  const plan = await prepareMerchantEnrollment({
    bundle,
    bundleUrl: "https://tea.example/.well-known/agentcart-registry-bundle.json",
    controller,
    deployment: testDeployment,
    publicClient,
    loadRecord: async () => record,
  });
  const requiredAck = plan.required_ack;
  const transactionData = plan.transaction_request.data;
  publicClient.call = async ({ account, to, data }) => {
    assert.equal(account, controller);
    assert.equal(to.toLowerCase(), registryAddress);
    assert.equal(data, transactionData);
  };
  publicClient.waitForTransactionReceipt = async ({ hash }) => {
    assert.equal(hash, transactionHash);
    return { blockNumber: receiptBlock, blockHash: receiptHash, status: "success" };
  };
  publicClient.getBlock = async ({ blockTag, blockNumber }) => {
    if (blockNumber === 30731101n) {
      return { number: blockNumber, hash: deploymentHash, timestamp: 1_787_000_000n };
    }
    if (blockNumber === receiptBlock) return { number: blockNumber, hash: receiptHash };
    assert.equal(blockTag, "finalized");
    return {
      number: 32_200_000n,
      hash: finalizedHash,
      timestamp: BigInt(Math.floor(Date.now() / 1000) - 30),
    };
  };
  let writes = 0;
  const walletClient = {
    async sendTransaction() {
      writes += 1;
      publicClient.setRegistryState({ recordHash });
      return transactionHash;
    },
  };
  await assert.rejects(
    executeMerchantPlan({
      plan,
      deployment: testDeployment,
      publicClient,
      walletClient,
      account: { address: controller },
      environment: { AGENTCART_ONCHAIN_ACK: "update:eip155:42431:wrong" },
      loadRecord: async () => record,
    }),
    /set AGENTCART_ONCHAIN_ACK=/,
  );
  assert.equal(writes, 0);

  const getBlock = publicClient.getBlock;
  publicClient.getBlock = async ({ blockTag, blockNumber }) => {
    if (blockNumber === 30731101n) {
      return { number: blockNumber, hash: `0x${"12".repeat(32)}`, timestamp: 1_787_000_000n };
    }
    return getBlock({ blockTag, blockNumber });
  };
  await assert.rejects(
    executeMerchantPlan({
      plan,
      deployment: testDeployment,
      publicClient,
      walletClient,
      account: { address: controller },
      environment: { AGENTCART_ONCHAIN_ACK: requiredAck },
      loadRecord: async () => record,
    }),
    /deployment_block_hash_mismatch/,
  );
  assert.equal(writes, 0);
  publicClient.getBlock = getBlock;

  await assert.rejects(
    executeMerchantPlan({
      plan,
      deployment: testDeployment,
      publicClient,
      walletClient,
      account: { address: controller },
      environment: { AGENTCART_ONCHAIN_ACK: requiredAck },
      loadRecord: async () => record,
      now: () => Date.parse(plan.expires_at),
    }),
    /merchant plan has expired/,
  );
  assert.equal(writes, 0);

  const tampered = structuredClone(plan);
  tampered.record.record_hash = `0x${"ab".repeat(32)}`;
  tampered.record.record_uri = `https://tea.example/.well-known/agentcart-registry-records/${"ab".repeat(32)}.json`;
  tampered.transaction_request.data = encodeFunctionData({
    abi: merchantRegistryAbi,
    functionName: "update",
    args: [recordId, tampered.record.record_hash, tampered.record.record_uri],
  });
  tampered.wallet_request.params[0] = tampered.transaction_request;
  tampered.intent_hash = merchantPlanIntentHash(tampered);
  tampered.required_ack = `update:eip155:42431:${registryAddress}:${recordId}:${tampered.intent_hash}`;
  await assert.rejects(
    executeMerchantPlan({
      plan: tampered,
      deployment: testDeployment,
      publicClient,
      walletClient,
      account: { address: controller },
      environment: { AGENTCART_ONCHAIN_ACK: requiredAck },
      loadRecord: async () => {
        throw new Error("tampered record must not be fetched");
      },
    }),
    /set AGENTCART_ONCHAIN_ACK=/,
  );
  assert.equal(writes, 0);

  publicClient.setRegistryState({ recordHash: `0x${"aa".repeat(32)}` });
  await assert.rejects(
    executeMerchantPlan({
      plan,
      deployment: testDeployment,
      publicClient,
      walletClient,
      account: { address: controller },
      environment: { AGENTCART_ONCHAIN_ACK: requiredAck },
      loadRecord: async () => record,
    }),
    /merchant_plan_precondition_current_record_hash_mismatch/,
  );
  assert.equal(writes, 0);
  publicClient.setRegistryState({ recordHash: priorRecordHash });

  const result = await executeMerchantPlan({
    plan,
    deployment: testDeployment,
    publicClient,
    walletClient,
    account: { address: controller },
    environment: { AGENTCART_ONCHAIN_ACK: requiredAck },
    loadRecord: async () => record,
  });

  assert.equal(writes, 1);
  assert.equal(result.state, "finalized_current");
  assert.equal(result.transaction.hash, transactionHash);
  assert.equal(result.finality.block_number, 32_200_000);

  publicClient.setRegistryState({ recordHash: priorRecordHash });
  publicClient.getBlock = async ({ blockTag, blockNumber }) => {
    if (blockNumber === 30731101n) {
      return { number: blockNumber, hash: deploymentHash, timestamp: 1_787_000_000n };
    }
    assert.equal(blockTag, "finalized");
    return {
      number: receiptBlock - 1n,
      hash: finalizedHash,
      timestamp: BigInt(Math.floor(Date.now() / 1000) - 30),
    };
  };
  let clock = 0;
  const pending = await executeMerchantPlan({
    plan,
    deployment: testDeployment,
    publicClient,
    walletClient,
    account: { address: controller },
    environment: { AGENTCART_ONCHAIN_ACK: requiredAck },
    loadRecord: async () => record,
    finalityOptions: {
      timeoutMs: 1000,
      wait: async () => {},
      now: () => {
        clock += 1001;
        return clock;
      },
    },
  });
  assert.equal(writes, 2);
  assert.equal(pending.state, "submitted_unverified");
  assert.equal(pending.ready, false);
  assert.equal(pending.transaction.hash, transactionHash);
  assert.deepEqual(pending.blockers, ["finality_timeout"]);
});

test("every post-broadcast failure preserves the transaction hash for recovery", async () => {
  const identity = {
    controller,
    chain_id: "eip155:42431",
    registry_address: registryAddress,
    record_id: recordId,
  };
  const record = baseRecord(identity);
  const bundle = await bundleFor(record);
  const priorRecordHash = `0x${"77".repeat(32)}`;
  const publicClient = client({ existingId: recordId, recordHash: priorRecordHash, status: 1 });
  const plan = await prepareMerchantEnrollment({
    bundle,
    bundleUrl: "https://tea.example/.well-known/agentcart-registry-bundle.json",
    controller,
    deployment: testDeployment,
    publicClient,
    loadRecord: async () => record,
  });
  const transactionHash = `0x${"88".repeat(32)}`;
  publicClient.call = async () => {};
  publicClient.waitForTransactionReceipt = async () => {
    throw new Error("rpc receipt unavailable");
  };
  let journal = null;
  const result = await executeMerchantPlan({
    plan,
    deployment: testDeployment,
    publicClient,
    walletClient: { sendTransaction: async () => transactionHash },
    account: { address: controller },
    environment: { AGENTCART_ONCHAIN_ACK: plan.required_ack },
    loadRecord: async () => record,
    onSubmitted: async (entry) => {
      journal = entry;
    },
  });

  assert.equal(result.state, "submitted_unverified");
  assert.equal(result.transaction.hash, transactionHash);
  assert.equal(journal.transaction.hash, transactionHash);
  assert.deepEqual(result.blockers, ["post_submission_verification_failed"]);
});

test("external-wallet verification binds finalized inclusion to the exact prepared transaction", async () => {
  const identity = {
    controller,
    chain_id: "eip155:42431",
    registry_address: registryAddress,
    record_id: recordId,
  };
  const record = baseRecord(identity);
  const bundle = await bundleFor(record);
  const targetHash = `0x${bundle.record_hash}`;
  const publicClient = client({
    existingId: recordId,
    recordHash: `0x${"77".repeat(32)}`,
    status: 1,
  });
  const plan = await prepareMerchantEnrollment({
    bundle,
    bundleUrl: "https://tea.example/.well-known/agentcart-registry-bundle.json",
    controller,
    deployment: testDeployment,
    publicClient,
    loadRecord: async () => record,
  });
  const transactionHash = `0x${"88".repeat(32)}`;
  const receiptHash = `0x${"99".repeat(32)}`;
  publicClient.setRegistryState({ recordHash: targetHash });
  publicClient.getTransactionReceipt = async () => ({
    transactionHash,
    blockNumber: 350n,
    blockHash: receiptHash,
    status: "success",
  });
  publicClient.getTransaction = async () => ({
    hash: transactionHash,
    from: controller,
    to: registryAddress,
    input: plan.transaction_request.data,
    value: 0n,
  });
  const originalGetBlock = publicClient.getBlock;
  publicClient.getBlock = async ({ blockTag, blockNumber }) => {
    if (blockNumber === 350n) return { number: blockNumber, hash: receiptHash };
    return originalGetBlock({ blockTag, blockNumber });
  };

  const result = await verifyMerchantTransactionInclusion({
    plan,
    transactionHash,
    deployment: testDeployment,
    publicClient,
  });
  assert.equal(result.ready, true);
  assert.equal(result.transaction.hash, transactionHash);

  publicClient.getTransaction = async () => ({
    hash: transactionHash,
    from: controller,
    to: registryAddress,
    input: "0xdeadbeef",
    value: 0n,
  });
  await assert.rejects(
    verifyMerchantTransactionInclusion({
      plan,
      transactionHash,
      deployment: testDeployment,
      publicClient,
    }),
    /merchant transaction calldata does not match the prepared plan/,
  );
});
