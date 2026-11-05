@integration
Feature: Deliverable Base Cases for DOI Preprint Lifecycle
  As a scholarly publishing editor at Observatory and IMI
  I want preprints with DOIs to progress through an automated, idempotent lifecycle
  So that academic metadata is indexed accurately without leaking dead links,
  version revisions remain connected, and retracted works are permanently tombstoned.

  Background:
    Given the DOI harness stack is running
    And the Crossref stub is reset

  # ── Base cases (vendored from janfrel/imi-wordpress) ─────────────────────────

  Scenario: Initial ingestion with pending DOI omits citation tags to prevent 404 indexing
    Given an author creates a preprint titled "Degrowth in Supply Chains"
    And the preprint has DOI suffix "imi.2026.050" with status "PENDING"
    When Flow generates the Google Scholar citation tags
    Then the citation output contains a "citation_title" tag with "Degrowth in Supply Chains"
    And the citation output does not contain a "citation_doi" tag
    When Flow publishes the preprint via WordPressOutlet
    Then the post meta "reg_doi_status" is "pending"
    And the post meta "reg_doi" is "10.67767/imi.2026.050"

  Scenario: Successful Crossref deposit mints active DOI and activates citation tags
    Given an author creates a preprint titled "Lithic Tool Technologies"
    And the primary author is "Deborah Barsky"
    And the preprint has DOI suffix "imi.2026.042" with Crossref deposit "cr-dep-9912"
    And the DOI status is "ACTIVE"
    When Flow generates the Google Scholar citation tags
    Then the citation output contains a "citation_doi" tag with "10.67767/imi.2026.042"
    When Flow publishes the preprint via WordPressOutlet
    Then the post meta "reg_doi" is "10.67767/imi.2026.042"
    And the post meta "reg_doi_url" is "https://doi.org/10.67767/imi.2026.042"
    And the post meta "reg_doi_status" is "active"
    And the post meta "reg_crossref_deposit_id" is "cr-dep-9912"

  Scenario: Version revision increments artifact and version number without fracturing DOI
    Given an author creates a preprint titled "Agade Positional Survey"
    And the preprint has version 1 with PDF artifact "https://ind.media/pdf/agade-v1.pdf"
    And the preprint has DOI suffix "imi.2026.088" with Crossref deposit "cr-dep-8811"
    And the DOI status is "ACTIVE"
    When the preprint is revised to version 2 with PDF artifact "https://ind.media/pdf/agade-v2.pdf"
    And Flow publishes the preprint via WordPressOutlet
    Then the post meta "reg_version" is 2
    And the post meta "reg_pdf_url" is "https://ind.media/pdf/agade-v2.pdf"
    And the post meta "reg_doi" is "10.67767/imi.2026.088"

  Scenario: Academic structured data parity generates compliant Schema.org JSON-LD
    Given an author creates a preprint titled "Body-Grammar Typology"
    And the primary author is "Jan Ritch-Frel"
    And the co-authors are "Ed Phillips" and "Maria Santos"
    And the preprint is in "LIVE_PREPRINT" editorial state
    When Flow generates the Schema.org JSON-LD
    Then the JSON-LD "@type" is "ScholarlyArticle"
    And the JSON-LD "creativeWorkStatus" is "Preprint"
    And the JSON-LD authors include "Jan Ritch-Frel" and "Ed Phillips"

  Scenario: Retraction preserves permanent DOI while updating status and notice
    Given an author creates a preprint titled "Marine Debris Valuation"
    And the preprint has DOI suffix "imi.2026.110" with Crossref deposit "cr-dep-7710"
    And the DOI status is "ACTIVE"
    When the preprint is retracted with notice "Funding disclosure error"
    And Flow publishes the preprint via WordPressOutlet
    Then the post meta "reg_doi_status" is "withdrawn"
    And the post meta "reg_doi" is "10.67767/imi.2026.110"
    And the post meta "reg_withdrawal_notice" is "Funding disclosure error"
    When Flow generates the Schema.org JSON-LD
    Then the JSON-LD "creativeWorkStatus" is "Retracted"

  # ── Black-box harness scenarios (real HTTP against the stack) ────────────────

  Scenario: Deposit receipt flows end to end through the stub
    Given a published preprint titled "Harness Smoke Test" with DOI suffix "imi.2026.900"
    When the harness deposits the preprint metadata to the Crossref stub
    Then the stub returns a deposit receipt with a "cr-dep-" id
    And the stub receipt for that id has status "pending"

  Scenario: Malformed Crossref receipt is rejected by the harness
    Given a published preprint titled "Harness Malformed" with DOI suffix "imi.2026.901"
    And the Crossref stub is scripted to return "malformed" for suffix "901"
    When the harness deposits the preprint metadata to the Crossref stub
    Then the harness records a malformed-receipt error and does not activate the DOI

  Scenario: Crossref simulator validates Schema 5.3.1 and rejects missing depositor
    Given a published preprint titled "Harness Schema Rejection" with DOI suffix "imi.2026.902"
    When the harness deposits malformed Schema XML missing depositor
    Then the Crossref simulator returns a Schema 5.3.1 diagnostic error
    And the DOI status remains "pending"

  Scenario: Registered DOI resolves via HTTP 302 to the preprint landing page
    Given a published preprint titled "Harness Resolution Test" with DOI suffix "imi.2026.903"
    When the harness deposits the preprint metadata to the Crossref stub
    Then resolving the DOI "10.67767/imi.2026.903" redirects to the preprint landing page
    And resolving the unregistered DOI "10.67767/imi.2026.999" returns 404


  Scenario: Live wire saga compensation purges WordPress post when Crossref deposit fails
    Given a valid preprint deposit request for "Faulty Stratigraphy Survey" with DOI suffix "imi.2026.904"
    And the Crossref stub is scripted to return "reject" for suffix "904"
    When the preprint publication saga executes against the live stack
    Then the saga execution fails with a Crossref rejection error
    And the preprint post is permanently purged from WordPress
    And resolving the unregistered DOI "10.67767/imi.2026.904" returns 404

  Scenario: Live wire saga completes 4-phase publication against live WordPress and Crossref
    Given a valid preprint deposit request for "Live Saga Stratigraphy" with DOI suffix "imi.2026.905"
    When the preprint publication saga executes against the live stack
    Then the saga completes successfully
    And the post meta "reg_doi_status" is "active"
    And the post meta "reg_doi" is "10.67767/imi.2026.905"
    And the post meta "reg_crossref_deposit_id" has prefix "cr-dep-"
    And resolving the DOI "10.67767/imi.2026.905" redirects to the preprint landing page
