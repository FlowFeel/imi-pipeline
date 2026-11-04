<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Domain;

/**
 * Scholarly contributor value object.
 *
 * Immutable personal and institutional metadata shared by primary authors and co-authors.
 */
readonly class Author
{
    public function __construct(
        public string $name,
        public string $orcid = '',
        public string $affiliation = '',
        public string $country = '',
    ) {}
}
