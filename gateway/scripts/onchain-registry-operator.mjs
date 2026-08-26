#!/usr/bin/env node

import process from "node:process";
import { readFile, writeFile } from "node:fs/promises";

import {
  createPublicClient,
  createWalletClient,
  decodeFunctionData,
  getAddress,
  http,
  isAddress,
  keccak256,
  parseAbi,
  toBytes,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";
import {
  assertControllerBoundIdentity,
  fetchPublicJsonDocument,
  fetchRegistryRecord,
  normalizedDomain,
  registryRecordHash,
} from "./onchain-registry-indexer.mjs";
import {
  merchantPlanIntentHash,
  merchantRegistryAbi,
  merchantRegistryDeployments,
  prepareMerchantEnrollment,
  prepareMerchantRevocation,
  validateMerchantRegistryDeployment,
  verifyMerchantRegistryDeployment,
  verifyMerchantPlanFinality,
} from "./merchant-registry-enrollment.mjs";

const statusAbi = parseAbi([
  "function owner() view returns (address)",
]);
const productionChainIds = new Set([1, 100, 4217]);

function usage() {
  return `Usage:
  node scripts/onchain-registry-operator.mjs prepare --deployment tempo-moderato --bundle-url https://shop.example/.well-known/agentcart-registry-bundle.json --controller 0x... [--output plan.json]
  node scripts/onchain-registry-operator.mjs execute --plan plan.json
  node scripts/onchain-registry-operator.mjs prepare-revoke --plan plan.json --reason merchant_admin_revoke [--output revoke-plan.json]
  node scripts/onchain-registry-operator.mjs verify --plan plan.json --transaction-hash 0x... [--expected-state active|revoked]
  node scripts/onchain-registry-operator.mjs status --deployment tempo-moderato [--record-id 0x...]

The operator exposes no free-form mutation command. Every write must come from
a short-lived, deployment-pinned plan whose acknowledgement includes the exact
intent hash. Never place a private key on the command line.

The prepare command performs no mutation and needs no private key. Its first run
returns four public WordPress settings; its second run returns a reviewed
eth_sendTransaction request for the controller's external wallet.

The execute command is an optional supervised fallback for an isolated signer.
It reads AGENTCART_ONCHAIN_PRIVATE_KEY and requires the plan's exact required_ack.
It writes a mode-0600 submission journal immediately after broadcast. Never
blindly retry a submitted_unverified result; use verify with its transaction hash.
`;
}

export function assertMutationNetworkAllowed(chainId, environment = process.env, networkClass = "") {
  if (
    (productionChainIds.has(Number(chainId)) || networkClass === "mainnet") &&
    String(environment.AGENTCART_ONCHAIN_ALLOW_MAINNET || "").toLowerCase() !== "true"
  ) {
    throw new Error(`production-network mutations are disabled for chain ${chainId}`);
  }
}

function parseArgs(argv) {
  const [command, ...rest] = argv;
  if (!command || ["-h", "--help", "help"].includes(command)) return { command: "help" };
  const values = { command };
  for (let index = 0; index < rest.length; index += 1) {
    const flag = rest[index];
    if (!flag.startsWith("--")) throw new Error(`unexpected argument: ${flag}`);
    const key = flag.slice(2).replaceAll("-", "_");
    const value = rest[index + 1];
    if (!value || value.startsWith("--")) throw new Error(`${flag} requires a value`);
    values[key] = value;
    index += 1;
  }
  return values;
}

function bytes32(value, flag) {
  if (!/^0x[0-9a-fA-F]{64}$/.test(String(value || ""))) {
    throw new Error(`${flag} must be a 0x-prefixed bytes32 value`);
  }
  return value.toLowerCase();
}

function recordJson(record) {
  const values = Array.isArray(record)
    ? {
        controller: record[0],
        recordHash: record[1],
        domainHash: record[2],
        updatedAt: record[3],
        attestedAt: record[4],
        attestationExpiresAt: record[5],
        attestationGeneration: record[6],
        attestationCount: record[7],
        status: record[8],
      }
    : record;
  return {
    controller: values.controller,
    record_hash: values.recordHash,
    domain_hash: values.domainHash,
    updated_at: Number(values.updatedAt),
    attested_at: Number(values.attestedAt),
    attestation_expires_at: Number(values.attestationExpiresAt),
    attestation_generation: Number(values.attestationGeneration),
    attestation_count: Number(values.attestationCount),
    status: Number(values.status),
  };
}

async function writeResult(result, output) {
  const text = `${JSON.stringify(result, null, 2)}\n`;
  if (output) {
    await writeFile(output, text, { encoding: "utf8", flag: "wx", mode: 0o600 });
    process.stdout.write(`${JSON.stringify({ state: result.state, output }, null, 2)}\n`);
    return;
  }
  process.stdout.write(text);
}

async function readPlan(path) {
  if (!path) throw new Error("--plan is required");
  const parsed = JSON.parse(await readFile(path, "utf8"));
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("--plan must contain a JSON object");
  }
  return parsed;
}

export async function waitForReceiptFinality(
  publicClient,
  receipt,
  {
    timeoutMs = 600_000,
    wait = () => new Promise((resolve) => setTimeout(resolve, 4_000)),
    now = () => Date.now(),
  } = {},
) {
  const startedAt = now();
  while (true) {
    const finalized = await publicClient.getBlock({ blockTag: "finalized" });
    if (!finalized?.hash || finalized.number === null || finalized.number === undefined) {
      throw new Error("RPC endpoint did not return a finalized block");
    }
    if (finalized.number >= receipt.blockNumber) {
      const canonicalReceiptBlock = await publicClient.getBlock({ blockNumber: receipt.blockNumber });
      if (String(canonicalReceiptBlock?.hash || "").toLowerCase() !== String(receipt.blockHash || "").toLowerCase()) {
        throw new Error("transaction receipt block is not canonical at finality");
      }
      return {
        block_tag: "finalized",
        block_number: Number(finalized.number),
        block_hash: finalized.hash,
        block_time: finalized.timestamp === undefined
          ? ""
          : new Date(Number(finalized.timestamp) * 1000).toISOString().replace(".000Z", "Z"),
        receipt_included: true,
      };
    }
    if (now() - startedAt >= timeoutMs) {
      throw new Error("transaction mined but did not reach finalized before timeout");
    }
    await wait();
  }
}

function merchantImmutableRecordUrl(value, domain, recordHash) {
  let url;
  try {
    url = new URL(String(value || ""));
  } catch {
    throw new Error("merchant plan record URI is invalid");
  }
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.port ||
    normalizedDomain(url.hostname) !== domain ||
    url.pathname !== `/.well-known/agentcart-registry-records/${recordHash.slice(2)}.json` ||
    url.search ||
    url.hash
  ) {
    throw new Error("merchant plan record URI is not the merchant content-addressed URI");
  }
  return url.toString();
}

function assertPreparedTransaction(
  plan,
  deployment,
  { now = () => Date.now(), enforceExpiry = true } = {},
) {
  if (plan?.schema !== "agentcart.merchant_onchain_plan.v1") {
    throw new Error("merchant plan schema is invalid");
  }
  if (plan.ready !== true || !["register", "update", "revoke"].includes(plan.operation)) {
    throw new Error("merchant plan is not ready for execution");
  }
  if (plan.state !== `ready_to_${plan.operation}`) {
    throw new Error("merchant plan state does not match its operation");
  }
  if (
    plan.deployment?.id !== deployment.id ||
    plan.deployment?.chain_id !== deployment.caip2 ||
    String(plan.deployment?.registry_address || "").toLowerCase() !== deployment.registry_address.toLowerCase() ||
    Number(plan.deployment?.deployment_block) !== deployment.deployment_block ||
    String(plan.deployment?.deployment_block_hash || "").toLowerCase() !== deployment.deployment_block_hash.toLowerCase() ||
    String(plan.deployment?.runtime_code_hash || "").toLowerCase() !== deployment.runtime_code_hash.toLowerCase()
  ) {
    throw new Error("merchant plan deployment does not match the selected deployment");
  }
  const preparedAt = Date.parse(String(plan.prepared_at || ""));
  const expiresAt = Date.parse(String(plan.expires_at || ""));
  const referenceTime = Number(now());
  if (
    !Number.isFinite(preparedAt) ||
    !Number.isFinite(expiresAt) ||
    !Number.isFinite(referenceTime) ||
    expiresAt - preparedAt !== 30 * 60 * 1000 ||
    preparedAt > referenceTime + 120 * 1000
  ) {
    throw new Error("merchant plan validity window is invalid");
  }
  if (enforceExpiry && referenceTime >= expiresAt) {
    throw new Error("merchant plan has expired; prepare a fresh plan");
  }
  if (!isAddress(plan.identity?.controller || "") || /^0x0{40}$/i.test(plan.identity.controller)) {
    throw new Error("merchant plan controller is invalid");
  }
  const controller = getAddress(plan.identity.controller);
  const recordId = bytes32(plan.identity?.record_id, "plan identity record_id");
  const domainHash = bytes32(plan.identity?.domain_hash, "plan identity domain_hash");
  const recordHash = bytes32(plan.record?.record_hash, "plan record_hash");
  const domain = normalizedDomain(plan.merchant?.domain);
  if (!domain || keccak256(toBytes(domain)).toLowerCase() !== domainHash) {
    throw new Error("merchant plan domain does not match its identity");
  }
  if (
    plan.chain_snapshot?.block_tag !== "finalized" ||
    !Number.isSafeInteger(Number(plan.chain_snapshot?.block_number)) ||
    Number(plan.chain_snapshot.block_number) < deployment.deployment_block
  ) {
    throw new Error("merchant plan finalized snapshot is invalid");
  }
  bytes32(plan.chain_snapshot?.block_hash, "plan chain_snapshot block_hash");
  const precondition = plan.precondition;
  if (!precondition || typeof precondition !== "object" || Array.isArray(precondition)) {
    throw new Error("merchant plan state precondition is missing");
  }
  if (precondition.writes_paused !== false) {
    throw new Error("merchant plan writes-paused precondition is invalid");
  }
  const expectedDomainRecordId = bytes32(
    precondition.domain_record_id,
    "plan precondition domain_record_id",
  );
  const expectedCurrentHash = bytes32(
    precondition.current_record_hash,
    "plan precondition current_record_hash",
  );
  if (plan.operation === "register") {
    if (
      expectedDomainRecordId !== `0x${"00".repeat(32)}` ||
      expectedCurrentHash !== `0x${"00".repeat(32)}` ||
      precondition.current_status !== "unregistered"
    ) {
      throw new Error("merchant plan register precondition is invalid");
    }
  } else if (
    expectedDomainRecordId !== recordId ||
    precondition.current_status !== "active" ||
    (plan.operation === "revoke" && expectedCurrentHash !== recordHash)
  ) {
    throw new Error("merchant plan active-record precondition is invalid");
  }
  const transaction = plan.transaction_request;
  if (!transaction || typeof transaction !== "object" || Array.isArray(transaction)) {
    throw new Error("merchant plan transaction request is missing");
  }
  if (
    transaction.chainId !== `0x${deployment.chain_id.toString(16)}` ||
    !isAddress(transaction.from || "") ||
    getAddress(transaction.from) !== controller ||
    !isAddress(transaction.to || "") ||
    getAddress(transaction.to) !== getAddress(deployment.registry_address) ||
    transaction.value !== "0x0" ||
    !/^0x[0-9a-fA-F]+$/.test(String(transaction.data || ""))
  ) {
    throw new Error("merchant plan transaction envelope is invalid");
  }

  let decoded;
  try {
    decoded = decodeFunctionData({ abi: merchantRegistryAbi, data: transaction.data });
  } catch {
    throw new Error("merchant plan transaction data is invalid");
  }
  if (decoded.functionName !== plan.operation) {
    throw new Error("merchant plan transaction operation mismatch");
  }
  const args = decoded.args || [];
  if (plan.operation === "register") {
    const recordUri = merchantImmutableRecordUrl(plan.record?.record_uri, domain, recordHash);
    if (
      String(args[0] || "").toLowerCase() !== domainHash ||
      String(args[1] || "").toLowerCase() !== recordHash ||
      String(args[2] || "") !== recordUri
    ) {
      throw new Error("merchant plan register arguments are invalid");
    }
  } else if (plan.operation === "update") {
    const recordUri = merchantImmutableRecordUrl(plan.record?.record_uri, domain, recordHash);
    if (
      String(args[0] || "").toLowerCase() !== recordId ||
      String(args[1] || "").toLowerCase() !== recordHash ||
      String(args[2] || "") !== recordUri
    ) {
      throw new Error("merchant plan update arguments are invalid");
    }
  } else {
    const reasonHash = bytes32(plan.reason_hash, "plan reason_hash");
    if (String(args[0] || "").toLowerCase() !== recordId || String(args[1] || "").toLowerCase() !== reasonHash) {
      throw new Error("merchant plan revoke arguments are invalid");
    }
  }
  if (
    plan.wallet_request?.method !== "eth_sendTransaction" ||
    !Array.isArray(plan.wallet_request?.params) ||
    plan.wallet_request.params.length !== 1 ||
    JSON.stringify(plan.wallet_request.params[0]) !== JSON.stringify(transaction)
  ) {
    throw new Error("merchant plan wallet request does not match its transaction");
  }
  const intentHash = merchantPlanIntentHash(plan);
  if (bytes32(plan.intent_hash, "plan intent_hash") !== intentHash) {
    throw new Error("merchant plan intent hash is invalid");
  }
  const requiredAck = `${plan.operation}:${deployment.caip2}:${deployment.registry_address.toLowerCase()}:${recordId}:${intentHash}`;
  if (plan.required_ack !== requiredAck) throw new Error("merchant plan acknowledgement is invalid");
  return {
    operation: plan.operation,
    controller,
    domain,
    domainHash,
    recordId,
    recordHash,
    transaction,
    precondition: {
      domainRecordId: expectedDomainRecordId,
      currentRecordHash: expectedCurrentHash,
      currentStatus: precondition.current_status,
    },
    intentHash,
    requiredAck,
  };
}

function onchainRecordValues(record) {
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

async function assertMerchantPlanPrecondition(publicClient, deployment, prepared, finalizedBlock) {
  const registryAddress = getAddress(deployment.registry_address);
  const [computedRecordId, writesPaused, currentRecordId] = await Promise.all([
    publicClient.readContract({
      address: registryAddress,
      abi: merchantRegistryAbi,
      functionName: "computeRecordId",
      args: [prepared.domainHash, prepared.controller],
      blockNumber: finalizedBlock.number,
    }),
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
      args: [prepared.domainHash],
      blockNumber: finalizedBlock.number,
    }),
  ]);
  if (bytes32(computedRecordId, "computed record id") !== prepared.recordId) {
    throw new Error("merchant_plan_record_id_recomputation_mismatch");
  }
  if (writesPaused) throw new Error("merchant_plan_precondition_writes_paused");
  if (bytes32(currentRecordId, "current domain record id") !== prepared.precondition.domainRecordId) {
    throw new Error("merchant_plan_precondition_domain_record_id_mismatch");
  }
  if (prepared.operation === "register") return;

  const stored = onchainRecordValues(
    await publicClient.readContract({
      address: registryAddress,
      abi: merchantRegistryAbi,
      functionName: "record",
      args: [prepared.recordId],
      blockNumber: finalizedBlock.number,
    }),
  );
  if (String(stored.controller || "").toLowerCase() !== prepared.controller.toLowerCase()) {
    throw new Error("merchant_plan_precondition_controller_mismatch");
  }
  if (String(stored.domainHash || "").toLowerCase() !== prepared.domainHash) {
    throw new Error("merchant_plan_precondition_domain_hash_mismatch");
  }
  if (stored.status !== 1) throw new Error("merchant_plan_precondition_status_mismatch");
  if (String(stored.recordHash || "").toLowerCase() !== prepared.precondition.currentRecordHash) {
    throw new Error("merchant_plan_precondition_current_record_hash_mismatch");
  }
}

async function assertMerchantImmutableRecord(plan, deployment, prepared, loadRecord) {
  if (prepared.operation === "revoke") return;
  const record = await loadRecord(plan.record.record_uri, prepared.recordHash);
  if (`0x${await registryRecordHash(record)}` !== prepared.recordHash) {
    throw new Error("merchant_plan_immutable_record_hash_mismatch");
  }
  assertControllerBoundIdentity(record, {
    chainId: deployment.chain_id,
    controller: prepared.controller,
    registryAddress: getAddress(deployment.registry_address),
    recordId: prepared.recordId,
    domainHash: prepared.domainHash,
  });
}

function submittedUnverified(plan, transaction, blocker = "post_submission_verification_failed") {
  return {
    schema: "agentcart.merchant_onchain_execution.v1",
    ready: false,
    state: "submitted_unverified",
    operation: plan.operation,
    deployment: plan.deployment,
    identity: plan.identity,
    record: plan.record,
    intent_hash: plan.intent_hash,
    transaction,
    finality: {
      block_tag: "finalized",
      receipt_included: false,
    },
    blockers: [blocker],
    next_action: "Do not retry. Retain this transaction hash and run verify with the prepared plan and exact transaction hash.",
  };
}

export async function executeMerchantPlan({
  plan,
  deployment,
  publicClient,
  walletClient,
  account,
  environment = process.env,
  finalityOptions = {},
  loadRecord = fetchRegistryRecord,
  onSubmitted = async () => {},
  now = () => Date.now(),
}) {
  validateMerchantRegistryDeployment(deployment);
  assertMutationNetworkAllowed(deployment.chain_id, environment, deployment.network_class);
  const prepared = assertPreparedTransaction(plan, deployment, { now });
  if (!account?.address || !isAddress(account.address) || getAddress(account.address) !== prepared.controller) {
    throw new Error("signer account does not match the merchant controller");
  }
  if (environment.AGENTCART_ONCHAIN_ACK !== prepared.requiredAck) {
    throw new Error(`set AGENTCART_ONCHAIN_ACK=${prepared.requiredAck}`);
  }
  const finalizedBlock = await verifyMerchantRegistryDeployment(publicClient, deployment, { now });
  await assertMerchantPlanPrecondition(publicClient, deployment, prepared, finalizedBlock);
  await assertMerchantImmutableRecord(plan, deployment, prepared, loadRecord);
  await publicClient.call({
    account: prepared.controller,
    to: getAddress(prepared.transaction.to),
    data: prepared.transaction.data,
    value: 0n,
  });
  const transactionHash = await walletClient.sendTransaction({
    account,
    to: getAddress(prepared.transaction.to),
    data: prepared.transaction.data,
    value: 0n,
  });
  const transaction = {
    hash: transactionHash,
    status: "submitted",
  };
  try {
    await onSubmitted({
      schema: "agentcart.merchant_onchain_submission.v1",
      state: "submitted_unverified",
      submitted_at: new Date(Number(now())).toISOString(),
      operation: plan.operation,
      intent_hash: prepared.intentHash,
      deployment: plan.deployment,
      identity: plan.identity,
      record: plan.record,
      transaction,
    });
  } catch {
    return submittedUnverified(plan, transaction, "submission_journal_failed");
  }

  try {
    const receipt = await publicClient.waitForTransactionReceipt({
      hash: transactionHash,
      confirmations: 1,
    });
    transaction.block_number = Number(receipt.blockNumber);
    transaction.block_hash = receipt.blockHash;
    transaction.status = receipt.status;
    if (receipt.status !== "success") throw new Error("merchant registry transaction reverted");
    const receiptFinality = await waitForReceiptFinality(publicClient, receipt, finalityOptions);
    const verification = await verifyMerchantPlanFinality({
      plan,
      expectedState: plan.operation === "revoke" ? "revoked" : "active",
      deployment,
      publicClient,
      now,
    });
    if (!verification.ready) throw new Error("merchant registry transaction finalized in an unexpected state");
    return {
      ...verification,
      transaction,
      finality: receiptFinality,
    };
  } catch (error) {
    const blocker = error instanceof Error && error.message === "transaction mined but did not reach finalized before timeout"
      ? "finality_timeout"
      : "post_submission_verification_failed";
    return submittedUnverified(plan, transaction, blocker);
  }
}

/**
 * Verify an external-wallet transaction, its exact plan-bound envelope, its
 * canonical finalized inclusion, and the resulting registry state.
 */
export async function verifyMerchantTransactionInclusion({
  plan,
  transactionHash,
  expectedState = plan?.operation === "revoke" ? "revoked" : "active",
  deployment,
  publicClient,
  finalityOptions = {},
  now = () => Date.now(),
}) {
  validateMerchantRegistryDeployment(deployment);
  const prepared = assertPreparedTransaction(plan, deployment, {
    now,
    enforceExpiry: false,
  });
  const normalizedTransactionHash = bytes32(transactionHash, "transaction hash");
  await verifyMerchantRegistryDeployment(publicClient, deployment, { now });
  const [receipt, transactionData] = await Promise.all([
    publicClient.getTransactionReceipt({ hash: normalizedTransactionHash }),
    publicClient.getTransaction({ hash: normalizedTransactionHash }),
  ]);
  if (
    String(receipt?.transactionHash || normalizedTransactionHash).toLowerCase() !== normalizedTransactionHash ||
    receipt?.status !== "success"
  ) {
    throw new Error("merchant transaction receipt is missing or unsuccessful");
  }
  if (
    String(transactionData?.hash || normalizedTransactionHash).toLowerCase() !== normalizedTransactionHash ||
    !isAddress(transactionData?.from || "") ||
    getAddress(transactionData.from) !== prepared.controller
  ) {
    throw new Error("merchant transaction sender does not match the prepared plan");
  }
  if (
    !isAddress(transactionData?.to || "") ||
    getAddress(transactionData.to) !== getAddress(prepared.transaction.to)
  ) {
    throw new Error("merchant transaction target does not match the prepared plan");
  }
  if (BigInt(transactionData?.value ?? 0) !== 0n) {
    throw new Error("merchant transaction value does not match the prepared plan");
  }
  if (String(transactionData?.input ?? transactionData?.data ?? "").toLowerCase() !== prepared.transaction.data.toLowerCase()) {
    throw new Error("merchant transaction calldata does not match the prepared plan");
  }
  const receiptFinality = await waitForReceiptFinality(publicClient, receipt, finalityOptions);
  const verification = await verifyMerchantPlanFinality({
    plan,
    expectedState,
    deployment,
    publicClient,
    now,
  });
  if (!verification.ready) {
    throw new Error("merchant registry transaction finalized in an unexpected state");
  }
  return {
    ...verification,
    transaction: {
      hash: normalizedTransactionHash,
      block_number: Number(receipt.blockNumber),
      block_hash: receipt.blockHash,
      status: receipt.status,
      exact_plan_match: true,
    },
    finality: receiptFinality,
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.command === "help") {
    process.stdout.write(usage());
    return;
  }
  if (options.command === "prepare") {
    const deploymentId = options.deployment || "tempo-moderato";
    const deployment = merchantRegistryDeployments.get(deploymentId);
    if (!deployment) throw new Error(`unknown deployment: ${deploymentId}`);
    if (!options.bundle_url) throw new Error("--bundle-url is required");
    if (!isAddress(options.controller || "")) throw new Error("--controller is invalid");
    const publicClient = createPublicClient({
      transport: http(options.rpc_url || deployment.rpc_url, { timeout: 15_000 }),
    });
    const bundle = await fetchPublicJsonDocument(options.bundle_url);
    const result = await prepareMerchantEnrollment({
      bundle,
      bundleUrl: options.bundle_url,
      controller: options.controller,
      deployment,
      publicClient,
    });
    await writeResult(result, options.output);
    return;
  }
  if (options.command === "execute") {
    const plan = await readPlan(options.plan);
    const deploymentId = options.deployment || plan.deployment?.id || "";
    const deployment = merchantRegistryDeployments.get(deploymentId);
    if (!deployment) throw new Error(`unknown deployment: ${deploymentId || "missing"}`);
    const privateKey = String(process.env.AGENTCART_ONCHAIN_PRIVATE_KEY || "");
    if (!/^0x[0-9a-fA-F]{64}$/.test(privateKey)) {
      throw new Error("AGENTCART_ONCHAIN_PRIVATE_KEY is missing or invalid");
    }
    const account = privateKeyToAccount(privateKey);
    const rpcUrl = options.rpc_url || deployment.rpc_url;
    const publicClient = createPublicClient({ transport: http(rpcUrl, { timeout: 15_000 }) });
    const walletClient = createWalletClient({ account, transport: http(rpcUrl, { timeout: 15_000 }) });
    let submissionJournal = "";
    const result = await executeMerchantPlan({
      plan,
      deployment,
      publicClient,
      walletClient,
      account,
      onSubmitted: async (entry) => {
        const hashPrefix = String(entry.transaction.hash || "").replace(/^0x/, "").slice(0, 12);
        submissionJournal = `${options.plan}.submission-${hashPrefix}.json`;
        await writeFile(submissionJournal, `${JSON.stringify(entry, null, 2)}\n`, {
          encoding: "utf8",
          flag: "wx",
          mode: 0o600,
        });
      },
    });
    await writeResult(
      submissionJournal ? { ...result, submission_journal: submissionJournal } : result,
      options.output,
    );
    return;
  }
  if (options.command === "prepare-revoke") {
    const plan = await readPlan(options.plan);
    const deploymentId = options.deployment || plan.deployment?.id || "";
    const deployment = merchantRegistryDeployments.get(deploymentId);
    if (!deployment) throw new Error(`unknown deployment: ${deploymentId || "missing"}`);
    const publicClient = createPublicClient({
      transport: http(options.rpc_url || deployment.rpc_url, { timeout: 15_000 }),
    });
    const result = await prepareMerchantRevocation({
      plan,
      reason: options.reason || "merchant_admin_revoke",
      deployment,
      publicClient,
    });
    await writeResult(result, options.output);
    return;
  }
  if (options.command === "verify") {
    const plan = await readPlan(options.plan);
    const deploymentId = options.deployment || plan.deployment?.id || "";
    const deployment = merchantRegistryDeployments.get(deploymentId);
    if (!deployment) throw new Error(`unknown deployment: ${deploymentId || "missing"}`);
    if (!options.transaction_hash) throw new Error("--transaction-hash is required");
    const publicClient = createPublicClient({
      transport: http(options.rpc_url || deployment.rpc_url, { timeout: 15_000 }),
    });
    const result = await verifyMerchantTransactionInclusion({
      plan,
      transactionHash: options.transaction_hash,
      expectedState: options.expected_state || (plan.operation === "revoke" ? "revoked" : "active"),
      deployment,
      publicClient,
    });
    await writeResult(result, options.output);
    if (!result.ready) process.exitCode = 2;
    return;
  }
  if (options.command === "status") {
    const deploymentId = options.deployment || "tempo-moderato";
    const deployment = merchantRegistryDeployments.get(deploymentId);
    if (!deployment) throw new Error(`unknown deployment: ${deploymentId}`);
    const publicClient = createPublicClient({
      transport: http(options.rpc_url || deployment.rpc_url, { timeout: 15_000 }),
    });
    const finalizedBlock = await verifyMerchantRegistryDeployment(publicClient, deployment);
    const registryAddress = getAddress(deployment.registry_address);
    const [owner, writesPaused] = await Promise.all([
      publicClient.readContract({
        address: registryAddress,
        abi: statusAbi,
        functionName: "owner",
        blockNumber: finalizedBlock.number,
      }),
      publicClient.readContract({
        address: registryAddress,
        abi: merchantRegistryAbi,
        functionName: "writesPaused",
        blockNumber: finalizedBlock.number,
      }),
    ]);
    const result = {
      schema: "agentcart.onchain_registry_operator_receipt.v1",
      command: "status",
      deployment: deployment.id,
      chain_id: deployment.caip2,
      registry_address: registryAddress,
      owner,
      writes_paused: writesPaused,
      finality: {
        block_tag: "finalized",
        block_number: Number(finalizedBlock.number),
        block_hash: finalizedBlock.hash,
        block_time: new Date(Number(finalizedBlock.timestamp) * 1000).toISOString().replace(".000Z", "Z"),
      },
    };
    if (options.record_id) {
      const recordId = bytes32(options.record_id, "--record-id");
      result.record_id = recordId;
      result.record = recordJson(
        await publicClient.readContract({
          address: registryAddress,
          abi: merchantRegistryAbi,
          functionName: "record",
          args: [recordId],
          blockNumber: finalizedBlock.number,
        }),
      );
    }
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  throw new Error(`unsupported command: ${options.command}`);
}

if (import.meta.url === new URL(process.argv[1], "file:").href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
