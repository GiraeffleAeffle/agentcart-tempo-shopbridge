import json
import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN_INCLUDES = ROOT / "woocommerce-shopbridge" / "agentcart-shopbridge" / "includes"
IDENTITY_MODULE = PLUGIN_INCLUDES / "class-agentcart-shopbridge-onchain-identity.php"
RPC_MODULE = PLUGIN_INCLUDES / "class-agentcart-shopbridge-registry-rpc.php"


@unittest.skipUnless(shutil.which("php"), "php is required for registry RPC verifier tests")
class RegistryRpcBehaviorTests(unittest.TestCase):
    now = 1_787_745_900
    controller = "0x" + "11" * 20
    registry = "0x" + "22" * 20
    record_id = "0x" + "33" * 32
    record_hash = "44" * 32
    domain = "tea.example"
    domain_hash = "0x200c4149ae3fd74164a5bbdf3560e81e0f9fdfc934772dd6bc55f068c26fc649"
    runtime_code = "0x6000"

    identity = {
        "controller": controller,
        "chain_id": "eip155:42431",
        "registry_address": registry,
        "record_id": record_id,
    }
    descriptor = {
        "id": "test-tempo",
        "chain_id": 42431,
        "caip2": "eip155:42431",
        "registry_address": registry,
        "deployment_block": 100,
        "deployment_block_hash": "0x" + "aa" * 32,
        "runtime_code_sha256": "f3df0a62b10f205b0f29768aa3d69e777154caaa179f64aabb0a4899c666b017",
        "rpc_url": "https://rpc.example",
        "max_finality_age_seconds": 600,
        "max_future_skew_seconds": 300,
    }

    def responses(self) -> dict:
        finalized_ref = f"hash:{'0x' + '55' * 32}:canonical"
        record_words = [
            "0" * 24 + self.controller[2:],
            self.record_hash,
            self.domain_hash[2:],
            "0" * 63 + "1",
            "0" * 64,
            "0" * 64,
            "0" * 64,
            "0" * 64,
            "0" * 63 + "1",
        ]
        return {
            "eth_chainId": "0xa5bf",
            "eth_getBlockByNumber:finalized": {
                "number": "0x96",
                "hash": "0x" + "55" * 32,
                "timestamp": hex(self.now - 60),
            },
            "eth_getBlockByNumber:0x64": {
                "number": "0x64",
                "hash": self.descriptor["deployment_block_hash"],
                "timestamp": "0x1",
            },
            f"eth_getCode:{self.registry}:0x64": self.runtime_code,
            f"eth_getCode:{self.registry}:0x63": "0x",
            f"eth_getCode:{self.registry}:{finalized_ref}": self.runtime_code,
            "web3_sha3:0x" + self.domain.encode().hex(): self.domain_hash,
            "eth_call:0xb5c645bd" + self.record_id[2:] + f":{finalized_ref}": "0x" + "".join(record_words),
            "eth_call:0x15daecde" + self.domain_hash[2:] + f":{finalized_ref}": self.record_id,
            "eth_call:0xf30566db" + self.record_hash + f":{finalized_ref}": "0x" + "0" * 64,
            (
                "eth_call:0xe26ec9d5"
                + self.domain_hash[2:]
                + "0" * 24
                + self.controller[2:]
                + f":{finalized_ref}"
            ): self.record_id,
        }

    def run_php(self, responses: dict) -> dict:
        script = f"""<?php
require {json.dumps(str(IDENTITY_MODULE))};
require {json.dumps(str(RPC_MODULE))};
$responses = json_decode({json.dumps(json.dumps(responses))}, true);
$rpc = static function ($method, $params) use ($responses) {{
    $key = $method;
    $block_key = static function ($block) {{
        if (!is_array($block)) {{
            return (string) $block;
        }}
        if (($block['requireCanonical'] ?? null) !== true) {{
            throw new RuntimeException('state_read_not_require_canonical');
        }}
        return 'hash:' . strtolower((string) ($block['blockHash'] ?? '')) . ':canonical';
    }};
    if ($method === 'eth_getBlockByNumber') {{
        $key .= ':' . $params[0];
    }} elseif ($method === 'eth_getCode') {{
        $key .= ':' . strtolower($params[0]) . ':' . $block_key($params[1]);
    }} elseif ($method === 'eth_call') {{
        $key .= ':' . strtolower($params[0]['data']) . ':' . $block_key($params[1]);
    }} elseif ($method === 'web3_sha3') {{
        $key .= ':' . strtolower($params[0]);
    }}
    if (!array_key_exists($key, $responses)) {{
        throw new RuntimeException('unexpected_rpc_call_' . $key);
    }}
    return $responses[$key];
}};
echo json_encode(AgentCart_ShopBridge_Registry_Rpc::verify(
    json_decode({json.dumps(json.dumps(self.identity))}, true),
    {json.dumps(self.record_hash)},
    [
        'merchant_id' => 'tea-shop',
        'name' => 'Tea Shop',
        'domain' => ' Tea.Example. ',
        'manifest_url' => 'https://tea.example/.well-known/agentcart.json',
    ],
    {self.now},
    $rpc,
    json_decode({json.dumps(json.dumps(self.descriptor))}, true)
));
"""
        completed = subprocess.run(["php"], input=script, text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def run_default_transport_php(self, responses: dict) -> dict:
        script = f"""<?php
$responses = json_decode({json.dumps(json.dumps(responses))}, true);
$batch_count = 0;
$rpc_urls = [];
$rpc_timeouts = [];
function wp_json_encode($value, $flags = 0) {{
    return json_encode($value, $flags);
}}
function is_wp_error($value) {{
    return false;
}}
function wp_remote_retrieve_response_code($response) {{
    return $response['code'];
}}
function wp_remote_retrieve_body($response) {{
    return $response['body'];
}}
function wp_remote_post($url, $args) {{
    global $responses, $batch_count, $rpc_urls, $rpc_timeouts;
    $batch_count += 1;
    $rpc_urls[] = $url;
    $rpc_timeouts[] = $args['timeout'] ?? null;
    $payload = json_decode($args['body'], true);
    $items = [];
    foreach ($payload as $request) {{
        $method = $request['method'];
        $params = $request['params'];
        $key = $method;
        $block_key = static function ($block) {{
            if (!is_array($block)) {{
                return (string) $block;
            }}
            return 'hash:' . strtolower((string) ($block['blockHash'] ?? '')) . ':' .
                (($block['requireCanonical'] ?? null) === true ? 'canonical' : 'noncanonical');
        }};
        if ($method === 'eth_getBlockByNumber') {{
            $key .= ':' . $params[0];
        }} elseif ($method === 'eth_getCode') {{
            $key .= ':' . strtolower($params[0]) . ':' . $block_key($params[1]);
        }} elseif ($method === 'eth_call') {{
            $key .= ':' . strtolower($params[0]['data']) . ':' . $block_key($params[1]);
        }} elseif ($method === 'web3_sha3') {{
            $key .= ':' . strtolower($params[0]);
        }}
        if (!array_key_exists($key, $responses)) {{
            throw new RuntimeException('unexpected_rpc_call_' . $key);
        }}
        $items[] = [
            'jsonrpc' => '2.0',
            'id' => $request['id'],
            'result' => $responses[$key],
        ];
    }}
    return [
        'code' => 200,
        'body' => json_encode(array_reverse($items)),
    ];
}}
require {json.dumps(str(IDENTITY_MODULE))};
require {json.dumps(str(RPC_MODULE))};
$result = AgentCart_ShopBridge_Registry_Rpc::verify(
    json_decode({json.dumps(json.dumps(self.identity))}, true),
    {json.dumps(self.record_hash)},
    [
        'merchant_id' => 'tea-shop',
        'name' => 'Tea Shop',
        'domain' => 'Tea.Example.',
        'manifest_url' => 'https://tea.example/.well-known/agentcart.json',
    ],
    {self.now},
    null,
    json_decode({json.dumps(json.dumps(self.descriptor))}, true)
);
echo json_encode([
    'result' => $result,
    'batch_count' => $batch_count,
    'rpc_urls' => $rpc_urls,
    'rpc_timeouts' => $rpc_timeouts,
]);
"""
        completed = subprocess.run(["php"], input=script, text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_direct_rpc_verifies_exact_finalized_contract_state(self) -> None:
        result = self.run_php(self.responses())

        self.assertEqual(result["errors"], [])
        self.assertTrue(result["onchain_source"]["chain_valid"])
        self.assertTrue(result["onchain_source"]["canonical_chain_verified"])
        self.assertEqual(result["onchain_source"]["verification_mode"], "direct_rpc")
        self.assertEqual(
            result["onchain_source"]["finality"]["state_selector"],
            "block_hash_require_canonical",
        )
        self.assertEqual(result["current_record"]["registry_record_hash"], self.record_hash)
        self.assertEqual(result["current_record"]["state"], "verified")

    def test_production_transport_uses_two_bounded_batches_and_response_ids(self) -> None:
        output = self.run_default_transport_php(self.responses())

        self.assertEqual(output["result"]["errors"], [])
        self.assertEqual(output["batch_count"], 2)
        self.assertEqual(output["rpc_urls"], [self.descriptor["rpc_url"]] * 2)
        self.assertEqual(output["rpc_timeouts"], [8, 8])

    def test_stale_finality_runtime_mismatch_or_changed_state_fails_closed(self) -> None:
        finalized_ref = f"hash:{'0x' + '55' * 32}:canonical"

        def change_rpc_domain_hash(responses: dict) -> None:
            changed_hash = "0x" + "77" * 32
            responses["web3_sha3:0x" + self.domain.encode().hex()] = changed_hash
            old_mapping_key = "eth_call:0x15daecde" + self.domain_hash[2:] + f":{finalized_ref}"
            old_compute_key = (
                "eth_call:0xe26ec9d5"
                + self.domain_hash[2:]
                + "0" * 24
                + self.controller[2:]
                + f":{finalized_ref}"
            )
            responses["eth_call:0x15daecde" + changed_hash[2:] + f":{finalized_ref}"] = responses.pop(
                old_mapping_key
            )
            responses[
                "eth_call:0xe26ec9d5"
                + changed_hash[2:]
                + "0" * 24
                + self.controller[2:]
                + f":{finalized_ref}"
            ] = responses.pop(old_compute_key)

        cases = {
            "stale finalized block": (
                lambda responses: responses["eth_getBlockByNumber:finalized"].__setitem__(
                    "timestamp", hex(self.now - 601)
                ),
                "rpc_finalized_block_time_stale",
            ),
            "runtime mismatch": (
                lambda responses: responses.__setitem__(
                    f"eth_getCode:{self.registry}:hash:{'0x' + '55' * 32}:canonical", "0x6001"
                ),
                "rpc_runtime_code_hash_mismatch",
            ),
            "changed domain mapping": (
                lambda responses: responses.__setitem__(
                    "eth_call:0x15daecde"
                    + self.domain_hash[2:]
                    + f":hash:{'0x' + '55' * 32}:canonical",
                    "0x" + "77" * 32,
                ),
                "rpc_domain_record_id_mismatch",
            ),
            "wrong merchant domain hash": (
                change_rpc_domain_hash,
                "rpc_record_domain_hash_mismatch",
            ),
            "wrong deterministic record id": (
                lambda responses: responses.__setitem__(
                    "eth_call:0xe26ec9d5"
                    + self.domain_hash[2:]
                    + "0" * 24
                    + self.controller[2:]
                    + f":hash:{'0x' + '55' * 32}:canonical",
                    "0x" + "77" * 32,
                ),
                "rpc_computed_record_id_mismatch",
            ),
        }
        for label, (mutate, error) in cases.items():
            with self.subTest(label=label):
                responses = self.responses()
                mutate(responses)
                result = self.run_php(responses)
                self.assertFalse(result["onchain_source"]["chain_valid"])
                self.assertEqual(result["current_record"], [])
                self.assertIn(error, result["errors"])

    def test_nonzero_address_padding_fails_closed(self) -> None:
        responses = self.responses()
        record_key = next(key for key in responses if key.startswith("eth_call:0xb5c645bd"))
        encoded_record = responses[record_key]
        responses[record_key] = "0x1" + encoded_record[3:]

        result = self.run_php(responses)

        self.assertFalse(result["onchain_source"]["chain_valid"])
        self.assertEqual(result["current_record"], [])
        self.assertIn("rpc_record_controller_padding_invalid", result["errors"])


if __name__ == "__main__":
    unittest.main()
