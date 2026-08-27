<?php
/**
 * Canonical, bounded category routing hints committed by a Registry Record.
 */

if (!defined('ABSPATH')) {
    exit;
}

final class AgentCart_ShopBridge_Discovery_Facets {
    const SCHEMA = 'agentcart.discovery_facets.v1';
    const TAXONOMY = 'woocommerce-product-category-slug-v1';
    const SOURCE = 'exposed_catalog_snapshot';
    const MAX_CATEGORIES = 8;

    public static function from_exposure_snapshot($snapshot) {
        $snapshot = is_array($snapshot) ? $snapshot : [];
        $products = is_array($snapshot['products'] ?? null) ? $snapshot['products'] : [];
        $counts = [];
        foreach ($products as $product) {
            if (!is_array($product)) {
                continue;
            }
            $categories = is_array($product['category_slugs'] ?? null) ? $product['category_slugs'] : [];
            foreach (array_unique($categories) as $raw_category) {
                $category = self::normalize_category($raw_category);
                if ($category === '') {
                    continue;
                }
                $counts[$category] = intval($counts[$category] ?? 0) + 1;
            }
        }
        if (!$counts) {
            return [];
        }
        $ranked = array_keys($counts);
        usort($ranked, static function ($left, $right) use ($counts) {
            $frequency = $counts[$right] <=> $counts[$left];
            return $frequency !== 0 ? $frequency : strcmp($left, $right);
        });
        $selected = array_slice($ranked, 0, self::MAX_CATEGORIES);
        sort($selected, SORT_STRING);
        $truncated = count($ranked) > count($selected);
        return [
            'schema' => self::SCHEMA,
            'taxonomy' => self::TAXONOMY,
            'source' => self::SOURCE,
            'categories' => $selected,
            'category_count_total' => count($ranked),
            'coverage' => $truncated ? 'partial' : 'complete',
            'truncated' => $truncated,
        ];
    }

    public static function normalize_category($value) {
        $value = strtolower(trim((string) $value));
        $value = str_replace('_', '-', $value);
        $value = preg_replace('/\s+/', '-', $value);
        $value = preg_replace('/-+/', '-', (string) $value);
        $value = trim((string) $value, '-');
        if ($value === '' || strlen($value) > 64 || !preg_match('/^[a-z0-9]+(?:-[a-z0-9]+)*$/', $value)) {
            return '';
        }
        return $value;
    }

    public static function validate($facets) {
        if ($facets === null) {
            return [];
        }
        if (!is_array($facets)) {
            return ['discovery_facets_must_be_object'];
        }
        $errors = [];
        if (($facets['schema'] ?? '') !== self::SCHEMA) {
            $errors[] = 'discovery_facets_schema_unsupported';
        }
        if (($facets['taxonomy'] ?? '') !== self::TAXONOMY) {
            $errors[] = 'discovery_facets_taxonomy_unsupported';
        }
        if (($facets['source'] ?? '') !== self::SOURCE) {
            $errors[] = 'discovery_facets_source_unsupported';
        }
        $categories = $facets['categories'] ?? null;
        if (!is_array($categories)) {
            $errors[] = 'discovery_facets_categories_must_be_array';
            return array_values(array_unique($errors));
        }
        if (!$categories || count($categories) > self::MAX_CATEGORIES) {
            $errors[] = 'discovery_facets_category_count_invalid';
        }
        $normalized = array_map([__CLASS__, 'normalize_category'], $categories);
        if (in_array('', $normalized, true)) {
            $errors[] = 'discovery_facets_category_invalid';
        }
        if ($normalized !== $categories) {
            $errors[] = 'discovery_facets_categories_not_canonical';
        }
        if (count(array_unique($normalized)) !== count($normalized)) {
            $errors[] = 'discovery_facets_categories_duplicate';
        }
        $sorted = $normalized;
        sort($sorted, SORT_STRING);
        if ($normalized !== $sorted) {
            $errors[] = 'discovery_facets_categories_not_sorted';
        }
        $total = $facets['category_count_total'] ?? null;
        if (!is_int($total) || $total < count($categories) || $total > 256) {
            $errors[] = 'discovery_facets_category_count_total_invalid';
            $total = count($categories);
        }
        $truncated = $facets['truncated'] ?? null;
        $coverage = $facets['coverage'] ?? '';
        if (!is_bool($truncated)) {
            $errors[] = 'discovery_facets_truncated_invalid';
        }
        if (!in_array($coverage, ['complete', 'partial'], true)) {
            $errors[] = 'discovery_facets_coverage_invalid';
        } elseif ($coverage === 'complete' && ($truncated !== false || $total !== count($categories))) {
            $errors[] = 'discovery_facets_coverage_inconsistent';
        } elseif ($coverage === 'partial' && ($truncated !== true || $total <= count($categories))) {
            $errors[] = 'discovery_facets_coverage_inconsistent';
        }
        return array_values(array_unique($errors));
    }
}
