<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Adapters\Scholarly;

require_once __DIR__ . '/../../Utils/HtmlUtils.php';
require_once __DIR__ . '/../../Utils/StringUtils.php';

use Phosphene\ImiWordpress\Domain\DOIStatus;
use Phosphene\ImiWordpress\Domain\PreprintEntry;
use Phosphene\ImiWordpress\Utils\HtmlUtils;
use Phosphene\ImiWordpress\Utils\StringUtils;

/**
 * Pure adapter projecting and rendering Google Scholar citation meta tags from a PreprintEntry.
 */
final class GoogleScholarAdapter
{
    /**
     * Project a PreprintEntry into a list of name => content tag pairs (pure data manipulation).
     *
     * @param PreprintEntry $entry
     * @param string $publisher
     * @return list<array{name: string, content: string}>
     */
    public static function toTags(PreprintEntry $entry, string $publisher = 'Independent Media Institute'): array
    {
        $tags = [
            ['name' => 'citation_title', 'content' => $entry->title],
            ['name' => 'citation_author', 'content' => $entry->primaryAuthor->name],
        ];

        // Individual tag for every co-author
        foreach ($entry->coauthors as $coauthor) {
            $tags[] = ['name' => 'citation_author', 'content' => $coauthor->name];
        }

        $tags[] = ['name' => 'citation_publisher', 'content' => $publisher];

        if ($entry->abstract !== '') {
            $tags[] = ['name' => 'citation_abstract', 'content' => $entry->abstract];
        }

        if (!empty($entry->keywords)) {
            $tags[] = ['name' => 'citation_keywords', 'content' => StringUtils::joinDelimited($entry->keywords)];
        }

        if ($entry->destinationUrl !== '') {
            $tags[] = ['name' => 'citation_fulltext_html_url', 'content' => $entry->destinationUrl];
        }

        if ($entry->pdfUrl !== '') {
            $tags[] = ['name' => 'citation_pdf_url', 'content' => $entry->pdfUrl];
        }

        // Only emit citation_doi if the DOI is ACTIVE
        if ($entry->doiRecord->status === DOIStatus::ACTIVE && $entry->doiRecord->doi !== null) {
            $tags[] = ['name' => 'citation_doi', 'content' => $entry->doiRecord->doi->value()];
        }

        return $tags;
    }

    /**
     * Render citation meta tags conforming to Google Scholar inclusion guidelines.
     *
     * @param PreprintEntry $entry
     * @param string $publisher
     * @return string
     */
    public static function render(PreprintEntry $entry, string $publisher = 'Independent Media Institute'): string
    {
        return HtmlUtils::renderMetaTags(self::toTags($entry, $publisher));
    }
}
