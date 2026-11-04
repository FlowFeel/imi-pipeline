<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Utils;

/**
 * Domain-agnostic string utilities for slugification and delimiter joining.
 */
final class StringUtils
{
    /**
     * Convert an arbitrary string into a deterministic, URL-safe ASCII slug.
     */
    public static function slugify(string $text, ?int $maxLength = null): string
    {
        if (trim($text) === '') {
            return '';
        }
        $clean = iconv('UTF-8', 'ASCII//TRANSLIT', $text) ?: $text;
        $clean = strtolower($clean);
        $clean = preg_replace('/[^a-z0-9]+/', '-', $clean);
        $slug = trim($clean ?? '', '-');

        if ($maxLength !== null && $maxLength > 0) {
            $slug = rtrim(substr($slug, 0, $maxLength), '-');
        }

        return $slug;
    }

    /**
     * Humanize a slug by converting underscores and hyphens to spaces.
     */
    public static function humanizeSlug(string $slug): string
    {
        return trim((string)preg_replace('/[_-]+/', ' ', $slug));
    }

    /**
     * Join an array of strings with strict null-omission.
     *
     * @param list<string> $items
     * @param string $delimiter
     * @return string
     */
    public static function joinDelimited(array $items, string $delimiter = ', '): string
    {
        $filtered = [];
        foreach ($items as $item) {
            $trimmed = trim((string)$item);
            if ($trimmed !== '') {
                $filtered[] = $trimmed;
            }
        }
        return implode($delimiter, $filtered);
    }
}
