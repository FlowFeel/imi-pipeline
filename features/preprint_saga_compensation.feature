@preprint @saga @compensation
Feature: Scholarly Preprint Publication Saga Compensation and Search Engine Safety
  As the IMI syndication platform
  I want failed Crossref metadata deposits to trigger automatic LIFO saga compensation
  So that unactivated DOIs never leak to search crawlers, broken WordPress posts are removed,
  and the Axiom of Search Engine Safety holds under failure.

  Scenario: Successful preprint publication saga progresses through all four phases
    Given a valid preprint deposit request for "Paleolithic Lithic Cultures" with DOI "10.67767/imi.2026.042"
    When the preprint publication saga executes
    Then the saga completes successfully
    And the preprint post is published to WordPress
    And the Crossref metadata deposit succeeds
    And the DOI status is active

  Scenario: Crossref deposit rejection triggers automatic saga rollback and post removal
    Given a valid preprint deposit request for "Faulty Stratigraphy Draft" with DOI "10.67767/imi.2026.999"
    And Crossref will reject the metadata deposit with "Malformed receipt XML: missing <doi>"
    When the preprint publication saga executes
    Then the saga fails with error containing "Malformed receipt XML"
    And the DOI is never activated
    And the WordPress preprint post is compensated and rolled back
    And the DOI status remains pending
