import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import { encodeAbiParameters, encodeEventTopics, keccak256, toBytes } from "viem";

import {
  CONTRACT_EVENTS_SCHEMA,
  INDEXER_IMPLEMENTATION,
  assertControllerBoundIdentity,
  assertSafeRecordUri,
  collectFinalizedEvents,
  fetchRegistryRecord,
  pinnedLookup,
  normalizedDomain,
  registryEventAbi,
  registryRecordHash,
} from "../scripts/onchain-registry-indexer.mjs";
import {
  collectIndependentlyVerifiedSnapshot,
  compareFinalizedSnapshots,
  isMainInvocation,
  refreshFinalizedSnapshot,
  runIndexerLoop,
  runtimeConfig,
  sendIndependentRpcAlert,
} from "../scripts/onchain-registry-indexer-loop.mjs";
import { assertMutationNetworkAllowed } from "../scripts/onchain-registry-operator.mjs";

const registryAddress = "0x2222222222222222222222222222222222222222";
const controller = "0xaAaAaAaaAaAaAaaAaAAAAAAAAaaaAaAaAaaAaaAa";
const recordId = `0x${"44".repeat(32)}`;
const domainHash = keccak256(toBytes("fixture-shop.example"));
const transactionHash = `0x${"aa".repeat(32)}`;
const blockHash = `0x${"bb".repeat(32)}`;

test("uses the shared lowercase ASCII LDH hostname normalization contract", async () => {
  const fixture = JSON.parse(
    await readFile(
      new URL("../../docs/fixtures/registry/domain-normalization.json", import.meta.url),
      "utf8",
    ),
  );
  for (const example of fixture.cases) {
    assert.equal(normalizedDomain(example.input), example.normalized, example.input);
  }
});

test("uses the shared nested onchain identity alias contract", async () => {
  const fixture = JSON.parse(
    await readFile(
      new URL("../../docs/fixtures/registry/onchain-identity-aliases.json", import.meta.url),
      "utf8",
    ),
  );
  const expected = {
    chainId: 42431,
    controller: fixture.expected.controller,
    registryAddress: fixture.expected.registry_address,
    recordId: fixture.expected.record_id,
    domainHash: keccak256(toBytes("fixture-shop.example")),
  };
  for (const example of fixture.cases) {
    const record = { domain: "fixture-shop.example" };
    if (example.container === "top_level") Object.assign(record, example.identity);
    else record[example.container] = example.identity;
    if (example.valid) assert.doesNotThrow(() => assertControllerBoundIdentity(record, expected));
    else assert.throws(() => assertControllerBoundIdentity(record, expected));
  }
});

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
  assert.equal(document.finality.block_time, "2026-08-06T07:06:40Z");
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
  assert.equal(config.witnessIndexer, null);
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

test("recurring indexer accepts a distinct HTTPS witness and secret-backed alert URL", () => {
  const config = runtimeConfig({
    AGENTCART_ONCHAIN_RPC_URL: "https://primary-rpc.example.test",
    AGENTCART_ONCHAIN_WITNESS_RPC_URL: "https://witness-rpc.example.test/project-key",
    AGENTCART_ONCHAIN_WITNESS_NAME: "independent-provider",
    AGENTCART_ONCHAIN_WITNESS_MAX_FINALITY_LAG_SECONDS: "180",
    AGENTCART_ONCHAIN_DIVERGENCE_ALERT_WEBHOOK_URL: "https://alerts.example.test/registry",
    AGENTCART_ONCHAIN_DIVERGENCE_ALERT_WEBHOOK_TOKEN: "fixture-token",
    AGENTCART_ONCHAIN_DIVERGENCE_ALERT_THROTTLE_SECONDS: "600",
    AGENTCART_ONCHAIN_REGISTRY_ADDRESS: registryAddress,
    AGENTCART_ONCHAIN_EXPECTED_CHAIN_ID: "42431",
    AGENTCART_ONCHAIN_EVENTS_OUTPUT: "/events/onchain-events.json",
  });

  assert.equal(config.witnessIndexer.rpcUrl, "https://witness-rpc.example.test/project-key");
  assert.equal(config.witnessName, "independent-provider");
  assert.equal(config.witnessMaxFinalityLagSeconds, 180);
  assert.equal(config.divergenceAlert.webhookUrl, "https://alerts.example.test/registry");
  assert.equal(config.divergenceAlert.throttleMilliseconds, 600_000);
  assert.throws(
    () => runtimeConfig({
      AGENTCART_ONCHAIN_RPC_URL: "https://same-rpc.example.test",
      AGENTCART_ONCHAIN_WITNESS_RPC_URL: "https://same-rpc.example.test",
      AGENTCART_ONCHAIN_REGISTRY_ADDRESS: registryAddress,
      AGENTCART_ONCHAIN_EXPECTED_CHAIN_ID: "42431",
      AGENTCART_ONCHAIN_EVENTS_OUTPUT: "/events/onchain-events.json",
    }),
    /must differ/,
  );
});

function finalizedSnapshot({
  events = [],
  finalizedBlock = 120,
  indexedToBlock = finalizedBlock,
  finalityHash = blockHash,
  finalityTime = "2026-08-13T00:00:00Z",
  chainId = "eip155:42431",
  address = registryAddress,
} = {}) {
  return {
    complete: true,
    errors: [],
    events,
    chain_id: chainId,
    registry_address: address,
    finality: {
      block_number: finalizedBlock,
      block_hash: finalityHash,
      block_time: finalityTime,
      indexed_from_block: 100,
      indexed_to_block: indexedToBlock,
    },
  };
}

test("independent RPC comparison publishes only the common matched finalized history", async () => {
  const sharedEvent = {
    event: "MerchantRevoked",
    block_number: 111,
    block_hash: blockHash,
    block_time: "2026-08-13T00:00:00Z",
    transaction_hash: transactionHash,
    log_index: 0,
    args: { recordId },
  };
  const primaryOnlyFutureEvent = { ...sharedEvent, block_number: 121, log_index: 1 };
  const primary = finalizedSnapshot({ events: [sharedEvent, primaryOnlyFutureEvent], finalizedBlock: 125 });
  const witness = finalizedSnapshot({ events: [sharedEvent], finalizedBlock: 120 });
  const comparison = compareFinalizedSnapshots(primary, witness, "witness-provider");
  assert.equal(comparison.status, "matched");
  assert.equal(comparison.common_finalized_block, 120);
  assert.equal(comparison.primary.canonical_events_sha256, comparison.witness_path.canonical_events_sha256);

  const calls = [];
  const document = await collectIndependentlyVerifiedSnapshot(
    {
      indexer: { rpcUrl: "https://primary.example.test" },
      witnessIndexer: { rpcUrl: "https://witness.example.test" },
      witnessName: "witness-provider",
    },
    {
      collect: async (options) => {
        calls.push(options.rpcUrl);
        return options.rpcUrl.includes("primary") ? primary : witness;
      },
    },
  );
  assert.deepEqual(calls, ["https://primary.example.test", "https://witness.example.test"]);
  assert.equal(document.events.length, 1);
  assert.equal(document.finality.indexed_to_block, 120);
  assert.equal(document.independent_verification.status, "matched");
});

test("independent RPC comparison fails closed on event or finalized-head divergence", async () => {
  const event = {
    event: "MerchantRevoked",
    block_number: 111,
    block_hash: blockHash,
    block_time: "2026-08-13T00:00:00Z",
    transaction_hash: transactionHash,
    log_index: 0,
    args: { recordId },
  };
  const primary = finalizedSnapshot({ events: [event] });
  const missingEvent = finalizedSnapshot({ events: [] });
  assert.equal(compareFinalizedSnapshots(primary, missingEvent).status, "diverged");
  assert.equal(
    compareFinalizedSnapshots(primary, finalizedSnapshot({ events: [event], finalityHash: `0x${"dd".repeat(32)}` })).status,
    "diverged",
  );
  const lagged = compareFinalizedSnapshots(
    primary,
    finalizedSnapshot({ events: [event], finalizedBlock: 119, finalityTime: "2026-08-12T23:50:00Z" }),
    "lagged-provider",
    300,
  );
  assert.equal(lagged.status, "diverged");
  assert.equal(lagged.finalized_time_lag_within_limit, false);

  await assert.rejects(
    collectIndependentlyVerifiedSnapshot(
      {
        indexer: { rpcUrl: "https://primary.example.test" },
        witnessIndexer: { rpcUrl: "https://witness.example.test" },
      },
      { collect: async (options) => options.rpcUrl.includes("primary") ? primary : missingEvent },
    ),
    (error) => error.code === "registry_rpc_divergence"
      && error.verification?.status === "diverged",
  );
});

test("independent RPC alert is redacted and carries no RPC URLs", async () => {
  const requests = [];
  const error = new Error("independent finalized RPC reconstructions diverged");
  error.code = "registry_rpc_divergence";
  error.verification = compareFinalizedSnapshots(finalizedSnapshot(), finalizedSnapshot({ events: [{
    event: "MerchantRevoked",
    block_number: 111,
    args: { recordId },
  }] }));
  const config = {
    expectedChainId: "42431",
    indexer: { registryAddress, rpcUrl: "https://primary.example.test/private-key" },
    witnessName: "independent-provider",
    divergenceAlert: {
      webhookUrl: "https://alerts.example.test/registry",
      webhookToken: "alert-token",
    },
  };
  await sendIndependentRpcAlert(config, error, "firing", {
    fetch: async (url, options) => {
      requests.push({ url, options });
      return { ok: true, status: 202 };
    },
  });

  assert.equal(requests[0].options.headers.authorization, "Bearer alert-token");
  const payload = JSON.parse(requests[0].options.body);
  assert.equal(payload.schema, "agentcart.onchain_registry_independent_rpc_alert.v1");
  assert.equal(payload.state, "firing");
  assert.equal(payload.code, "registry_rpc_divergence");
  assert.doesNotMatch(requests[0].options.body, /primary\.example|private-key|alerts\.example/);
});

test("recurring witness mode throttles repeated divergence and emits resolution", async () => {
  const event = {
    event: "MerchantRevoked",
    block_number: 111,
    block_hash: blockHash,
    block_time: "2026-08-13T00:00:00Z",
    transaction_hash: transactionHash,
    log_index: 0,
    args: { recordId },
  };
  let collections = 0;
  const notifications = [];
  const writes = [];
  const errors = [];
  await runIndexerLoop(
    {
      expectedChainId: "42431",
      indexer: { registryAddress, rpcUrl: "https://primary.example.test" },
      witnessIndexer: { registryAddress, rpcUrl: "https://witness.example.test" },
      witnessName: "independent-provider",
      output: "/events/onchain-events.json",
      refreshMilliseconds: 60_000,
      divergenceAlert: { webhookUrl: "https://alerts.example.test", throttleMilliseconds: 900_000 },
    },
    {
      collect: async (options) => {
        collections += 1;
        const cycle = Math.ceil(collections / 2);
        const witness = options.rpcUrl.includes("witness");
        return finalizedSnapshot({ events: witness && cycle < 3 ? [] : [event] });
      },
      write: async (document) => writes.push(document),
      wait: async () => {},
      now: () => 1_000,
      notify: async (_config, error, state) => notifications.push({ code: error.code, state }),
      onSuccess: () => {},
      onError: (error) => errors.push(error.code || error.message),
      shouldContinue: () => collections < 6,
    },
  );

  assert.deepEqual(notifications, [
    { code: "registry_rpc_divergence", state: "firing" },
    { code: "registry_rpc_divergence", state: "resolved" },
  ]);
  assert.deepEqual(errors, ["registry_rpc_divergence", "registry_rpc_divergence"]);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].independent_verification.status, "matched");
});

test("registry mutations require an explicit production-network override", () => {
  assert.doesNotThrow(() => assertMutationNetworkAllowed(42431, {}));
  assert.throws(() => assertMutationNetworkAllowed(1, {}), /production-network mutations are disabled/);
  assert.throws(() => assertMutationNetworkAllowed(100, {}), /production-network mutations are disabled/);
  assert.throws(() => assertMutationNetworkAllowed(4217, {}), /production-network mutations are disabled/);
  assert.throws(
    () => assertMutationNetworkAllowed(999999, {}, "mainnet"),
    /production-network mutations are disabled/,
  );
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
