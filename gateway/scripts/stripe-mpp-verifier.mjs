#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";

import { createPublicClient, createWalletClient, http as viemHttp, parseUnits } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { tempo as tempoMainnet, tempoModerato } from "viem/tempo/chains";
import Stripe from "stripe";
import { Challenge, Receipt } from "mppx";
import { Mppx, stripe as mppStripe } from "mppx/server";
import {
  claimSQLiteReplayReference,
  sqliteReplayStoreDiagnostics,
  sqliteReplayStoreWriteProbe,
} from "./verifier-sqlite-replay-store.mjs";

const host = process.env.STRIPE_MPP_VERIFIER_BIND || "127.0.0.1";
const port = Number(process.env.STRIPE_MPP_VERIFIER_PORT || "4260");
const stripeSecretKey = (
  process.env.STRIPE_SANDBOX_SECRET_KEY ||
  process.env.STRIPE_SECRET_KEY ||
  ""
).trim();
const stripeProfileId = (process.env.STRIPE_PROFILE_ID || process.env.AGENTCART_STRIPE_PROFILE_ID || "").trim();
const mppSecretKey = (process.env.MPP_SECRET_KEY || "").trim();
const verifierToken = (process.env.AGENTCART_PAYMENT_VERIFIER_TOKEN || "").trim();
const replayStorePath = (
  process.env.AGENTCART_VERIFIER_REPLAY_STORE_PATH ||
  process.env.STRIPE_MPP_REPLAY_STORE_PATH ||
  ""
).trim();
const replayStoreDriver = normalizeReplayStoreDriver(process.env.AGENTCART_VERIFIER_REPLAY_STORE_DRIVER || "");
const replayStoreLockTimeoutMs = Number(process.env.AGENTCART_VERIFIER_REPLAY_LOCK_TIMEOUT_MS || "5000");
const requireDurableReplayStore = envFlag(process.env.AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY);
const replayJournalPath = (
  process.env.AGENTCART_VERIFIER_REPLAY_JOURNAL_PATH ||
  process.env.STRIPE_MPP_REPLAY_JOURNAL_PATH ||
  ""
).trim();
const requireReplayJournal = envFlag(process.env.AGENTCART_VERIFIER_REQUIRE_REPLAY_JOURNAL);
const defaultCurrency = (process.env.STRIPE_MPP_CURRENCY || "eur").trim().toLowerCase();
const paymentMethodTypes = (process.env.STRIPE_MPP_PAYMENT_METHOD_TYPES || "card,link")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);
const verifierAlertWebhookUrl = (process.env.AGENTCART_VERIFIER_ALERT_WEBHOOK_URL || "").trim();
const verifierAlertWebhookToken = (process.env.AGENTCART_VERIFIER_ALERT_WEBHOOK_TOKEN || "").trim();
const verifierAlertMinSeverity = normalizeSeverity(process.env.AGENTCART_VERIFIER_ALERT_MIN_SEVERITY || "warning");
const verifierAlertThrottleSeconds = Math.max(
  0,
  Number(process.env.AGENTCART_VERIFIER_ALERT_THROTTLE_SECONDS || "300"),
);
const tempoRefundMode = (process.env.AGENTCART_TEMPO_REFUND_MODE || "disabled").trim().toLowerCase();
const tempoRefundPrivateKey = (process.env.AGENTCART_TEMPO_REFUND_PRIVATE_KEY || "").trim();
const tempoRefundRpcUrl = (process.env.AGENTCART_TEMPO_REFUND_RPC_URL || "").trim();
const tempoRefundTokenAddress = (process.env.AGENTCART_TEMPO_REFUND_TOKEN_ADDRESS || "").trim();
const tempoRefundAsset = (process.env.AGENTCART_TEMPO_REFUND_ASSET || "").trim();
const tempoRefundDecimals = Number(process.env.AGENTCART_TEMPO_REFUND_DECIMALS || "6");
const tempoRefundConfirmations = Math.max(1, Number(process.env.AGENTCART_TEMPO_REFUND_CONFIRMATIONS || "1"));
const tempoSettlementMode = (process.env.AGENTCART_TEMPO_SETTLEMENT_MODE || "disabled").trim().toLowerCase();
const tempoSettlementRpcUrl = (process.env.AGENTCART_TEMPO_SETTLEMENT_RPC_URL || "").trim();
const tempoSettlementTokenAddress = (process.env.AGENTCART_TEMPO_SETTLEMENT_TOKEN_ADDRESS || "").trim();
const tempoSettlementAsset = (process.env.AGENTCART_TEMPO_SETTLEMENT_ASSET || "").trim();
const tempoSettlementDecimals = Number(process.env.AGENTCART_TEMPO_SETTLEMENT_DECIMALS || "6");
const tempoSettlementConfirmations = Math.max(
  1,
  Number(process.env.AGENTCART_TEMPO_SETTLEMENT_CONFIRMATIONS || "1"),
);

const tempoTokenDefaults = {
  mainnet: {
    asset: "USDC.e",
    tokenAddress: "0x20C000000000000000000000b9537d11c60E8b50",
  },
  testnet: {
    asset: "pathUSD",
    tokenAddress: "0x20c0000000000000000000000000000000000000",
  },
};
const erc20TransferAbi = [
  {
    type: "function",
    name: "balanceOf",
    stateMutability: "view",
    inputs: [{ name: "account", type: "address" }],
    outputs: [{ name: "balance", type: "uint256" }],
  },
  {
    type: "function",
    name: "transfer",
    stateMutability: "nonpayable",
    inputs: [
      { name: "to", type: "address" },
      { name: "amount", type: "uint256" },
    ],
    outputs: [{ name: "success", type: "bool" }],
  },
];
const erc20TransferTopic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";

const stripeClient = stripeSecretKey
  ? new Stripe(stripeSecretKey, { apiVersion: "2026-02-25.preview" })
  : null;
const memoryReplayStore = blankReplayStore();
const verifierStartedAt = new Date().toISOString();
const verifierMetrics = blankVerifierMetrics();
const verifierAlertState = { lastSentByFingerprint: new Map() };

function envFlag(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function normalizeReplayStoreDriver(value) {
  const driver = String(value || "").trim().toLowerCase();
  if (["sqlite", "sqlite3"].includes(driver)) return "sqlite";
  if (["json", "file", "lockfile"].includes(driver)) return "json";
  return "json";
}

function normalizeSeverity(value) {
  const severity = String(value || "warning").trim().toLowerCase();
  return ["info", "warning", "critical"].includes(severity) ? severity : "warning";
}

function severityAllowed(severity, minimum) {
  const rank = { info: 1, warning: 2, critical: 3 };
  return rank[normalizeSeverity(severity)] >= rank[normalizeSeverity(minimum)];
}

function jsonResponse(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body, null, 2) + "\n", {
    status,
    headers: {
      "cache-control": "no-store",
      "content-type": "application/json; charset=utf-8",
      ...headers,
    },
  });
}

function blankLatencyMetrics() {
  return {
    count: 0,
    total_ms: 0,
    max_ms: 0,
    last_ms: 0,
  };
}

function blankOutcomeBucket() {
  return {
    total: 0,
    ok: 0,
    rejected: 0,
    error: 0,
    latency_ms: blankLatencyMetrics(),
  };
}

function blankVerifierMetrics() {
  return {
    schema: "agentcart.verifierMetrics.v1",
    service: "agentcart-stripe-mpp-verifier",
    mode: "sandbox",
    started_at: verifierStartedAt,
    requests_total: 0,
    responses_total: 0,
    outcomes: { ok: 0, rejected: 0, error: 0 },
    by_operation: {},
    by_rail: {},
    by_status: {},
    rejections: {},
    provider_errors: {},
    settlement: {
      real_settlement_verified: 0,
      demo_settlement_verified: 0,
      real_refund_verified: 0,
      idempotent_replay: 0,
    },
    replay_journal: {
      configured: Boolean(replayJournalPath),
      required: requireReplayJournal,
      appended: 0,
      failed: 0,
      last_event: null,
      last_error: null,
    },
    alerts: {
      webhook_configured: Boolean(verifierAlertWebhookUrl),
      min_severity: verifierAlertMinSeverity,
      throttle_seconds: verifierAlertThrottleSeconds,
      sent: 0,
      failed: 0,
      skipped: 0,
      throttled: 0,
      last_delivery: null,
    },
    latency_ms: blankLatencyMetrics(),
    last_event: null,
  };
}

function incrementCounter(bucket, key, amount = 1) {
  const safeKey = String(key || "unknown");
  bucket[safeKey] = Number(bucket[safeKey] || 0) + amount;
}

function latencyMsSince(startedNs) {
  return Number((process.hrtime.bigint() - startedNs) / 1000000n);
}

function recordLatency(target, latencyMs) {
  target.count += 1;
  target.total_ms += latencyMs;
  target.max_ms = Math.max(target.max_ms, latencyMs);
  target.last_ms = latencyMs;
}

function latencySnapshot(metrics) {
  return {
    ...metrics,
    avg_ms: metrics.count ? Number((metrics.total_ms / metrics.count).toFixed(2)) : 0,
  };
}

function bucketSnapshot(bucket) {
  const snapshot = {};
  for (const [key, value] of Object.entries(bucket)) {
    snapshot[key] = {
      ...value,
      success_rate: value.total ? Number((value.ok / value.total).toFixed(4)) : 0,
      latency_ms: latencySnapshot(value.latency_ms),
    };
  }
  return snapshot;
}

function verifierMetricsSnapshot() {
  return {
    ...verifierMetrics,
    success_rate: verifierMetrics.responses_total
      ? Number((verifierMetrics.outcomes.ok / verifierMetrics.responses_total).toFixed(4))
      : 0,
    latency_ms: latencySnapshot(verifierMetrics.latency_ms),
    by_operation: bucketSnapshot(verifierMetrics.by_operation),
    by_rail: bucketSnapshot(verifierMetrics.by_rail),
    replay_store: replayStoreDiagnostics(),
    replay_journal: {
      ...verifierMetrics.replay_journal,
      ...replayJournalDiagnostics(),
    },
  };
}

function sanitizeMetricKey(value) {
  const normalized = String(value || "unknown")
    .toLowerCase()
    .replace(/[^a-z0-9_.:-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 120);
  return normalized || "unknown";
}

function responseJsonOrNull(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) return Promise.resolve(null);
  return response
    .clone()
    .json()
    .catch(() => null);
}

function requestCorrelationId(request) {
  const supplied =
    request.headers.get("x-agentcart-correlation-id") ||
    request.headers.get("x-request-id") ||
    request.headers.get("traceparent") ||
    "";
  return String(supplied || crypto.randomUUID()).trim().slice(0, 160);
}

function applyCorrelationHeader(response, correlationId) {
  try {
    response.headers.set("x-agentcart-correlation-id", correlationId);
  } catch {
    // Some third-party Response objects can have immutable headers.
  }
  return response;
}

function operationFromRequest(url, payload) {
  if (url.pathname === "/" || url.pathname === "/health") return "health";
  if (url.pathname === "/metrics" || url.pathname === "/metrics.json") return "metrics";
  if (url.pathname === "/stripe-mpp/challenge") return "challenge";
  if (url.pathname === "/stripe-mpp/paid") return "paid";
  if (url.pathname === "/agentcart/verify") return String(payload.operation || "payment").toLowerCase();
  return "unknown";
}

function railFromPayloadOrBody(payload, body) {
  const expected = payload.expected && typeof payload.expected === "object" ? payload.expected : {};
  const receipt =
    payload.payment_receipt && typeof payload.payment_receipt === "object" ? payload.payment_receipt : {};
  const refund = payload.refund && typeof payload.refund === "object" ? payload.refund : {};
  const raw = body?.rail || expected.rail || receipt.rail || receipt.method || receipt.provider || refund.rail || payload.rail || "";
  return raw ? normalizeRail(raw) : "none";
}

function quoteHashFromPayloadOrBody(payload, body) {
  const expected = payload.expected && typeof payload.expected === "object" ? payload.expected : {};
  const receipt =
    payload.payment_receipt && typeof payload.payment_receipt === "object" ? payload.payment_receipt : {};
  const quote = payload.quote && typeof payload.quote === "object" ? payload.quote : {};
  return String(body?.quote_hash || payload.quote_hash || expected.quote_hash || quote.quote_hash || receipt.quote_hash || "");
}

function paymentContractHashFromPayloadOrBody(payload, body) {
  const expected = payload.expected && typeof payload.expected === "object" ? payload.expected : {};
  const receipt =
    payload.payment_receipt && typeof payload.payment_receipt === "object" ? payload.payment_receipt : {};
  return String(body?.payment_contract_hash || payload.payment_contract_hash || expected.payment_contract_hash || receipt.payment_contract_hash || "");
}

function outcomeFromResponse(response, body) {
  if (response.status >= 500) return "error";
  if (body?.ok === true && response.status < 400) return "ok";
  if (response.status >= 400) return "rejected";
  return "ok";
}

function rejectionReason(response, body) {
  if (body?.replay_conflict) return "replay_conflict";
  if (body?.provider_error_class) return `provider_${body.provider_error_class}`;
  if (body?.error) return sanitizeMetricKey(body.error);
  if (response.status >= 400) return `http_${response.status}`;
  return "";
}

function updateBucket(bucket, key, outcome, latencyMs) {
  if (!bucket[key]) bucket[key] = blankOutcomeBucket();
  bucket[key].total += 1;
  bucket[key][outcome] += 1;
  recordLatency(bucket[key].latency_ms, latencyMs);
}

function structuredLog(event) {
  console.log(
    JSON.stringify({
      schema: "agentcart.verifierEvent.v1",
      at: new Date().toISOString(),
      service: "agentcart-stripe-mpp-verifier",
      ...event,
    }),
  );
}

function verifierAlertForEvent(event) {
  if (event.outcome === "ok") return null;
  const reason = sanitizeMetricKey(event.rejection_reason || `http_${event.status}`);
  const severity = event.outcome === "error" || event.status >= 500 ? "critical" : "warning";
  if (!severityAllowed(severity, verifierAlertMinSeverity)) {
    return {
      skipped: true,
      reason: "below_configured_severity",
      severity,
      code: reason,
    };
  }
  return {
    schema: "agentcart.verifier_alert_notification.v1",
    id: `verifier_alert_${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`,
    created_at: new Date().toISOString(),
    service: "agentcart-stripe-mpp-verifier",
    severity,
    code: reason,
    message: `Verifier ${event.operation} ${event.outcome}: ${reason}`,
    suggested_action:
      severity === "critical"
        ? "Check verifier configuration, provider availability, and replay store health."
        : "Inspect the payment receipt, quote binding, and provider rejection details.",
    alert: {
      operation: event.operation,
      rail: event.rail,
      status: event.status,
      outcome: event.outcome,
      rejection_reason: event.rejection_reason || null,
      provider_error_class: event.provider_error_class || null,
      retryable: event.retryable === undefined ? null : Boolean(event.retryable),
      quote_hash: event.quote_hash || null,
      payment_contract_hash: event.payment_contract_hash || null,
      correlation_id: event.correlation_id,
    },
    metrics_url: `http://${host}:${port}/metrics`,
    health_url: `http://${host}:${port}/health`,
  };
}

function verifierAlertFingerprint(alert) {
  return crypto
    .createHash("sha256")
    .update(
      JSON.stringify({
        severity: alert.severity,
        code: alert.code,
        operation: alert.alert?.operation || "",
        rail: alert.alert?.rail || "",
        status: alert.alert?.status || "",
      }),
    )
    .digest("hex");
}

function verifierAlertDeliverySkipped(reason, detail = {}) {
  const delivery = {
    schema: "agentcart.verifier_alert_delivery.v1",
    state: "skipped",
    reason,
    created_at: new Date().toISOString(),
    configured: {
      webhook_configured: Boolean(verifierAlertWebhookUrl),
      min_severity: verifierAlertMinSeverity,
      throttle_seconds: verifierAlertThrottleSeconds,
    },
    ...detail,
  };
  verifierMetrics.alerts.skipped += 1;
  verifierMetrics.alerts.last_delivery = delivery;
  return delivery;
}

async function deliverVerifierAlert(alert) {
  if (!alert) return verifierAlertDeliverySkipped("no_alert");
  if (alert.skipped) return verifierAlertDeliverySkipped(alert.reason, { alert });
  if (!verifierAlertWebhookUrl) return verifierAlertDeliverySkipped("no_verifier_alert_webhook_configured", { alert });

  const fingerprint = verifierAlertFingerprint(alert);
  const now = Date.now();
  const lastSent = verifierAlertState.lastSentByFingerprint.get(fingerprint) || 0;
  if (verifierAlertThrottleSeconds > 0 && now - lastSent < verifierAlertThrottleSeconds * 1000) {
    verifierMetrics.alerts.throttled += 1;
    const delivery = {
      schema: "agentcart.verifier_alert_delivery.v1",
      state: "skipped",
      reason: "alert_throttled",
      created_at: new Date().toISOString(),
      fingerprint,
      alert,
    };
    verifierMetrics.alerts.last_delivery = delivery;
    return delivery;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 3000);
  try {
    const response = await fetch(verifierAlertWebhookUrl, {
      body: JSON.stringify(alert),
      headers: {
        "content-type": "application/json; charset=utf-8",
        "x-agentcart-event": "verifier.alert",
        "x-agentcart-event-id": alert.id,
        ...(verifierAlertWebhookToken ? { authorization: `Bearer ${verifierAlertWebhookToken}` } : {}),
      },
      method: "POST",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`webhook returned HTTP ${response.status}`);
    verifierAlertState.lastSentByFingerprint.set(fingerprint, now);
    verifierMetrics.alerts.sent += 1;
    const delivery = {
      schema: "agentcart.verifier_alert_delivery.v1",
      state: "sent",
      created_at: new Date().toISOString(),
      fingerprint,
      sink: "webhook",
      url: verifierAlertWebhookUrl,
      alert,
    };
    verifierMetrics.alerts.last_delivery = delivery;
    return delivery;
  } catch (error) {
    verifierMetrics.alerts.failed += 1;
    const delivery = {
      schema: "agentcart.verifier_alert_delivery.v1",
      state: "failed",
      created_at: new Date().toISOString(),
      fingerprint,
      sink: "webhook",
      url: verifierAlertWebhookUrl,
      error: error instanceof Error ? error.message : String(error),
      alert,
    };
    verifierMetrics.alerts.last_delivery = delivery;
    return delivery;
  } finally {
    clearTimeout(timeout);
  }
}

async function recordVerifierResponse(request, url, payload, response, startedNs, correlationId) {
  if (url.pathname === "/metrics" || url.pathname === "/metrics.json") return;
  const body = await responseJsonOrNull(response);
  const latencyMs = latencyMsSince(startedNs);
  const operation = operationFromRequest(url, payload);
  const rail = railFromPayloadOrBody(payload, body);
  const outcome = outcomeFromResponse(response, body);
  const reason = outcome === "ok" ? "" : rejectionReason(response, body);

  verifierMetrics.requests_total += 1;
  verifierMetrics.responses_total += 1;
  verifierMetrics.outcomes[outcome] += 1;
  recordLatency(verifierMetrics.latency_ms, latencyMs);
  updateBucket(verifierMetrics.by_operation, operation, outcome, latencyMs);
  if (rail !== "none") updateBucket(verifierMetrics.by_rail, rail, outcome, latencyMs);
  incrementCounter(verifierMetrics.by_status, String(response.status));
  if (reason) incrementCounter(verifierMetrics.rejections, reason);
  if (body?.provider_error_class) incrementCounter(verifierMetrics.provider_errors, body.provider_error_class);
  if (body?.real_settlement_verified === true) verifierMetrics.settlement.real_settlement_verified += 1;
  if (body?.real_settlement_verified === false && operation === "payment") {
    verifierMetrics.settlement.demo_settlement_verified += 1;
  }
  if (body?.real_refund_verified === true) verifierMetrics.settlement.real_refund_verified += 1;
  if (body?.idempotent_replay === true) verifierMetrics.settlement.idempotent_replay += 1;

  const event = {
    event: "verifier_request",
    correlation_id: correlationId,
    method: request.method,
    path: url.pathname,
    operation,
    rail,
    status: response.status,
    outcome,
    ok: body?.ok === true,
    latency_ms: latencyMs,
    rejection_reason: reason || undefined,
    provider_error_class: body?.provider_error_class || undefined,
    retryable: body?.retryable === undefined ? undefined : Boolean(body.retryable),
    quote_hash: quoteHashFromPayloadOrBody(payload, body) || undefined,
    payment_contract_hash: paymentContractHashFromPayloadOrBody(payload, body) || undefined,
    idempotent_replay: body?.idempotent_replay === true || undefined,
    real_settlement_verified:
      body?.real_settlement_verified === undefined ? undefined : Boolean(body.real_settlement_verified),
    real_refund_verified: body?.real_refund_verified === undefined ? undefined : Boolean(body.real_refund_verified),
  };
  verifierMetrics.last_event = event;
  structuredLog(event);
  if (outcome !== "ok") {
    const delivery = await deliverVerifierAlert(verifierAlertForEvent(event));
    structuredLog({
      event: "verifier_alert_delivery",
      correlation_id: correlationId,
      state: delivery.state,
      reason: delivery.reason || undefined,
      sink: delivery.sink || undefined,
      alert_code: delivery.alert?.code || undefined,
      alert_severity: delivery.alert?.severity || undefined,
    });
  }
}

function missingConfig() {
  const missing = [];
  if (!stripeSecretKey) missing.push("STRIPE_SANDBOX_SECRET_KEY");
  if (!stripeProfileId) missing.push("STRIPE_PROFILE_ID");
  if (!mppSecretKey) missing.push("MPP_SECRET_KEY");
  if (!verifierToken) missing.push("AGENTCART_PAYMENT_VERIFIER_TOKEN");
  if (requireDurableReplayStore && !replayStorePath) {
    missing.push("AGENTCART_VERIFIER_REPLAY_STORE_PATH");
  }
  if (requireReplayJournal && !replayJournalPath) {
    missing.push("AGENTCART_VERIFIER_REPLAY_JOURNAL_PATH");
  }
  return missing;
}

function readiness() {
  const missing = missingConfig();
  const replay = replayStoreDiagnostics();
  const journal = replayJournalDiagnostics();
  const ok = missing.length === 0 && !replay.error && !journal.error;
  return {
    ok,
    service: "agentcart-stripe-mpp-verifier",
    mode: "sandbox",
    endpoints: {
      health: `http://${host}:${port}/health`,
      metrics: `http://${host}:${port}/metrics`,
      challenge: `http://${host}:${port}/stripe-mpp/challenge`,
      paid: `http://${host}:${port}/stripe-mpp/paid`,
      verify: `http://${host}:${port}/agentcart/verify`,
    },
    stripe_profile_id: stripeProfileId || null,
    default_currency: defaultCurrency,
    payment_method_types: paymentMethodTypes,
    token_required: verifierToken !== "",
    replay_store: replay.label,
    replay_store_driver: replayStoreDriver,
    replay_store_kind: replay.kind,
    replay_store_required: requireDurableReplayStore,
    replay_store_durable: replay.durable,
    replay_store_locking: replay.locking,
    replay_store_writable: replay.writable,
    replay_store_counts: replay.counts,
    replay_store_error: replay.error,
    replay_journal: journal.label,
    replay_journal_configured: journal.configured,
    replay_journal_required: journal.required,
    replay_journal_writable: journal.writable,
    replay_journal_entry_count: journal.entry_count,
    replay_journal_error: journal.error,
    alerts: {
      webhook_configured: Boolean(verifierAlertWebhookUrl),
      min_severity: verifierAlertMinSeverity,
      throttle_seconds: verifierAlertThrottleSeconds,
    },
    tempo_settlement: tempoSettlementReadiness(),
    tempo_refunds: tempoRefundReadiness(),
    missing,
  };
}

function requireReady() {
  const status = readiness();
  if (!status.ok) {
    return jsonResponse(
      {
        ok: false,
        error: "Stripe MPP verifier is not configured.",
        missing: status.missing,
        replay_store_required: status.replay_store_required,
        replay_store_durable: status.replay_store_durable,
        replay_store_writable: status.replay_store_writable,
        replay_store_error: status.replay_store_error,
        replay_journal_required: status.replay_journal_required,
        replay_journal_writable: status.replay_journal_writable,
        replay_journal_error: status.replay_journal_error,
      },
      503,
    );
  }
  return null;
}

async function parseJsonRequest(request) {
  const text = await request.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw Object.assign(new Error("Request body must be valid JSON."), { status: 400 });
  }
}

function bearerToken(request) {
  const header = request.headers.get("authorization") || "";
  const match = header.match(/^Bearer\s+(.+)$/i);
  return match?.[1]?.trim() || "";
}

function requireVerifierToken(request) {
  if (!verifierToken) return null;
  const supplied = bearerToken(request);
  const expected = Buffer.from(verifierToken);
  const actual = Buffer.from(supplied);
  if (actual.length !== expected.length || !crypto.timingSafeEqual(actual, expected)) {
    return jsonResponse({ ok: false, error: "Unauthorized verifier request." }, 401);
  }
  return null;
}

function normalizeRail(value) {
  const rail = String(value || "").trim().toLowerCase().replaceAll("_", "-");
  if (rail === "stripe" || rail === "stripe-card" || rail === "stripe-card-mpp") return "stripe-card-mpp";
  if (rail === "tempo" || rail === "tempo-mpp" || rail === "mpp") return "tempo-mpp";
  return rail || "stripe-card-mpp";
}

function blankReplayStore() {
  return {
    schema: "agentcart.verifierReplay.v1",
    payments: {},
    refund_requests: {},
    refunds: {},
  };
}

function replayStoreLabel() {
  return replayStorePath || "memory";
}

function replayStoreLockPath() {
  return replayStorePath ? `${replayStorePath}.lock` : "";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizeReplayStore(raw) {
  const store = raw && typeof raw === "object" ? raw : {};
  return {
    schema: "agentcart.verifierReplay.v1",
    payments: store.payments && typeof store.payments === "object" ? store.payments : {},
    refund_requests:
      store.refund_requests && typeof store.refund_requests === "object" ? store.refund_requests : {},
    refunds: store.refunds && typeof store.refunds === "object" ? store.refunds : {},
  };
}

function normalizeReplayMetadata(value) {
  if (Array.isArray(value)) return value.map((entry) => normalizeReplayMetadata(entry));
  if (!value || typeof value !== "object") return value;
  const normalized = {};
  for (const key of Object.keys(value).sort()) {
    const entry = value[key];
    if (entry !== undefined) normalized[key] = normalizeReplayMetadata(entry);
  }
  return normalized;
}

function replayComparableMetadata(entry) {
  if (!entry || typeof entry !== "object") return {};
  const metadata = { ...entry };
  delete metadata.first_seen_at;
  delete metadata.last_seen_at;
  delete metadata.replay_count;
  delete metadata.request_hash;
  return normalizeReplayMetadata(metadata);
}

function replayRequestHash(bucket, reference, metadata = {}) {
  return crypto
    .createHash("sha256")
    .update(
      JSON.stringify({
        bucket,
        reference: String(reference || "").trim(),
        metadata: normalizeReplayMetadata(metadata),
      }),
    )
    .digest("hex");
}

function loadReplayStore() {
  if (!replayStorePath) return memoryReplayStore;
  if (!fs.existsSync(replayStorePath)) return blankReplayStore();
  try {
    return normalizeReplayStore(JSON.parse(fs.readFileSync(replayStorePath, "utf8")));
  } catch (error) {
    throw Object.assign(new Error(`Could not read verifier replay store: ${error.message}`), { status: 500 });
  }
}

function saveReplayStore(store) {
  if (!replayStorePath) return;
  const directory = path.dirname(replayStorePath);
  fs.mkdirSync(directory, { recursive: true });
  const tempPath = `${replayStorePath}.${process.pid}.${Date.now()}.tmp`;
  fs.writeFileSync(tempPath, `${JSON.stringify(store, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(tempPath, replayStorePath);
}

function replayStoreWriteProbe() {
  if (replayStoreDriver === "sqlite") {
    return sqliteReplayStoreWriteProbe(replayStorePath, { busyTimeoutMs: replayStoreLockTimeoutMs });
  }
  if (!replayStorePath) return { ok: true, durable: false };
  const directory = path.dirname(replayStorePath);
  try {
    fs.mkdirSync(directory, { recursive: true });
    if (fs.existsSync(replayStorePath)) {
      fs.accessSync(replayStorePath, fs.constants.R_OK | fs.constants.W_OK);
    }
    const probePath = path.join(directory, `.agentcart-replay-probe-${process.pid}-${Date.now()}`);
    fs.writeFileSync(probePath, "ok\n", { mode: 0o600 });
    fs.unlinkSync(probePath);
    return { ok: true, durable: true };
  } catch (error) {
    return {
      ok: false,
      durable: true,
      error: `Could not write verifier replay store: ${error.message}`,
    };
  }
}

function replayJournalWriteProbe() {
  if (!replayJournalPath) return { ok: true, configured: false };
  const directory = path.dirname(replayJournalPath);
  try {
    fs.mkdirSync(directory, { recursive: true });
    if (fs.existsSync(replayJournalPath)) {
      fs.accessSync(replayJournalPath, fs.constants.R_OK | fs.constants.W_OK);
    }
    const probePath = path.join(directory, `.agentcart-replay-journal-probe-${process.pid}-${Date.now()}`);
    fs.writeFileSync(probePath, "ok\n", { mode: 0o600 });
    fs.unlinkSync(probePath);
    return { ok: true, configured: true };
  } catch (error) {
    return {
      ok: false,
      configured: true,
      error: `Could not write verifier replay journal: ${error.message}`,
    };
  }
}

function replayJournalEntryCount() {
  if (!replayJournalPath || !fs.existsSync(replayJournalPath)) return 0;
  const raw = fs.readFileSync(replayJournalPath, "utf8");
  if (!raw.trim()) return 0;
  return raw.split("\n").filter((line) => line.trim()).length;
}

function replayJournalDiagnostics() {
  const diagnostics = {
    label: replayJournalPath || "disabled",
    configured: Boolean(replayJournalPath),
    required: requireReplayJournal,
    writable: !replayJournalPath ? !requireReplayJournal : false,
    entry_count: null,
    error: null,
  };
  try {
    const writeProbe = replayJournalWriteProbe();
    diagnostics.writable = Boolean(writeProbe.ok);
    if (!writeProbe.ok) diagnostics.error = writeProbe.error;
    diagnostics.entry_count = replayJournalEntryCount();
  } catch (error) {
    diagnostics.error = error.message;
  }
  return diagnostics;
}

function replayReferenceHash(reference) {
  return crypto.createHash("sha256").update(String(reference || "").trim()).digest("hex");
}

function replayJournalMetadata(metadata) {
  const safe = {};
  for (const key of [
    "provider",
    "rail",
    "amount_cents",
    "currency",
    "quote_hash",
    "payment_contract_hash",
    "stripe_profile_id",
    "network",
    "recipient",
  ]) {
    if (metadata?.[key] !== undefined) safe[key] = metadata[key];
  }
  const referenceHashes = {
    original_transaction_reference: "original_transaction_reference_hash",
    requested_reference: "requested_reference_hash",
    refund_reference: "refund_reference_hash",
  };
  for (const [key, hashKey] of Object.entries(referenceHashes)) {
    if (metadata?.[key] !== undefined) safe[hashKey] = replayReferenceHash(metadata[key]);
  }
  return normalizeReplayMetadata(safe);
}

function appendReplayJournalEvent(event) {
  if (!replayJournalPath) return { ok: true, configured: false };
  const entry = {
    schema: "agentcart.verifierReplayJournal.v1",
    at: new Date().toISOString(),
    service: "agentcart-stripe-mpp-verifier",
    ...event,
  };
  try {
    fs.mkdirSync(path.dirname(replayJournalPath), { recursive: true });
    fs.appendFileSync(replayJournalPath, `${JSON.stringify(entry)}\n`, { mode: 0o600 });
    verifierMetrics.replay_journal.appended += 1;
    verifierMetrics.replay_journal.last_event = entry;
    verifierMetrics.replay_journal.last_error = null;
    return { ok: true, configured: true, entry };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    verifierMetrics.replay_journal.failed += 1;
    verifierMetrics.replay_journal.last_error = message;
    return { ok: false, configured: true, error: message, entry };
  }
}

function recordReplayJournalClaim({ bucket, reference, metadata, requestHash, result }) {
  const existing = result?.existing && typeof result.existing === "object" ? result.existing : {};
  const event = {
    event: result?.ok
      ? result.idempotentReplay
        ? "idempotent_replay"
        : "claim_accepted"
      : "replay_conflict",
    bucket,
    reference_hash: replayReferenceHash(reference),
    request_hash: requestHash,
    existing_request_hash: result?.existingRequestHash || existing.request_hash || undefined,
    first_seen_at: existing.first_seen_at || undefined,
    replay_count: existing.replay_count === undefined ? undefined : Number(existing.replay_count),
    metadata: replayJournalMetadata(metadata),
  };
  return appendReplayJournalEvent(event);
}

async function acquireReplayStoreLock() {
  if (!replayStorePath) {
    return () => {};
  }
  const lockPath = replayStoreLockPath();
  const started = Date.now();
  fs.mkdirSync(path.dirname(replayStorePath), { recursive: true });
  while (true) {
    try {
      const fd = fs.openSync(lockPath, "wx", 0o600);
      fs.writeFileSync(fd, JSON.stringify({ pid: process.pid, created_at: new Date().toISOString() }));
      fs.closeSync(fd);
      return () => {
        try {
          fs.unlinkSync(lockPath);
        } catch {
          // Ignore stale cleanup races; the next claimant can recover.
        }
      };
    } catch (error) {
      if (error?.code !== "EEXIST") {
        throw Object.assign(new Error(`Could not acquire verifier replay lock: ${error.message}`), { status: 500 });
      }
      try {
        const stat = fs.statSync(lockPath);
        if (Date.now() - stat.mtimeMs > replayStoreLockTimeoutMs) {
          fs.unlinkSync(lockPath);
          continue;
        }
      } catch (statError) {
        if (statError?.code !== "ENOENT") {
          throw Object.assign(new Error(`Could not inspect verifier replay lock: ${statError.message}`), {
            status: 500,
          });
        }
      }
      if (Date.now() - started > replayStoreLockTimeoutMs) {
        throw Object.assign(new Error("Timed out acquiring verifier replay lock."), { status: 503 });
      }
      await sleep(25 + Math.floor(Math.random() * 50));
    }
  }
}

async function withReplayStoreMutation(mutator) {
  const release = await acquireReplayStoreLock();
  try {
    const store = loadReplayStore();
    const result = mutator(store);
    if (result?.save !== false) {
      saveReplayStore(store);
    }
    return result;
  } finally {
    release();
  }
}

function replayStoreDiagnostics() {
  if (replayStoreDriver === "sqlite") {
    return sqliteReplayStoreDiagnostics(replayStorePath, { busyTimeoutMs: replayStoreLockTimeoutMs });
  }
  const diagnostics = {
    label: replayStoreLabel(),
    kind: replayStorePath ? "file" : "memory",
    durable: Boolean(replayStorePath),
    locking: replayStorePath ? "lockfile" : "process",
    counts: null,
    error: null,
    writable: !replayStorePath,
  };
  try {
    const store = loadReplayStore();
    const writeProbe = replayStoreWriteProbe();
    diagnostics.writable = Boolean(writeProbe.ok);
    if (!writeProbe.ok) diagnostics.error = writeProbe.error;
    diagnostics.counts = {
      payments: Object.keys(store.payments || {}).length,
      refund_requests: Object.keys(store.refund_requests || {}).length,
      refunds: Object.keys(store.refunds || {}).length,
    };
  } catch (error) {
    diagnostics.error = error.message;
  }
  return diagnostics;
}

async function claimReplayReference(bucket, reference, metadata = {}) {
  const key = String(reference || "").trim();
  if (!key) {
    return { ok: false, response: jsonResponse({ ok: false, error: "replay reference is required." }, 400) };
  }
  const normalizedMetadata = normalizeReplayMetadata(metadata);
  const requestHash = replayRequestHash(bucket, key, normalizedMetadata);
  const result =
    replayStoreDriver === "sqlite"
      ? sqliteReplayClaimResult(bucket, key, normalizedMetadata, requestHash)
      : await withReplayStoreMutation((store) => {
          if (!store[bucket] || typeof store[bucket] !== "object") store[bucket] = {};
          const existing = store[bucket][key];
          if (existing) {
            const existingHash =
              typeof existing.request_hash === "string" && existing.request_hash
                ? existing.request_hash
                : replayRequestHash(bucket, key, replayComparableMetadata(existing));
            if (existingHash === requestHash) {
              existing.request_hash = existingHash;
              existing.last_seen_at = new Date().toISOString();
              existing.replay_count = Number(existing.replay_count || 0) + 1;
              return {
                ok: true,
                idempotentReplay: true,
                existing,
                requestHash,
              };
            }
            return {
              ok: false,
              save: false,
              existingRequestHash: existingHash,
              response: replayConflictResponse(bucket, key, existing, existingHash, requestHash),
            };
          }
          store[bucket][key] = {
            ...normalizedMetadata,
            first_seen_at: new Date().toISOString(),
            request_hash: requestHash,
            replay_count: 0,
          };
          return { ok: true, requestHash };
        });
  const journal = recordReplayJournalClaim({ bucket, reference: key, metadata: normalizedMetadata, requestHash, result });
  if (!journal.ok && requireReplayJournal) {
    return {
      ok: false,
      response: jsonResponse(
        {
          ok: false,
          error: "Verifier replay journal write failed.",
          replay_journal_error: journal.error,
        },
        503,
      ),
    };
  }
  return result;
}

function replayConflictResponse(bucket, reference, existing, existingHash, requestHash) {
  return jsonResponse(
    {
      ok: false,
      error: `${bucket.slice(0, -1).replace("_", " ")} reference has already been used for different payment fields.`,
      replay_conflict: true,
      replay_bucket: bucket,
      replay_reference: reference,
      first_seen_at: existing.first_seen_at || null,
      existing_request_hash: existingHash,
      request_hash: requestHash,
    },
    409,
  );
}

function sqliteReplayClaimResult(bucket, reference, metadata, requestHash) {
  const claim = claimSQLiteReplayReference({
    dbPath: replayStorePath,
    bucket,
    reference,
    metadata,
    requestHash,
    busyTimeoutMs: replayStoreLockTimeoutMs,
  });
  if (claim.ok) {
    return {
      ok: true,
      idempotentReplay: claim.idempotentReplay || undefined,
      existing: {
        ...(claim.existing?.metadata || {}),
        first_seen_at: claim.existing?.first_seen_at,
        request_hash: claim.existing?.request_hash,
        replay_count: claim.existing?.replay_count,
      },
      requestHash,
    };
  }
  const existing = {
    ...(claim.existing?.metadata || {}),
    first_seen_at: claim.existing?.first_seen_at,
    request_hash: claim.existing?.request_hash,
    replay_count: claim.existing?.replay_count,
  };
  return {
    ok: false,
    existing,
    existingRequestHash: claim.existingRequestHash,
    response: replayConflictResponse(bucket, reference, existing, claim.existingRequestHash, requestHash),
  };
}

function expectedFromPayload(payload) {
  const expected = payload.expected && typeof payload.expected === "object" ? payload.expected : {};
  const quote = payload.quote && typeof payload.quote === "object" ? payload.quote : {};
  const receipt =
    payload.payment_receipt && typeof payload.payment_receipt === "object" ? payload.payment_receipt : {};
  const quoteHash = String(payload.quote_hash || expected.quote_hash || quote.quote_hash || receipt.quote_hash || "");
  const amountCents = Number(expected.amount_cents ?? quote.total_cents ?? receipt.amount_cents);
  const currency = String(expected.currency || quote.currency || receipt.currency || defaultCurrency).toLowerCase();
  const merchantId = String(expected.merchant_id || quote.merchant_id || receipt.merchant_id || "");
  const rail = normalizeRail(expected.rail || receipt.rail || receipt.method || receipt.provider || payload.rail);
  const profileId = String(expected.stripe_profile_id || stripeProfileId);
  const tempoNetwork = String(expected.tempo_network || "").trim();
  const tempoRecipient = String(expected.tempo_recipient || "").trim().toLowerCase();
  const requirements =
    quote.payment_requirements && typeof quote.payment_requirements === "object" ? quote.payment_requirements : {};
  const verification =
    requirements.verification && typeof requirements.verification === "object" ? requirements.verification : {};
  const suppliedContractHashes = [
    payload.payment_contract_hash,
    expected.payment_contract_hash,
    requirements.payment_contract_hash,
    verification.payment_contract_hash,
    receipt.payment_contract_hash,
    receipt.contract_hash,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  const authoritativeContractHashes = [
    payload.payment_contract_hash,
    expected.payment_contract_hash,
    requirements.payment_contract_hash,
    verification.payment_contract_hash,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  const uniqueContractHashes = new Set(suppliedContractHashes);
  if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
    throw Object.assign(new Error("expected.amount_cents must be a positive integer."), { status: 400 });
  }
  if (!currency) {
    throw Object.assign(new Error("expected.currency is required."), { status: 400 });
  }
  if (!quoteHash) {
    throw Object.assign(new Error("quote_hash is required."), { status: 400 });
  }
  if (!["stripe-card-mpp", "tempo-mpp"].includes(rail)) {
    throw Object.assign(new Error(`Unsupported rail for this verifier: ${rail}`), { status: 400 });
  }
  if (rail === "stripe-card-mpp" && profileId !== stripeProfileId) {
    throw Object.assign(new Error("Stripe profile id does not match verifier configuration."), { status: 400 });
  }
  if (!authoritativeContractHashes.length) {
    throw Object.assign(new Error("payment_contract_hash is required from the request, expected block, or quote."), {
      status: 400,
    });
  }
  if (suppliedContractHashes.some((value) => !/^[a-f0-9]{64}$/i.test(value))) {
    throw Object.assign(new Error("payment_contract_hash must be a SHA-256 hex digest."), { status: 400 });
  }
  if (uniqueContractHashes.size > 1) {
    throw Object.assign(new Error("payment_contract_hash values do not match."), { status: 400 });
  }
  return {
    amountCents,
    currency,
    merchantId,
    paymentContractHash: suppliedContractHashes[0] || "",
    profileId,
    quoteHash,
    rail,
    tempoNetwork,
    tempoRecipient,
  };
}

function assertReceiptMatchesExpected(receipt, expected) {
  if (!receipt || typeof receipt !== "object") return;
  const amount = receipt.amount_cents;
  if (amount !== undefined && Number(amount) !== expected.amountCents) {
    throw Object.assign(new Error("payment_receipt.amount_cents does not match expected.amount_cents."), { status: 400 });
  }
  const currency = String(receipt.currency || "").trim();
  if (currency && currency.toUpperCase() !== expected.currency.toUpperCase()) {
    throw Object.assign(new Error("payment_receipt.currency does not match expected.currency."), { status: 400 });
  }
  const quoteHash = String(receipt.quote_hash || "").trim();
  if (quoteHash && quoteHash !== expected.quoteHash) {
    throw Object.assign(new Error("payment_receipt.quote_hash does not match expected quote_hash."), { status: 400 });
  }
  const receiptRail = normalizeRail(receipt.rail || receipt.method || receipt.provider || "");
  if (receiptRail && receiptRail !== expected.rail) {
    throw Object.assign(new Error("payment_receipt rail does not match expected.rail."), { status: 400 });
  }
  const receiptContractHash = String(receipt.payment_contract_hash || receipt.contract_hash || "").trim();
  if (expected.paymentContractHash && !receiptContractHash) {
    throw Object.assign(new Error("payment_receipt.payment_contract_hash is required."), { status: 400 });
  }
  if (receiptContractHash && expected.paymentContractHash && receiptContractHash !== expected.paymentContractHash) {
    throw Object.assign(new Error("payment_receipt.payment_contract_hash does not match expected payment_contract_hash."), {
      status: 400,
    });
  }
  const receiptProfile = String(receipt.stripe_profile_id || "").trim();
  if (expected.rail === "stripe-card-mpp" && receiptProfile && receiptProfile !== expected.profileId) {
    throw Object.assign(new Error("payment_receipt.stripe_profile_id does not match expected Stripe profile."), {
      status: 400,
    });
  }
}

function decimalAmountToCents(value) {
  const raw = String(value ?? "").trim();
  const match = raw.match(/^(\d+)(?:\.(\d{1,6}))?$/);
  if (!match) return NaN;
  const whole = Number(match[1]);
  const fraction = (match[2] || "").padEnd(2, "0").slice(0, 2);
  return whole * 100 + Number(fraction);
}

function centsToDecimal(cents) {
  return `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, "0")}`;
}

function tempoProofFromReceipt(receipt) {
  if (!receipt || typeof receipt !== "object") return {};
  const proof =
    receipt.external_value_proof && typeof receipt.external_value_proof === "object"
      ? receipt.external_value_proof
      : receipt;
  const body = proof.body && typeof proof.body === "object" ? proof.body : {};
  const proofReceipt =
    proof.payment_receipt && typeof proof.payment_receipt === "object" ? proof.payment_receipt : {};
  return { proof, body, proofReceipt };
}

function normalizeEvmAddress(value) {
  const address = String(value || "").trim();
  return /^0x[a-fA-F0-9]{40}$/.test(address) ? address.toLowerCase() : "";
}

function normalizePrivateKey(value) {
  const key = String(value || "").trim();
  return /^0x[a-fA-F0-9]{64}$/.test(key) ? key : "";
}

function addressFromPayerSource(value) {
  const source = String(value || "").trim();
  const match = /^did:pkh:eip155:(0|[1-9]\d*):(0x[a-fA-F0-9]{40})$/.exec(source);
  return match ? match[2].toLowerCase() : "";
}

function tempoPayerFromProof(proof, body, proofReceipt) {
  const payerSource = String(
    proof.payer_source ||
      body.payer_source ||
      proofReceipt.payer_source ||
      proof.payment_source ||
      body.payment_source ||
      "",
  ).trim();
  const payerAddress =
    normalizeEvmAddress(proof.payer_address) ||
    normalizeEvmAddress(body.payer_address) ||
    normalizeEvmAddress(proofReceipt.payer_address) ||
    normalizeEvmAddress(proof.source_address) ||
    normalizeEvmAddress(body.source_address) ||
    addressFromPayerSource(payerSource);
  return {
    payerAddress,
    payerSource,
  };
}

function tempoNetworkName(value) {
  const network = String(value || "").trim().toLowerCase();
  if (["mainnet", "tempo-mainnet", String(tempoMainnet.id)].includes(network)) return "mainnet";
  if (["testnet", "moderato", "tempo-testnet", String(tempoModerato.id)].includes(network)) return "testnet";
  return network;
}

function tempoChainForNetwork(value) {
  const network = tempoNetworkName(value);
  if (network === "mainnet") return tempoMainnet;
  if (network === "testnet") return tempoModerato;
  throw Object.assign(new Error(`Unsupported Tempo network: ${value || "missing"}`), { status: 400 });
}

function tempoRefundDefaults(network) {
  return tempoTokenDefaults[tempoNetworkName(network)] || tempoTokenDefaults.testnet;
}

function tempoSettlementDefaults(network) {
  return tempoTokenDefaults[tempoNetworkName(network)] || tempoTokenDefaults.testnet;
}

function normalizeTransactionHash(value) {
  const hash = String(value || "").trim();
  return /^0x[a-fA-F0-9]{64}$/.test(hash) ? hash.toLowerCase() : "";
}

function addressFromTopic(topic) {
  const value = String(topic || "").trim();
  if (!/^0x[a-fA-F0-9]{64}$/.test(value)) return "";
  return normalizeEvmAddress(`0x${value.slice(-40)}`);
}

function uint256FromHex(value) {
  const hex = String(value || "").trim();
  if (!/^0x[a-fA-F0-9]+$/.test(hex)) return null;
  return BigInt(hex);
}

function tempoRefundWalletAddress() {
  const privateKey = normalizePrivateKey(tempoRefundPrivateKey);
  if (!privateKey) return "";
  try {
    return privateKeyToAccount(privateKey).address.toLowerCase();
  } catch {
    return "";
  }
}

function tempoRefundReadiness() {
  const mode = ["disabled", "live"].includes(tempoRefundMode) ? tempoRefundMode : "invalid";
  const walletAddress = tempoRefundWalletAddress();
  const tokenAddress = normalizeEvmAddress(tempoRefundTokenAddress);
  const configured =
    mode === "live" &&
    Boolean(walletAddress) &&
    Number.isSafeInteger(tempoRefundDecimals) &&
    tempoRefundDecimals >= 0 &&
    tempoRefundDecimals <= 18 &&
    (!tempoRefundTokenAddress || Boolean(tokenAddress));
  return {
    mode,
    configured,
    wallet_configured: Boolean(walletAddress),
    wallet_address: walletAddress || null,
    token_address_override: tokenAddress || null,
    asset_override: tempoRefundAsset || null,
    decimals: tempoRefundDecimals,
    confirmations: tempoRefundConfirmations,
    rpc_url_configured: Boolean(tempoRefundRpcUrl),
  };
}

function tempoSettlementReadiness() {
  const mode = ["disabled", "verify"].includes(tempoSettlementMode) ? tempoSettlementMode : "invalid";
  const tokenAddress = normalizeEvmAddress(tempoSettlementTokenAddress);
  const configured =
    mode === "verify" &&
    Number.isSafeInteger(tempoSettlementDecimals) &&
    tempoSettlementDecimals >= 0 &&
    tempoSettlementDecimals <= 18 &&
    (!tempoSettlementTokenAddress || Boolean(tokenAddress));
  return {
    mode,
    configured,
    token_address_override: tokenAddress || null,
    asset_override: tempoSettlementAsset || null,
    decimals: tempoSettlementDecimals,
    confirmations: tempoSettlementConfirmations,
    rpc_url_configured: Boolean(tempoSettlementRpcUrl),
  };
}

function requireTempoSettlementVerifyConfig(network, proofTokenAddress = "") {
  if (tempoSettlementMode !== "verify") {
    throw Object.assign(new Error("Tempo settlement verification is not enabled."), {
      status: 400,
      code: "tempo_settlement_verifier_disabled",
    });
  }
  if (!Number.isSafeInteger(tempoSettlementDecimals) || tempoSettlementDecimals < 0 || tempoSettlementDecimals > 18) {
    throw Object.assign(new Error("Tempo settlement token decimals must be between 0 and 18."), {
      status: 503,
      code: "tempo_settlement_decimals_invalid",
    });
  }
  const chain = tempoChainForNetwork(network);
  const defaults = tempoSettlementDefaults(network);
  const tokenAddress = normalizeEvmAddress(tempoSettlementTokenAddress || defaults.tokenAddress);
  if (!tokenAddress) {
    throw Object.assign(new Error("Tempo settlement token address is missing or invalid."), {
      status: 503,
      code: "tempo_settlement_token_invalid",
    });
  }
  if (proofTokenAddress && proofTokenAddress !== tokenAddress) {
    throw Object.assign(new Error("Tempo proof token address does not match verifier configuration."), {
      status: 400,
      code: "tempo_settlement_token_mismatch",
    });
  }
  return {
    asset: tempoSettlementAsset || defaults.asset,
    chain,
    confirmations: tempoSettlementConfirmations,
    decimals: tempoSettlementDecimals,
    network: tempoNetworkName(network),
    rpcUrl: tempoSettlementRpcUrl || chain.rpcUrls.default.http[0],
    tokenAddress,
  };
}

function tempoSettlementErrorResponse(error) {
  const status = Number(error.status || 400);
  return jsonResponse(
    {
      ok: false,
      error: error.message || "Tempo settlement verification failed.",
      provider: "tempo",
      provider_error_class: error.code || "tempo_settlement_error",
      provider_message: error.providerMessage || null,
      retryable: Boolean(error.retryable || status >= 500),
    },
    status,
  );
}

async function verifyTempoSettlementTransfer({
  amountCents,
  network,
  payerAddress,
  proofTokenAddress,
  recipient,
  transactionReference,
}) {
  const resolvedNetwork = tempoNetworkName(network || "testnet") || "testnet";
  const defaults = tempoSettlementDefaults(resolvedNetwork);
  if (tempoSettlementMode !== "verify") {
    return {
      verified: false,
      mode: "disabled",
      asset: tempoSettlementAsset || defaults.asset,
      network: resolvedNetwork,
      tokenAddress: normalizeEvmAddress(tempoSettlementTokenAddress || defaults.tokenAddress),
    };
  }

  const hash = normalizeTransactionHash(transactionReference);
  if (!hash) {
    throw Object.assign(new Error("Tempo proof transaction reference must be an EVM transaction hash."), {
      status: 400,
      code: "tempo_settlement_reference_invalid",
    });
  }
  if (!recipient) {
    throw Object.assign(new Error("Tempo settlement recipient is required for on-chain verification."), {
      status: 400,
      code: "tempo_settlement_recipient_missing",
    });
  }
  if (!payerAddress) {
    throw Object.assign(new Error("Tempo settlement payer address is required for on-chain verification."), {
      status: 400,
      code: "tempo_settlement_payer_missing",
    });
  }

  const config = requireTempoSettlementVerifyConfig(resolvedNetwork, proofTokenAddress);
  const expectedAmount = parseUnits(centsToDecimal(amountCents), config.decimals);
  const publicClient = createPublicClient({ chain: config.chain, transport: viemHttp(config.rpcUrl) });
  let receipt;
  try {
    receipt = await publicClient.waitForTransactionReceipt({
      confirmations: config.confirmations,
      hash,
    });
  } catch (error) {
    throw Object.assign(new Error("Tempo settlement transaction lookup failed."), {
      status: 502,
      code: error?.name || "tempo_settlement_lookup_failed",
      providerMessage: error?.shortMessage || error?.message || null,
      retryable: true,
    });
  }
  if (receipt.status !== "success") {
    throw Object.assign(new Error("Tempo settlement transaction did not succeed."), {
      status: 400,
      code: "tempo_settlement_transaction_failed",
    });
  }

  const transferLog = receipt.logs.find((log) => {
    const from = addressFromTopic(log.topics?.[1]);
    const to = addressFromTopic(log.topics?.[2]);
    const amount = uint256FromHex(log.data);
    return (
      normalizeEvmAddress(log.address) === config.tokenAddress &&
      String(log.topics?.[0] || "").toLowerCase() === erc20TransferTopic &&
      from === payerAddress &&
      to === recipient &&
      amount === expectedAmount
    );
  });
  if (!transferLog) {
    throw Object.assign(new Error("Tempo settlement transaction does not contain the expected token transfer."), {
      status: 400,
      code: "tempo_settlement_transfer_missing",
    });
  }

  return {
    verified: true,
    mode: "onchain_erc20_transfer",
    asset: config.asset,
    amount: centsToDecimal(amountCents),
    blockHash: receipt.blockHash,
    blockNumber: receipt.blockNumber?.toString(),
    confirmations: config.confirmations,
    from: payerAddress,
    network: config.network,
    recipient,
    rawAmount: expectedAmount.toString(),
    tokenAddress: config.tokenAddress,
    transactionHash: hash,
  };
}

function requireTempoRefundLiveConfig(network) {
  if (tempoRefundMode !== "live") {
    throw Object.assign(new Error("Tempo refund adapter is not configured for live transfers."), {
      status: 400,
      code: "tempo_refund_adapter_missing",
    });
  }
  const privateKey = normalizePrivateKey(tempoRefundPrivateKey);
  if (!privateKey) {
    throw Object.assign(new Error("Tempo refund adapter private key is missing or invalid."), {
      status: 503,
      code: "tempo_refund_wallet_missing",
    });
  }
  if (!Number.isSafeInteger(tempoRefundDecimals) || tempoRefundDecimals < 0 || tempoRefundDecimals > 18) {
    throw Object.assign(new Error("Tempo refund token decimals must be between 0 and 18."), {
      status: 503,
      code: "tempo_refund_decimals_invalid",
    });
  }
  const chain = tempoChainForNetwork(network);
  const defaults = tempoRefundDefaults(network);
  const tokenAddress = normalizeEvmAddress(tempoRefundTokenAddress || defaults.tokenAddress);
  if (!tokenAddress) {
    throw Object.assign(new Error("Tempo refund token address is missing or invalid."), {
      status: 503,
      code: "tempo_refund_token_invalid",
    });
  }
  const account = privateKeyToAccount(privateKey);
  return {
    account,
    asset: tempoRefundAsset || defaults.asset,
    chain,
    network: tempoNetworkName(network),
    rpcUrl: tempoRefundRpcUrl || chain.rpcUrls.default.http[0],
    tokenAddress,
  };
}

function tempoRefundErrorResponse(error) {
  return jsonResponse(
    {
      ok: false,
      error: error.message || "Tempo refund failed.",
      provider: "tempo",
      provider_error_class: error.code || "tempo_refund_error",
      retryable: false,
    },
    Number(error.status || 400),
  );
}

function chargeOptions(expected) {
  return {
    amount: String(expected.amountCents),
    currency: expected.currency,
    decimals: 2,
    description: `AgentCart quote ${expected.quoteHash.slice(0, 12)}`,
    externalId: expected.quoteHash,
    metadata: {
      agentcart_quote_hash: expected.quoteHash,
      agentcart_payment_contract_hash: expected.paymentContractHash,
      agentcart_merchant_id: expected.merchantId,
      agentcart_rail: expected.rail,
    },
    networkId: expected.profileId,
    paymentMethodTypes,
  };
}

function createMppx(expected) {
  if (!stripeClient) throw Object.assign(new Error("Stripe client is not configured."), { status: 503 });
  return Mppx.create({
    methods: [
      mppStripe.charge({
        client: stripeClient,
        ...chargeOptions(expected),
      }),
    ],
    realm: "agentcart-stripe-mpp-verifier",
    secretKey: mppSecretKey,
  });
}

function providerErrorClass(error) {
  const type = String(error?.type || error?.name || "").toLowerCase();
  const code = String(error?.code || "").toLowerCase();
  const status = Number(error?.statusCode || error?.status || 0);
  if (code === "rate_limit" || type.includes("ratelimit")) return "provider_rate_limited";
  if (status >= 500) return "provider_unavailable";
  if (type.includes("authentication")) return "provider_authentication_failed";
  if (type.includes("permission")) return "provider_permission_denied";
  if (type.includes("invalidrequest")) return "provider_invalid_request";
  if (type.includes("card")) return "provider_card_error";
  if (type.includes("api")) return "provider_api_error";
  return "provider_error";
}

function providerErrorResponse(operation, error) {
  const classification = providerErrorClass(error);
  const status = Number(error?.statusCode || error?.status || 0);
  const retryable = classification === "provider_rate_limited" || classification === "provider_unavailable";
  return jsonResponse(
    {
      ok: false,
      error: `${operation} failed at payment provider.`,
      provider: "stripe",
      provider_error_class: classification,
      provider_status: status || null,
      provider_code: error?.code || null,
      request_id: error?.requestId || null,
      retryable,
    },
    retryable ? 502 : 400,
  );
}

function credentialFromReceipt(receipt) {
  if (!receipt || typeof receipt !== "object") return "";
  for (const key of [
    "authorization",
    "mpp_authorization",
    "payment_authorization",
    "credential",
    "mpp_credential",
  ]) {
    const value = receipt[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

async function challenge(payload) {
  const ready = requireReady();
  if (ready) return ready;
  const expected = expectedFromPayload(payload);
  const mppx = createMppx(expected);
  const challenge = await mppx.challenge.stripe.charge(chargeOptions(expected));
  return jsonResponse({
    ok: true,
    rail: "stripe-card-mpp",
    quote_hash: expected.quoteHash,
    payment_contract_hash: expected.paymentContractHash || undefined,
    amount_cents: expected.amountCents,
    currency: expected.currency.toUpperCase(),
    stripe_profile_id: stripeProfileId,
    challenge,
    www_authenticate: Challenge.serialize(challenge),
    authorization_hint: "Use link-cli to create a test SPT and retry with Authorization: Payment ...",
  });
}

async function verifyPayment(payload) {
  const ready = requireReady();
  if (ready) return ready;
  const expected = expectedFromPayload(payload);
  const receipt =
    payload.payment_receipt && typeof payload.payment_receipt === "object" ? payload.payment_receipt : {};
  assertReceiptMatchesExpected(receipt, expected);
  if (expected.rail === "tempo-mpp") {
    return verifyTempoFxPayment(receipt, expected);
  }
  const authorization = credentialFromReceipt(receipt);
  if (!authorization) {
    return jsonResponse(
      {
        ok: false,
        error: "payment_receipt.authorization or payment_receipt.credential is required.",
      },
      400,
    );
  }
  const mppx = createMppx(expected);
  let mppReceipt;
  try {
    mppReceipt = await mppx.verifyCredential(authorization, { request: chargeOptions(expected) });
  } catch (error) {
    return providerErrorResponse("Stripe/card MPP credential verification", error);
  }
  const transactionReference = String(mppReceipt.reference || "").trim();
  const replayClaim = await claimReplayReference("payments", transactionReference, {
    provider: "stripe",
    rail: "stripe-card-mpp",
    amount_cents: expected.amountCents,
    currency: expected.currency.toUpperCase(),
    quote_hash: expected.quoteHash,
    payment_contract_hash: expected.paymentContractHash || undefined,
    stripe_profile_id: stripeProfileId,
  });
  if (!replayClaim.ok) return replayClaim.response;
  return jsonResponse({
    ok: true,
    idempotent_replay: replayClaim.idempotentReplay || undefined,
    provider: "stripe",
    rail: "stripe-card-mpp",
    amount_cents: expected.amountCents,
    currency: expected.currency.toUpperCase(),
    quote_hash: expected.quoteHash,
    payment_contract_hash: expected.paymentContractHash || undefined,
    stripe_profile_id: stripeProfileId,
    transaction_reference: transactionReference,
    replay_reference: transactionReference,
    replay_request_hash: replayClaim.requestHash,
    mpp_receipt: mppReceipt,
    real_settlement_verified: true,
  });
}

async function verifyTempoFxPayment(receipt, expected) {
  const { proof, body, proofReceipt } = tempoProofFromReceipt(receipt);
  const provider = String(proof.provider || body.provider || receipt.provider || "").trim();
  const state = String(proof.state || body.state || "").trim();
  if (provider !== "tempo_mpp") {
    return jsonResponse({ ok: false, error: "Tempo proof is required for tempo-mpp verification." }, 400);
  }
  if (state && state !== "succeeded") {
    return jsonResponse({ ok: false, error: `Tempo proof state is ${state}.` }, 400);
  }
  const settlementAmount = body.amount ?? proof.amount ?? proof.receipt?.amount;
  const settlementAmountCents = decimalAmountToCents(settlementAmount);
  if (settlementAmountCents !== expected.amountCents) {
    return jsonResponse(
      {
        ok: false,
        error: "Tempo proof amount does not match the demo FX policy.",
        expected_settlement_amount: centsToDecimal(expected.amountCents),
        actual_settlement_amount: settlementAmount || null,
      },
      400,
    );
  }
  const network = tempoNetworkName(proof.network || body.network || proofReceipt.network || expected.tempoNetwork || "");
  if (expected.tempoNetwork && network && network !== tempoNetworkName(expected.tempoNetwork)) {
    return jsonResponse({ ok: false, error: "Tempo proof network does not match merchant configuration." }, 400);
  }
  const recipient = normalizeEvmAddress(body.recipient || proof.recipient || proofReceipt.recipient || receipt.recipient);
  if (expected.tempoRecipient && recipient && recipient !== expected.tempoRecipient) {
    return jsonResponse({ ok: false, error: "Tempo proof recipient does not match merchant configuration." }, 400);
  }
  const payer = tempoPayerFromProof(proof, body, proofReceipt);
  const transactionReference = String(
    proof.transaction_reference ||
      proof.reference ||
      proofReceipt.reference ||
      body.transaction_reference ||
      body.reference ||
      "",
  ).trim();
  if (!transactionReference) {
    return jsonResponse({ ok: false, error: "Tempo proof transaction reference is required." }, 400);
  }
  const proofTokenAddress = normalizeEvmAddress(
    proof.token_address ||
      body.token_address ||
      proofReceipt.token_address ||
      proof.token ||
      body.token ||
      proofReceipt.token ||
      proof.asset ||
      body.asset ||
      proofReceipt.asset ||
      receipt.asset,
  );
  let settlement;
  try {
    settlement = await verifyTempoSettlementTransfer({
      amountCents: expected.amountCents,
      network: expected.tempoNetwork || network,
      payerAddress: payer.payerAddress,
      proofTokenAddress,
      recipient: expected.tempoRecipient || recipient,
      transactionReference,
    });
  } catch (error) {
    return tempoSettlementErrorResponse(error);
  }
  const replayClaim = await claimReplayReference("payments", transactionReference, {
    provider: "tempo_mpp",
    rail: "tempo-mpp",
    amount_cents: expected.amountCents,
    currency: expected.currency.toUpperCase(),
    quote_hash: expected.quoteHash,
    payment_contract_hash: expected.paymentContractHash || undefined,
    network: expected.tempoNetwork || network,
    recipient: expected.tempoRecipient || recipient,
    payer_address: payer.payerAddress || undefined,
    asset: settlement.asset,
    token_address: settlement.tokenAddress || undefined,
    settlement_reference: settlement.transactionHash || undefined,
    real_settlement_verified: settlement.verified === true,
  });
  if (!replayClaim.ok) return replayClaim.response;
  const bodyOut = {
    ok: true,
    idempotent_replay: replayClaim.idempotentReplay || undefined,
    provider: "tempo_mpp",
    rail: "tempo-mpp",
    amount_cents: expected.amountCents,
    currency: expected.currency.toUpperCase(),
    quote_hash: expected.quoteHash,
    payment_contract_hash: expected.paymentContractHash || undefined,
    network: expected.tempoNetwork || network,
    recipient: expected.tempoRecipient || recipient,
    payer_address: payer.payerAddress || undefined,
    payer_source: payer.payerSource || undefined,
    asset: settlement.asset,
    token_address: settlement.tokenAddress || undefined,
    transaction_reference: transactionReference,
    settlement_reference: settlement.transactionHash || undefined,
    replay_reference: transactionReference,
    replay_request_hash: replayClaim.requestHash,
    real_settlement_verified: settlement.verified === true,
    settlement_verification:
      settlement.verified === true
        ? {
            mode: settlement.mode,
            asset: settlement.asset,
            token_address: settlement.tokenAddress,
            amount: settlement.amount,
            raw_amount: settlement.rawAmount,
            transaction_hash: settlement.transactionHash,
            block_hash: settlement.blockHash,
            block_number: settlement.blockNumber,
            confirmations: settlement.confirmations,
          }
        : undefined,
  };
  if (settlement.verified !== true) {
    bodyOut.fx = {
      mode: "demo_fixed_1_1",
      quote_currency: expected.currency.toUpperCase(),
      settlement_asset: settlement.asset || "pathUSD",
      settlement_amount: centsToDecimal(expected.amountCents),
      note: "Demo verifier: numeric 1:1 quote-to-pathUSD testnet binding, not production FX settlement.",
    };
  }
  return jsonResponse(bodyOut);
}

function refundExpectedFromPayload(payload, refund, expected) {
  const order = payload.order && typeof payload.order === "object" ? payload.order : {};
  const verification =
    order.payment_verification && typeof order.payment_verification === "object" ? order.payment_verification : {};
  const quoteHash = String(expected.quote_hash || payload.quote_hash || order.quote_hash || "");
  const originalReference = String(
    expected.original_transaction_reference ||
      payload.original_transaction_reference ||
      order.transaction_reference ||
      verification.transaction_reference ||
      "",
  ).trim();
  const network = String(expected.tempo_network || verification.tempo_network || verification.network || "testnet").trim();
  const originalRecipient = normalizeEvmAddress(
    expected.tempo_recipient || verification.recipient || verification.tempo_recipient || "",
  );
  const payerAddress = normalizeEvmAddress(verification.payer_address || "");
  const refundRecipient = normalizeEvmAddress(refund.recipient || refund.refund_recipient || expected.refund_recipient);
  const asset = String(refund.asset || expected.asset || verification.asset || tempoRefundDefaults(network).asset).trim();
  return {
    asset,
    network,
    originalRecipient,
    originalReference,
    payerAddress,
    quoteHash,
    refundRecipient,
    verification,
  };
}

async function verifyTempoRefund(payload, refund, expected, amountCents, currency, requestedReference) {
  const refundExpected = refundExpectedFromPayload(payload, refund, expected);
  if (currency !== "USD") {
    return jsonResponse({ ok: false, error: "Tempo refunds currently require USD-denominated amounts." }, 400);
  }
  if (!refundExpected.quoteHash) {
    return jsonResponse({ ok: false, error: "expected.quote_hash is required." }, 400);
  }
  if (!refundExpected.originalReference) {
    return jsonResponse({ ok: false, error: "original transaction reference is required." }, 400);
  }
  if (!refundExpected.refundRecipient) {
    return jsonResponse({ ok: false, error: "refund.recipient must be the original Tempo payer address." }, 400);
  }
  if (!refundExpected.payerAddress) {
    return jsonResponse({ ok: false, error: "Tempo refund requires the original payer address." }, 400);
  }
  if (refundExpected.payerAddress && refundExpected.refundRecipient !== refundExpected.payerAddress) {
    return jsonResponse({ ok: false, error: "Tempo refund recipient must match the original payer address." }, 400);
  }
  let config;
  try {
    config = requireTempoRefundLiveConfig(refundExpected.network);
  } catch (error) {
    return tempoRefundErrorResponse(error);
  }
  if (refundExpected.originalRecipient && config.account.address.toLowerCase() !== refundExpected.originalRecipient) {
    return jsonResponse(
      {
        ok: false,
        error: "Tempo refund wallet does not match the original payment recipient.",
        provider: "tempo",
        wallet_address: config.account.address.toLowerCase(),
        original_recipient: refundExpected.originalRecipient,
      },
      503,
    );
  }
  if (refundExpected.verification.real_settlement_verified !== true) {
    return jsonResponse(
      {
        ok: false,
        error: "Tempo refund requires real settlement evidence on the original payment.",
        provider: "tempo",
      },
      400,
    );
  }
  if (refundExpected.asset && refundExpected.asset !== config.asset) {
    return jsonResponse(
      {
        ok: false,
        error: "Tempo refund asset does not match verifier configuration.",
        provider: "tempo",
        expected_asset: config.asset,
        actual_asset: refundExpected.asset,
      },
      400,
    );
  }

  const amount = parseUnits(centsToDecimal(amountCents), tempoRefundDecimals);
  const publicClient = createPublicClient({ chain: config.chain, transport: viemHttp(config.rpcUrl) });
  let balance;
  try {
    balance = await publicClient.readContract({
      address: config.tokenAddress,
      abi: erc20TransferAbi,
      functionName: "balanceOf",
      args: [config.account.address],
    });
  } catch (error) {
    return jsonResponse(
      {
        ok: false,
        error: "Tempo refund wallet balance check failed.",
        provider: "tempo",
        provider_error_class: error?.name || "tempo_refund_balance_check_failed",
        provider_message: error?.shortMessage || error?.message || null,
        retryable: true,
      },
      502,
    );
  }
  if (balance < amount) {
    return jsonResponse(
      {
        ok: false,
        error: "Tempo refund wallet balance is insufficient.",
        provider: "tempo",
        retryable: true,
      },
      402,
    );
  }

  const requestClaim = await claimReplayReference("refund_requests", requestedReference, {
    provider: "tempo",
    rail: "tempo-mpp",
    amount_cents: amountCents,
    currency,
    quote_hash: refundExpected.quoteHash,
    original_transaction_reference: refundExpected.originalReference,
    refund_recipient: refundExpected.refundRecipient,
    asset: config.asset,
    token_address: config.tokenAddress,
    network: config.network,
  });
  if (!requestClaim.ok) return requestClaim.response;
  if (requestClaim.idempotentReplay) {
    return jsonResponse(
      {
        ok: false,
        error: "Tempo refund request was already reserved; use the order refund idempotency endpoint result or operator review.",
        provider: "tempo",
        replay_reference: requestedReference,
        replay_request_hash: requestClaim.requestHash,
      },
      409,
    );
  }

  let transactionHash;
  let receipt;
  try {
    const walletClient = createWalletClient({
      account: config.account,
      chain: config.chain,
      transport: viemHttp(config.rpcUrl),
    });
    transactionHash = await walletClient.writeContract({
      address: config.tokenAddress,
      abi: erc20TransferAbi,
      functionName: "transfer",
      args: [refundExpected.refundRecipient, amount],
    });
    receipt = await publicClient.waitForTransactionReceipt({
      hash: transactionHash,
      confirmations: tempoRefundConfirmations,
    });
  } catch (error) {
    return jsonResponse(
      {
        ok: false,
        error: "Tempo refund transfer failed after idempotency reservation.",
        provider: "tempo",
        provider_error_class: error?.name || "tempo_refund_transfer_failed",
        provider_message: error?.shortMessage || error?.message || null,
        retryable: false,
        replay_reference: requestedReference,
        replay_request_hash: requestClaim.requestHash,
      },
      502,
    );
  }
  if (receipt.status !== "success") {
    return jsonResponse(
      {
        ok: false,
        error: "Tempo refund transaction did not succeed.",
        provider: "tempo",
        refund_reference: transactionHash,
        refund_status: receipt.status,
        replay_reference: requestedReference,
        replay_request_hash: requestClaim.requestHash,
      },
      502,
    );
  }

  const refundClaim = await claimReplayReference("refunds", transactionHash, {
    provider: "tempo",
    rail: "tempo-mpp",
    amount_cents: amountCents,
    currency,
    quote_hash: refundExpected.quoteHash,
    original_transaction_reference: refundExpected.originalReference,
    requested_reference: requestedReference,
    refund_recipient: refundExpected.refundRecipient,
    asset: config.asset,
    token_address: config.tokenAddress,
    network: config.network,
  });
  if (!refundClaim.ok) return refundClaim.response;
  return jsonResponse({
    ok: true,
    idempotent_replay: refundClaim.idempotentReplay || undefined,
    provider: "tempo",
    rail: "tempo-mpp",
    amount_cents: amountCents,
    currency,
    quote_hash: refundExpected.quoteHash,
    original_transaction_reference: refundExpected.originalReference,
    network: config.network,
    original_recipient: refundExpected.originalRecipient || config.account.address.toLowerCase(),
    refund_recipient: refundExpected.refundRecipient,
    asset: config.asset,
    token_address: config.tokenAddress,
    refund_reference: transactionHash,
    replay_reference: transactionHash,
    replay_request_hash: refundClaim.requestHash,
    refund_status: "succeeded",
    block_hash: receipt.blockHash,
    block_number: receipt.blockNumber?.toString(),
    real_refund_verified: true,
  });
}

async function verifyRefund(payload) {
  const ready = requireReady();
  if (ready) return ready;
  const expected = payload.expected && typeof payload.expected === "object" ? payload.expected : {};
  const refund = payload.refund && typeof payload.refund === "object" ? payload.refund : {};
  const amountCents = Number(expected.amount_cents ?? refund.amount_cents);
  const currency = String(expected.currency || refund.currency || defaultCurrency).toUpperCase();
  const quoteHash = String(expected.quote_hash || payload.quote_hash || "");
  const originalReference = String(
    expected.original_transaction_reference ||
      payload.original_transaction_reference ||
      payload.order?.transaction_reference ||
      payload.order?.payment_verification?.transaction_reference ||
      "",
  );
  const rail = normalizeRail(refund.rail || payload.rail || "stripe-card-mpp");
  if (rail === "tempo-mpp") {
    if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
      return jsonResponse({ ok: false, error: "refund.amount_cents must be a positive integer." }, 400);
    }
    const requestedReference = String(refund.requested_reference || payload.requested_reference || "").trim();
    if (!requestedReference) {
      return jsonResponse({ ok: false, error: "refund.requested_reference is required." }, 400);
    }
    return verifyTempoRefund(payload, refund, expected, amountCents, currency, requestedReference);
  }
  if (rail !== "stripe-card-mpp") {
    return jsonResponse({ ok: false, error: `Unsupported refund rail: ${rail}` }, 400);
  }
  if (!stripeClient) return jsonResponse({ ok: false, error: "Stripe client is not configured." }, 503);
  if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
    return jsonResponse({ ok: false, error: "refund.amount_cents must be a positive integer." }, 400);
  }
  if (!originalReference) {
    return jsonResponse({ ok: false, error: "original transaction reference is required." }, 400);
  }
  const requestedReference = String(refund.requested_reference || payload.requested_reference || "").trim();
  if (!requestedReference) {
    return jsonResponse({ ok: false, error: "refund.requested_reference is required." }, 400);
  }
  let refundResult;
  try {
    refundResult = await stripeClient.refunds.create(
      {
        amount: amountCents,
        metadata: {
          agentcart_quote_hash: quoteHash,
          agentcart_refund_reason: String(refund.reason || "AgentCart refund"),
        },
        payment_intent: originalReference,
        reason: "requested_by_customer",
      },
      {
        idempotencyKey: requestedReference,
      },
    );
  } catch (error) {
    return providerErrorResponse("Stripe/card refund", error);
  }
  const requestClaim = await claimReplayReference("refund_requests", requestedReference, {
    provider: "stripe",
    rail,
    amount_cents: amountCents,
    currency,
    quote_hash: quoteHash,
    original_transaction_reference: originalReference,
    refund_reference: refundResult.id,
  });
  if (!requestClaim.ok) return requestClaim.response;
  const refundClaim = await claimReplayReference("refunds", refundResult.id, {
    provider: "stripe",
    rail: "stripe-card-mpp",
    amount_cents: amountCents,
    currency,
    quote_hash: quoteHash,
    original_transaction_reference: originalReference,
    requested_reference: requestedReference,
  });
  if (!refundClaim.ok) return refundClaim.response;
  return jsonResponse({
    ok: true,
    idempotent_replay: requestClaim.idempotentReplay || refundClaim.idempotentReplay || undefined,
    provider: "stripe",
    rail: "stripe-card-mpp",
    amount_cents: amountCents,
    currency,
    quote_hash: quoteHash,
    original_transaction_reference: originalReference,
    refund_reference: refundResult.id,
    replay_reference: refundResult.id,
    replay_request_hash: refundClaim.requestHash,
    refund_status: refundResult.status,
    real_refund_verified: true,
  });
}

async function paid(request, payload) {
  const ready = requireReady();
  if (ready) return ready;
  const expected = expectedFromPayload(payload);
  if (expected.rail !== "stripe-card-mpp") {
    return jsonResponse({ ok: false, error: `Unsupported paid endpoint rail: ${expected.rail}` }, 400);
  }
  const mppx = createMppx(expected);
  const result = await mppx.compose([
    "stripe/charge",
    chargeOptions(expected),
  ])(request);
  if (result.status === 402) return result.challenge;
  return result.withReceipt(
    jsonResponse({
      ok: true,
      rail: "stripe-card-mpp",
      quote_hash: expected.quoteHash,
      payment_contract_hash: expected.paymentContractHash || undefined,
      amount_cents: expected.amountCents,
      currency: expected.currency.toUpperCase(),
      stripe_profile_id: stripeProfileId,
    }),
  );
}

async function handler(request) {
  const url = new URL(request.url);
  const startedNs = process.hrtime.bigint();
  const correlationId = requestCorrelationId(request);
  let payload = {};
  let response;
  try {
    if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) {
      const status = readiness();
      response = jsonResponse(status, status.ok ? 200 : 503);
    } else if (request.method === "GET" && (url.pathname === "/metrics" || url.pathname === "/metrics.json")) {
      const unauthorized = requireVerifierToken(request);
      response = unauthorized || jsonResponse(verifierMetricsSnapshot());
    } else if (request.method !== "POST") {
      response = jsonResponse({ ok: false, error: "not found" }, 404);
    } else {
      payload = await parseJsonRequest(request);
      if (url.pathname === "/stripe-mpp/challenge") {
        response = await challenge(payload);
      } else if (url.pathname === "/stripe-mpp/paid") {
        response = await paid(request, payload);
      } else if (url.pathname === "/agentcart/verify") {
        const unauthorized = requireVerifierToken(request);
        if (unauthorized) {
          response = unauthorized;
        } else {
          const operation = String(payload.operation || "payment").toLowerCase();
          if (operation === "payment" || operation === "charge") {
            response = await verifyPayment(payload);
          } else if (operation === "refund") {
            response = await verifyRefund(payload);
          } else {
            response = jsonResponse({ ok: false, error: `Unsupported operation: ${operation}` }, 400);
          }
        }
      } else {
        response = jsonResponse({ ok: false, error: "not found" }, 404);
      }
    }
  } catch (error) {
    response = jsonResponse(
      {
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      },
      Number.isInteger(error?.status) ? error.status : 500,
    );
  }
  applyCorrelationHeader(response, correlationId);
  await recordVerifierResponse(request, url, payload, response, startedNs, correlationId);
  return response;
}

async function sendResponse(response, nodeResponse) {
  nodeResponse.statusCode = response.status;
  response.headers.forEach((value, key) => {
    nodeResponse.setHeader(key, value);
  });
  nodeResponse.end(Buffer.from(await response.arrayBuffer()));
}

const server = http.createServer(async (request, response) => {
  try {
    const body = await new Promise((resolve, reject) => {
      const chunks = [];
      request.on("data", (chunk) => chunks.push(chunk));
      request.on("end", () => resolve(Buffer.concat(chunks)));
      request.on("error", reject);
    });
    const url = `http://${request.headers.host}${request.url}`;
    const headers = new Headers();
    for (const [name, value] of Object.entries(request.headers)) {
      if (Array.isArray(value)) {
        for (const entry of value) headers.append(name, entry);
      } else if (value !== undefined) {
        headers.set(name, value);
      }
    }
    const fetchRequest = new Request(url, {
      body: ["GET", "HEAD"].includes(request.method || "GET") ? undefined : body,
      headers,
      method: request.method,
    });
    await sendResponse(await handler(fetchRequest), response);
  } catch (error) {
    await sendResponse(
      jsonResponse(
        {
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        },
        Number.isInteger(error?.status) ? error.status : 500,
      ),
      response,
    );
  }
});

server.listen(port, host, () => {
  const status = readiness();
  console.log(`AgentCart Stripe MPP verifier listening on http://${host}:${port}`);
  console.log(JSON.stringify({ ...status, token_required: Boolean(verifierToken) }, null, 2));
});
