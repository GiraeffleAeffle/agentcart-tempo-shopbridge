<?php
/**
 * Canonical public identity for the AgentCart onchain merchant registry.
 *
 * @package AgentCart_ShopBridge
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * Validates public registry identity without handling wallet secrets.
 */
final class AgentCart_ShopBridge_Onchain_Identity {
    /**
     * Compose an all-or-none identity document.
     *
     * @param string $controller Public controller address.
     * @param string $chain_id CAIP-2 EVM chain id.
     * @param string $registry_address Public registry contract address.
     * @param string $record_id Deterministic registry record id.
     * @return array<string,string>
     */
    public static function compose(string $controller, string $chain_id, string $registry_address, string $record_id): array {
        $identity = [
            'controller'       => self::sanitize_address($controller),
            'chain_id'         => self::sanitize_chain_id($chain_id),
            'registry_address' => self::sanitize_address($registry_address),
            'record_id'        => self::sanitize_record_id($record_id),
        ];
        if (in_array('', $identity, true)) {
            return [];
        }

        $identity['standard'] = 'AgentCart-Onchain-Registry-v1';
        return $identity;
    }

    /**
     * Canonicalize a nonzero EVM address.
     *
     * @param mixed $value Candidate address.
     * @return string
     */
    public static function sanitize_address($value): string {
        $value = strtolower(trim((string) $value));
        if (preg_match('/^0x[a-f0-9]{40}$/D', $value) !== 1 || $value === '0x' . str_repeat('0', 40)) {
            return '';
        }
        return $value;
    }

    /**
     * Validate a canonical CAIP-2 EVM chain id.
     *
     * @param mixed $value Candidate chain id.
     * @return string
     */
    public static function sanitize_chain_id($value): string {
        $value = trim((string) $value);
        if (preg_match('/^eip155:([1-9][0-9]*)$/D', $value, $matches) !== 1) {
            return '';
        }
        return 'eip155:' . $matches[1];
    }

    /**
     * Canonicalize a nonzero bytes32 record id.
     *
     * @param mixed $value Candidate record id.
     * @return string
     */
    public static function sanitize_record_id($value): string {
        $value = strtolower(trim((string) $value));
        if (preg_match('/^0x[a-f0-9]{64}$/D', $value) !== 1 || $value === '0x' . str_repeat('0', 64)) {
            return '';
        }
        return $value;
    }
}
