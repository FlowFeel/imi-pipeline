<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Domain;

/**
 * Pure domain entity representing a scholarly preprint registry record.
 *
 * Models business reality with semantic collections and zero transport knowledge.
 */
readonly class PreprintEntry
{
    /**
     * @param string[] $keywords
     * @param Author[] $coauthors
     */
    public function __construct(
        public string $title,
        public Author $primaryAuthor,
        public string $slug = '',
        public EditorialState $editorialState = EditorialState::DRAFT,
        public string $abstract = '',
        public string $methodology = '',
        public License $license = License::CC_BY_NC_SA_4_0,
        public bool $declaration = true,
        public array $keywords = [],
        public array $coauthors = [],
        public string $destinationUrl = '',
        public string $publishedDestination = 'Observatory',
        public string $pdfUrl = '',
        public string $schemaType = 'ScholarlyArticle',
        public string $registryId = '',
        public DOIRecord $doiRecord = new DOIRecord(),
        public VersionInfo $version = new VersionInfo(),
        public string $withdrawalNotice = '',
    ) {}
}
