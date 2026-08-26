#!/usr/bin/env node

import dns from "node:dns/promises";
import fs from "node:fs/promises";
import nodeHttp from "node:http";
import nodeHttps from "node:https";
import net from "node:net";
import path from "node:path";
import process from "node:process";

import {
  createPublicClient,
  decodeEventLog,
  getAddress,
  http,
  isAddress,
  keccak256,
  toBytes,
} from "viem";

export const CONTRACT_EVENTS_SCHEMA = "agentcart.onchain_registry_contract_events.v1";
export const INDEXER_IMPLEMENTATION = "agentcart.onchain_registry_rpc_indexer.v1";
const MAX_RECORD_BYTES = 1024 * 1024;

export const registryEventAbi = [
  {
    type: "event",
    name: "MerchantRegistered",
    inputs: [
      { indexed: true, name: "recordId", type: "bytes32" },
      { indexed: true, name: "controller", type: "address" },
      { indexed: true, name: "domainHash", type: "bytes32" },
      { indexed: false, name: "recordHash", type: "bytes32" },
      { indexed: false, name: "recordURI", type: "string" },
    ],
  },
  {
    type: "event",
    name: "MerchantUpdated",
    inputs: [
      { indexed: true, name: "recordId", type: "bytes32" },
      { indexed: false, name: "recordHash", type: "bytes32" },
      { indexed: false, name: "recordURI", type: "string" },
    ],
  },
  {
    type: "event",
    name: "ControllerChanged",
    inputs: [
      { indexed: true, name: "recordId", type: "bytes32" },
      { indexed: true, name: "newController", type: "address" },
      { indexed: false, name: "newRecordHash", type: "bytes32" },
      { indexed: false, name: "recordURI", type: "string" },
    ],
  },
  {
    type: "event",
    name: "MerchantRevoked",
    inputs: [
      { indexed: true, name: "recordId", type: "bytes32" },
      { indexed: false, name: "reasonHash", type: "bytes32" },
    ],
  },
  {
    type: "event",
    name: "MerchantForceRevoked",
    inputs: [
      { indexed: true, name: "recordId", type: "bytes32" },
      { indexed: true, name: "operator", type: "address" },
      { indexed: false, name: "reasonHash", type: "bytes32" },
    ],
  },
  {
    type: "event",
    name: "SupersessionRequested",
    inputs: [
      { indexed: true, name: "domainHash", type: "bytes32" },
      { indexed: true, name: "previousRecordId", type: "bytes32" },
      { indexed: true, name: "pendingRecordId", type: "bytes32" },
      { indexed: false, name: "controller", type: "address" },
      { indexed: false, name: "recordHash", type: "bytes32" },
      { indexed: false, name: "reasonHash", type: "bytes32" },
      { indexed: false, name: "availableAt", type: "uint64" },
      { indexed: false, name: "recordURI", type: "string" },
      { indexed: false, name: "evidenceURI", type: "string" },
    ],
  },
  {
    type: "event",
    name: "SupersessionApproved",
    inputs: [
      { indexed: true, name: "domainHash", type: "bytes32" },
      { indexed: true, name: "previousRecordId", type: "bytes32" },
      { indexed: true, name: "pendingRecordId", type: "bytes32" },
      { indexed: false, name: "approver", type: "address" },
      { indexed: false, name: "recordHash", type: "bytes32" },
      { indexed: false, name: "availableAt", type: "uint64" },
      { indexed: false, name: "evidenceURI", type: "string" },
    ],
  },
  {
    type: "event",
    name: "SupersessionCanceled",
    inputs: [
      { indexed: true, name: "pendingRecordId", type: "bytes32" },
      { indexed: true, name: "operator", type: "address" },
      { indexed: false, name: "reasonHash", type: "bytes32" },
    ],
  },
  {
    type: "event",
    name: "SupersessionActivated",
    inputs: [
      { indexed: true, name: "domainHash", type: "bytes32" },
      { indexed: true, name: "previousRecordId", type: "bytes32" },
      { indexed: true, name: "recordId", type: "bytes32" },
      { indexed: false, name: "controller", type: "address" },
      { indexed: false, name: "recordHash", type: "bytes32" },
      { indexed: false, name: "recordURI", type: "string" },
    ],
  },
  {
    type: "event",
    name: "MerchantAttested",
    inputs: [
      { indexed: true, name: "recordId", type: "bytes32" },
      { indexed: true, name: "validator", type: "address" },
      { indexed: false, name: "recordHash", type: "bytes32" },
      { indexed: false, name: "resultHash", type: "bytes32" },
      { indexed: false, name: "expiresAt", type: "uint64" },
      { indexed: false, name: "evidenceURI", type: "string" },
    ],
  },
  {
    type: "event",
    name: "MerchantSuspended",
    inputs: [
      { indexed: true, name: "recordId", type: "bytes32" },
      { indexed: false, name: "reasonHash", type: "bytes32" },
    ],
  },
  {
    type: "event",
    name: "MerchantUnsuspended",
    inputs: [{ indexed: true, name: "recordId", type: "bytes32" }],
  },
  {
    type: "event",
    name: "MerchantFlagged",
    inputs: [
      { indexed: true, name: "recordId", type: "bytes32" },
      { indexed: true, name: "flagger", type: "address" },
      { indexed: false, name: "challengeType", type: "bytes32" },
      { indexed: false, name: "evidenceURI", type: "string" },
    ],
  },
  {
    type: "event",
    name: "ValidatorSet",
    inputs: [
      { indexed: true, name: "validator", type: "address" },
      { indexed: false, name: "enabled", type: "bool" },
    ],
  },
  {
    type: "event",
    name: "AttestationThresholdSet",
    inputs: [{ indexed: false, name: "threshold", type: "uint16" }],
  },
  {
    type: "event",
    name: "GovernanceActionScheduled",
    inputs: [
      { indexed: true, name: "actionHash", type: "bytes32" },
      { indexed: false, name: "readyAt", type: "uint64" },
    ],
  },
  {
    type: "event",
    name: "GovernanceActionCanceled",
    inputs: [{ indexed: true, name: "actionHash", type: "bytes32" }],
  },
  {
    type: "event",
    name: "WritesPaused",
    inputs: [{ indexed: false, name: "paused", type: "bool" }],
  },
  {
    type: "event",
    name: "OwnershipTransferStarted",
    inputs: [
      { indexed: true, name: "previousOwner", type: "address" },
      { indexed: true, name: "newOwner", type: "address" },
    ],
  },
  {
    type: "event",
    name: "OwnershipTransferred",
    inputs: [
      { indexed: true, name: "previousOwner", type: "address" },
      { indexed: true, name: "newOwner", type: "address" },
    ],
  },
];

function usage() {
  return `Usage: node gateway/scripts/onchain-registry-indexer.mjs [options]

Required:
  --rpc-url URL                 Ethereum-compatible JSON-RPC endpoint
  --registry-address ADDRESS    AgentCartMerchantRegistry address

Options:
  --from-block NUMBER           First deployment block (default: 0)
  --to-block NUMBER             Last block, capped at finalized (default: finalized)
  --chunk-size NUMBER           eth_getLogs range size (default: 2000)
  --output PATH                 Atomically write JSON instead of stdout
  --allow-private-record-uri    Test-only: allow loopback/private record URLs
  --allow-incomplete-records    Emit fetch failures instead of failing closed
  --help                        Show this help

Environment aliases: AGENTCART_ONCHAIN_RPC_URL,
AGENTCART_ONCHAIN_REGISTRY_ADDRESS, AGENTCART_ONCHAIN_FROM_BLOCK,
AGENTCART_ONCHAIN_TO_BLOCK, AGENTCART_ONCHAIN_EVENTS_OUTPUT.
`;
}

export function parseArgs(argv) {
  const values = {
    rpcUrl: process.env.AGENTCART_ONCHAIN_RPC_URL || "",
    registryAddress: process.env.AGENTCART_ONCHAIN_REGISTRY_ADDRESS || "",
    fromBlock: process.env.AGENTCART_ONCHAIN_FROM_BLOCK || "0",
    toBlock: process.env.AGENTCART_ONCHAIN_TO_BLOCK || "finalized",
    chunkSize: process.env.AGENTCART_ONCHAIN_LOG_CHUNK_SIZE || "2000",
    output: process.env.AGENTCART_ONCHAIN_EVENTS_OUTPUT || "",
    allowPrivateRecordUri: false,
    allowIncompleteRecords: false,
    help: false,
  };
  const valueFlags = new Map([
    ["--rpc-url", "rpcUrl"],
    ["--registry-address", "registryAddress"],
    ["--from-block", "fromBlock"],
    ["--to-block", "toBlock"],
    ["--chunk-size", "chunkSize"],
    ["--output", "output"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (valueFlags.has(flag)) {
      const next = argv[index + 1];
      if (!next) throw new Error(`${flag} requires a value`);
      values[valueFlags.get(flag)] = next;
      index += 1;
    } else if (flag === "--allow-private-record-uri") {
      values.allowPrivateRecordUri = true;
    } else if (flag === "--allow-incomplete-records") {
      values.allowIncompleteRecords = true;
    } else if (flag === "--help" || flag === "-h") {
      values.help = true;
    } else {
      throw new Error(`unknown argument: ${flag}`);
    }
  }
  return values;
}

function parseBlockNumber(value, field) {
  if (!/^(0|[1-9][0-9]*)$/.test(String(value))) {
    throw new Error(`${field} must be a non-negative integer`);
  }
  return BigInt(value);
}

function jsonSafe(value) {
  if (typeof value === "bigint") return value.toString();
  if (Array.isArray(value)) return value.map(jsonSafe);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, jsonSafe(item)]));
  }
  return value;
}

function privateIp(address) {
  if (net.isIPv4(address)) {
    const [a, b, c] = address.split(".").map(Number);
    return (
      a === 0 ||
      a === 10 ||
      a === 127 ||
      (a === 100 && b >= 64 && b <= 127) ||
      (a === 169 && b === 254) ||
      (a === 172 && b >= 16 && b <= 31) ||
      (a === 192 && b === 0 && (c === 0 || c === 2)) ||
      (a === 192 && b === 88 && c === 99) ||
      (a === 192 && b === 168) ||
      (a === 198 && (b === 18 || b === 19)) ||
      (a === 198 && b === 51 && c === 100) ||
      (a === 203 && b === 0 && c === 113) ||
      a >= 224
    );
  }
  if (net.isIPv6(address)) {
    const normalized = address.toLowerCase();
    return (
      normalized === "::" ||
      normalized === "::1" ||
      normalized.startsWith("::ffff:") ||
      normalized.startsWith("64:ff9b:") ||
      normalized.startsWith("fc") ||
      normalized.startsWith("fd") ||
      /^fe[89abcdef]/.test(normalized) ||
      normalized.startsWith("2001:db8:") ||
      normalized.startsWith("ff")
    );
  }
  return true;
}

async function resolveSafeRecordTarget(rawUrl, { allowPrivate = false } = {}) {
  const url = new URL(String(rawUrl || ""));
  if (!allowPrivate && url.protocol !== "https:") {
    throw new Error("record_uri_requires_https");
  }
  if (allowPrivate && !["http:", "https:"].includes(url.protocol)) {
    throw new Error("record_uri_protocol_invalid");
  }
  if (url.username || url.password) throw new Error("record_uri_userinfo_forbidden");
  if (!allowPrivate && url.port) throw new Error("record_uri_port_forbidden");
  const hostname = url.hostname.replace(/^\[|\]$/g, "").toLowerCase();
  let resolved = [];
  if (!allowPrivate) {
    if (hostname === "localhost" || hostname.endsWith(".localhost") || hostname.endsWith(".local")) {
      throw new Error("record_uri_private_host");
    }
    resolved = net.isIP(hostname)
      ? [{ address: hostname, family: net.isIPv6(hostname) ? 6 : 4 }]
      : await dns.lookup(hostname, { all: true });
    if (!resolved.length || resolved.some(({ address }) => privateIp(address))) {
      throw new Error("record_uri_private_address");
    }
  }
  return { resolved, url };
}

export async function assertSafeRecordUri(rawUrl, { allowPrivate = false } = {}) {
  return (await resolveSafeRecordTarget(rawUrl, { allowPrivate })).url;
}

export function pinnedLookup(resolved) {
  const addresses = resolved.map(({ address, family }) => ({
    address,
    family: Number(family) || (net.isIPv6(address) ? 6 : 4),
  }));
  if (!addresses.length) throw new Error("record_uri_address_missing");
  return (_hostname, options, callback) => {
    const requestedFamily = typeof options === "number" ? options : Number(options?.family || 0);
    const matching = requestedFamily
      ? addresses.filter(({ family }) => family === requestedFamily)
      : addresses;
    if (!matching.length) {
      callback(Object.assign(new Error("record_uri_address_family_unavailable"), { code: "ENOTFOUND" }));
      return;
    }
    if (typeof options === "object" && options?.all) {
      callback(null, matching);
      return;
    }
    callback(null, matching[0].address, matching[0].family);
  };
}

function fetchPinnedDocument(url, resolved, { allowPrivate = false, timeoutMs = 10_000 } = {}) {
  return new Promise((resolve, reject) => {
    const transport = url.protocol === "https:" ? nodeHttps : nodeHttp;
    const requestOptions = {
      headers: {
        accept: "application/json",
        connection: "close",
        "user-agent": "AgentCart-Onchain-Indexer/1",
      },
      method: "GET",
    };
    if (!allowPrivate) requestOptions.lookup = pinnedLookup(resolved);
    const request = transport.request(url, requestOptions, (response) => {
      const status = Number(response.statusCode || 0);
      if (status < 200 || status >= 300) {
        response.resume();
        reject(new Error(`record_uri_http_${status || "unknown"}`));
        return;
      }
      const declaredLength = Number(response.headers["content-length"] || "0");
      if (!Number.isFinite(declaredLength) || declaredLength < 0 || declaredLength > MAX_RECORD_BYTES) {
        response.destroy(new Error("record_document_too_large"));
        return;
      }
      const chunks = [];
      let bytes = 0;
      response.on("data", (chunk) => {
        bytes += chunk.length;
        if (bytes > MAX_RECORD_BYTES) {
          response.destroy(new Error("record_document_too_large"));
          return;
        }
        chunks.push(chunk);
      });
      response.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
      response.on("error", reject);
    });
    request.setTimeout(timeoutMs, () => request.destroy(new Error("record_uri_timeout")));
    request.on("error", reject);
    request.end();
  });
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function registrySignaturePayload(record) {
  const omitted = new Set([
    "signature",
    "verification",
    "manifest",
    "manifest_snapshot",
    "proof_snapshot",
    "revocation_snapshot",
  ]);
  return Object.fromEntries(Object.entries(record).filter(([key]) => !omitted.has(key)));
}

async function sha256Hex(value) {
  const { createHash } = await import("node:crypto");
  return createHash("sha256").update(value, "utf8").digest("hex");
}

export async function registryRecordHash(record) {
  return sha256Hex(canonicalJson(registrySignaturePayload(record)));
}

export function normalizedDomain(value) {
  const raw = String(value || "").trim().replace(/\.$/, "").toLowerCase();
  if (!raw || !/^[\x00-\x7f]+$/.test(raw) || raw.length > 253) return "";
  const labels = raw.split(".");
  if (
    labels.some(
      (label) =>
        !label ||
        label.length > 63 ||
        label.startsWith("xn--") ||
        !/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label),
    )
  ) {
    return "";
  }
  return raw;
}

function recordIdentity(record) {
  if (record?.onchain_identity && typeof record.onchain_identity === "object") return record.onchain_identity;
  if (record?.erc8004_identity && typeof record.erc8004_identity === "object") return record.erc8004_identity;
  return {};
}

export function assertControllerBoundIdentity(record, expected) {
  const identity = recordIdentity(record);
  const suppliedChainId = String(identity.chain_id || identity.chain || identity.chainId || "");
  const suppliedController = String(
    identity.controller || identity.controller_address || identity.merchant_controller || "",
  );
  const suppliedRegistry = String(
    identity.registry_address ||
      identity.registry ||
      identity.registry_contract ||
      identity.contract ||
      "",
  );
  const suppliedRecordId = String(identity.record_id || identity.id || "");
  if (suppliedChainId !== `eip155:${expected.chainId}`) throw new Error("controller_proof_chain_id_mismatch");
  if (suppliedController.toLowerCase() !== String(expected.controller || "").toLowerCase()) {
    throw new Error("controller_proof_controller_mismatch");
  }
  if (suppliedRegistry.toLowerCase() !== expected.registryAddress.toLowerCase()) {
    throw new Error("controller_proof_registry_address_mismatch");
  }
  if (suppliedRecordId.toLowerCase() !== String(expected.recordId || "").toLowerCase()) {
    throw new Error("controller_proof_record_id_mismatch");
  }
  const domain = normalizedDomain(record.domain);
  if (!domain) throw new Error("controller_proof_domain_missing");
  if (keccak256(toBytes(domain)).toLowerCase() !== String(expected.domainHash || "").toLowerCase()) {
    throw new Error("controller_proof_domain_hash_mismatch");
  }
}

function recordCandidates(document) {
  const candidates = [];
  const push = (value) => {
    if (value && typeof value === "object" && !Array.isArray(value)) candidates.push(value);
  };
  if (!document || typeof document !== "object" || Array.isArray(document)) return candidates;
  push(document.registry_record);
  push(document.registry_onboarding_bundle?.registry_record);
  push(document.bundle?.registry_record);
  for (const entry of document.registry_feed?.entries || []) push(entry);
  for (const entry of document.entries || []) push(entry);
  if (document.merchant_id && document.manifest_url) push(document);
  return candidates;
}

export async function fetchRegistryRecord(recordUri, expectedHash, options = {}) {
  const target = await resolveSafeRecordTarget(recordUri, { allowPrivate: options.allowPrivate });
  const text = await fetchPinnedDocument(target.url, target.resolved, {
    allowPrivate: options.allowPrivate,
    timeoutMs: options.timeoutMs,
  });
  const document = JSON.parse(text);
  const normalizedExpected = String(expectedHash || "").replace(/^0x/, "").toLowerCase();
  for (const candidate of recordCandidates(document)) {
    if ((await registryRecordHash(candidate)) === normalizedExpected) return candidate;
  }
  throw new Error("record_hash_mismatch");
}

export async function fetchPublicJsonDocument(documentUri, options = {}) {
  const target = await resolveSafeRecordTarget(documentUri, { allowPrivate: options.allowPrivate });
  const text = await fetchPinnedDocument(target.url, target.resolved, {
    allowPrivate: options.allowPrivate,
    timeoutMs: options.timeoutMs,
  });
  const document = JSON.parse(text);
  if (!document || typeof document !== "object" || Array.isArray(document)) {
    throw new Error("record_document_object_required");
  }
  return document;
}

function recordReference(args) {
  const recordURI = args.recordURI;
  const recordHash = args.recordHash || args.newRecordHash;
  if (typeof recordURI !== "string" || !recordURI || typeof recordHash !== "string" || !recordHash) return null;
  return { recordURI, recordHash };
}

async function collectLogs(client, address, fromBlock, toBlock, chunkSize) {
  const logs = [];
  for (let start = fromBlock; start <= toBlock; start += chunkSize) {
    const end = start + chunkSize - 1n > toBlock ? toBlock : start + chunkSize - 1n;
    const page = await client.getLogs({ address, fromBlock: start, toBlock: end });
    logs.push(...page);
  }
  return logs.sort((left, right) => {
    const blockOrder = Number((left.blockNumber || 0n) - (right.blockNumber || 0n));
    return blockOrder || Number((left.logIndex || 0) - (right.logIndex || 0));
  });
}

export async function collectFinalizedEvents(options, injectedClient = null) {
  if (!options.rpcUrl) throw new Error("--rpc-url is required");
  if (!isAddress(options.registryAddress)) throw new Error("--registry-address must be a valid EVM address");
  const registryAddress = getAddress(options.registryAddress);
  const fromBlock = parseBlockNumber(options.fromBlock, "--from-block");
  const chunkSize = parseBlockNumber(options.chunkSize, "--chunk-size");
  if (chunkSize < 1n || chunkSize > 100_000n) throw new Error("--chunk-size must be between 1 and 100000");
  const client = injectedClient || createPublicClient({ transport: http(options.rpcUrl, { timeout: 15_000 }) });
  const [chainId, finalizedBlock] = await Promise.all([
    client.getChainId(),
    client.getBlock({ blockTag: "finalized" }),
  ]);
  if (finalizedBlock.number === null || !finalizedBlock.hash) {
    throw new Error("RPC endpoint did not return a finalized block");
  }
  const requestedTo = options.toBlock === "finalized"
    ? finalizedBlock.number
    : parseBlockNumber(options.toBlock, "--to-block");
  if (requestedTo > finalizedBlock.number) {
    throw new Error(`--to-block ${requestedTo} is newer than finalized block ${finalizedBlock.number}`);
  }
  if (fromBlock > requestedTo) throw new Error("--from-block is newer than the selected finalized range");

  const logs = await collectLogs(client, registryAddress, fromBlock, requestedTo, chunkSize);
  const blockCache = new Map();
  const recordCache = new Map();
  const recordLoader = options.fetchRecord || fetchRegistryRecord;
  const controllerByRecordId = new Map();
  const domainHashByRecordId = new Map();
  const errors = [];
  const events = [];
  for (const log of logs) {
    if (log.removed) throw new Error("finalized log was marked removed");
    let decoded;
    try {
      decoded = decodeEventLog({ abi: registryEventAbi, data: log.data, topics: log.topics, strict: true });
    } catch (error) {
      errors.push({
        code: "event_decode_failed",
        block_number: Number(log.blockNumber || 0n),
        transaction_hash: log.transactionHash || "",
        log_index: Number(log.logIndex || 0),
        message: error instanceof Error ? error.message : String(error),
      });
      continue;
    }
    const args = jsonSafe(decoded.args || {});
    const blockNumber = log.blockNumber || 0n;
    if (!blockCache.has(blockNumber.toString())) {
      blockCache.set(blockNumber.toString(), await client.getBlock({ blockNumber }));
    }
    const block = blockCache.get(blockNumber.toString());
    const event = {
      event: decoded.eventName,
      block_number: Number(blockNumber),
      block_hash: log.blockHash || block.hash || "",
      block_time: new Date(Number(block.timestamp) * 1000).toISOString().replace(".000Z", "Z"),
      transaction_hash: log.transactionHash || "",
      log_index: Number(log.logIndex || 0),
      args,
    };
    const targetRecordId = String(args.recordId || args.pendingRecordId || "");
    const expectedController = String(
      args.controller ||
        args.newController ||
        controllerByRecordId.get(targetRecordId.toLowerCase()) ||
        "",
    );
    const expectedDomainHash = String(
      args.domainHash || domainHashByRecordId.get(targetRecordId.toLowerCase()) || "",
    );
    const reference = recordReference(args);
    if (reference) {
      const cacheKey = `${reference.recordURI}\n${reference.recordHash.toLowerCase()}`;
      if (!recordCache.has(cacheKey)) {
        recordCache.set(
          cacheKey,
          recordLoader(reference.recordURI, reference.recordHash, {
            allowPrivate: options.allowPrivateRecordUri,
          }),
        );
      }
      try {
        event.registry_record = await recordCache.get(cacheKey);
        assertControllerBoundIdentity(event.registry_record, {
          chainId,
          controller: expectedController,
          registryAddress,
          recordId: targetRecordId,
          domainHash: expectedDomainHash,
        });
      } catch (error) {
        const failure = {
          code: "record_fetch_failed",
          event: decoded.eventName,
          block_number: Number(blockNumber),
          transaction_hash: log.transactionHash || "",
          record_uri: reference.recordURI,
          message: error instanceof Error ? error.message : String(error),
        };
        event.record_fetch_error = failure.code;
        errors.push(failure);
      }
    }
    if (["MerchantRegistered", "ControllerChanged", "SupersessionRequested", "SupersessionActivated"].includes(decoded.eventName)) {
      if (targetRecordId && expectedController) {
        controllerByRecordId.set(targetRecordId.toLowerCase(), expectedController);
      }
      if (targetRecordId && expectedDomainHash) {
        domainHashByRecordId.set(targetRecordId.toLowerCase(), expectedDomainHash);
      }
    }
    if (decoded.eventName === "MerchantRevoked") {
      controllerByRecordId.delete(targetRecordId.toLowerCase());
      domainHashByRecordId.delete(targetRecordId.toLowerCase());
    }
    events.push(event);
  }

  const document = {
    schema: CONTRACT_EVENTS_SCHEMA,
    implementation: INDEXER_IMPLEMENTATION,
    chain_id: `eip155:${chainId}`,
    registry_address: registryAddress,
    finality: {
      block_tag: "finalized",
      block_number: Number(finalizedBlock.number),
      block_hash: finalizedBlock.hash,
      block_time: new Date(Number(finalizedBlock.timestamp) * 1000).toISOString().replace(".000Z", "Z"),
      indexed_from_block: Number(fromBlock),
      indexed_to_block: Number(requestedTo),
    },
    indexed_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
    complete: errors.length === 0,
    errors,
    events,
  };
  if (errors.length && !options.allowIncompleteRecords) {
    const error = new Error(`indexing failed closed with ${errors.length} error(s)`);
    error.document = document;
    throw error;
  }
  return document;
}

export async function writeDocument(document, output) {
  const serialized = `${JSON.stringify(document, null, 2)}\n`;
  if (!output) {
    process.stdout.write(serialized);
    return;
  }
  const absolute = path.resolve(output);
  const temporary = `${absolute}.tmp-${process.pid}`;
  await fs.mkdir(path.dirname(absolute), { recursive: true });
  await fs.writeFile(temporary, serialized, { mode: 0o644 });
  await fs.rename(temporary, absolute);
}

async function main() {
  let options;
  try {
    options = parseArgs(process.argv.slice(2));
    if (options.help) {
      process.stdout.write(usage());
      return;
    }
    const document = await collectFinalizedEvents(options);
    await writeDocument(document, options.output);
  } catch (error) {
    if (error?.document && options?.output) await writeDocument(error.document, options.output);
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}

if (import.meta.url === new URL(process.argv[1], "file:").href) {
  await main();
}
