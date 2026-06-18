#!/usr/bin/env node
import crypto from "node:crypto";
import http from "node:http";

import { Mppx, tempo } from "mppx/server";

const host = process.env.MPP_SMOKE_BIND || "127.0.0.1";
const port = Number(process.env.MPP_SMOKE_PORT || "4250");
const network = process.env.MPP_SMOKE_NETWORK || "testnet";
const recipient = (
  process.env.MPP_SMOKE_RECIPIENT ||
  process.env.AGENTCART_TEMPO_RECIPIENT_ADDRESS ||
  ""
).trim();
const token = process.env.MPP_SMOKE_TOKEN || "0x20c0000000000000000000000000000000000000";
const amount = process.env.MPP_SMOKE_AMOUNT || "0.01";
const secretKey =
  process.env.MPP_SMOKE_SECRET_KEY || crypto.randomBytes(32).toString("base64");

function jsonResponse(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body, null, 2) + "\n", {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...headers,
    },
  });
}

function parseBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => resolve(Buffer.concat(chunks)));
    request.on("error", reject);
  });
}

async function toFetchRequest(request, body) {
  const url = `http://${request.headers.host}${request.url}`;
  const headers = new Headers();
  for (const [name, value] of Object.entries(request.headers)) {
    if (Array.isArray(value)) {
      for (const entry of value) headers.append(name, entry);
    } else if (value !== undefined) {
      headers.set(name, value);
    }
  }
  const hasBody = !["GET", "HEAD"].includes(request.method || "GET");
  return new Request(url, {
    method: request.method,
    headers,
    body: hasBody ? body : undefined,
  });
}

async function writeResponse(response, nodeResponse) {
  nodeResponse.statusCode = response.status;
  response.headers.forEach((value, key) => {
    nodeResponse.setHeader(key, value);
  });
  const buffer = Buffer.from(await response.arrayBuffer());
  nodeResponse.end(buffer);
}

function readiness() {
  return {
    ok: Boolean(recipient),
    service: "agentcart-mpp-smoke",
    network,
    token,
    amount,
    recipient: recipient || null,
    paid_endpoint: `http://${host}:${port}/paid`,
    missing: recipient ? [] : ["MPP_SMOKE_RECIPIENT or AGENTCART_TEMPO_RECIPIENT_ADDRESS"],
  };
}

async function paid(fetchRequest) {
  if (!recipient) {
    return jsonResponse(
      {
        error: "MPP smoke server is missing a recipient address",
        missing: readiness().missing,
        hint: "Run `npm run mpp:account:create`, then `npm run mpp:account:view`, and export MPP_SMOKE_RECIPIENT=<address>`.",
      },
      503,
    );
  }

  const mpp = Mppx.create({
    methods: [
      tempo.charge({
        currency: token,
        recipient,
        testnet: network === "testnet",
      }),
    ],
    secretKey,
  });

  const result = await Mppx.compose(
    mpp.tempo.charge({
      amount,
      recipient,
    }),
  )(fetchRequest);

  if (result.status === 402) return result.challenge;

  return result.withReceipt(
    jsonResponse({
      ok: true,
      provider: "tempo_mpp",
      real_settlement: network !== "testnet",
      testnet: network === "testnet",
      amount,
      token,
      recipient,
      delivered_at: new Date().toISOString(),
      artifact: "AgentCart MPP smoke paid resource",
    }),
  );
}

const server = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", `http://${request.headers.host}`);
    if (url.pathname === "/health" || url.pathname === "/") {
      await writeResponse(jsonResponse(readiness()), response);
      return;
    }
    if (url.pathname !== "/paid") {
      await writeResponse(jsonResponse({ error: "not found" }, 404), response);
      return;
    }
    const body = await parseBody(request);
    await writeResponse(await paid(await toFetchRequest(request, body)), response);
  } catch (error) {
    await writeResponse(
      jsonResponse(
        {
          error: error instanceof Error ? error.message : String(error),
          stack: process.env.NODE_ENV === "development" && error instanceof Error ? error.stack : undefined,
        },
        500,
      ),
      response,
    );
  }
});

server.listen(port, host, () => {
  const status = readiness();
  console.log(`AgentCart MPP smoke server listening on http://${host}:${port}`);
  console.log(JSON.stringify(status, null, 2));
});

