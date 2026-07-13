Feature: WordPress outlet payload contract

  Scenario: Published article produces valid WordPress entry
    Given a valid ArticleDraft with cave paper metadata
    When the WordPressOutlet publishes to the mock server
    Then the payload has no hollow fields
    And the outlet returns a successful result with an entry URL

  Scenario: WordPress JSON-LD meets Kelly contract
    Given a valid ArticleDraft with JSON-LD metadata
    When the WordPressOutlet publishes to the mock server
    Then sameAs is an array
    And the author type is Person
    And all dates are in Z form
    And the schema type is valid
