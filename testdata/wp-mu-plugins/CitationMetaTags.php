<?php

declare(strict_types=1);

/**
 * Google Scholar citation meta tag generator.
 *
 * Pure PHP — zero WordPress dependencies. Uses htmlspecialchars() for escaping;
 * the WP adapter thin-wrapper can substitute esc_attr() at the plugin layer.
 *
 * Tags generated:
 *   - citation_title (required)
 *   - citation_author (required)
 *   - citation_publisher (required, defaults to Independent Media Institute)
 *   - citation_publication_date (optional)
 *   - citation_journal_title (optional)
 *   - citation_doi (optional)
 *
 * ### Invariants
 * - render() never returns an empty string when title and author are non-empty
 * - All content values are HTML-escaped via htmlspecialchars()
 * - Optional fields (doi, journal) are omitted entirely when null — never emitted as empty strings
 */
class CitationMetaTags
{
    private string $title;
    private string $author;
    private ?string $published_date;
    private ?string $journal;
    private ?string $doi;
    private string $publisher;

    public function __construct(
        string $title,
        string $author,
        ?string $published_date = null,
        ?string $journal = null,
        ?string $doi = null,
        string $publisher = 'Independent Media Institute'
    ) {
        $this->title = $title;
        $this->author = $author;
        $this->published_date = $published_date;
        $this->journal = $journal;
        $this->doi = $doi;
        $this->publisher = $publisher;
    }

    /**
     * Render all applicable citation meta tags.
     *
     * @return string Newline-joined <meta> tags for <head> injection.
     */
    public function render(): string
    {
        $tags = [
            $this->tag('citation_title', $this->title),
            $this->tag('citation_author', $this->author),
            $this->tag('citation_publisher', $this->publisher),
        ];

        if ($this->published_date !== null) {
            $tags[] = $this->tag('citation_publication_date', $this->published_date);
        }
        if ($this->journal !== null) {
            $tags[] = $this->tag('citation_journal_title', $this->journal);
        }
        if ($this->doi !== null) {
            $tags[] = $this->tag('citation_doi', $this->doi);
        }

        return implode("\n", $tags);
    }

    /**
     * Render a single <meta> tag with HTML-escaped content.
     */
    private function tag(string $name, string $content): string
    {
        $escaped = htmlspecialchars($content, ENT_QUOTES, 'UTF-8');
        return '<meta name="' . $name . '" content="' . $escaped . '" />';
    }
}
