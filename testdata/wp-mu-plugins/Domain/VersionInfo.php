<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Domain;

/**
 * Preprint version lineage value object.
 */
readonly class VersionInfo
{
    /**
     * @param string[] $priorVersions
     */
    public function __construct(
        public int $number = 1,
        public string $versionType = 'major',
        public string $history = '',
        public array $priorVersions = [],
    ) {}
}
