<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Domain;

/**
 * Scholarly DOI registration and state record. Pure data.
 */
readonly class DOIRecord
{
    public function __construct(
        public ?DOI $doi = null,
        public DOIStatus $status = DOIStatus::UNASSIGNED,
        public string $mintedDate = '',
        public string $depositId = '',
    ) {}
}
