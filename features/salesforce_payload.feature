Feature: Salesforce outlet payload contract

  Scenario: Published article produces valid Salesforce record
    Given a valid ArticleDraft with cave paper metadata
    When the SalesforceOutlet publishes to the mock server
    Then the payload has no hollow fields
    And the outlet returns a successful result with a record ID

  Scenario: Salesforce payload carries required fields
    Given a valid ArticleDraft with cave paper metadata
    When the SalesforceOutlet publishes to the mock server
    Then the payload contains Headline__c
    And the payload contains Date_Received__c
    And the payload contains Observatory_wiki_Site_Link__c
