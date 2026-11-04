<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Utils;

/**
 * Domain-agnostic HTML presentation utilities.
 */
final class HtmlUtils
{
    /**
     * Render a single HTML <meta> tag with attribute escaping.
     */
    public static function renderMetaTag(string $name, string $content): string
    {
        return '<meta name="' . htmlspecialchars($name, ENT_QUOTES, 'UTF-8') .
               '" content="' . htmlspecialchars($content, ENT_QUOTES, 'UTF-8') . '" />';
    }

    /**
     * Render an array of name => content pairs or MetaTag structures.
     *
     * @param list<array{name: string, content: string}> $tags
     * @return string
     */
    public static function renderMetaTags(array $tags): string
    {
        $rendered = [];
        foreach ($tags as $tag) {
            $name = (string)($tag['name'] ?? '');
            $content = (string)($tag['content'] ?? '');
            if ($name !== '') {
                $rendered[] = self::renderMetaTag($name, $content);
            }
        }
        return implode("\n", $rendered);
    }
}
