<?php
/**
 * Plugin Name: IMI Citation Meta Tags
 * Description: Google Scholar citation meta tags and Schema.org JSON-LD for imi_registry posts.
 * Version: 1.0.0
 * Author: Flow (flow@ind.media)
 */

declare(strict_types=1);

define('IMI_CITATION_META_VERSION', '1.0.0');

require_once __DIR__ . '/Domain/License.php';
require_once __DIR__ . '/Domain/DOIStatus.php';
require_once __DIR__ . '/Domain/EditorialState.php';
require_once __DIR__ . '/Domain/Author.php';
require_once __DIR__ . '/Domain/DOI.php';
require_once __DIR__ . '/Domain/DOIRecord.php';
require_once __DIR__ . '/Domain/VersionInfo.php';
require_once __DIR__ . '/Domain/PreprintEntry.php';
require_once __DIR__ . '/Adapters/WordPress/PostMetaHydrator.php';
require_once __DIR__ . '/Adapters/Scholarly/GoogleScholarAdapter.php';
require_once __DIR__ . '/Adapters/Scholarly/SchemaJsonLdAdapter.php';

use Phosphene\ImiWordpress\Adapters\Scholarly\GoogleScholarAdapter;
use Phosphene\ImiWordpress\Adapters\Scholarly\SchemaJsonLdAdapter;
use Phosphene\ImiWordpress\Adapters\WordPress\PostMetaHydrator;

add_action('wp_head', function () {
    if (!is_singular('imi_registry')) {
        return;
    }
    $post_id = get_the_ID();
    if (!$post_id) {
        return;
    }

    // Fetch all postmeta as a flattened dictionary
    $raw_meta = get_post_meta($post_id);
    $meta = [];
    if (is_array($raw_meta)) {
        foreach ($raw_meta as $key => $values) {
            $meta[$key] = is_array($values) ? ($values[0] ?? '') : $values;
        }
    }

    $title = (string) get_the_title();
    $slug = (string) get_post_field('post_name', $post_id);

    $entry = PostMetaHydrator::fromMeta($title, $meta, $slug);

    echo GoogleScholarAdapter::render($entry) . "\n";
    echo SchemaJsonLdAdapter::renderScriptTag($entry) . "\n";
});
