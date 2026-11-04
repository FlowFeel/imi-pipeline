<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Adapters\Scholarly;

use Phosphene\ImiWordpress\Domain\EditorialState;
use Phosphene\ImiWordpress\Domain\PreprintEntry;

/**
 * Pure adapter building Schema.org JSON-LD arrays from a PreprintEntry.
 */
final class SchemaJsonLdAdapter
{
    /**
     * Build Schema.org JSON-LD data structure.
     *
     * @param PreprintEntry $entry
     * @return array<string, mixed>
     */
    public static function build(PreprintEntry $entry): array
    {
        $authors = [
            ['@type' => 'Person', 'name' => $entry->primaryAuthor->name],
        ];
        foreach ($entry->coauthors as $coauthor) {
            $authors[] = ['@type' => 'Person', 'name' => $coauthor->name];
        }

        $data = [
            '@context' => 'https://schema.org',
            '@type' => $entry->schemaType,
            'headline' => $entry->title,
            'description' => $entry->abstract,
            'author' => $authors,
        ];

        // Gap B fix: emit creativeWorkStatus
        $creativeStatus = match ($entry->editorialState) {
            EditorialState::LIVE_PREPRINT => 'Preprint',
            EditorialState::PUBLISHED => 'Published',
            EditorialState::WITHDRAWN => 'Retracted',
            default => null,
        };

        if ($creativeStatus !== null) {
            $data['creativeWorkStatus'] = $creativeStatus;
        }

        if ($entry->doiRecord->doi !== null) {
            $data['identifier'] = $entry->doiRecord->doi->url();
            $data['sameAs'] = $entry->doiRecord->doi->url();
        }

        return $data;
    }

    /**
     * Render the JSON-LD script tag.
     *
     * @param PreprintEntry $entry
     * @return string
     */
    public static function renderScriptTag(PreprintEntry $entry): string
    {
        $json = json_encode(
            self::build($entry),
            JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT
        );
        return '<script type="application/ld+json">' . "\n" . $json . "\n" . '</script>';
    }
}
