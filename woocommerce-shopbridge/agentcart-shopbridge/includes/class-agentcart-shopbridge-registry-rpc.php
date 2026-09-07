<?php
/**
 * Direct, read-only verification of the pinned merchant registry contract.
 *
 * @package AgentCart_ShopBridge
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * Verifies the exact merchant record against a fresh finalized RPC view.
 */
final class AgentCart_ShopBridge_Registry_Rpc {
    private const RESPONSE_MAX_BYTES = 1048576;
    private const ELIGIBILITY_SELECTOR = '0x46a18c77'; // phpcs:ignore PHPCompatibility.Miscellaneous.ValidIntegers.HexNumericStringFound -- ABI selector is an opaque string.
    private const RECORD_SELECTOR = '0xb5c645bd'; // phpcs:ignore PHPCompatibility.Miscellaneous.ValidIntegers.HexNumericStringFound -- ABI selectors are opaque strings.
    private const DOMAIN_RECORD_SELECTOR = '0x15daecde'; // phpcs:ignore PHPCompatibility.Miscellaneous.ValidIntegers.HexNumericStringFound -- ABI selectors are opaque strings.
    private const REVOKED_HASH_SELECTOR = '0xf30566db'; // phpcs:ignore PHPCompatibility.Miscellaneous.ValidIntegers.HexNumericStringFound -- ABI selectors are opaque strings.

    /**
     * Verify the configured identity and record at the pinned finalized chain.
     *
     * The callable and descriptor arguments exist for deterministic tests. The
     * plugin uses its deployment configuration when no override is supplied.
     *
     * @param array<string,mixed>      $identity Public merchant identity.
     * @param string                   $record_hash Canonical current record hash.
     * @param array<string,mixed>      $merchant Public merchant summary.
     * @param int|null                 $now Optional Unix evaluation time.
     * @param callable|null            $rpc Optional test RPC transport.
     * @param array<string,mixed>|null $descriptor Optional test descriptor.
     * @return array<string,mixed>
     */
    public static function verify(
        array $identity,
        string $record_hash,
        array $merchant,
        ?int $now = null,
        ?callable $rpc = null,
        ?array $descriptor = null
    ): array {
        $reference_time = $now ?? time();
        $deployment = $descriptor ?? self::configured_descriptor();
        $chain_id = AgentCart_ShopBridge_Onchain_Identity::sanitize_chain_id($identity['chain_id'] ?? '');
        $registry_address = AgentCart_ShopBridge_Onchain_Identity::sanitize_address(
            $identity['registry_address'] ?? ''
        );
        $controller = AgentCart_ShopBridge_Onchain_Identity::sanitize_address($identity['controller'] ?? '');
        $record_id = AgentCart_ShopBridge_Onchain_Identity::sanitize_record_id($identity['record_id'] ?? '');
        $expected_hash = self::normalize_hash($record_hash);
        $merchant_domain = self::normalize_domain($merchant['domain'] ?? '');
        $source = self::source(false, false, $chain_id, $registry_address, []);

        try {
            self::validate_descriptor($deployment);
            $v2 = ($deployment['registry_version'] ?? 1) === 2;
            if (
                $chain_id !== $deployment['caip2'] ||
                $registry_address !== strtolower((string) $deployment['registry_address'])
            ) {
                self::fail('rpc_identity_deployment_mismatch');
            }
            if ($controller === '' || $record_id === '' || $expected_hash === '' || $merchant_domain === '') {
                self::fail('rpc_expected_identity_invalid');
            }

            $deployment_tag = '0x' . dechex(intval($deployment['deployment_block']));
            $previous_tag = '0x' . dechex(intval($deployment['deployment_block']) - 1);
            $initial_requests = [
                ['method' => 'eth_chainId', 'params' => []],
                ['method' => 'eth_getBlockByNumber', 'params' => ['finalized', false]],
                ['method' => 'eth_getBlockByNumber', 'params' => [$deployment_tag, false]],
                ['method' => 'eth_getCode', 'params' => [$registry_address, $deployment_tag]],
                ['method' => 'eth_getCode', 'params' => [$registry_address, $previous_tag]],
                ['method' => 'web3_sha3', 'params' => ['0x' . bin2hex($merchant_domain)]],
            ];
            $initial_reads = self::request_many($rpc, (string) $deployment['rpc_url'], $initial_requests);
            if ($v2) {
                $initial_reads = self::witness_initial($rpc, $deployment, $initial_requests, $initial_reads, $reference_time);
            }
            $rpc_chain_id = self::hex_int($initial_reads[0] ?? null, 'rpc_chain_id_invalid');
            if ($rpc_chain_id !== intval($deployment['chain_id'])) {
                self::fail('rpc_chain_id_mismatch');
            }

            $finalized = $initial_reads[1] ?? null;
            $deployment_block = $initial_reads[2] ?? null;
            if (!is_array($finalized) || !is_array($deployment_block)) {
                self::fail('rpc_block_response_invalid');
            }
            $finalized_number = self::hex_int(
                $finalized['number'] ?? null,
                'rpc_finalized_block_number_invalid'
            );
            $finalized_timestamp = self::hex_int(
                $finalized['timestamp'] ?? null,
                'rpc_finalized_block_time_invalid'
            );
            $finalized_hash = self::prefixed_hash(
                $finalized['hash'] ?? null,
                'rpc_finalized_block_hash_invalid'
            );
            $finalized_ref = [
                'blockHash' => $finalized_hash,
                'requireCanonical' => true,
            ];
            if ($finalized_number < intval($deployment['deployment_block'])) {
                self::fail('rpc_finalized_block_before_deployment');
            }
            if ($finalized_timestamp < $reference_time - intval($deployment['max_finality_age_seconds'])) {
                self::fail('rpc_finalized_block_time_stale');
            }
            if ($finalized_timestamp > $reference_time + intval($deployment['max_future_skew_seconds'])) {
                self::fail('rpc_finalized_block_time_future');
            }
            if (
                self::hex_int($deployment_block['number'] ?? null, 'rpc_deployment_block_number_invalid') !==
                    intval($deployment['deployment_block']) ||
                self::prefixed_hash(
                    $deployment_block['hash'] ?? null,
                    'rpc_deployment_block_hash_invalid'
                ) !== strtolower((string) $deployment['deployment_block_hash'])
            ) {
                self::fail('rpc_deployment_block_hash_mismatch');
            }

            $code_at_deployment = $initial_reads[3] ?? null;
            $code_before_deployment = $initial_reads[4] ?? null;
            if ($code_before_deployment !== '0x') {
                self::fail('rpc_deployment_not_creation_boundary');
            }
            $expected_domain_hash = self::prefixed_hash(
                $initial_reads[5] ?? null,
                'rpc_domain_hash_invalid'
            );

            $state_requests = [
                ['method' => 'eth_getCode', 'params' => [$registry_address, $finalized_ref]],
                [
                    'method' => 'eth_call',
                    'params' => [
                        [
                            'to' => $registry_address,
                            'data' => self::RECORD_SELECTOR . substr($record_id, 2),
                        ],
                        $finalized_ref,
                    ],
                ],
                [
                    'method' => 'eth_call',
                    'params' => [
                        [
                            'to' => $registry_address,
                            'data' => self::DOMAIN_RECORD_SELECTOR . substr($expected_domain_hash, 2),
                        ],
                        $finalized_ref,
                    ],
                ],
                [
                    'method' => 'eth_call',
                    'params' => [
                        [
                            'to' => $registry_address,
                            'data' => self::REVOKED_HASH_SELECTOR . $expected_hash,
                        ],
                        $finalized_ref,
                    ],
                ],
            ];
            if ($v2) {
                $state_requests[] = [
                    'method' => 'eth_call',
                    'params' => [
                        ['to' => $registry_address, 'data' => self::ELIGIBILITY_SELECTOR . substr($record_id, 2)],
                        $finalized_ref,
                    ],
                ];
            }
            $state_reads = self::request_many($rpc, (string) $deployment['rpc_url'], $state_requests);
            if ($v2) {
                $witness = self::request_many($rpc, (string) $deployment['witness_rpc_url'], $state_requests);
                self::require_agreement($state_reads, $witness);
            }
            $code_at_finality = $state_reads[0] ?? null;
            if (!self::has_code($code_at_deployment) || !self::has_code($code_at_finality)) {
                self::fail('rpc_registry_code_missing');
            }
            $expected_runtime_hash = strtolower((string) $deployment['runtime_code_sha256']);
            if (
                self::code_sha256($code_at_deployment) !== $expected_runtime_hash ||
                self::code_sha256($code_at_finality) !== $expected_runtime_hash
            ) {
                self::fail('rpc_runtime_code_hash_mismatch');
            }

            $record_result = $state_reads[1] ?? null;
            $record = self::decode_record($record_result);
            if ($record['controller'] !== $controller) {
                self::fail('rpc_record_controller_mismatch');
            }
            if ($record['record_hash'] !== $expected_hash) {
                self::fail('rpc_record_hash_mismatch');
            }
            if ($record['domain_hash'] !== $expected_domain_hash) {
                self::fail('rpc_record_domain_hash_mismatch');
            }
            if ($record['status'] !== 1) {
                self::fail('rpc_record_not_active');
            }

            $mapped_record_id = self::word_result(
                $state_reads[2] ?? null,
                'rpc_domain_record_result_invalid'
            );
            if ('0x' . $mapped_record_id !== $record_id) {
                self::fail('rpc_domain_record_id_mismatch');
            }
            $revoked = self::word_result(
                $state_reads[3] ?? null,
                'rpc_revoked_hash_result_invalid'
            );
            if (preg_match('/^0{64}$/D', $revoked) !== 1) {
                self::fail('rpc_record_hash_revoked');
            }
            $admission = $v2 ? self::decode_admission($state_reads[4] ?? null, $reference_time) : [];
            $finality = [
                'block_tag' => 'finalized',
                'block_number' => $finalized_number,
                'block_hash' => $finalized_hash,
                'block_time' => gmdate('Y-m-d\TH:i:s\Z', $finalized_timestamp),
                'state_selector' => 'block_hash_require_canonical',
            ];
            $source = self::source(true, true, $chain_id, $registry_address, $finality);
            if ($v2) {
                $source['registry_version'] = 2;
                $source['deployment_fingerprint'] = self::descriptor_fingerprint($deployment);
                $source['witness_agreement'] = true;
            }
            $onchain_identity = [
                'standard' => (string) ($identity['standard'] ?? 'AgentCart-Onchain-Registry-v1'),
                'controller' => $controller,
                'chain_id' => $chain_id,
                'registry_address' => $registry_address,
                'record_id' => $record_id,
                'record_hash' => $expected_hash,
                'status' => 'mapped',
            ];
            return [
                'onchain_source' => $source,
                'current_record' => [
                    'merchant_id' => (string) ($merchant['merchant_id'] ?? ''),
                    'name' => (string) ($merchant['name'] ?? ''),
                    'domain' => $merchant_domain,
                    'manifest_url' => (string) ($merchant['manifest_url'] ?? ''),
                    'registry_record_hash' => $expected_hash,
                    'state' => 'verified',
                    'eligible' => true,
                    'reason' => $v2
                        ? 'exact finalized record and current admission agreed by two configured RPCs'
                        : 'exact block-hash-pinned finalized state through the pinned RPC',
                    'errors' => [],
                    'error_count' => 0,
                    'onchain_identity' => $onchain_identity,
                    'match_type' => 'record_hash',
                    'admission' => $admission,
                ],
                'errors' => [],
            ];
        } catch (Throwable $error) {
            $code = preg_match('/^rpc_[a-z0-9_]+$/D', $error->getMessage()) === 1
                ? $error->getMessage()
                : 'rpc_request_failed';
            return [
                'onchain_source' => $source,
                'current_record' => [],
                'errors' => [$code],
            ];
        }
    }

    /**
     * Read the operator-managed descriptor, never merchant HTTP metadata.
     *
     * @return array<string,mixed>
     */
    public static function configured_descriptor(): array {
        if (!defined('AGENTCART_REGISTRY_V2_DEPLOYMENT')) {
            return self::tempo_moderato_descriptor();
        }
        $raw = constant('AGENTCART_REGISTRY_V2_DEPLOYMENT');
        $descriptor = is_string($raw) ? json_decode($raw, true) : $raw;
        if (!is_array($descriptor) || ($descriptor['registry_version'] ?? null) !== 2) {
            return ['registry_version' => 2]; // Invalid explicit configuration fails closed.
        }
        return $descriptor;
    }

    /**
     * Bind cached evidence to the entire reviewed configuration, including RPCs.
     *
     * @param array<string,mixed> $descriptor Deployment configuration.
     * @return string
     */
    public static function descriptor_fingerprint(array $descriptor): string {
        ksort($descriptor);
        return hash('sha256', (string) wp_json_encode($descriptor, JSON_UNESCAPED_SLASHES));
    }

    /**
     * Require a public HTTPS RPC hostname; WordPress also checks resolved IPs.
     *
     * @param mixed $url Candidate endpoint.
     * @return string
     */
    private static function public_rpc_host($url): string {
        $parts = is_string($url) ? wp_parse_url($url) : false;
        $host = is_array($parts) ? strtolower((string) ($parts['host'] ?? '')) : '';
        if (!is_array($parts) || ($parts['scheme'] ?? '') !== 'https' ||
            isset($parts['user']) || isset($parts['pass']) || isset($parts['fragment']) ||
            (isset($parts['port']) && $parts['port'] !== 443) ||
            self::normalize_domain($host) !== $host || strpos($host, '.') === false ||
            filter_var($host, FILTER_VALIDATE_IP) !== false || str_ends_with($host, '.localhost')) {
            self::fail('rpc_public_https_endpoint_required');
        }
        return $host;
    }

    /**
     * Check both finalized heads and choose the lower common canonical boundary.
     *
     * @param callable|null                  $rpc Test transport.
     * @param array<string,mixed>            $deployment Pinned deployment.
     * @param array<int,array<string,mixed>> $requests Initial reads.
     * @param array<int,mixed>               $primary Primary results.
     * @param int                            $now Evaluation time.
     * @return array<int,mixed>
     */
    private static function witness_initial(?callable $rpc, array $deployment, array $requests, array $primary, int $now): array {
        $witness = self::request_many($rpc, (string) $deployment['witness_rpc_url'], $requests);
        $primary_head = self::block_boundary($primary[1] ?? null);
        $witness_head = self::block_boundary($witness[1] ?? null);
        foreach ([$primary_head, $witness_head] as $head) {
            if ($head['timestamp'] < $now - $deployment['max_finality_age_seconds'] ||
                $head['timestamp'] > $now + $deployment['max_future_skew_seconds']) {
                self::fail('rpc_witness_finality_not_fresh');
            }
        }
        $number = min($primary_head['number'], $witness_head['number']);
        $request = [['method' => 'eth_getBlockByNumber', 'params' => ['0x' . dechex($number), false]]];
        $left = self::request_many($rpc, (string) $deployment['rpc_url'], $request)[0] ?? null;
        $right = self::request_many($rpc, (string) $deployment['witness_rpc_url'], $request)[0] ?? null;
        $boundary = self::block_boundary($left);
        self::require_agreement($boundary, self::block_boundary($right));
        if ($boundary['number'] !== $number ||
            ($primary_head['number'] === $number && $primary_head !== $boundary) ||
            ($witness_head['number'] === $number && $witness_head !== $boundary)) {
            self::fail('rpc_witness_finality_mismatch');
        }
        $primary[1] = $left;
        $witness[1] = $left;
        // Providers may expose different extra header fields, which are not evidence.
        self::require_agreement(self::block_boundary($primary[2] ?? null), self::block_boundary($witness[2] ?? null));
        $witness[2] = $primary[2];
        self::require_agreement($primary, $witness);
        return $primary;
    }

    /**
     * Normalize the header fields used as verification evidence.
     *
     * @param mixed $block RPC block.
     * @return array<string,mixed>
     */
    private static function block_boundary($block): array {
        if (!is_array($block)) {
            self::fail('rpc_block_response_invalid');
        }
        return [
            'number' => self::hex_int($block['number'] ?? null, 'rpc_block_number_invalid'),
            'hash' => self::prefixed_hash($block['hash'] ?? null, 'rpc_block_hash_invalid'),
            'timestamp' => self::hex_int($block['timestamp'] ?? null, 'rpc_block_time_invalid'),
        ];
    }

    /**
     * Fail closed on any disagreement, including differently encoded state.
     *
     * @param array<mixed> $primary Primary view.
     * @param array<mixed> $witness Witness view.
     */
    private static function require_agreement(array $primary, array $witness): void {
        if ($primary !== $witness) {
            self::fail('rpc_witness_disagreement');
        }
    }

    /**
     * Decode contract eligibility without rounding uint256 bond amounts.
     *
     * @param mixed $value ABI response.
     * @param int   $now Evaluation time.
     * @return array<string,mixed>
     */
    private static function decode_admission($value, int $now): array {
        if (!is_string($value) || preg_match('/^0x[a-fA-F0-9]{256}$/D', $value) !== 1) {
            self::fail('rpc_admission_result_invalid');
        }
        $hex = strtolower(substr($value, 2));
        $eligible = self::word_int(self::word($hex, 0), 'rpc_admission_boolean_invalid');
        $entity = self::word($hex, 1);
        $expires = self::word_int(self::word($hex, 2), 'rpc_admission_expiry_invalid');
        $bond = self::word($hex, 3);
        if ($eligible !== 1 || trim($entity, '0') === '' || trim($bond, '0') === '') {
            self::fail('rpc_admission_ineligible');
        }
        if ($expires <= $now) {
            self::fail('rpc_admission_expired');
        }
        return [
			'eligible' => true, 'entity_id' => '0x' . $entity,
            'expires_at' => $expires, 'bond_base_units_hex' => '0x' . $bond,
		];
    }

    /**
     * Return the immutable Tempo Moderato deployment descriptor.
     *
     * @return array<string,mixed>
     */
    private static function tempo_moderato_descriptor(): array {
        return [
            'id' => 'tempo-moderato',
            'chain_id' => 42431,
            'caip2' => 'eip155:42431',
            'registry_address' => '0x0965961617c5b0898167aa4034c5511db0efca07', // phpcs:ignore PHPCompatibility.Miscellaneous.ValidIntegers.HexNumericStringFound -- Contract address is an opaque string.
            'deployment_block' => 30731101,
            'deployment_block_hash' => '0x8646ecbbb11ac5cf6195dd7e288acb2541f02ef0d580e3bc9afa2e42045edd26', // phpcs:ignore PHPCompatibility.Miscellaneous.ValidIntegers.HexNumericStringFound -- Block hash is an opaque string.
            'runtime_code_sha256' => '3d15aed6f0419451ef151e85662199f9f9958a11487198ad971e0bba8bdda37b',
            'rpc_url' => 'https://rpc.moderato.tempo.xyz',
            'max_finality_age_seconds' => 600,
            'max_future_skew_seconds' => 300,
        ];
    }

    /**
     * Validate a deployment descriptor before any RPC request.
     *
     * @param array<string,mixed> $descriptor Candidate descriptor.
     */
    private static function validate_descriptor(array $descriptor): void {
        if (
            !in_array($descriptor['registry_version'] ?? 1, [1, 2], true) ||
            !is_int($descriptor['chain_id'] ?? null) ||
            $descriptor['chain_id'] <= 0 ||
            ($descriptor['caip2'] ?? '') !== 'eip155:' . $descriptor['chain_id'] ||
            AgentCart_ShopBridge_Onchain_Identity::sanitize_address(
                $descriptor['registry_address'] ?? ''
            ) === '' ||
            !is_int($descriptor['deployment_block'] ?? null) ||
            intval($descriptor['deployment_block']) <= 0 ||
            !self::is_prefixed_hash($descriptor['deployment_block_hash'] ?? null) ||
            preg_match('/^[a-f0-9]{64}$/D', (string) ($descriptor['runtime_code_sha256'] ?? '')) !== 1 ||
            !is_int($descriptor['max_finality_age_seconds'] ?? null) ||
            intval($descriptor['max_finality_age_seconds']) <= 0 ||
            intval($descriptor['max_finality_age_seconds']) > 600 ||
            !is_int($descriptor['max_future_skew_seconds'] ?? null) ||
            intval($descriptor['max_future_skew_seconds']) < 0 ||
            intval($descriptor['max_future_skew_seconds']) > 300 ||
            !is_string($descriptor['rpc_url'] ?? null)
        ) {
            self::fail('rpc_deployment_descriptor_invalid');
        }
        if (($descriptor['registry_version'] ?? 1) === 2) {
            $primary_host = self::public_rpc_host($descriptor['rpc_url']);
            $witness_host = self::public_rpc_host($descriptor['witness_rpc_url'] ?? null);
            if ($primary_host === $witness_host) {
                self::fail('rpc_witness_must_be_distinct');
            }
        }
    }

    /**
     * Build normalized source evidence.
     *
     * @param bool                $valid Whether canonical state passed.
     * @param bool                $complete Whether all required reads passed.
     * @param string              $chain_id Expected CAIP-2 chain id.
     * @param string              $registry_address Registry contract address.
     * @param array<string,mixed> $finality Finalized block evidence.
     * @return array<string,mixed>
     */
    private static function source(
        bool $valid,
        bool $complete,
        string $chain_id,
        string $registry_address,
        array $finality
    ): array {
        return [
            'enabled' => true,
            'chain_valid' => $valid,
            'snapshot_valid' => $valid,
            'canonical_chain_verified' => $valid,
            'verification_mode' => 'direct_rpc',
            'complete' => $complete,
            'chain_id' => $chain_id,
            'registry_address' => $registry_address,
            'finality' => $finality,
        ];
    }

    /**
     * Decode the fixed registry Record tuple.
     *
     * @param mixed $value Raw eth_call result.
     * @return array{controller:string,record_hash:string,domain_hash:string,status:int}
     */
    private static function decode_record($value): array {
        if (!is_string($value) || preg_match('/^0x[a-fA-F0-9]{576}$/D', $value) !== 1) {
            self::fail('rpc_record_result_invalid');
        }
        $hex = strtolower(substr($value, 2));
        $controller_word = self::word($hex, 0);
        if (preg_match('/^0{24}[a-f0-9]{40}$/D', $controller_word) !== 1) {
            self::fail('rpc_record_controller_padding_invalid');
        }
        $controller = AgentCart_ShopBridge_Onchain_Identity::sanitize_address(
            '0x' . substr($controller_word, 24)
        );
        if ($controller === '') {
            self::fail('rpc_record_controller_invalid');
        }
        return [
            'controller' => $controller,
            'record_hash' => self::word($hex, 1),
            'domain_hash' => '0x' . self::word($hex, 2),
            'status' => self::word_int(self::word($hex, 8), 'rpc_record_status_invalid'),
        ];
    }

    private static function word(string $hex, int $index): string {
        return substr($hex, $index * 64, 64);
    }

    private static function word_result($value, string $error): string {
        if (!is_string($value) || preg_match('/^0x[a-fA-F0-9]{64}$/D', $value) !== 1) {
            self::fail($error);
        }
        return strtolower(substr($value, 2));
    }

    private static function word_int(string $word, string $error): int {
        if (preg_match('/^[a-f0-9]{64}$/D', $word) !== 1) {
            self::fail($error);
        }
        $trimmed = ltrim($word, '0');
        if (strlen($trimmed) > 15) {
            self::fail($error);
        }
        return $trimmed === '' ? 0 : intval(hexdec($trimmed));
    }

    private static function hex_int($value, string $error): int {
        if (!is_string($value) || preg_match('/^0x(?:0|[1-9a-fA-F][a-fA-F0-9]*)$/D', $value) !== 1) {
            self::fail($error);
        }
        $digits = substr($value, 2);
        if (strlen($digits) > 15) {
            self::fail($error);
        }
        return intval(hexdec($digits));
    }

    private static function prefixed_hash($value, string $error): string {
        if (!self::is_prefixed_hash($value)) {
            self::fail($error);
        }
        return strtolower((string) $value);
    }

    private static function is_prefixed_hash($value): bool {
        return is_string($value) && preg_match('/^0x[a-fA-F0-9]{64}$/D', $value) === 1;
    }

    private static function has_code($value): bool {
        return is_string($value) && preg_match('/^0x(?:[a-fA-F0-9]{2})+$/D', $value) === 1 &&
            !in_array(strtolower($value), ['0x00'], true); // phpcs:ignore PHPCompatibility.Miscellaneous.ValidIntegers.HexNumericStringFound -- Empty bytecode is an opaque RPC string.
    }

    private static function code_sha256($value): string {
        if (!is_string($value) || preg_match('/^0x(?:[a-fA-F0-9]{2})+$/D', $value) !== 1) {
            self::fail('rpc_runtime_code_invalid');
        }
        $bytes = hex2bin(substr($value, 2));
        if ($bytes === false) {
            self::fail('rpc_runtime_code_invalid');
        }
        return hash('sha256', $bytes);
    }

    private static function normalize_hash(string $value): string {
        $value = strtolower(trim($value));
        if (str_starts_with($value, '0x')) {
            $value = substr($value, 2);
        }
        return preg_match('/^[a-f0-9]{64}$/D', $value) === 1 ? $value : '';
    }

    /**
     * Normalize an ASCII hostname exactly like the buyer-side verifier.
     *
     * IDN A-labels remain rejected until every verifier runtime shares one
     * pinned UTS-46 implementation.
     *
     * @param mixed $value Candidate hostname.
     */
    private static function normalize_domain($value): string {
        if (!is_string($value)) {
            return '';
        }
        $domain = strtolower(trim($value));
        if (str_ends_with($domain, '.')) {
            $domain = substr($domain, 0, -1);
        }
        if (
            $domain === '' ||
            strlen($domain) > 253 ||
            preg_match('/^[\x00-\x7f]+$/D', $domain) !== 1
        ) {
            return '';
        }
        foreach (explode('.', $domain) as $label) {
            if (
                $label === '' ||
                strlen($label) > 63 ||
                str_starts_with($label, 'xn--') ||
                preg_match('/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/D', $label) !== 1
            ) {
                return '';
            }
        }
        return $domain;
    }

    /**
     * Execute deterministic reads, batching the production transport into one
     * HTTP request while keeping a simple callable seam for behavior tests.
     *
     * @param callable|null                  $rpc Optional test transport.
     * @param string                         $url Fixed RPC URL.
     * @param array<int,array<string,mixed>> $requests Ordered JSON-RPC requests.
     * @return array<int,mixed>
     */
    private static function request_many(?callable $rpc, string $url, array $requests): array {
        if ($rpc === null) {
            return self::call_rpc_batch($url, $requests);
        }
        $results = [];
        foreach ($requests as $request) {
            if (
                !is_string($request['method'] ?? null) ||
                !is_array($request['params'] ?? null)
            ) {
                self::fail('rpc_request_invalid');
            }
            $results[] = $rpc($request['method'], $request['params'], $url);
        }
        return $results;
    }

    /**
     * Execute an ordered JSON-RPC batch and reject missing, duplicate, errored,
     * or unexpected response ids.
     *
     * @param string                         $url Fixed RPC URL.
     * @param array<int,array<string,mixed>> $requests Ordered requests.
     * @return array<int,mixed>
     */
    private static function call_rpc_batch(string $url, array $requests): array {
        if (!function_exists('wp_remote_post')) {
            self::fail('rpc_wordpress_transport_unavailable');
        }
        if ($requests === []) {
            self::fail('rpc_request_invalid');
        }
        $payload = [];
        foreach (array_values($requests) as $index => $request) {
            if (
                !is_string($request['method'] ?? null) ||
                !is_array($request['params'] ?? null)
            ) {
                self::fail('rpc_request_invalid');
            }
            $payload[] = [
                'jsonrpc' => '2.0',
                'id' => $index + 1,
                'method' => $request['method'],
                'params' => $request['params'],
            ];
        }
        $encoded = wp_json_encode($payload, JSON_UNESCAPED_SLASHES);
        if (!is_string($encoded)) {
            self::fail('rpc_request_invalid');
        }
        $response = wp_remote_post($url, [
            'timeout' => 8,
            'redirection' => 0,
            'reject_unsafe_urls' => true,
            'limit_response_size' => self::RESPONSE_MAX_BYTES + 1,
            'headers' => [
                'Accept' => 'application/json',
                'Content-Type' => 'application/json',
            ],
            'body' => $encoded,
        ]);
        if (is_wp_error($response)) {
            self::fail('rpc_request_failed');
        }
        $status = intval(wp_remote_retrieve_response_code($response));
        $body = (string) wp_remote_retrieve_body($response);
        if ($status < 200 || $status >= 300 || strlen($body) > self::RESPONSE_MAX_BYTES) {
            self::fail('rpc_response_invalid');
        }
        $decoded = json_decode($body, true);
        if (!is_array($decoded) || !self::is_list($decoded) || count($decoded) !== count($payload)) {
            self::fail('rpc_response_invalid');
        }
        $by_id = [];
        foreach ($decoded as $item) {
            $id = is_array($item) ? ($item['id'] ?? null) : null;
            if (
                !is_int($id) ||
                $id < 1 ||
                $id > count($payload) ||
                array_key_exists($id, $by_id) ||
                ($item['jsonrpc'] ?? '') !== '2.0' ||
                array_key_exists('error', $item) ||
                !array_key_exists('result', $item)
            ) {
                self::fail('rpc_response_invalid');
            }
            $by_id[$id] = $item['result'];
        }
        $results = [];
        foreach ($payload as $item) {
            $results[] = $by_id[$item['id']];
        }
        return $results;
    }

    private static function fail(string $code): void {
        throw new RuntimeException($code); // phpcs:ignore WordPress.Security.EscapeOutput.ExceptionNotEscaped -- Fixed internal error codes are caught and never rendered directly.
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
