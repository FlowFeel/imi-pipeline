<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Domain;

/**
 * Lifecycle status of a Digital Object Identifier.
 */
enum DOIStatus: string
{
    case UNASSIGNED = 'unassigned';
    case PENDING = 'pending';
    case ACTIVE = 'active';
    case WITHDRAWN = 'withdrawn';
}
