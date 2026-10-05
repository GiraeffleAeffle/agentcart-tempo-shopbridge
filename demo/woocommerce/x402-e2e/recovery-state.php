<?php
// Read only operational draft metadata, never persisted request bodies or credentials.
$phase = $args[0] ?? '';
$hook = 'agentcart_shopbridge_recover_checkout';
$now = time();
$cases = [];
foreach (['positive' => 'positive-result', 'N1' => 'N1', 'N2' => 'N2', 'N3' => 'N3'] as $case => $file) {
    $record = json_decode(file_get_contents('/work/' . $file . '.json'), true);
    $order = AgentCart_ShopBridge_Checkout_Store::find($record['quote_id']);
    if (!$order) { throw new RuntimeException('Missing draft for ' . $case); }
    $cases[$case] = [
        'order_id' => $order->get_id(),
        'quote_hash' => $record['quote_hash'],
        'payment_contract_hash' => $record['payment_contract_hash'],
        'state' => $order->get_meta(AgentCart_ShopBridge_Checkout_Store::STATE_META, true),
        'paid' => $order->is_paid(),
        'verifier_attempted' => AgentCart_ShopBridge_Checkout_Store::verification_attempted($order),
        'recovery_attempts' => intval($order->get_meta('_agentcart_recovery_attempts', true)),
        'next_scheduled_at' => wp_next_scheduled($hook, [$order->get_id()]),
    ];
}
if (!$cases['positive']['paid'] || $cases['positive']['state'] !== 'completed') {
    throw new RuntimeException('Positive order lost completed/paid state');
}
foreach (['N1', 'N2'] as $case) {
    if ($cases[$case]['paid'] || $cases[$case]['verifier_attempted'] || $cases[$case]['recovery_attempts'] !== 0 || $cases[$case]['next_scheduled_at']) {
        throw new RuntimeException($case . ' was attempted or scheduled for recovery: ' . json_encode($cases[$case]));
    }
}
if ($cases['N2']['state'] !== 'checkout_rejected') { throw new RuntimeException('N2 draft was not rejected'); }
$n3 = $cases['N3'];
if ($n3['paid'] || !$n3['verifier_attempted'] || $n3['state'] !== 'verification_pending') {
    throw new RuntimeException('N3 must remain unpaid and verification_pending');
}
$result = ['phase' => $phase, 'observed_at' => $now, 'cases' => $cases];
if ($phase === 'before') {
    if (!$n3['next_scheduled_at'] || $n3['recovery_attempts'] !== 0) {
        throw new RuntimeException('N3 has no initial scheduled recovery event');
    }
} elseif ($phase === 'due') {
    $before = json_decode(file_get_contents('/work/recovery-before.json'), true);
    if (!$n3['next_scheduled_at'] || $n3['next_scheduled_at'] !== $before['cases']['N3']['next_scheduled_at'] || $n3['next_scheduled_at'] > $now) {
        throw new RuntimeException('N3 recovery event is not actually due');
    }
    $result['was_due'] = true;
} elseif ($phase === 'after') {
    $before = json_decode(file_get_contents('/work/recovery-before.json'), true);
    $due = json_decode(file_get_contents('/work/recovery-due.json'), true);
    $ran_hook = strpos(file_get_contents('/work/cron.log'), $hook) !== false;
    if (!$due['was_due'] || !$ran_hook || $n3['recovery_attempts'] !== $before['cases']['N3']['recovery_attempts'] + 1) {
        throw new RuntimeException('Due recovery must run exactly once');
    }
    if ($n3['next_scheduled_at'] && ($n3['next_scheduled_at'] <= $now || $n3['next_scheduled_at'] <= $due['cases']['N3']['next_scheduled_at'])) {
        throw new RuntimeException('Recovery was not removed or rescheduled with backoff');
    }
    $result['was_due'] = true;
    $result['recovery_ran'] = true;
    $result['schedule_state'] = $n3['next_scheduled_at'] ? 'rescheduled_with_backoff' : 'removed';
    $result['due_at'] = $due['cases']['N3']['next_scheduled_at'];
} else {
    throw new RuntimeException('Unknown recovery observation phase');
}
echo json_encode($result) . "\n";
