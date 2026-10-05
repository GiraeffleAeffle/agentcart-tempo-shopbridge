import { spawn } from 'node:child_process';

const LISTENING = /AgentCart Stripe MPP verifier listening on http:\/\/127\.0\.0\.1:(\d+)/;

async function stop(child) {
  if (child.exitCode === null && child.signalCode === null) {
    const exited = new Promise(resolve => child.once('exit', resolve));
    child.kill();
    await exited;
  }
}

// Starts scripts/stripe-mpp-verifier.mjs on an OS-assigned port. The verifier binds port 0 itself
// and logs the port it bound, so no concurrent test can take the port between selection and bind.
// Resolves once /health answers; on any failure the child is stopped before rejecting.
export async function spawnVerifier(env, { timeoutMs = 15000 } = {}) {
  const child = spawn(process.execPath, ['scripts/stripe-mpp-verifier.mjs'], {
    cwd: new URL('../..', import.meta.url),
    env: { ...process.env, ...env, STRIPE_MPP_VERIFIER_BIND: '127.0.0.1', STRIPE_MPP_VERIFIER_PORT: '0' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  child.stderr.on('data', data => { output += data; });
  const deadline = Date.now() + timeoutMs;
  try {
    const port = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('verifier did not report its port')), timeoutMs);
      child.once('error', error => { clearTimeout(timer); reject(error); });
      child.once('exit', code => { clearTimeout(timer); reject(new Error(`verifier exited with ${code} before listening`)); });
      child.stdout.on('data', data => {
        output += data;
        const match = output.match(LISTENING);
        if (match) {
          clearTimeout(timer);
          resolve(Number(match[1]));
        }
      });
    });
    const base = `http://127.0.0.1:${port}`;
    for (;;) {
      if (child.exitCode !== null) throw new Error(`verifier exited with ${child.exitCode}`);
      try {
        await fetch(`${base}/health`);
        break;
      } catch {
        if (Date.now() > deadline) throw new Error('verifier /health did not answer');
        await new Promise(resolve => setTimeout(resolve, 50));
      }
    }
    return { child, base, output: () => output, close: () => stop(child) };
  } catch (error) {
    await stop(child);
    throw new Error(`${error.message}:\n${output}`);
  }
}
