<?php

declare(strict_types=1);

namespace Phosphene\ImiWordpress\Domain;

/**
 * Scholarly publication licenses.
 */
enum License: string
{
    case CC_BY_NC_SA_4_0 = 'CC BY-NC-SA 4.0';
    case CC_BY_4_0 = 'CC BY 4.0';
    case CC0_1_0 = 'CC0 1.0';
}
