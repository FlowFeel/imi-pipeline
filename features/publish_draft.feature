@author_flow @okr_publish_pipeline
Feature: Jan publishes a draft article to Observatory
  As Jan, Editor in Chief of the Independent Media Institute
  I want to hand Flow a finished article draft from Asana or Telegram
  So that it appears on observatory.wiki with correct SEO
  Without any manual MediaWiki editing

  Background:
    Given the Observatory publisher is configured

  @tracer_bullet
  Scenario: A draft article is published to observatory.wiki
    Given a finished draft titled "Why Care Work Matters"
    And the author is "Gunnar Rundgren"
    And the category is "Economy"
    And the body contains substantive content
    When Flow publishes the draft
    Then the article exists on observatory.wiki
    And the article has a canonical URL
    And the publish contract passes

  @idempotency
  Scenario: Publishing the same draft twice is safe
    Given a draft that has already been published as "Why Care Work Matters"
    When Flow attempts to publish the same draft again
    Then no duplicate article is created
    And the existing article URL is returned

  @v2_smw
  Scenario: Published article has SMW Modification date populated
    Given a finished draft titled "BDD SMW Probe"
    And the author is "Flow (automated test)"
    And the category is "Test"
    And the body contains substantive content
    When Flow publishes the draft
    Then the article exists on observatory.wiki
    And the article has Modification date in the SMW store

  @validation
  Scenario: A draft without an author is rejected before publish
    Given an incomplete draft missing the author field
    When Flow attempts to publish the draft
    Then the draft is rejected with a validation error
    And no article is created on observatory.wiki
