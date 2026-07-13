"""Gate types — local definitions so IMI BDD runs without phosphene.temporal.

These are the data contracts for human gate interactions. They must remain
structurally identical to phosphene.temporal.workflows.human_gate — that
module is the runtime implementation, this module is the contract surface
that BDD and unit tests can import without Temporal installed.

When phosphene.temporal is available at runtime, the Temporal workflow
uses its own definitions. The gate wiring in gates.py will be updated
to use these local types for the contract surface and delegate to
Temporal only for the actual workflow execution.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ApprovalRequest:
    """Update payload from the reviewer."""

    reviewer: str
    decision: str
    notes: str = ""


@dataclass
class HumanGateResult:
    """Result returned by a human gate decision."""

    approved: bool
    reviewer: str | None = None
    notes: str | None = None
    timed_out: bool = False
