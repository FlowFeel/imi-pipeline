@author_flow @okr_pipeline_a
Feature: Human gate approval via Telegram

  Scenario: Reviewer approves a pending SEO package
    Given a HumanGateWorkflow is waiting for a decision
    When Kelly sends /approve with notes "Looks good"
    Then the gate result shows approved=True
    And the reviewer is recorded as "Kelly"

  Scenario: Reviewer rejects a pending SEO package
    Given a HumanGateWorkflow is waiting for a decision
    When Kelly sends /reject with notes "Needs more keywords"
    Then the gate result shows approved=False
    And the notes are recorded
