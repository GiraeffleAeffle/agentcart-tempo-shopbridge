// Test-only, local-network bridge: sign with viem; the ephemeral key stays in memory and is never logged.
// Resolve viem beside the verifier's installed dependencies, not the mounted driver directory.
import { createRequire } from 'node:module';
import http from 'node:http';
const require = createRequire('/app/package.json');
const { generatePrivateKey, privateKeyToAccount } = require('viem/accounts');
const account = privateKeyToAccount(generatePrivateKey());
const payer = account.address;
http.createServer(async (req, res) => {
  res.setHeader('content-type', 'application/json');
  if (req.method === 'GET' && req.url === '/payer') {
    res.end(JSON.stringify({ payer }));
    return;
  }
  if (req.method !== 'POST' || req.url !== '/sign') { res.writeHead(404); res.end('{}'); return; }
  let input = '';
  for await (const chunk of req) input += chunk;
  try {
    const { typed_data: typed } = JSON.parse(input);
    const signature = await account.signTypedData({
      ...typed, domain: { ...typed.domain, chainId: Number(typed.domain.chainId) },
    });
    res.end(JSON.stringify({ payer, signature }));
  } catch {
    res.writeHead(400);
    res.end(JSON.stringify({ error: 'test_signer_rejected_input' }));
  }
}).listen(4293, '0.0.0.0');
