#!/usr/bin/env node
import crypto from "node:crypto";
import http from "node:http";

import Stripe from "stripe";
import { Challenge, Receipt } from "mppx";
import { Mppx, stripe as mppStripe } from "mppx/server";

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
const defaultCurrency = (process.env.STRIPE_MPP_CURRENCY || "eur").trim().toLowerCase();
const paymentMethodTypes = (process.env.STRIPE_MPP_PAYMENT_METHOD_TYPES || "card,link")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

const stripeClient = stripeSecretKey
  ? new Stripe(stripeSecretKey, { apiVersion: "2026-02-25.preview" })
  : null;

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

function missingConfig() {
  const missing = [];
  if (!stripeSecretKey) missing.push("STRIPE_SANDBOX_SECRET_KEY");
  if (!stripeProfileId) missing.push("STRIPE_PROFILE_ID");
  if (!mppSecretKey) missing.push("MPP_SECRET_KEY");
  if (!verifierToken) missing.push("AGENTCART_PAYMENT_VERIFIER_TOKEN");
  return missing;
}

function readiness() {
  const missing = missingConfig();
  return {
    ok: missing.length === 0,
    service: "agentcart-stripe-mpp-verifier",
    mode: "sandbox",
    endpoints: {
      health: `http://${host}:${port}/health`,
      challenge: `http://${host}:${port}/stripe-mpp/challenge`,
      paid: `http://${host}:${port}/stripe-mpp/paid`,
      verify: `http://${host}:${port}/agentcart/verify`,
    },
    stripe_profile_id: stripeProfileId || null,
    default_currency: defaultCurrency,
    payment_method_types: paymentMethodTypes,
    token_required: verifierToken !== "",
    missing,
  };
}

function requireReady() {
  const missing = missingConfig();
  if (missing.length) {
    return jsonResponse(
      {
        ok: false,
        error: "Stripe MPP verifier is not configured.",
        missing,
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
  if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
    throw Object.assign(new Error("expected.amount_cents must be a positive integer."), { status: 400 });
  }
  if (!currency) {
    throw Object.assign(new Error("expected.currency is required."), { status: 400 });
  }
  if (!quoteHash) {
    throw Object.assign(new Error("quote_hash is required."), { status: 400 });
  }
  if (rail !== "stripe-card-mpp") {
    throw Object.assign(new Error(`Unsupported rail for this verifier: ${rail}`), { status: 400 });
  }
  if (profileId !== stripeProfileId) {
    throw Object.assign(new Error("Stripe profile id does not match verifier configuration."), { status: 400 });
  }
  return { amountCents, currency, merchantId, profileId, quoteHash, rail };
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
  const mppReceipt = await mppx.verifyCredential(authorization, { request: chargeOptions(expected) });
  return jsonResponse({
    ok: true,
    provider: "stripe",
    rail: "stripe-card-mpp",
    amount_cents: expected.amountCents,
    currency: expected.currency.toUpperCase(),
    quote_hash: expected.quoteHash,
    stripe_profile_id: stripeProfileId,
    transaction_reference: mppReceipt.reference,
    mpp_receipt: mppReceipt,
    real_settlement_verified: true,
  });
}

async function verifyRefund(payload) {
  const ready = requireReady();
  if (ready) return ready;
  if (!stripeClient) return jsonResponse({ ok: false, error: "Stripe client is not configured." }, 503);
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
  if (rail !== "stripe-card-mpp") {
    return jsonResponse({ ok: false, error: `Unsupported refund rail: ${rail}` }, 400);
  }
  if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
    return jsonResponse({ ok: false, error: "refund.amount_cents must be a positive integer." }, 400);
  }
  if (!originalReference) {
    return jsonResponse({ ok: false, error: "original transaction reference is required." }, 400);
  }
  const refundResult = await stripeClient.refunds.create(
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
      idempotencyKey: `agentcart_refund_${originalReference}_${amountCents}_${quoteHash || "nohash"}`,
    },
  );
  return jsonResponse({
    ok: true,
    provider: "stripe",
    rail: "stripe-card-mpp",
    amount_cents: amountCents,
    currency,
    quote_hash: quoteHash,
    original_transaction_reference: originalReference,
    refund_reference: refundResult.id,
    refund_status: refundResult.status,
    real_refund_verified: true,
  });
}

async function paid(request, payload) {
  const ready = requireReady();
  if (ready) return ready;
  const expected = expectedFromPayload(payload);
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
      amount_cents: expected.amountCents,
      currency: expected.currency.toUpperCase(),
      stripe_profile_id: stripeProfileId,
    }),
  );
}

async function handler(request) {
  const url = new URL(request.url);
  if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) {
    return jsonResponse(readiness(), readiness().ok ? 200 : 503);
  }
  if (request.method !== "POST") {
    return jsonResponse({ ok: false, error: "not found" }, 404);
  }
  const payload = await parseJsonRequest(request);
  if (url.pathname === "/stripe-mpp/challenge") return challenge(payload);
  if (url.pathname === "/stripe-mpp/paid") return paid(request, payload);
  if (url.pathname === "/agentcart/verify") {
    const unauthorized = requireVerifierToken(request);
    if (unauthorized) return unauthorized;
    const operation = String(payload.operation || "payment").toLowerCase();
    if (operation === "payment" || operation === "charge") return verifyPayment(payload);
    if (operation === "refund") return verifyRefund(payload);
    return jsonResponse({ ok: false, error: `Unsupported operation: ${operation}` }, 400);
  }
  return jsonResponse({ ok: false, error: "not found" }, 404);
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
