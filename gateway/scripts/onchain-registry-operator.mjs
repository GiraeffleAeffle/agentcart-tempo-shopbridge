#!/usr/bin/env node

import process from "node:process";

import {
  createPublicClient,
  createWalletClient,
  getAddress,
  http,
  isAddress,
  parseAbi,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";

const abi = parseAbi([
  "function owner() view returns (address)",
  "function writesPaused() view returns (bool)",
  "function recordIdForDomain(bytes32 domainHash) view returns (bytes32)",
  "function computeRecordId(bytes32 domainHash, address controller) view returns (bytes32)",
  "function revokedRecordHashes(bytes32 recordHash) view returns (bool)",
  "function record(bytes32 recordId) view returns ((address controller, bytes32 recordHash, bytes32 domainHash, uint64 updatedAt, uint64 attestedAt, uint64 attestationExpiresAt, uint32 attestationGeneration, uint16 attestationCount, uint8 status))",
  "function register(bytes32 domainHash, bytes32 recordHash, string recordURI) returns (bytes32 recordId)",
  "function update(bytes32 recordId, bytes32 recordHash, string recordURI)",
  "function revoke(bytes32 recordId, bytes32 reasonHash)",
]);
const productionChainIds = new Set([1, 100, 4217]);

function usage() {
  return `Usage:
  node scripts/onchain-registry-operator.mjs status --rpc-url URL --registry-address 0x... [--record-id 0x...]
  node scripts/onchain-registry-operator.mjs register --rpc-url URL --registry-address 0x... --domain-hash 0x... --record-hash 0x... --record-uri https://...
  node scripts/onchain-registry-operator.mjs update --rpc-url URL --registry-address 0x... --record-id 0x... --record-hash 0x... --record-uri https://...
  node scripts/onchain-registry-operator.mjs revoke --rpc-url URL --registry-address 0x... --record-id 0x... --reason-hash 0x...

Mutations read AGENTCART_ONCHAIN_PRIVATE_KEY from the environment and require:
  AGENTCART_ONCHAIN_ACK=<command>:<chain-id>:<lowercase-registry-address>

Ethereum, Gnosis, and Tempo mainnet mutations are additionally blocked unless
AGENTCART_ONCHAIN_ALLOW_MAINNET=true. Never place a private key on the command line.
`;
}

export function assertMutationNetworkAllowed(chainId, environment = process.env) {
  if (
    productionChainIds.has(Number(chainId)) &&
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

function publicHttpsUrl(value, flag) {
  const url = new URL(String(value || ""));
  if (url.protocol !== "https:" || url.username || url.password || url.port) {
    throw new Error(`${flag} must be a public HTTPS URL without credentials or a custom port`);
  }
  if (!url.hostname || url.hostname === "localhost" || url.hostname.endsWith(".local")) {
    throw new Error(`${flag} must use a public hostname`);
  }
  return url.toString();
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

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.command === "help") {
    process.stdout.write(usage());
    return;
  }
  if (!["status", "register", "update", "revoke"].includes(options.command)) {
    throw new Error(`unsupported command: ${options.command}`);
  }
  if (!options.rpc_url) throw new Error("--rpc-url is required");
  if (!isAddress(options.registry_address || "")) throw new Error("--registry-address is invalid");
  const registryAddress = getAddress(options.registry_address);
  const publicClient = createPublicClient({ transport: http(options.rpc_url, { timeout: 15_000 }) });
  const chainId = await publicClient.getChainId();

  if (options.command === "status") {
    const [owner, writesPaused] = await Promise.all([
      publicClient.readContract({ address: registryAddress, abi, functionName: "owner" }),
      publicClient.readContract({ address: registryAddress, abi, functionName: "writesPaused" }),
    ]);
    const result = {
      schema: "agentcart.onchain_registry_operator_receipt.v1",
      command: "status",
      chain_id: chainId,
      registry_address: registryAddress,
      owner,
      writes_paused: writesPaused,
    };
    if (options.record_id) {
      const recordId = bytes32(options.record_id, "--record-id");
      result.record_id = recordId;
      result.record = recordJson(
        await publicClient.readContract({ address: registryAddress, abi, functionName: "record", args: [recordId] }),
      );
    }
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }

  assertMutationNetworkAllowed(chainId);
  const expectedAck = `${options.command}:${chainId}:${registryAddress.toLowerCase()}`;
  if (process.env.AGENTCART_ONCHAIN_ACK !== expectedAck) {
    throw new Error(`set AGENTCART_ONCHAIN_ACK=${expectedAck}`);
  }
  const privateKey = String(process.env.AGENTCART_ONCHAIN_PRIVATE_KEY || "");
  if (!/^0x[0-9a-fA-F]{64}$/.test(privateKey)) {
    throw new Error("AGENTCART_ONCHAIN_PRIVATE_KEY is missing or invalid");
  }
  const account = privateKeyToAccount(privateKey);
  const walletClient = createWalletClient({ account, transport: http(options.rpc_url, { timeout: 15_000 }) });
  let functionName;
  let args;
  let recordId = options.record_id ? bytes32(options.record_id, "--record-id") : "";
  if (options.command === "register") {
    const domainHash = bytes32(options.domain_hash, "--domain-hash");
    const recordHash = bytes32(options.record_hash, "--record-hash");
    const recordUri = publicHttpsUrl(options.record_uri, "--record-uri");
    recordId = await publicClient.readContract({
      address: registryAddress,
      abi,
      functionName: "computeRecordId",
      args: [domainHash, account.address],
    });
    functionName = "register";
    args = [domainHash, recordHash, recordUri];
  } else if (options.command === "update") {
    if (!recordId) throw new Error("--record-id is required");
    functionName = "update";
    args = [
      recordId,
      bytes32(options.record_hash, "--record-hash"),
      publicHttpsUrl(options.record_uri, "--record-uri"),
    ];
  } else {
    if (!recordId) throw new Error("--record-id is required");
    functionName = "revoke";
    args = [recordId, bytes32(options.reason_hash, "--reason-hash")];
  }

  const simulation = await publicClient.simulateContract({
    account,
    address: registryAddress,
    abi,
    functionName,
    args,
  });
  const transactionHash = await walletClient.writeContract(simulation.request);
  const receipt = await publicClient.waitForTransactionReceipt({ hash: transactionHash, confirmations: 1 });
  const record = recordId
    ? await publicClient.readContract({ address: registryAddress, abi, functionName: "record", args: [recordId] })
    : null;
  process.stdout.write(
    `${JSON.stringify(
      {
        schema: "agentcart.onchain_registry_operator_receipt.v1",
        command: options.command,
        chain_id: chainId,
        registry_address: registryAddress,
        controller: account.address,
        record_id: recordId,
        transaction_hash: transactionHash,
        block_number: Number(receipt.blockNumber),
        block_hash: receipt.blockHash,
        status: receipt.status,
        record: record ? recordJson(record) : null,
      },
      null,
      2,
    )}\n`,
  );
}

if (import.meta.url === new URL(process.argv[1], "file:").href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
