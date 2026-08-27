#!/usr/bin/env node

import process from "node:process";
import { readFile, writeFile } from "node:fs/promises";

import {
  createPublicClient,
  createWalletClient,
  encodeFunctionData,
  getAddress,
  http,
  isAddress,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";

import {
  merchantRegistryDeployments,
} from "./merchant-registry-enrollment.mjs";
import {
  merchantDiscoveryFacetsAbi,
  prepareDiscoveryFacetsPublication,
  verifyDiscoveryFacetsState,
} from "./merchant-discovery-facets.mjs";
import { assertMutationNetworkAllowed, waitForReceiptFinality } from "./onchain-registry-operator.mjs";

function usage() {
  return `Usage:
  node scripts/onchain-discovery-facets-operator.mjs prepare --enrollment-plan merchant-enrollment-plan.json [--output facets-plan.json]
  node scripts/onchain-discovery-facets-operator.mjs execute --plan facets-plan.json
  node scripts/onchain-discovery-facets-operator.mjs verify --plan facets-plan.json --transaction-hash 0x...

Run this after the Merchant Registry record is finalized. Prepare reads the
hash-committed categories from the merchant's immutable record and emits one
exact external-wallet request. Never place a private key on the command line.
`;
}

function parseArgs(argv) {
  const [command, ...rest] = argv;
  if (!command || ["help", "-h", "--help"].includes(command)) return { command: "help" };
  const result = { command };
  for (let index = 0; index < rest.length; index += 2) {
    const flag = rest[index];
    const value = rest[index + 1];
    if (!flag?.startsWith("--") || !value || value.startsWith("--")) {
      throw new Error(`invalid argument near ${flag || "end of command"}`);
    }
    result[flag.slice(2).replaceAll("-", "_")] = value;
  }
  return result;
}

async function readJson(path, flag) {
  if (!path) throw new Error(`${flag} is required`);
  const value = JSON.parse(await readFile(path, "utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${flag} must contain a JSON object`);
  }
  return value;
}

async function writeResult(result, output) {
  const body = `${JSON.stringify(result, null, 2)}\n`;
  if (!output) {
    process.stdout.write(body);
    return;
  }
  await writeFile(output, body, { encoding: "utf8", flag: "wx", mode: 0o600 });
  process.stdout.write(`${JSON.stringify({ state: result.state, output }, null, 2)}\n`);
}

function deploymentFor(plan, options) {
  const id = options.deployment || plan?.deployment?.id || "tempo-moderato";
  const deployment = merchantRegistryDeployments.get(id);
  if (!deployment) throw new Error(`unknown deployment: ${id}`);
  return deployment;
}

function exactPreparedTransaction(plan, deployment) {
  if (plan?.schema !== "agentcart.merchant_discovery_facets_plan.v1" || plan.state !== "ready_to_publish") {
    throw new Error("discovery facets plan is not ready to publish");
  }
  const controller = plan.identity?.controller;
  if (!isAddress(controller || "")) throw new Error("discovery facets plan controller is invalid");
  const recordId = String(plan.identity?.record_id || "").toLowerCase();
  const recordHash = String(plan.identity?.record_hash || "").toLowerCase();
  const categorySetHash = String(plan.category_set_hash || "").toLowerCase();
  const categoryHashes = plan.category_hashes;
  if (
    !/^0x[0-9a-f]{64}$/.test(recordId) ||
    !/^0x[0-9a-f]{64}$/.test(recordHash) ||
    !/^0x[0-9a-f]{64}$/.test(categorySetHash) ||
    !Array.isArray(categoryHashes) ||
    categoryHashes.length < 1 ||
    categoryHashes.length > 8 ||
    categoryHashes.some((value) => !/^0x[0-9a-f]{64}$/.test(String(value))) ||
    JSON.stringify(categoryHashes) !== JSON.stringify([...categoryHashes].sort())
  ) {
    throw new Error("discovery facets plan commitment is invalid");
  }
  const facetsAddress = getAddress(deployment.discovery_facets.address);
  const expected = {
    chainId: `0x${deployment.chain_id.toString(16)}`,
    from: getAddress(controller),
    to: facetsAddress,
    data: encodeFunctionData({
      abi: merchantDiscoveryFacetsAbi,
      functionName: "publish",
      args: [recordId, recordHash, categoryHashes],
    }),
    value: "0x0",
  };
  if (JSON.stringify(plan.transaction_request) !== JSON.stringify(expected)) {
    throw new Error("discovery facets plan transaction was modified");
  }
  const requiredAck = [
    "publish-facets",
    deployment.caip2,
    facetsAddress.toLowerCase(),
    recordId,
    recordHash,
    categorySetHash,
  ].join(":");
  if (plan.required_ack !== requiredAck) throw new Error("discovery facets plan acknowledgement is invalid");
  return { controller: getAddress(controller), transaction: expected, requiredAck };
}

async function verifyTransaction({ plan, transactionHash, deployment, publicClient }) {
  const prepared = exactPreparedTransaction(plan, deployment);
  if (!/^0x[0-9a-fA-F]{64}$/.test(String(transactionHash || ""))) {
    throw new Error("--transaction-hash must be a 0x-prefixed transaction hash");
  }
  const hash = transactionHash.toLowerCase();
  const [receipt, transaction] = await Promise.all([
    publicClient.waitForTransactionReceipt({ hash, confirmations: 1 }),
    publicClient.getTransaction({ hash }),
  ]);
  if (receipt?.status !== "success") throw new Error("discovery facets transaction was not successful");
  if (
    getAddress(transaction?.from || "0x0000000000000000000000000000000000000000") !== prepared.controller ||
    getAddress(transaction?.to || "0x0000000000000000000000000000000000000000") !== prepared.transaction.to ||
    BigInt(transaction?.value ?? 0) !== 0n ||
    String(transaction?.input ?? transaction?.data ?? "").toLowerCase() !== prepared.transaction.data.toLowerCase()
  ) {
    throw new Error("discovery facets transaction does not match the prepared plan");
  }
  const finality = await waitForReceiptFinality(publicClient, receipt);
  const state = await verifyDiscoveryFacetsState({ plan, deployment, publicClient });
  if (!state.ready) throw new Error("discovery facets transaction finalized in an unexpected state");
  return {
    ...state,
    transaction: {
      hash,
      block_number: Number(receipt.blockNumber),
      block_hash: receipt.blockHash,
      exact_plan_match: true,
    },
    finality,
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.command === "help") {
    process.stdout.write(usage());
    return;
  }
  if (options.command === "prepare") {
    const enrollmentPlan = await readJson(options.enrollment_plan, "--enrollment-plan");
    const deployment = deploymentFor(enrollmentPlan, options);
    const publicClient = createPublicClient({
      transport: http(options.rpc_url || deployment.rpc_url, { timeout: 15_000 }),
    });
    const result = await prepareDiscoveryFacetsPublication({
      enrollmentPlan,
      deployment,
      publicClient,
    });
    await writeResult(result, options.output);
    return;
  }
  const plan = await readJson(options.plan, "--plan");
  const deployment = deploymentFor(plan, options);
  const rpcUrl = options.rpc_url || deployment.rpc_url;
  const publicClient = createPublicClient({ transport: http(rpcUrl, { timeout: 15_000 }) });
  if (options.command === "verify") {
    await writeResult(
      await verifyTransaction({ plan, transactionHash: options.transaction_hash, deployment, publicClient }),
      options.output,
    );
    return;
  }
  if (options.command === "execute") {
    assertMutationNetworkAllowed(deployment.chain_id, process.env, deployment.network_class);
    const prepared = exactPreparedTransaction(plan, deployment);
    if (process.env.AGENTCART_ONCHAIN_ACK !== prepared.requiredAck) {
      throw new Error(`set AGENTCART_ONCHAIN_ACK=${prepared.requiredAck}`);
    }
    const privateKey = String(process.env.AGENTCART_ONCHAIN_PRIVATE_KEY || "");
    if (!/^0x[0-9a-fA-F]{64}$/.test(privateKey)) {
      throw new Error("AGENTCART_ONCHAIN_PRIVATE_KEY is missing or invalid");
    }
    const account = privateKeyToAccount(privateKey);
    if (account.address !== prepared.controller) throw new Error("signer does not match the merchant controller");
    await publicClient.call({
      account,
      to: prepared.transaction.to,
      data: prepared.transaction.data,
      value: 0n,
    });
    const walletClient = createWalletClient({ account, transport: http(rpcUrl, { timeout: 15_000 }) });
    const hash = await walletClient.sendTransaction({
      account,
      to: prepared.transaction.to,
      data: prepared.transaction.data,
      value: 0n,
    });
    const journalPath = `${options.plan}.submission-${hash.slice(2, 14)}.json`;
    await writeFile(
      journalPath,
      `${JSON.stringify({ schema: "agentcart.discovery_facets_submission.v1", state: "submitted_unverified", transaction_hash: hash }, null, 2)}\n`,
      { encoding: "utf8", flag: "wx", mode: 0o600 },
    );
    const result = await verifyTransaction({ plan, transactionHash: hash, deployment, publicClient });
    await writeResult({ ...result, submission_journal: journalPath }, options.output);
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
