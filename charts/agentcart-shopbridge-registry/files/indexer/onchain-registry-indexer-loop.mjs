#!/usr/bin/env node

import { realpath } from "node:fs/promises";
import process from "node:process";
import { fileURLToPath } from "node:url";

import {
  collectFinalizedEvents,
  writeDocument,
} from "./onchain-registry-indexer.mjs";

const DEFAULT_REFRESH_SECONDS = 240;
const MIN_REFRESH_SECONDS = 60;
const MAX_REFRESH_SECONDS = 300;

function requiredEnvironment(environment, name) {
  const value = String(environment[name] || "").trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function boundedInteger(value, name, minimum, maximum) {
  if (!/^[1-9][0-9]*$/.test(String(value || ""))) {
    throw new Error(`${name} must be a positive integer`);
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${name} must be between ${minimum} and ${maximum}`);
  }
  return parsed;
}

export function runtimeConfig(environment = process.env) {
  const refreshSeconds = boundedInteger(
    environment.AGENTCART_ONCHAIN_REFRESH_SECONDS || String(DEFAULT_REFRESH_SECONDS),
    "AGENTCART_ONCHAIN_REFRESH_SECONDS",
    MIN_REFRESH_SECONDS,
    MAX_REFRESH_SECONDS,
  );
  return {
    output: requiredEnvironment(environment, "AGENTCART_ONCHAIN_EVENTS_OUTPUT"),
    expectedChainId: requiredEnvironment(environment, "AGENTCART_ONCHAIN_EXPECTED_CHAIN_ID"),
    refreshMilliseconds: refreshSeconds * 1000,
    indexer: {
      rpcUrl: requiredEnvironment(environment, "AGENTCART_ONCHAIN_RPC_URL"),
      registryAddress: requiredEnvironment(environment, "AGENTCART_ONCHAIN_REGISTRY_ADDRESS"),
      fromBlock: String(environment.AGENTCART_ONCHAIN_FROM_BLOCK || "0"),
      toBlock: "finalized",
      chunkSize: String(environment.AGENTCART_ONCHAIN_LOG_CHUNK_SIZE || "10000"),
      allowPrivateRecordUri: false,
      allowIncompleteRecords: false,
    },
  };
}

export async function refreshFinalizedSnapshot(config, dependencies = {}) {
  const collect = dependencies.collect || collectFinalizedEvents;
  const write = dependencies.write || writeDocument;
  const document = await collect(config.indexer);
  if (!document?.complete || document?.errors?.length) {
    throw new Error("indexer returned an incomplete finalized snapshot");
  }
  if (document.chain_id !== `eip155:${config.expectedChainId}`) {
    throw new Error("indexer RPC chain does not match the selected registry deployment");
  }
  if (String(document.registry_address || "").toLowerCase() !== config.indexer.registryAddress.toLowerCase()) {
    throw new Error("indexer output registry does not match the selected registry deployment");
  }
  await write(document, config.output);
  return document;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export async function runIndexerLoop(config, dependencies = {}) {
  const wait = dependencies.wait || delay;
  const onSuccess = dependencies.onSuccess || ((document) => {
    process.stdout.write(
      `indexed finalized block ${document.finality.block_number} with ${document.events.length} event(s)\n`,
    );
  });
  const onError = dependencies.onError || ((error) => {
    process.stderr.write(`finalized registry refresh failed: ${error instanceof Error ? error.message : String(error)}\n`);
  });
  const shouldContinue = dependencies.shouldContinue || (() => true);

  while (shouldContinue()) {
    try {
      onSuccess(await refreshFinalizedSnapshot(config, dependencies));
    } catch (error) {
      // Preserve the last complete snapshot. Buyer-side freshness enforcement
      // turns it unusable after the configured trust window if failures persist.
      onError(error);
    }
    if (shouldContinue()) await wait(config.refreshMilliseconds);
  }
}

async function main() {
  await runIndexerLoop(runtimeConfig());
}

export async function isMainInvocation(moduleUrl, invocationPath) {
  if (!invocationPath) return false;
  const [modulePath, executablePath] = await Promise.all([
    realpath(fileURLToPath(moduleUrl)),
    realpath(invocationPath),
  ]);
  return modulePath === executablePath;
}

if (await isMainInvocation(import.meta.url, process.argv[1])) {
  await main();
}
