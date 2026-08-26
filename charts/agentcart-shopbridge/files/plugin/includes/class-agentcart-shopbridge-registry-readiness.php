<?php
/**
 * Truthful merchant registry readiness derived from finalized public evidence.
 *
 * @package AgentCart_ShopBridge
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * Evaluates metadata, identity, and exact finalized inclusion as separate states.
 */
final class AgentCart_ShopBridge_Registry_Readiness {
    private const MAX_EVIDENCE_AGE_SECONDS = 600;
    private const MAX_FUTURE_SKEW_SECONDS = 300;

    /**
     * Evaluate the current merchant registry state.
     *
     * @param bool                $metadata_ready Whether HTTPS metadata is valid.
     * @param array<string,mixed> $identity Complete public onchain identity.
     * @param string              $record_hash Current canonical record hash.
     * @param array<string,mixed> $health Last registry health response.
     * @param int|null            $now Optional Unix timestamp for deterministic evaluation.
     * @return array<string,mixed>
     */
    public static function evaluate(
        bool $metadata_ready,
        array $identity,
        string $record_hash,
        array $health,
        ?int $now = null
    ): array {
        $reference_time = $now ?? time();
        if (!$metadata_ready) {
            return self::result('metadata_incomplete', false, 'Publish the manifest and domain proof over HTTPS.');
        }
        foreach (['controller', 'chain_id', 'registry_address', 'record_id'] as $field) {
            if (trim((string) ($identity[$field] ?? '')) === '') {
                return self::result('identity_required', false, 'Run enrollment preparation and save the four public registry identity fields.');
            }
        }
        if ($health === []) {
            return self::result('not_checked', false, 'Check registry health after submitting the wallet transaction.');
        }

        $current_hash = self::normalize_hash($record_hash);
        $checked_hash = self::normalize_hash((string) ($health['record_hash'] ?? ''));
        if ($checked_hash !== '' && $checked_hash !== $current_hash) {
            return self::result('onchain_update_required', false, 'The shop record changed after the last onchain check. Prepare and sign an update.');
        }

        $health_body = is_array($health['health'] ?? null) ? $health['health'] : [];
        $source = is_array($health_body['onchain_source'] ?? null) ? $health_body['onchain_source'] : [];
        $finality = is_array($source['finality'] ?? null) ? $source['finality'] : [];
        $source_valid = !empty($source['enabled'])
            && !empty($source['chain_valid'])
            && !empty($source['canonical_chain_verified'])
            && ($source['verification_mode'] ?? '') === 'direct_rpc'
            && !empty($source['complete'])
            && hash_equals((string) $identity['chain_id'], (string) ($source['chain_id'] ?? ''))
            && hash_equals(strtolower((string) $identity['registry_address']), strtolower((string) ($source['registry_address'] ?? '')))
            && (string) ($finality['block_tag'] ?? '') === 'finalized'
            && (string) ($finality['state_selector'] ?? '') === 'block_hash_require_canonical'
            && intval($finality['block_number'] ?? 0) > 0
            && preg_match('/^0x[a-f0-9]{64}$/D', strtolower((string) ($finality['block_hash'] ?? ''))) === 1
            && self::timestamp_is_fresh($health['checked_at'] ?? null, $reference_time)
            && self::timestamp_is_fresh($finality['block_time'] ?? null, $reference_time);
        if (!$source_valid) {
            return self::result('source_unverified', false, 'The plugin did not verify fresh block-hash-pinned finalized contract state through the pinned RPC.');
        }

        $record = is_array($health_body['current_record'] ?? null) ? $health_body['current_record'] : [];
        if ($record === [] || (string) ($record['match_type'] ?? '') !== 'record_hash') {
            return self::result('not_included', false, 'The current record hash is not in the finalized registry projection.');
        }
        $onchain_identity = is_array($record['onchain_identity'] ?? null) ? $record['onchain_identity'] : [];
        $identity_matches = self::normalize_hash((string) ($record['registry_record_hash'] ?? '')) === $current_hash
            && self::normalize_hash((string) ($onchain_identity['record_hash'] ?? '')) === $current_hash
            && hash_equals(strtolower((string) $identity['controller']), strtolower((string) ($onchain_identity['controller'] ?? '')))
            && hash_equals((string) $identity['chain_id'], (string) ($onchain_identity['chain_id'] ?? ''))
            && hash_equals(strtolower((string) $identity['registry_address']), strtolower((string) ($onchain_identity['registry_address'] ?? '')))
            && hash_equals(strtolower((string) $identity['record_id']), strtolower((string) ($onchain_identity['record_id'] ?? '')));
        if (!$identity_matches || ($record['state'] ?? '') !== 'verified' || empty($record['eligible'])) {
            return self::result('not_included', false, 'The finalized registry entry does not exactly match the current merchant identity and record.');
        }

        $result = self::result('finalized_current', true, 'The exact current record is active at one canonical finalized block through the pinned RPC.');
        $result['finality'] = $finality;
        return $result;
    }

    /**
     * Build a stable state result.
     *
     * @param string $state State code.
     * @param bool   $ready Finalized readiness.
     * @param string $message Merchant-facing explanation.
     * @return array<string,mixed>
     */
    private static function result(string $state, bool $ready, string $message): array {
        return [
            'state'   => $state,
            'ready'   => $ready,
            'message' => $message,
        ];
    }

    /**
     * Normalize a SHA-256 hash for exact comparisons.
     *
     * @param string $value Hash with or without 0x.
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
}
