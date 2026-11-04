<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Adapters\WordPress;

use Phosphene\ImiWordpress\Domain\Author;
use Phosphene\ImiWordpress\Domain\DOI;
use Phosphene\ImiWordpress\Domain\DOIRecord;
use Phosphene\ImiWordpress\Domain\DOIStatus;
use Phosphene\ImiWordpress\Domain\EditorialState;
use Phosphene\ImiWordpress\Domain\License;
use Phosphene\ImiWordpress\Domain\PreprintEntry;
use Phosphene\ImiWordpress\Domain\VersionInfo;

/**
 * Pure hydrator constructing domain PreprintEntry instances from WordPress metadata.
 */
final class PostMetaHydrator
{
    /**
     * Hydrate a PreprintEntry from a post title and meta key-value array.
     *
     * @param string $title
     * @param array<string, mixed> $meta WordPress postmeta dictionary
     * @param string $slug
     * @return PreprintEntry
     */
    public static function fromMeta(string $title, array $meta, string $slug = ''): PreprintEntry
    {
        // Parse primary author
        $primaryAuthor = new Author(
            name: (string)($meta['reg_author_name'] ?? ''),
            orcid: (string)($meta['reg_orcid'] ?? ''),
            affiliation: (string)($meta['reg_affiliation'] ?? ''),
            country: (string)($meta['reg_country'] ?? ''),
        );

        // Parse coauthors (newline-separated)
        $coauthors = [];
        $rawCoauthors = (string)($meta['reg_coauthors'] ?? '');
        if ($rawCoauthors !== '') {
            $normalized = str_replace("\r", '', $rawCoauthors);
            foreach (explode("\n", $normalized) as $line) {
                $trimmed = trim($line);
                if ($trimmed !== '') {
                    $coauthors[] = new Author(name: $trimmed);
                }
            }
        }

        // Parse keywords (comma-separated)
        $keywords = [];
        $rawKeywords = (string)($meta['reg_keywords'] ?? '');
        if ($rawKeywords !== '') {
            foreach (explode(',', $rawKeywords) as $kw) {
                $trimmed = trim($kw);
                if ($trimmed !== '') {
                    $keywords[] = $trimmed;
                }
            }
        }

        // Parse DOI and status
        $rawDoi = trim((string)($meta['reg_doi'] ?? ''));
        $doi = $rawDoi !== '' ? DOI::fromString($rawDoi) : null;
        $rawDoiStatus = (string)($meta['reg_doi_status'] ?? '');
        $doiStatus = DOIStatus::tryFrom($rawDoiStatus) ?? DOIStatus::UNASSIGNED;

        $doiRecord = new DOIRecord(
            doi: $doi,
            status: $doiStatus,
            mintedDate: (string)($meta['reg_doi_minted_date'] ?? ''),
            depositId: (string)($meta['reg_crossref_deposit_id'] ?? ''),
        );

        // Map editorial state from reg_pipeline_status
        $pipelineStatus = (string)($meta['reg_pipeline_status'] ?? '');
        $editorialState = match ($pipelineStatus) {
            'preprint' => EditorialState::LIVE_PREPRINT,
            'published' => EditorialState::PUBLISHED,
            'withdrawn' => EditorialState::WITHDRAWN,
            'under_review' => EditorialState::UNDER_REVIEW,
            'pending_review' => EditorialState::PENDING_REVIEW,
            default => EditorialState::DRAFT,
        };

        // Parse versioning
        $rawPriorVersions = (string)($meta['reg_prior_versions'] ?? '');
        $priorVersions = [];
        if ($rawPriorVersions !== '') {
            foreach (explode("\n", str_replace("\r", '', $rawPriorVersions)) as $pv) {
                $trimmed = trim($pv);
                if ($trimmed !== '') {
                    $priorVersions[] = $trimmed;
                }
            }
        }

        $version = new VersionInfo(
            number: (int)($meta['reg_version'] ?? 1),
            versionType: (string)($meta['reg_version_type'] ?? 'major'),
            history: (string)($meta['reg_version_history'] ?? ''),
            priorVersions: $priorVersions,
        );

        // Parse license
        $rawLicense = (string)($meta['reg_license'] ?? '');
        $license = License::tryFrom($rawLicense) ?? License::CC_BY_NC_SA_4_0;

        return new PreprintEntry(
            title: $title,
            primaryAuthor: $primaryAuthor,
            slug: $slug,
            editorialState: $editorialState,
            abstract: (string)($meta['reg_abstract'] ?? ''),
            methodology: (string)($meta['reg_methodology'] ?? ''),
            license: $license,
            declaration: (bool)($meta['reg_declaration'] ?? true),
            keywords: $keywords,
            coauthors: $coauthors,
            destinationUrl: (string)($meta['reg_destination_url'] ?? ''),
            publishedDestination: (string)($meta['reg_published_destination'] ?? 'Observatory'),
            pdfUrl: (string)($meta['reg_pdf_url'] ?? ''),
            schemaType: (string)($meta['reg_schema_type'] ?? 'ScholarlyArticle'),
            registryId: (string)($meta['reg_registry_id'] ?? ''),
            doiRecord: $doiRecord,
            version: $version,
            withdrawalNotice: (string)($meta['reg_withdrawal_notice'] ?? ''),
        );
    }
}
