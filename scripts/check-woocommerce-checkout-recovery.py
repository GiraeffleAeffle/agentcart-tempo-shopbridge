#!/usr/bin/env python3
"""Exercise an already-seeded isolated shop; never target production data."""
import argparse
import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='Existing isolated Compose project, starting with shopbridge-recovery-')
    args = parser.parse_args()
    if not args.project.startswith('shopbridge-recovery-'):
        parser.error('Use a dedicated shopbridge-recovery-* project seeded for this test.')
    base = ['docker', 'compose', '-p', args.project, '-f', str(ROOT / 'demo/woocommerce/docker-compose.yml'),
            'run', '--rm', '--no-deps', '--entrypoint', 'wp', '-e', 'AGENTCART_CHECKOUT_INTEGRATION=1',
            '-v', f'{ROOT / "woocommerce-shopbridge/tests"}:/tests:ro']
    tail = ['wpcli', 'eval-file', '/tests/integration-checkout-recovery.php', '--allow-root']
    def command(**env):
        return base + [value for key, val in env.items() for value in ('-e', f'{key}={val}')] + tail
    # Restrict the environment to selecting this test stack; credentials in the
    # production shell cannot change its database or verifier fixture.
    env = {k: v for k, v in os.environ.items() if not k.startswith(('AGENTCART_', 'WORDPRESS_', 'WOO_'))}
    subprocess.run(command(), env=env, check=True)
    created = subprocess.run(command(AGENTCART_STOCK_RACE_MODE='create'), env=env, text=True, capture_output=True, check=True)
    product_id = created.stdout.strip()
    if not product_id.isdigit():
        raise RuntimeError(f'Unexpected fixture product result: {product_id}')
    jobs = [subprocess.Popen(command(AGENTCART_STOCK_RACE_MODE='reserve', AGENTCART_STOCK_RACE_PRODUCT=product_id),
                             env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
    outcomes = []
    for job in jobs:
        stdout, stderr = job.communicate(timeout=60)
        if job.returncode:
            raise RuntimeError(stderr)
        outcomes.append(stdout.strip())
    if sorted(outcomes) != ['held', 'rejected']:
        raise RuntimeError(f'Concurrent stock reservation failed: {outcomes}')
    print('PASS separate workers cannot both reserve the last unit')


if __name__ == '__main__':
    main()
