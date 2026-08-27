<?php
/**
 * Fail-closed projection of the public finalized registry event document.
 *
 * @package AgentCart_ShopBridge
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * Projects one merchant's exact active record from finalized lifecycle events.
 */
final class AgentCart_ShopBridge_Registry_Events {
    private const PINNED_IMPLEMENTATION = 'agentcart.onchain_registry_rpc_indexer.v1';
    private const MAX_EVIDENCE_AGE_SECONDS = 600;
    private const MAX_FUTURE_SKEW_SECONDS = 300;

    /**
     * Project the expected merchant from a complete finalized event document.
     *
     * @param array<string,mixed> $document Public onchain event document.
     * @param array<string,mixed> $identity Expected public merchant identity.
     * @param string              $record_hash Expected canonical record hash.
     * @param array<string,mixed> $merchant Expected public merchant summary.
     * @param int|null            $now Optional Unix timestamp for deterministic evaluation.
     * @return array<string,mixed>
     */
    public static function project(
        array $document,
        array $identity,
        string $record_hash,
        array $merchant,
        ?int $now = null
    ): array {
        $reference_time = $now ?? time();
        $errors = [];
        $expected_chain = AgentCart_ShopBridge_Onchain_Identity::sanitize_chain_id($identity['chain_id'] ?? '');
        $expected_registry = AgentCart_ShopBridge_Onchain_Identity::sanitize_address($identity['registry_address'] ?? '');
        $expected_controller = AgentCart_ShopBridge_Onchain_Identity::sanitize_address($identity['controller'] ?? '');
        $expected_record_id = AgentCart_ShopBridge_Onchain_Identity::sanitize_record_id($identity['record_id'] ?? '');
        $expected_hash = self::normalize_hash($record_hash);
        $chain_id = AgentCart_ShopBridge_Onchain_Identity::sanitize_chain_id($document['chain_id'] ?? '');
        $registry_address = AgentCart_ShopBridge_Onchain_Identity::sanitize_address($document['registry_address'] ?? '');
        $raw_finality = is_array($document['finality'] ?? null) ? $document['finality'] : [];
        $finality = self::finality($raw_finality, $document);

        if (($document['schema'] ?? '') !== 'agentcart.onchain_registry_contract_events.v1') {
            $errors[] = 'events_schema_invalid';
        }
        if (($document['implementation'] ?? '') !== self::PINNED_IMPLEMENTATION) {
            $errors[] = 'events_implementation_invalid';
        }
        if (($document['complete'] ?? null) !== true) {
            $errors[] = 'events_snapshot_incomplete';
        }
        $independent = is_array($document['independent_verification'] ?? null)
            ? $document['independent_verification']
            : [];
        $primary = is_array($independent['primary'] ?? null) ? $independent['primary'] : [];
        $witness = is_array($independent['witness_path'] ?? null) ? $independent['witness_path'] : [];
        if (($document['completeness_authority'] ?? '') !== 'independently_verified') {
            $errors[] = 'events_independent_authority_required';
        }
        if (
            ($independent['schema'] ?? '') !== 'agentcart.onchain_registry_independent_verification.v1' ||
            ($independent['status'] ?? '') !== 'matched' ||
            ($independent['chain_id_match'] ?? null) !== true ||
            ($independent['registry_address_match'] ?? null) !== true ||
            ($independent['finalized_time_lag_within_limit'] ?? null) !== true ||
            !in_array($independent['finalized_head_hash_match'] ?? null, [null, true], true)
        ) {
            $errors[] = 'events_independent_match_required';
        }
        if (
            self::strict_nonnegative_int($independent['common_finalized_block'] ?? null) !==
            self::strict_nonnegative_int($raw_finality['indexed_to_block'] ?? null)
        ) {
            $errors[] = 'events_independent_range_mismatch';
        }
        $primary_hash = self::normalize_hash((string) ($primary['canonical_events_sha256'] ?? ''));
        $witness_hash = self::normalize_hash((string) ($witness['canonical_events_sha256'] ?? ''));
        if ($primary_hash === '' || $witness_hash === '' || !hash_equals($primary_hash, $witness_hash)) {
            $errors[] = 'events_independent_history_mismatch';
        }
        $document_errors = $document['errors'] ?? null;
        if (!is_array($document_errors) || !self::is_list($document_errors) || $document_errors !== []) {
            $errors[] = 'events_snapshot_has_errors';
        }
        if ($expected_chain === '' || $chain_id === '' || !hash_equals($expected_chain, $chain_id)) {
            $errors[] = 'events_chain_id_mismatch';
        }
        if (
            $expected_registry === '' ||
            $registry_address === '' ||
            !hash_equals($expected_registry, $registry_address)
        ) {
            $errors[] = 'events_registry_address_mismatch';
        }
        if ($expected_controller === '' || $expected_record_id === '' || $expected_hash === '') {
            $errors[] = 'events_expected_identity_invalid';
        }
        if (!self::finality_is_valid($raw_finality)) {
            $errors[] = 'events_finality_invalid';
        }
        if (!self::timestamp_is_fresh($document['indexed_at'] ?? null, $reference_time)) {
            $errors[] = 'events_indexed_at_invalid';
        }
        if (!self::timestamp_is_fresh($raw_finality['block_time'] ?? null, $reference_time)) {
            $errors[] = 'events_finality_block_time_invalid';
        }

        $events = $document['events'] ?? null;
        if (!is_array($events) || !self::is_list($events)) {
            $errors[] = 'events_entries_invalid';
            $events = [];
        }
        $comparable_events = [];
        foreach ($events as $event) {
            if (!is_array($event)) {
                continue;
            }
            $normalized_event = [
                'event' => (string) ($event['event'] ?? ''),
                'block_number' => intval($event['block_number'] ?? 0),
                'block_hash' => strtolower((string) ($event['block_hash'] ?? '')),
                'block_time' => (string) ($event['block_time'] ?? ''),
                'transaction_hash' => strtolower((string) ($event['transaction_hash'] ?? '')),
                'log_index' => intval($event['log_index'] ?? 0),
                'args' => is_array($event['args'] ?? null) ? $event['args'] : [],
            ];
            if (is_array($event['registry_record'] ?? null)) {
                $normalized_event['registry_record'] = $event['registry_record'];
            }
            if (!empty($event['record_fetch_error'])) {
                $normalized_event['record_fetch_error'] = (string) $event['record_fetch_error'];
            }
            $comparable_events[] = $normalized_event;
        }
        $actual_events_hash = hash('sha256', self::canonical_json($comparable_events));
        $primary_count = self::strict_nonnegative_int($primary['event_count'] ?? null);
        $witness_count = self::strict_nonnegative_int($witness['event_count'] ?? null);
        if (
            $primary_count !== count($events) ||
            $witness_count !== count($events) ||
            $primary_hash === '' ||
            $witness_hash === '' ||
            !hash_equals($actual_events_hash, $primary_hash) ||
            !hash_equals($actual_events_hash, $witness_hash)
        ) {
            $errors[] = 'events_independent_history_mismatch';
        }
        $state = 'none';
        $active_hash = '';
        $active_controller = '';
        $previous_block = null;
        $previous_log_index = null;
        foreach ($events as $event) {
            if (!is_array($event)) {
                $errors[] = 'events_entry_invalid';
                continue;
            }
            $block_number = self::strict_nonnegative_int($event['block_number'] ?? null);
            $log_index = self::strict_nonnegative_int($event['log_index'] ?? null);
            if ($block_number === null || $log_index === null) {
                $errors[] = 'events_entry_position_invalid';
            } else {
                if (
                    $block_number < intval($finality['indexed_from_block']) ||
                    $block_number > intval($finality['indexed_to_block']) ||
                    $block_number > intval($finality['block_number'])
                ) {
                    $errors[] = 'events_entry_outside_finalized_range';
                }
                if (
                    $previous_block !== null &&
                    (
                        $block_number < $previous_block ||
                        ($block_number === $previous_block && $log_index <= $previous_log_index)
                    )
                ) {
                    $errors[] = 'events_order_invalid';
                }
                $previous_block = $block_number;
                $previous_log_index = $log_index;
            }
            if (!self::is_prefixed_hash($event['block_hash'] ?? null)) {
                $errors[] = 'events_entry_block_hash_invalid';
            }
            if (!self::is_prefixed_hash($event['transaction_hash'] ?? null)) {
                $errors[] = 'events_entry_transaction_hash_invalid';
            }

            $args = is_array($event['args'] ?? null) ? $event['args'] : [];
            $event_record_id = AgentCart_ShopBridge_Onchain_Identity::sanitize_record_id(
                $args['recordId'] ?? ''
            );
            if ($event_record_id === '' || !hash_equals($expected_record_id, $event_record_id)) {
                continue;
            }
            $event_name = (string) ($event['event'] ?? '');
            if ($event_name === 'MerchantRegistered') {
                $active_controller = AgentCart_ShopBridge_Onchain_Identity::sanitize_address(
                    $args['controller'] ?? ''
                );
                $active_hash = self::normalize_hash((string) ($args['recordHash'] ?? ''));
                if ($active_controller === '' || $active_hash === '') {
                    $errors[] = 'events_registration_invalid';
                    $state = 'invalid';
                } else {
                    $state = 'active';
                }
            } elseif ($event_name === 'MerchantUpdated') {
                $updated_hash = self::normalize_hash((string) ($args['recordHash'] ?? ''));
                if ($state !== 'active' || $updated_hash === '') {
                    $errors[] = 'events_update_without_active_record';
                    $state = 'invalid';
                } else {
                    $active_hash = $updated_hash;
                }
            } elseif ($event_name === 'ControllerChanged') {
                $new_controller = AgentCart_ShopBridge_Onchain_Identity::sanitize_address(
                    $args['newController'] ?? ''
                );
                $new_hash = self::normalize_hash((string) ($args['newRecordHash'] ?? ''));
                if ($state !== 'active' || $new_controller === '' || $new_hash === '') {
                    $errors[] = 'events_controller_change_invalid';
                    $state = 'invalid';
                } else {
                    $active_controller = $new_controller;
                    $active_hash = $new_hash;
                }
            } elseif (in_array($event_name, ['MerchantRevoked', 'MerchantForceRevoked'], true)) {
                $state = 'revoked';
            } elseif ($event_name === 'MerchantSuspended') {
                $state = 'suspended';
            } elseif ($event_name === 'MerchantUnsuspended' && $state === 'suspended') {
                $state = 'active';
            }
        }

        $errors = array_values(array_unique($errors));
        $chain_valid = empty($errors);
        $source = [
            'enabled' => true,
            'chain_valid' => false,
            'snapshot_valid' => $chain_valid,
            'canonical_chain_verified' => false,
            'verification_mode' => 'operator_snapshot',
            'complete' => ($document['complete'] ?? null) === true,
            'chain_id' => $chain_id,
            'registry_address' => $registry_address,
            'finality' => $finality,
        ];
        $current_record = [];
        if (
            $chain_valid &&
            $state === 'active' &&
            hash_equals($expected_hash, $active_hash) &&
            hash_equals($expected_controller, $active_controller)
        ) {
            $onchain_identity = [
                'standard' => (string) ($identity['standard'] ?? 'AgentCart-Onchain-Registry-v1'),
                'controller' => $expected_controller,
                'chain_id' => $expected_chain,
                'registry_address' => $expected_registry,
                'record_id' => $expected_record_id,
                'record_hash' => $expected_hash,
                'status' => 'mapped',
            ];
            $current_record = [
                'merchant_id' => (string) ($merchant['merchant_id'] ?? ''),
                'name' => (string) ($merchant['name'] ?? ''),
                'domain' => (string) ($merchant['domain'] ?? ''),
                'manifest_url' => (string) ($merchant['manifest_url'] ?? ''),
                'registry_record_hash' => $expected_hash,
                'state' => 'verified',
                'eligible' => true,
                'reason' => 'exact finalized event projection',
                'errors' => [],
                'error_count' => 0,
                'onchain_identity' => $onchain_identity,
                'match_type' => 'record_hash',
            ];
        }

        return [
            'onchain_source' => $source,
            'current_record' => $current_record,
            'errors' => $errors,
        ];
    }

    /**
     * Normalize finalized source metadata.
     *
     * @param array<string,mixed> $raw_finality Raw finality object.
     * @param array<string,mixed> $document Event document.
     * @return array<string,mixed>
     */
    private static function finality(array $raw_finality, array $document): array {
        return [
            'block_tag' => (string) ($raw_finality['block_tag'] ?? ''),
            'block_number' => intval($raw_finality['block_number'] ?? 0),
            'block_hash' => strtolower(trim((string) ($raw_finality['block_hash'] ?? ''))),
            'block_time' => (string) ($raw_finality['block_time'] ?? ''),
            'indexed_from_block' => intval($raw_finality['indexed_from_block'] ?? -1),
            'indexed_to_block' => intval($raw_finality['indexed_to_block'] ?? -1),
            'indexed_at' => (string) ($document['indexed_at'] ?? ''),
        ];
    }

    /**
     * Check that the projection is bounded by an identified finalized block.
     *
     * @param array<string,mixed> $finality Raw finality object.
     * @return bool
     */
    private static function finality_is_valid(array $finality): bool {
        $block_number = self::strict_nonnegative_int($finality['block_number'] ?? null);
        $indexed_from = self::strict_nonnegative_int($finality['indexed_from_block'] ?? null);
        $indexed_to = self::strict_nonnegative_int($finality['indexed_to_block'] ?? null);
        return ($finality['block_tag'] ?? '') === 'finalized'
            && $block_number !== null
            && $block_number > 0
            && self::is_prefixed_hash($finality['block_hash'] ?? null)
            && $indexed_from !== null
            && $indexed_to !== null
            && $indexed_to >= $indexed_from
            && $indexed_to <= $block_number;
    }

    /**
     * Return an integer only when JSON supplied an actual non-negative integer.
     *
     * @param mixed $value Candidate value.
     * @return int|null
     */
    private static function strict_nonnegative_int($value): ?int {
        return is_int($value) && $value >= 0 ? $value : null;
    }

    /**
     * Check a bytes32 hash with the canonical 0x prefix.
     *
     * @param mixed $value Candidate value.
     * @return bool
     */
    private static function is_prefixed_hash($value): bool {
        return is_string($value) && preg_match('/^0x[a-fA-F0-9]{64}$/D', $value) === 1;
    }

    /**
     * Require a canonical UTC timestamp close to the evaluation clock.
     *
     * @param mixed $value Candidate RFC3339 timestamp.
     * @param int   $reference_time Evaluation clock.
     * @return bool
     */
    private static function timestamp_is_fresh($value, int $reference_time): bool {
        if (!is_string($value) || preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/D', $value) !== 1) {
            return false;
        }
        $date = DateTimeImmutable::createFromFormat(
            '!Y-m-d\TH:i:s\Z',
            $value,
            new DateTimeZone('UTC')
        );
        $parse_errors = DateTimeImmutable::getLastErrors();
        if (
            $date === false ||
            ($parse_errors !== false && ($parse_errors['warning_count'] > 0 || $parse_errors['error_count'] > 0)) ||
            $date->format('Y-m-d\TH:i:s\Z') !== $value
        ) {
            return false;
        }
        $timestamp = $date->getTimestamp();
        return $timestamp >= $reference_time - self::MAX_EVIDENCE_AGE_SECONDS
            && $timestamp <= $reference_time + self::MAX_FUTURE_SKEW_SECONDS;
    }

    /**
     * Normalize a SHA-256 or bytes32 hash without its optional prefix.
     *
     * @param string $value Candidate hash.
     * @return string
     */
    private static function normalize_hash(string $value): string {
        $value = strtolower(trim($value));
        if (str_starts_with($value, '0x')) {
            $value = substr($value, 2);
        }
        return preg_match('/^[a-f0-9]{64}$/D', $value) === 1 ? $value : '';
    }

    /**
     * Encode the cross-runtime canonical JSON form used by both RPC paths.
     *
     * @param mixed $value JSON value.
     */
    private static function canonical_json($value): string {
        if (is_array($value)) {
            if (self::is_list($value)) {
                return '[' . implode(',', array_map([self::class, 'canonical_json'], $value)) . ']';
            }
            ksort($value, SORT_STRING);
            $members = [];
            foreach ($value as $key => $member) {
                $members[] = self::canonical_json((string) $key) . ':' . self::canonical_json($member);
            }
            return '{' . implode(',', $members) . '}';
        }
        $encoded = wp_json_encode(
            $value,
            JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION
        );
        return is_string($encoded) ? $encoded : 'null';
    }

    /**
     * WordPress 6.4-compatible list detection.
     *
     * @param array<mixed> $value Candidate list.
     */
    private static function is_list(array $value): bool {
        return $value === [] || array_keys($value) === range(0, count($value) - 1);
    }
}
