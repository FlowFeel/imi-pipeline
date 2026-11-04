"""Design-for-Testability axioms — the phosphene method, adapted for WordPress.

This module defines the six DFT axioms that govern every module in the
imi-wordpress toolkit. The axioms are not just code-quality rules — they
are the *preconditions* that make the codebase provably testable.

The axioms are enforced by the foundry validator (``foundry.py``), which
checks every source module against them. A module that violates an axiom
fails CI.

The axioms:

A1. pure-io-separation
    Pure logic modules import no I/O (no ``urllib``, ``os``, ``http``,
    ``socket``, ``subprocess``). I/O lives behind Protocol interfaces
    (``WPClientProtocol``, ``DBClientProtocol``) in separate modules.
    The test doubles (``FakeWPClient``, ``FakeDBClient``) are real
    in-process implementations, not mocks.

    Why: I/O cost is isolable from logic cost. Pure logic is testable
    in 0ms with zero fixtures. A logic module that imports ``urllib``
    cannot be tested without a network or a mock — both of which couple
    the test to the I/O boundary.

A2. determinism
    Pure logic modules contain no ``datetime.now()``, ``time.time()``,
    ``uuid.uuid4()``, ``random.random()``, or any other non-deterministic
    call. Time is injected via a ``Clock`` Protocol. IDs are injected
    via an ``IdGenerator`` Protocol.

    Why: deterministic tests are reproducible. The same inputs yield
    byte-identical outputs across runs. Non-determinism forces tests
    to use ranges, mocks, or flaky assertions — all of which erode
    confidence.

A3. manifest-conformance
    Every CPT definition (``cpts/*.py``) declares its fields and meta
    keys. The ``to_wp_payload()`` method must produce exactly those
    keys — no more, no less. The validator checks that the payload
    keys match the declared schema.

    Why: a CPT that silently adds or drops a meta key in its payload
    will write incomplete data to WordPress. The manifest is the
    contract; the payload is the proof.

A4. dft-docs
    Every source ``.py`` module has a ``@dft`` section in its docstring
    documenting which axioms apply and how the module satisfies them.

    Why: the testability contract is explicit in the source. A new
    contributor can read the ``@dft`` section and know immediately
    whether the module is pure logic, I/O wiring, or a Protocol.

A5. mock-doubles
    Tests use real in-process doubles (``FakeWPClient``, ``FakeDBClient``)
    that satisfy the Protocol interfaces — not ``MagicMock(spec=...)``.
    ``MagicMock`` records calls but does not execute behavior; a fake
    executes the real behavior in-process.

    Why: a mock that returns a canned response tests that the caller
    *called* the right method. A fake that executes real behavior tests
    that the caller *handles* the response correctly. Fakes catch logic
    bugs that mocks cannot.

A6. check-result
    Mutating logic functions return a result dataclass (not ``None``,
    not a bare dict) that carries the proof of the mutation. The caller
    can inspect the result to verify the mutation succeeded.

    Why: a function that returns ``None`` forces the caller to re-query
    to verify the mutation. A function that returns a result dataclass
    carries its own proof — the caller asserts on the result, not on a
    separate read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# ── Axiom identifiers ────────────────────────────────────────────

A1_PURE_IO_SEPARATION = "pure-io-separation"
A2_DETERMINISM = "determinism"
A3_MANIFEST_CONFORMANCE = "manifest-conformance"
A4_DFT_DOCS = "dft-docs"
A5_MOCK_DOUBLES = "mock-doubles"
A6_CHECK_RESULT = "check-result"

ALL_AXIOMS = (
    A1_PURE_IO_SEPARATION,
    A2_DETERMINISM,
    A3_MANIFEST_CONFORMANCE,
    A4_DFT_DOCS,
    A5_MOCK_DOUBLES,
    A6_CHECK_RESULT,
)


# ── A2: Determinism — injectable time ───────────────────────────


class Clock(Protocol):
    """Protocol for injectable time — enables deterministic testing.

    Pure logic modules depend on this Protocol, not on ``datetime.now()``.
    Production uses :class:`SystemClock`; tests use
    :class:`DeterministicClock`.
    """

    def now_iso(self) -> str:
        """Return the current time as an ISO 8601 string."""
        ...

    def now_ts(self) -> float:
        """Return the current time as a Unix timestamp."""
        ...


class SystemClock:
    """Production clock — reads real wall-clock time.

    @dft A2 (determinism): this is the ONLY module that may call
    ``datetime.now()``. All other modules inject a ``Clock``.
    """

    def now_iso(self) -> str:
        import datetime

        return datetime.datetime.now(datetime.UTC).isoformat()

    def now_ts(self) -> float:
        import time

        return time.time()


class DeterministicClock:
    """Test clock — returns fixed, controllable time values.

    @dft A2 (determinism): injectable time for reproducible tests.
    The same sequence of calls always yields the same outputs.
    """

    def __init__(
        self, start_ts: float = 1_000_000.0, start_iso: str = "2026-08-07T00:00:00+00:00"
    ) -> None:
        self._ts = start_ts
        self._iso = start_iso

    def now_iso(self) -> str:
        return self._iso

    def now_ts(self) -> float:
        return self._ts

    def advance(self, seconds: float) -> None:
        """Advance the clock by ``seconds`` for the next call."""
        self._ts += seconds

    def set_iso(self, iso: str) -> None:
        """Set the ISO string for the next ``now_iso()`` call."""
        self._iso = iso


# ── A6: Check-result — result dataclasses ───────────────────────


@dataclass(frozen=True)
class DftViolation:
    """An axiom violation found by the foundry validator.

    The violation carries its own proof (file, axiom, message, severity).

    @dft A6 (check-result): the validator returns a list of these,
    not a boolean. The caller inspects the list to see exactly what
    failed.
    """

    axiom: str
    file: str
    message: str
    severity: str  # "error" or "warn"
