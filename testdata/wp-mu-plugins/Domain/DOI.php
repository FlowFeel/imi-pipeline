<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Domain;

/**
 * Scholarly Digital Object Identifier value object.
 *
 * Constructive and immutable. Defaults to IMI's Crossref prefix (10.67767).
 */
readonly class DOI
{
    public const DEFAULT_PREFIX = '10.67767';

    public function __construct(
        public string $suffix,
        public string $prefix = self::DEFAULT_PREFIX,
    ) {}

    public function value(): string
    {
        return "{$this->prefix}/{$this->suffix}";
    }

    public function url(): string
    {
        return "https://doi.org/{$this->value()}";
    }

    public static function fromString(string $raw): self
    {
        $clean = trim($raw);
        if (str_contains($clean, '/')) {
            [$prefix, $suffix] = explode('/', $clean, 2);
            return new self($suffix, $prefix);
        }
        return new self($clean);
    }
}
