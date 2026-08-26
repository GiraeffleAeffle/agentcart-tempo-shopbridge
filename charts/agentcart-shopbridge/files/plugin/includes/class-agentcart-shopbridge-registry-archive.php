<?php
/**
 * Immutable storage primitives for merchant-owned registry records.
 *
 * @package AgentCart_ShopBridge
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * Maps registry record hashes to stable public paths and archive entries.
 */
final class AgentCart_ShopBridge_Registry_Archive {
    private const PUBLIC_PATH_PREFIX = '/.well-known/agentcart-registry-records/';

    /**
     * Return the immutable public path for a registry record hash.
     *
     * @param string $record_hash Lowercase SHA-256 hash without a prefix.
     * @return string
     */
    public static function immutable_path(string $record_hash): string {
        self::assert_valid_hash($record_hash);

        return self::PUBLIC_PATH_PREFIX . $record_hash . '.json';
    }

    /**
     * Parse an immutable record path.
     *
     * @param string $path Request path.
     * @return string Empty when the path does not match.
     */
    public static function hash_from_path(string $path): string {
        $pattern = '#^' . preg_quote(self::PUBLIC_PATH_PREFIX, '#') . '([a-f0-9]{64})\.json$#D';
        if (preg_match($pattern, $path, $matches) !== 1) {
            return '';
        }

        return $matches[1];
    }

    /**
     * Add a record to an append-only archive.
     *
     * @param array<string,array<string,mixed>> $archive Existing archive.
     * @param string                            $record_hash Lowercase SHA-256 hash.
     * @param array<string,mixed>               $record Canonical registry record.
     * @param string                            $archived_at RFC 3339 timestamp.
     * @return array<string,array<string,mixed>>
     * @throws RuntimeException When an existing hash maps to different content.
     */
    public static function put(array $archive, string $record_hash, array $record, string $archived_at): array {
        self::assert_valid_hash($record_hash);

        if (isset($archive[$record_hash])) {
            if (($archive[$record_hash]['record'] ?? null) !== $record) {
                throw new RuntimeException('immutable registry record hash collision');
            }

            return $archive;
        }

        $archive[$record_hash] = [
            'record_hash' => $record_hash,
            'record'      => $record,
            'archived_at' => $archived_at,
        ];

        return $archive;
    }

    /**
     * Read an archived registry record.
     *
     * @param array<string,array<string,mixed>> $archive Existing archive.
     * @param string                            $record_hash Lowercase SHA-256 hash.
     * @return array<string,mixed>|null
     */
    public static function get(array $archive, string $record_hash): ?array {
        self::assert_valid_hash($record_hash);

        return $archive[$record_hash] ?? null;
    }

    /**
     * Validate a public registry record hash.
     *
     * @param string $record_hash Candidate hash.
     * @return void
     * @throws InvalidArgumentException When the record hash is invalid.
     */
    private static function assert_valid_hash(string $record_hash): void {
        if (preg_match('/^[a-f0-9]{64}$/D', $record_hash) !== 1) {
            throw new InvalidArgumentException('registry record hash must be 64 lowercase hex characters');
        }
    }
}
