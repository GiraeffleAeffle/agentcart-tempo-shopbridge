import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import { encodeAbiParameters, encodeEventTopics, keccak256, toBytes } from "viem";

import {
  CONTRACT_EVENTS_SCHEMA,
  INDEXER_IMPLEMENTATION,
  assertSafeRecordUri,
  collectFinalizedEvents,
  fetchRegistryRecord,
  pinnedLookup,
  registryEventAbi,
  registryRecordHash,
} from "../scripts/onchain-registry-indexer.mjs";
import {
  isMainInvocation,
  refreshFinalizedSnapshot,
  runIndexerLoop,
  runtimeConfig,
} from "../scripts/onchain-registry-indexer-loop.mjs";
import { assertMutationNetworkAllowed } from "../scripts/onchain-registry-operator.mjs";

const registryAddress = "0x2222222222222222222222222222222222222222";
const controller = "0xaAaAaAaaAaAaAaaAaAAAAAAAAaaaAaAaAaaAaaAa";
const recordId = `0x${"44".repeat(32)}`;
const domainHash = keccak256(toBytes("fixture-shop.example"));
const transactionHash = `0x${"aa".repeat(32)}`;
const blockHash = `0x${"bb".repeat(32)}`;

test("recognizes a ConfigMap-style symlink as the main module", async (context) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "agentcart-indexer-main-"));
  context.after(() => rm(directory, { force: true, recursive: true }));
  const modulePath = path.join(directory, "..2026_08_23", "onchain-registry-indexer-loop.mjs");
  const invocationPath = path.join(directory, "onchain-registry-indexer-loop.mjs");
  await mkdir(path.dirname(modulePath));
  await writeFile(modulePath, "", { flag: "wx" });
  await symlink(modulePath, invocationPath);

  assert.equal(await isMainInvocation(pathToFileURL(modulePath).href, invocationPath), true);
  assert.equal(await isMainInvocation(pathToFileURL(modulePath).href, undefined), false);
});

function fakeClient(logs, finalized = 120n) {
  return {
    async getChainId() {
      return 42431;
    },
    async getBlock({ blockTag, blockNumber }) {
      if (blockTag === "finalized") {
        return { number: finalized, hash: blockHash, timestamp: 1_786_000_000n };
      }
      return { number: blockNumber, hash: blockHash, timestamp: 1_786_000_000n };
    },
    async getLogs({ fromBlock, toBlock }) {
      return logs.filter((log) => log.blockNumber >= fromBlock && log.blockNumber <= toBlock);
    },
  };
}

function registeredLog(recordHash, recordUri, { blockNumber = 110n, logIndex = 0, txHash = transactionHash } = {}) {
  const topics = encodeEventTopics({
    abi: registryEventAbi,
    eventName: "MerchantRegistered",
    args: { recordId, controller, domainHash },
  });
  const data = encodeAbiParameters(
    [{ type: "bytes32" }, { type: "string" }],
    [recordHash, recordUri],
  );
  return {
    address: registryAddress,
    blockHash,
    blockNumber,
    data,
    logIndex,
    removed: false,
    topics,
    transactionHash: txHash,
    transactionIndex: 0,
  };
}

function revokedLog(reasonHash, { blockNumber = 111n, logIndex = 0, txHash = `0x${"cc".repeat(32)}` } = {}) {
  const topics = encodeEventTopics({
    abi: registryEventAbi,
    eventName: "MerchantRevoked",
    args: { recordId },
  });
  const data = encodeAbiParameters([{ type: "bytes32" }], [reasonHash]);
  return {
    address: registryAddress,
    blockHash,
    blockNumber,
    data,
    logIndex,
    removed: false,
    topics,
    transactionHash: txHash,
    transactionIndex: 0,
  };
}

test("indexes only the finalized range and binds a fetched registry record", async () => {
  const record = {
    merchant_id: "fixture-tea-shop",
    domain: "fixture-shop.example",
    manifest_url: "https://fixture-shop.example/.well-known/agentcart.json",
    updated_at: "2026-08-13T00:00:00Z",
    payment_network: "testnet",
    payment_recipient: "0x1111111111111111111111111111111111111111",
    onchain_identity: {
      standard: "AgentCart-Onchain-Registry-v1",
      chain_id: "eip155:42431",
      controller,
      registry_address: registryAddress,
      record_id: recordId,
    },
  };
  const recordHash = `0x${await registryRecordHash(record)}`;
  const recordUri = "https://fixture-shop.example/.well-known/agentcart-registry-bundle.json";
  const document = await collectFinalizedEvents(
    {
      rpcUrl: "http://unused.test",
      registryAddress,
      fromBlock: "100",
      toBlock: "finalized",
      chunkSize: "10",
      allowPrivateRecordUri: false,
      allowIncompleteRecords: false,
      fetchRecord: async (url, expectedHash) => {
        assert.equal(url, recordUri);
        assert.equal(expectedHash, recordHash);
        return record;
      },
    },
    fakeClient([registeredLog(recordHash, recordUri)]),
  );

  assert.equal(document.schema, CONTRACT_EVENTS_SCHEMA);
  assert.equal(document.implementation, INDEXER_IMPLEMENTATION);
  assert.equal(document.chain_id, "eip155:42431");
  assert.equal(document.finality.block_tag, "finalized");
  assert.equal(document.finality.indexed_to_block, 120);
  assert.equal(document.complete, true);
  assert.deepEqual(document.events[0].registry_record, record);
  assert.equal(document.events[0].args.recordHash, recordHash);
});

test("fails closed when a record URI does not produce the committed hash", async () => {
  const recordUri = "https://wrong.example/.well-known/agentcart-registry-bundle.json";
  await assert.rejects(
    collectFinalizedEvents(
      {
        rpcUrl: "http://unused.test",
        registryAddress,
        fromBlock: "100",
        toBlock: "finalized",
        chunkSize: "100",
        allowPrivateRecordUri: false,
        allowIncompleteRecords: false,
        fetchRecord: async () => {
          throw new Error("record_hash_mismatch");
        },
      },
      fakeClient([registeredLog(`0x${"11".repeat(32)}`, recordUri)]),
    ),
    (error) => error.document?.complete === false && error.document?.errors?.[0]?.code === "record_fetch_failed",
  );
});

test("replays registration, revocation, and recovery through immutable record URIs", async () => {
  const identity = {
    standard: "AgentCart-Onchain-Registry-v1",
    chain_id: "eip155:42431",
    controller,
    registry_address: registryAddress,
    record_id: recordId,
  };
  const first = {
    merchant_id: "fixture-tea-shop",
    domain: "fixture-shop.example",
    manifest_url: "https://fixture-shop.example/.well-known/agentcart.json",
    updated_at: "2026-08-13T00:00:00Z",
    payment_network: "testnet",
    payment_recipient: "0x1111111111111111111111111111111111111111",
    onchain_identity: identity,
  };
  const recovered = { ...first, updated_at: "2026-08-13T00:01:00Z" };
  const firstHash = `0x${await registryRecordHash(first)}`;
  const recoveredHash = `0x${await registryRecordHash(recovered)}`;
  const firstUri = `https://registry.agentcart.eu/v1/registry/onchain/records/${firstHash.slice(2)}`;
  const recoveredUri = `https://registry.agentcart.eu/v1/registry/onchain/records/${recoveredHash.slice(2)}`;
  const records = new Map([[firstUri, first], [recoveredUri, recovered]]);
  const document = await collectFinalizedEvents(
    {
      rpcUrl: "http://unused.test",
      registryAddress,
      fromBlock: "100",
      toBlock: "finalized",
      chunkSize: "100",
      allowPrivateRecordUri: false,
      allowIncompleteRecords: false,
      fetchRecord: async (url, expectedHash) => {
        const record = records.get(url);
        assert.ok(record);
        assert.equal(`0x${await registryRecordHash(record)}`, expectedHash);
        return record;
      },
    },
    fakeClient([
      registeredLog(firstHash, firstUri),
      revokedLog(`0x${"dd".repeat(32)}`),
      registeredLog(recoveredHash, recoveredUri, {
        blockNumber: 112n,
        txHash: `0x${"ee".repeat(32)}`,
      }),
    ]),
  );

  assert.equal(document.complete, true);
  assert.equal(document.events.length, 3);
  assert.deepEqual(document.events[0].registry_record, first);
  assert.deepEqual(document.events[2].registry_record, recovered);
});

test("rejects unfinalized upper bounds", async () => {
  await assert.rejects(
    collectFinalizedEvents(
      {
        rpcUrl: "http://unused.test",
        registryAddress,
        fromBlock: "100",
        toBlock: "121",
        chunkSize: "100",
        allowPrivateRecordUri: false,
        allowIncompleteRecords: false,
      },
      fakeClient([]),
    ),
    /newer than finalized block 120/,
  );
});

test("rejects private record endpoints by default", async () => {
  await assert.rejects(
    assertSafeRecordUri("http://127.0.0.1/.well-known/agentcart-registry-bundle.json"),
    /record_uri_requires_https/,
  );
  await assert.rejects(
    assertSafeRecordUri("https://[::ffff:7f00:1]/.well-known/agentcart-registry-bundle.json"),
    /record_uri_private_address/,
  );
});

test("pins record fetches to the addresses that passed public-range validation", async () => {
  const lookup = pinnedLookup([
    { address: "203.0.113.10", family: 4 },
    { address: "2001:db8::10", family: 6 },
  ]);
  const all = await new Promise((resolve, reject) => {
    lookup("rebound.example", { all: true }, (error, addresses) => error ? reject(error) : resolve(addresses));
  });
  const ipv6 = await new Promise((resolve, reject) => {
    lookup("rebound.example", { family: 6 }, (error, address, family) => (
      error ? reject(error) : resolve({ address, family })
    ));
  });

  assert.deepEqual(all, [
    { address: "203.0.113.10", family: 4 },
    { address: "2001:db8::10", family: 6 },
  ]);
  assert.deepEqual(ipv6, { address: "2001:db8::10", family: 6 });
});

test("fetches and verifies an immutable record through the test-only private transport", async (context) => {
  const record = {
    merchant_id: "local-fixture-shop",
    domain: "local-fixture.example",
    manifest_url: "https://local-fixture.example/.well-known/agentcart.json",
  };
  const expectedHash = `0x${await registryRecordHash(record)}`;
  const server = http.createServer((_request, response) => {
    const body = JSON.stringify({ registry_record: record });
    response.writeHead(200, { "content-length": Buffer.byteLength(body), "content-type": "application/json" });
    response.end(body);
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  context.after(() => new Promise((resolve) => server.close(resolve)));
  const address = server.address();
  assert.equal(typeof address, "object");

  const fetched = await fetchRegistryRecord(
    `http://127.0.0.1:${address.port}/record.json`,
    expectedHash,
    { allowPrivate: true },
  );

  assert.deepEqual(fetched, record);
});

test("recurring indexer configuration is bounded below the buyer freshness window", () => {
  const config = runtimeConfig({
    AGENTCART_ONCHAIN_RPC_URL: "https://rpc.example.test",
    AGENTCART_ONCHAIN_REGISTRY_ADDRESS: registryAddress,
    AGENTCART_ONCHAIN_EXPECTED_CHAIN_ID: "42431",
    AGENTCART_ONCHAIN_FROM_BLOCK: "100",
    AGENTCART_ONCHAIN_LOG_CHUNK_SIZE: "2000",
    AGENTCART_ONCHAIN_EVENTS_OUTPUT: "/events/onchain-events.json",
    AGENTCART_ONCHAIN_REFRESH_SECONDS: "240",
  });

  assert.equal(config.refreshMilliseconds, 240_000);
  assert.equal(config.indexer.toBlock, "finalized");
  assert.equal(config.expectedChainId, "42431");
  assert.equal(config.indexer.allowIncompleteRecords, false);
  assert.equal(config.output, "/events/onchain-events.json");
  assert.throws(
    () => runtimeConfig({
      AGENTCART_ONCHAIN_RPC_URL: "https://rpc.example.test",
      AGENTCART_ONCHAIN_REGISTRY_ADDRESS: registryAddress,
      AGENTCART_ONCHAIN_EXPECTED_CHAIN_ID: "42431",
      AGENTCART_ONCHAIN_EVENTS_OUTPUT: "/events/onchain-events.json",
      AGENTCART_ONCHAIN_REFRESH_SECONDS: "301",
    }),
    /between 60 and 300/,
  );
});

test("registry mutations require an explicit production-network override", () => {
  assert.doesNotThrow(() => assertMutationNetworkAllowed(42431, {}));
  assert.throws(() => assertMutationNetworkAllowed(1, {}), /production-network mutations are disabled/);
  assert.throws(() => assertMutationNetworkAllowed(4217, {}), /production-network mutations are disabled/);
  assert.doesNotThrow(() => (
    assertMutationNetworkAllowed(4217, { AGENTCART_ONCHAIN_ALLOW_MAINNET: "true" })
  ));
});

test("recurring indexer publishes only complete snapshots", async () => {
  const writes = [];
  const complete = {
    complete: true,
    errors: [],
    events: [],
    chain_id: "eip155:42431",
    registry_address: registryAddress,
    finality: { block_number: 120 },
  };
  await refreshFinalizedSnapshot(
    {
      expectedChainId: "42431",
      indexer: { registryAddress },
      output: "/events/onchain-events.json",
    },
    {
      collect: async () => complete,
      write: async (document, output) => writes.push({ document, output }),
    },
  );
  assert.deepEqual(writes, [{ document: complete, output: "/events/onchain-events.json" }]);

  await assert.rejects(
    refreshFinalizedSnapshot(
      {
        expectedChainId: "42431",
        indexer: { registryAddress },
        output: "/events/onchain-events.json",
      },
      {
        collect: async () => ({ complete: false, errors: [{ code: "fixture" }] }),
        write: async () => writes.push("unexpected"),
      },
    ),
    /incomplete finalized snapshot/,
  );
  assert.equal(writes.length, 1);

  await assert.rejects(
    refreshFinalizedSnapshot(
      {
        expectedChainId: "1",
        indexer: { registryAddress },
        output: "/events/onchain-events.json",
      },
      {
        collect: async () => complete,
        write: async () => writes.push("unexpected"),
      },
    ),
    /RPC chain does not match/,
  );
  assert.equal(writes.length, 1);
});

test("recurring indexer preserves the previous snapshot after refresh failure", async () => {
  let attempts = 0;
  const writes = [];
  const errors = [];
  const waits = [];
  await runIndexerLoop(
    {
      expectedChainId: "42431",
      indexer: { registryAddress },
      output: "/events/onchain-events.json",
      refreshMilliseconds: 60_000,
    },
    {
      collect: async () => {
        attempts += 1;
        if (attempts === 2) throw new Error("rpc unavailable");
        return {
          complete: true,
          errors: [],
          events: [],
          chain_id: "eip155:42431",
          registry_address: registryAddress,
          finality: { block_number: 100 + attempts },
        };
      },
      write: async (document) => writes.push(document.finality.block_number),
      wait: async (milliseconds) => waits.push(milliseconds),
      onSuccess: () => {},
      onError: (error) => errors.push(error.message),
      shouldContinue: () => attempts < 2,
    },
  );

  assert.deepEqual(writes, [101]);
  assert.deepEqual(errors, ["rpc unavailable"]);
  assert.deepEqual(waits, [60_000]);
});
