#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import { privateKeyToAccount } from "viem/accounts";

const root = path.resolve(import.meta.dirname, "../..");
const output = path.resolve(
  process.env.AGENTCART_ONCHAIN_PILOT_KEYS_FILE ||
    path.join(root, ".secrets", "onchain-registry-moderato-keys.env"),
);

if (fs.existsSync(output)) {
  process.stderr.write(`Refusing to overwrite existing pilot key file: ${output}\n`);
  process.exit(2);
}

function account() {
  const privateKey = `0x${crypto.randomBytes(32).toString("hex")}`;
  return { privateKey, address: privateKeyToAccount(privateKey).address };
}

const owner = account();
const controller = account();
const validator = account();
const lines = [
  "# Dedicated, disposable Tempo Moderato pilot identities. Never use on mainnet.",
  "MODERATO_RPC_URL=https://rpc.moderato.tempo.xyz",
  "MODERATO_CHAIN_ID=42431",
  `REGISTRY_OWNER_PRIVATE_KEY=${owner.privateKey}`,
  `REGISTRY_OWNER_ADDRESS=${owner.address}`,
  `REGISTRY_CONTROLLER_PRIVATE_KEY=${controller.privateKey}`,
  `REGISTRY_CONTROLLER_ADDRESS=${controller.address}`,
  `REGISTRY_VALIDATOR_PRIVATE_KEY=${validator.privateKey}`,
  `REGISTRY_VALIDATOR_ADDRESS=${validator.address}`,
  "",
];

fs.mkdirSync(path.dirname(output), { recursive: true, mode: 0o700 });
fs.writeFileSync(output, lines.join("\n"), { mode: 0o600, flag: "wx" });
process.stdout.write(
  `${JSON.stringify({
    output,
    owner: owner.address,
    controller: controller.address,
    validator: validator.address,
    network: "Tempo Moderato",
    chain_id: 42431,
  }, null, 2)}\n`,
);
