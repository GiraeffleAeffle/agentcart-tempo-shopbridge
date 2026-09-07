#!/usr/bin/env node
import { readFile, writeFile } from "node:fs/promises";
import { createPublicClient, http } from "viem";
import { prepareRegistryV2Operation, registryV2Operations } from "./registry-v2-plans.mjs";

try {
  const [command, ...rest] = process.argv.slice(2);
  if (!command || ["--help", "help", "-h"].includes(command)) {
    process.stdout.write(`Usage: node scripts/registry-v2-operator.mjs prepare --deployment-file deployment.json --request-file request.json [--output plan.json]\n\nRead-only: validates deployment evidence and simulates one typed operation at a finalized block.\nReview the decoded operation, token amounts, beneficiary and wallet request before signing externally.\nPrepare again after expiry or any prerequisite transaction. This tool never signs or broadcasts.\n\nRequest: {"operation":"...","actor":"0x...","parameters":{...}}\nuint fields use positive decimal strings; hashes and addresses are 0x-prefixed.\nOperations and required parameters:\n${JSON.stringify(registryV2Operations(), null, 2)}\n`);
  } else {
    if (command !== "prepare" || rest.length % 2) throw new Error("only prepare with named flag/value pairs is supported");
    const flags = {};
    for (let index = 0; index < rest.length; index += 2) {
      if (!["--deployment-file", "--request-file", "--output"].includes(rest[index]) || flags[rest[index]]) throw new Error("unknown or duplicate flag");
      flags[rest[index]] = rest[index + 1];
    }
    if (!flags["--deployment-file"] || !flags["--request-file"]) throw new Error("deployment-file and request-file are required");
    const deployment = JSON.parse(await readFile(flags["--deployment-file"], "utf8"));
    const request = JSON.parse(await readFile(flags["--request-file"], "utf8"));
    const rpc = new URL(deployment.rpc_url);
    if (rpc.protocol !== "https:" && !(rpc.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(rpc.hostname))) throw new Error("RPC must use HTTPS or local HTTP");
    const publicClient = createPublicClient({ transport: http(rpc.toString(), { timeout: 15000, retryCount: 1 }) });
    const plan = await prepareRegistryV2Operation({ request, deployment, publicClient });
    const output = `${JSON.stringify(plan, null, 2)}\n`;
    if (flags["--output"]) {
      await writeFile(flags["--output"], output, { flag: "wx", mode: 0o600 });
      process.stdout.write(`${JSON.stringify({ state: plan.state, output: flags["--output"], intent_hash: plan.intent_hash })}\n`);
    } else process.stdout.write(output);
  }
} catch (error) {
  // RPC exceptions can contain credential-bearing URLs. Keep CLI output terse.
  const message = String(error?.shortMessage || error?.message || "operation_preparation_failed").split("\n")[0];
  process.stderr.write(`${message.replace(/https?:\/\/\S+/g, "[RPC or document URL]")}\n`);
  process.exitCode = 1;
}
