<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Domain;

/**
 * Jan's 5-state preprint editorial lifecycle plus withdrawal.
 */
enum EditorialState: string
{
    case DRAFT = 'draft';
    case PENDING_REVIEW = 'pending_review';
    case UNDER_REVIEW = 'under_review';
    case LIVE_PREPRINT = 'live_preprint';
    case PUBLISHED = 'published';
    case WITHDRAWN = 'withdrawn';

    /**
     * True if the state requires a publicly indexable landing page.
     */
    public function isPublished(): bool
    {
        return match ($this) {
            self::LIVE_PREPRINT, self::PUBLISHED, self::WITHDRAWN => true,
            default => false,
        };
    }
}
