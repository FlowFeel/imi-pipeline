<?php

declare(strict_types=1);

/**
 * RegistryCPTConfig — pure CPT configuration data.
 * Zero WordPress dependencies — fully unit testable.
 *
 * ### Lifecycle Phase
 * Registered on WordPress 'init' action. Must run before any REST API
 * endpoint registration that depends on the post type.
 */
class RegistryCPTConfig
{
    public const VERSION = '1.0.0';
    public const SLUG = 'imi_registry';
    public const LABEL = 'IMI Registry';

    /**
     * Arguments for register_post_type().
     *
     * @return array<string, mixed>
     */
    public static function post_type_args(): array
    {
        return [
            'label' => self::LABEL,
            'public' => true,
            'show_in_rest' => true,
            'supports' => ['title', 'editor', 'custom-fields'],
            'rewrite' => ['slug' => 'registry'],
        ];
    }

    /**
     * Canonical meta fields registration schema.
     *
     * Exposes canonical 39 fields (reg_*) and backward-compatible legacy keys.
     *
     * @return array<string, array<string, mixed>>
     */
    public static function meta_fields(): array
    {
        return [
            // Canonical Registry & Scholarly Fields
            'reg_author_name'          => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_orcid'                => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_affiliation'          => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_country'              => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_abstract'             => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_methodology'          => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_license'              => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_declaration'          => ['type' => 'boolean', 'single' => true, 'show_in_rest' => true],
            'reg_keywords'             => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_coauthors'            => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_destination_url'      => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_published_destination'=> ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_pdf_url'              => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_pdf_id'               => ['type' => 'integer', 'single' => true, 'show_in_rest' => true],
            'reg_download_count'       => ['type' => 'integer', 'single' => true, 'show_in_rest' => true],
            'reg_schema_type'          => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_registry_id'          => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_pipeline_status'      => ['type' => 'string',  'single' => true, 'show_in_rest' => true],

            // Versioning Lineage Fields
            'reg_version'              => ['type' => 'integer', 'single' => true, 'show_in_rest' => true],
            'reg_version_type'         => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_version_history'      => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_prior_versions'       => ['type' => 'string',  'single' => true, 'show_in_rest' => true],

            // DOI & Crossref Deposit Fields
            'reg_doi'                  => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_doi_url'              => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_doi_status'           => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_doi_minted_date'      => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_crossref_deposit_id'  => ['type' => 'string',  'single' => true, 'show_in_rest' => true],

            // Retraction / Withdrawal
            'reg_withdrawal_notice'    => ['type' => 'string',  'single' => true, 'show_in_rest' => true],

            // Optional Metadata & Disclosures
            'reg_title_original'       => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_image_url'            => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_funding'              => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_conflicts'            => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_data_availability'    => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'reg_registered_date'      => ['type' => 'string',  'single' => true, 'show_in_rest' => true],

            // Backward-Compatibility Legacy Keys
            'author_name'              => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'category'                 => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
            'source_url'               => ['type' => 'string',  'single' => true, 'show_in_rest' => true],
        ];
    }
}
