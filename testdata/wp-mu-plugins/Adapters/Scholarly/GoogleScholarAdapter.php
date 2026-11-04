<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Adapters\Scholarly;

use Phosphene\ImiWordpress\Domain\DOIStatus;
use Phosphene\ImiWordpress\Domain\PreprintEntry;

/**
 * Pure adapter rendering Google Scholar citation meta tags from a PreprintEntry.
 */
final class GoogleScholarAdapter
{
    /**
     * Render citation meta tags conforming to Google Scholar inclusion guidelines.
     *
     * @param PreprintEntry $entry
     * @param string $publisher
     * @return string
     */
    public static function render(PreprintEntry $entry, string $publisher = 'Independent Media Institute'): string
    {
        $tags = [
            self::tag('citation_title', $entry->title),
            self::tag('citation_author', $entry->primaryAuthor->name),
        ];

        // Individual tag for every co-author
        foreach ($entry->coauthors as $coauthor) {
            $tags[] = self::tag('citation_author', $coauthor->name);
        }

        $tags[] = self::tag('citation_publisher', $publisher);

        if ($entry->abstract !== '') {
            $tags[] = self::tag('citation_abstract', $entry->abstract);
        }

        if (!empty($entry->keywords)) {
            $tags[] = self::tag('citation_keywords', implode(', ', $entry->keywords));
        }

        if ($entry->destinationUrl !== '') {
            $tags[] = self::tag('citation_fulltext_html_url', $entry->destinationUrl);
        }

        if ($entry->pdfUrl !== '') {
            $tags[] = self::tag('citation_pdf_url', $entry->pdfUrl);
        }

        // Only emit citation_doi if the DOI is ACTIVE
        if ($entry->doiRecord->status === DOIStatus::ACTIVE && $entry->doiRecord->doi !== null) {
            $tags[] = self::tag('citation_doi', $entry->doiRecord->doi->value());
        }

        return implode("\n", $tags);
    }

    private static function tag(string $name, string $content): string
    {
        return '<meta name="' . $name . '" content="' . htmlspecialchars($content, ENT_QUOTES, 'UTF-8') . '" />';
    }
}
