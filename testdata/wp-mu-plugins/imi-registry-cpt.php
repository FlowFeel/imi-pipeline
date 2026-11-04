<?php
/**
 * Plugin Name: IMI Registry CPT
 * Description: Registers imi_registry custom post type for the Scholar Registry.
 * Version: 1.0.0
 * Author: Flow (flow@ind.media)
 */
require_once __DIR__ . '/RegistryCPTConfig.php';

add_action('init', function() {
    register_post_type(RegistryCPTConfig::SLUG, RegistryCPTConfig::post_type_args());
    foreach (RegistryCPTConfig::meta_fields() as $key => $args) {
        register_post_meta(RegistryCPTConfig::SLUG, $key, $args);
    }
});
