Feature: Integration guard prevents production writes

  The DryRunGuard enforces a hard code-level lock against production writes.
  Test clients must explicitly set _IS_TEST_CLIENT = True.
  Any client that does not carry this flag is blocked unconditionally.

  Scenario: Production write blocked on non-test client
    Given a DryRunGuard instance without test flag
    When a guarded write is attempted
    Then ProductionWriteBlocked is raised

  Scenario: Test client passes guard
    Given a DryRunGuard subclass with _IS_TEST_CLIENT True
    When a guarded write is attempted
    Then no exception is raised
