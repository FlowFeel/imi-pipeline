"""DryRunGuard — hard lock against production writes.

The guard enforces a structural invariant at the class level:
a client that is not explicitly marked as a test client cannot
invoke guarded operations.

This is not a pattern match or a runtime check on environment
variables — it is a code-level hard lock. Production clients
never have _IS_TEST_CLIENT = True. Test clients always do.

Usage::

    class MySFTestClient(DryRunGuard):
        _IS_TEST_CLIENT = True

        def create_record(self, ...):
            self._check_guard()
            ...

OKR: @okr_publish_pipeline
"""

from __future__ import annotations


class ProductionWriteBlocked(RuntimeError):
    """Raised when a write is attempted outside test context.

    This exception indicates a hard configuration error —
    a real client was used in a context that requires a test client.
    Do not catch this exception; fix the configuration.
    """


class DryRunGuard:
    """Base class for dry-run clients. Subclasses set _IS_TEST_CLIENT = True.

    The base class defaults _IS_TEST_CLIENT to False so that:
      - Subclasses that forget to opt in are blocked, not silently passed.
      - Only subclasses that explicitly declare _IS_TEST_CLIENT = True
        are permitted to call guarded operations.

    Usage::

        class TestSFClient(DryRunGuard):
            _IS_TEST_CLIENT = True

            def create_record(self, ...):
                self._check_guard()
                ...
    """

    _IS_TEST_CLIENT: bool = False

    def _check_guard(self) -> None:
        """Assert this instance is a test client before allowing a write.

        Raises:
            ProductionWriteBlocked: If _IS_TEST_CLIENT is not True.
                The message includes the class name so the caller can
                identify which client needs the flag set.
        """
        if not self._IS_TEST_CLIENT:
            raise ProductionWriteBlocked(
                f"{self.__class__.__name__} is not marked as a test client. "
                "Set _IS_TEST_CLIENT = True or use the DryRun variant."
            )
