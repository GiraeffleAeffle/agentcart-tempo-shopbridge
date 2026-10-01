<?php
// Standalone CLI test: load the real plugin; only WordPress hook registration and
// its JSON wrapper are stubbed. No database or WooCommerce execution is needed.
define('ABSPATH', '/');
function add_action(...$args) {}
function add_filter(...$args) {}
function wp_json_encode($value, $flags = 0, $depth = 512) {
    return json_encode($value, $flags, $depth);
}

$root = dirname(__DIR__, 2);
require $root . '/woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php';
$fixture = json_decode(file_get_contents($root . '/docs/fixtures/canonical-json/vectors.json'), false, 512, JSON_THROW_ON_ERROR);
$passed = 0;
foreach ([AgentCart_ShopBridge::class, AgentCart_ShopBridge_Registry_Events::class] as $class) {
    $method = new ReflectionMethod($class, 'canonical_json');
    foreach ($fixture->cases as $vector) {
        $canonical = $method->invoke(null, $vector->value);
        if ($canonical !== $vector->canonical || hash('sha256', $canonical) !== $vector->sha256) {
            throw new RuntimeException($class . ': ' . $vector->name . ' canonical JSON or SHA-256 mismatch');
        }
        $passed++;
    }
    // PHP associative decoding irreversibly collapses {} into [] and
    // {"0":"zero"} into a list. Pin this documented input-domain limitation.
    if ($method->invoke(null, json_decode('{}', true)) !== '[]') {
        throw new RuntimeException($class . ': empty PHP array must remain a JSON list');
    }
    if ($method->invoke(null, json_decode('{"0":"zero"}', true)) !== '["zero"]') {
        throw new RuntimeException($class . ': contiguous numeric PHP keys are a JSON list');
    }
}
echo 'PASS: ' . $passed . ' shared PHP canonical JSON vector cases; array/object ambiguity documented' . PHP_EOL;
