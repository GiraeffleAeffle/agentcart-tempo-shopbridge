#!/usr/bin/env node

import { createHash } from "node:crypto";
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
const DEFAULT_ALERT_THROTTLE_SECONDS = 900;
const MIN_ALERT_THROTTLE_SECONDS = 60;
const MAX_ALERT_THROTTLE_SECONDS = 86_400;
const DEFAULT_MAX_FINALITY_LAG_SECONDS = 300;
const MIN_MAX_FINALITY_LAG_SECONDS = 30;
const MAX_MAX_FINALITY_LAG_SECONDS = 3600;
const INDEPENDENT_VERIFICATION_SCHEMA = "agentcart.onchain_registry_independent_verification.v1";
const INDEPENDENT_ALERT_SCHEMA = "agentcart.onchain_registry_independent_rpc_alert.v1";

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

function optionalHttpsUrl(value, name) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`${name} must be a valid HTTPS URL`);
  }
  if (url.protocol !== "https:" || url.username || url.password) {
    throw new Error(`${name} must be an HTTPS URL without user information`);
  }
  return raw;
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

function sha256Canonical(value) {
  return createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

function comparableEvents(document, throughBlock) {
  const events = Array.isArray(document?.events) ? document.events : [];
  return events
    .filter((event) => Number(event?.block_number) <= throughBlock)
    .map((event) => ({
      event: String(event?.event || ""),
      block_number: Number(event?.block_number || 0),
      block_hash: String(event?.block_hash || "").toLowerCase(),
      block_time: String(event?.block_time || ""),
      transaction_hash: String(event?.transaction_hash || "").toLowerCase(),
      log_index: Number(event?.log_index || 0),
      args: event?.args && typeof event.args === "object" ? event.args : {},
      ...(event?.registry_record && typeof event.registry_record === "object"
        ? { registry_record: event.registry_record }
        : {}),
      ...(event?.record_fetch_error ? { record_fetch_error: String(event.record_fetch_error) } : {}),
    }));
}

function completeSnapshot(document, role) {
  if (!document?.complete || document?.errors?.length) {
    const error = new Error(`${role} indexer returned an incomplete finalized snapshot`);
    error.code = `registry_${role}_rpc_incomplete`;
    throw error;
  }
  const indexedToBlock = Number(document?.finality?.indexed_to_block);
  const finalizedBlock = Number(document?.finality?.block_number);
  const finalizedAt = Date.parse(String(document?.finality?.block_time || ""));
  if (
    !Number.isSafeInteger(indexedToBlock)
    || !Number.isSafeInteger(finalizedBlock)
    || !Number.isFinite(finalizedAt)
  ) {
    const error = new Error(`${role} indexer returned invalid finality metadata`);
    error.code = `registry_${role}_rpc_invalid`;
    throw error;
  }
  return { finalizedAt, finalizedBlock, indexedToBlock };
}

export function compareFinalizedSnapshots(
  primary,
  witness,
  witnessName = "witness",
  maxFinalityLagSeconds = DEFAULT_MAX_FINALITY_LAG_SECONDS,
) {
  const primaryFinality = completeSnapshot(primary, "primary");
  const witnessFinality = completeSnapshot(witness, "witness");
  const commonFinalizedBlock = Math.min(primaryFinality.indexedToBlock, witnessFinality.indexedToBlock);
  const primaryEvents = comparableEvents(primary, commonFinalizedBlock);
  const witnessEvents = comparableEvents(witness, commonFinalizedBlock);
  const primaryHash = sha256Canonical(primaryEvents);
  const witnessHash = sha256Canonical(witnessEvents);
  const sameChain = String(primary.chain_id || "") === String(witness.chain_id || "");
  const sameRegistry = String(primary.registry_address || "").toLowerCase()
    === String(witness.registry_address || "").toLowerCase();
  const comparableHeadHashes = primaryFinality.finalizedBlock === witnessFinality.finalizedBlock;
  const headHashMatch = comparableHeadHashes
    ? String(primary.finality.block_hash || "").toLowerCase()
      === String(witness.finality.block_hash || "").toLowerCase()
    : null;
  const finalityLagSeconds = Math.abs(primaryFinality.finalizedAt - witnessFinality.finalizedAt) / 1000;
  const finalityLagWithinLimit = finalityLagSeconds <= maxFinalityLagSeconds;
  const matched = sameChain
    && sameRegistry
    && primaryHash === witnessHash
    && headHashMatch !== false
    && finalityLagWithinLimit !== false;
  return {
    schema: INDEPENDENT_VERIFICATION_SCHEMA,
    status: matched ? "matched" : "diverged",
    witness: String(witnessName || "witness"),
    checked_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
    common_finalized_block: commonFinalizedBlock,
    chain_id_match: sameChain,
    registry_address_match: sameRegistry,
    finalized_head_hash_match: headHashMatch,
    finalized_time_lag_seconds: finalityLagSeconds,
    max_finalized_time_lag_seconds: maxFinalityLagSeconds,
    finalized_time_lag_within_limit: finalityLagWithinLimit,
    primary: {
      finalized_block: primaryFinality.finalizedBlock,
      event_count: primaryEvents.length,
      canonical_events_sha256: primaryHash,
    },
    witness_path: {
      finalized_block: witnessFinality.finalizedBlock,
      event_count: witnessEvents.length,
      canonical_events_sha256: witnessHash,
    },
  };
}

function taggedCollectionError(role, error) {
  const wrapped = new Error(`${role} finalized RPC reconstruction failed`);
  wrapped.code = `registry_${role}_rpc_failed`;
  wrapped.cause = error;
  return wrapped;
}

export async function collectIndependentlyVerifiedSnapshot(config, dependencies = {}) {
  const collect = dependencies.collect || collectFinalizedEvents;
  let primary;
  let witness;
  try {
    primary = await collect(config.indexer);
  } catch (error) {
    throw taggedCollectionError("primary", error);
  }
  try {
    witness = await collect(config.witnessIndexer);
  } catch (error) {
    throw taggedCollectionError("witness", error);
  }
  const verification = compareFinalizedSnapshots(
    primary,
    witness,
    config.witnessName,
    config.witnessMaxFinalityLagSeconds,
  );
  if (verification.status !== "matched") {
    const error = new Error("independent finalized RPC reconstructions diverged");
    error.code = "registry_rpc_divergence";
    error.verification = verification;
    throw error;
  }
  return {
    ...primary,
    completeness_authority: "independently_verified",
    finality: {
      ...primary.finality,
      indexed_to_block: verification.common_finalized_block,
    },
    events: (Array.isArray(primary.events) ? primary.events : [])
      .filter((event) => Number(event?.block_number) <= verification.common_finalized_block),
    independent_verification: verification,
  };
}

export function runtimeConfig(environment = process.env) {
  const refreshSeconds = boundedInteger(
    environment.AGENTCART_ONCHAIN_REFRESH_SECONDS || String(DEFAULT_REFRESH_SECONDS),
    "AGENTCART_ONCHAIN_REFRESH_SECONDS",
    MIN_REFRESH_SECONDS,
    MAX_REFRESH_SECONDS,
  );
  const rpcUrl = requiredEnvironment(environment, "AGENTCART_ONCHAIN_RPC_URL");
  const witnessRpcUrl = optionalHttpsUrl(
    environment.AGENTCART_ONCHAIN_WITNESS_RPC_URL,
    "AGENTCART_ONCHAIN_WITNESS_RPC_URL",
  );
  if (witnessRpcUrl && witnessRpcUrl === rpcUrl) {
    throw new Error("AGENTCART_ONCHAIN_WITNESS_RPC_URL must differ from AGENTCART_ONCHAIN_RPC_URL");
  }
  const alertWebhookUrl = optionalHttpsUrl(
    environment.AGENTCART_ONCHAIN_DIVERGENCE_ALERT_WEBHOOK_URL,
    "AGENTCART_ONCHAIN_DIVERGENCE_ALERT_WEBHOOK_URL",
  );
  if (alertWebhookUrl && !witnessRpcUrl) {
    throw new Error("AGENTCART_ONCHAIN_WITNESS_RPC_URL is required when divergence alerts are configured");
  }
  const indexer = {
    rpcUrl,
    registryAddress: requiredEnvironment(environment, "AGENTCART_ONCHAIN_REGISTRY_ADDRESS"),
    fromBlock: String(environment.AGENTCART_ONCHAIN_FROM_BLOCK || "0"),
    toBlock: "finalized",
    chunkSize: String(environment.AGENTCART_ONCHAIN_LOG_CHUNK_SIZE || "10000"),
    allowPrivateRecordUri: false,
    allowIncompleteRecords: false,
  };
  return {
    output: requiredEnvironment(environment, "AGENTCART_ONCHAIN_EVENTS_OUTPUT"),
    expectedChainId: requiredEnvironment(environment, "AGENTCART_ONCHAIN_EXPECTED_CHAIN_ID"),
    refreshMilliseconds: refreshSeconds * 1000,
    indexer,
    witnessIndexer: witnessRpcUrl ? { ...indexer, rpcUrl: witnessRpcUrl } : null,
    witnessName: String(environment.AGENTCART_ONCHAIN_WITNESS_NAME || "independent-rpc").trim(),
    witnessMaxFinalityLagSeconds: boundedInteger(
      environment.AGENTCART_ONCHAIN_WITNESS_MAX_FINALITY_LAG_SECONDS
        || String(DEFAULT_MAX_FINALITY_LAG_SECONDS),
      "AGENTCART_ONCHAIN_WITNESS_MAX_FINALITY_LAG_SECONDS",
      MIN_MAX_FINALITY_LAG_SECONDS,
      MAX_MAX_FINALITY_LAG_SECONDS,
    ),
    divergenceAlert: {
      webhookUrl: alertWebhookUrl,
      webhookToken: String(environment.AGENTCART_ONCHAIN_DIVERGENCE_ALERT_WEBHOOK_TOKEN || ""),
      throttleMilliseconds: boundedInteger(
        environment.AGENTCART_ONCHAIN_DIVERGENCE_ALERT_THROTTLE_SECONDS
          || String(DEFAULT_ALERT_THROTTLE_SECONDS),
        "AGENTCART_ONCHAIN_DIVERGENCE_ALERT_THROTTLE_SECONDS",
        MIN_ALERT_THROTTLE_SECONDS,
        MAX_ALERT_THROTTLE_SECONDS,
      ) * 1000,
    },
  };
}

export async function refreshFinalizedSnapshot(config, dependencies = {}) {
  const collect = dependencies.collect || collectFinalizedEvents;
  const write = dependencies.write || writeDocument;
  const document = config.witnessIndexer
    ? await collectIndependentlyVerifiedSnapshot(config, { collect })
    : await collect(config.indexer);
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

function independentRpcAlertPayload(config, error, state) {
  const verification = error?.verification && typeof error.verification === "object"
    ? error.verification
    : null;
  return {
    schema: INDEPENDENT_ALERT_SCHEMA,
    state,
    severity: state === "resolved" ? "info" : "critical",
    code: String(error?.code || "registry_independent_rpc_failed"),
    observed_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
    chain_id: `eip155:${config.expectedChainId}`,
    registry_address: String(config.indexer.registryAddress || ""),
    witness: String(config.witnessName || "independent-rpc"),
    ...(verification ? { verification } : {}),
  };
}

export async function sendIndependentRpcAlert(config, error, state, dependencies = {}) {
  const webhookUrl = config?.divergenceAlert?.webhookUrl;
  if (!webhookUrl) return { delivered: false, reason: "not_configured" };
  const fetchImpl = dependencies.fetch || globalThis.fetch;
  const headers = {
    "content-type": "application/json",
    "user-agent": "AgentCart-Onchain-Indexer/1",
    "x-agentcart-event": "registry.independent-rpc",
  };
  if (config.divergenceAlert.webhookToken) {
    headers.authorization = `Bearer ${config.divergenceAlert.webhookToken}`;
  }
  const response = await fetchImpl(webhookUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(independentRpcAlertPayload(config, error, state)),
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error(`independent RPC alert webhook returned HTTP ${response.status}`);
  return { delivered: true, status: response.status };
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
  const notify = dependencies.notify || sendIndependentRpcAlert;
  const now = dependencies.now || (() => Date.now());
  let activeIndependentRpcError = null;
  let lastAlertFingerprint = "";
  let lastAlertAt = 0;

  while (shouldContinue()) {
    try {
      const document = await refreshFinalizedSnapshot(config, dependencies);
      if (activeIndependentRpcError) {
        try {
          await notify(config, activeIndependentRpcError, "resolved", dependencies);
        } catch (alertError) {
          onError(alertError);
        }
        activeIndependentRpcError = null;
        lastAlertFingerprint = "";
        lastAlertAt = 0;
      }
      onSuccess(document);
    } catch (error) {
      // Preserve the last complete snapshot. Buyer-side freshness enforcement
      // turns it unusable after the configured trust window if failures persist.
      onError(error);
      if (config.witnessIndexer && String(error?.code || "").startsWith("registry_")) {
        const fingerprint = sha256Canonical({
          code: String(error?.code || ""),
          verification: error?.verification ? {
            status: error.verification.status,
            chain_id_match: error.verification.chain_id_match,
            registry_address_match: error.verification.registry_address_match,
            finalized_head_hash_match: error.verification.finalized_head_hash_match,
            finalized_time_lag_within_limit: error.verification.finalized_time_lag_within_limit,
            primary: {
              event_count: error.verification.primary?.event_count,
              canonical_events_sha256: error.verification.primary?.canonical_events_sha256,
            },
            witness_path: {
              event_count: error.verification.witness_path?.event_count,
              canonical_events_sha256: error.verification.witness_path?.canonical_events_sha256,
            },
          } : null,
        });
        const observedAt = now();
        const throttle = Number(config?.divergenceAlert?.throttleMilliseconds || 0);
        if (fingerprint !== lastAlertFingerprint || observedAt - lastAlertAt >= throttle) {
          try {
            await notify(config, error, "firing", dependencies);
            lastAlertFingerprint = fingerprint;
            lastAlertAt = observedAt;
          } catch (alertError) {
            onError(alertError);
          }
        }
        activeIndependentRpcError = error;
      }
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
