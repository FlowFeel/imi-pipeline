Feature: Observatory outlet payload contract

  Scenario: Published article creates a Draft page
    Given a valid ArticleDraft with cave paper metadata
    When the ObservatoryOutlet publishes to the mock server
    Then the outlet returns a successful result
    And the page title starts with "Draft:"

  Scenario: Observatory wikitext contains Article template
    Given a valid ArticleDraft with cave paper metadata
    When the ObservatoryOutlet publishes to the mock server
    Then the created wikitext contains the Article template
