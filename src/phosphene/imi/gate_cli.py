"""CLI entry point for human gate approve/reject commands.

Usage::

    python -m phosphene.imi.gate_cli approve <wf_id> \
        [--reviewer Kelly] [--notes "LGTM"]
    python -m phosphene.imi.gate_cli reject <wf_id> \
        [--reviewer Kelly] [--notes "Needs work"]

Calls :func:`~phosphene.imi.gates.approve_gate` or
:func:`~phosphene.imi.gates.reject_gate` via ``asyncio.run()``.
Prints result as JSON to stdout.

Exit codes:
    0 — approved
    1 — rejected or timed out

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict

from phosphene.imi.gates import approve_gate, reject_gate

# Indirection for testability — tests patch asyncio_run to avoid real event loops.
asyncio_run = asyncio.run


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Returns:
        Configured ``argparse.ArgumentParser``.
    """
    parser = argparse.ArgumentParser(
        prog="gate_cli",
        description="Approve or reject a HumanGateWorkflow via Temporal Update.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for cmd in ("approve", "reject"):
        sub = subparsers.add_parser(cmd, help=f"{cmd.title()} a pending gate.")
        sub.add_argument("workflow_id", help="Temporal workflow ID of the gate.")
        sub.add_argument(
            "--reviewer",
            default="unknown",
            help="Name of the reviewer (default: unknown).",
        )
        sub.add_argument("--notes", default="", help="Optional notes or rationale.")

    return parser


def main() -> None:
    """Parse args, call approve_gate or reject_gate, print JSON, exit.

    Raises:
        SystemExit: 0 on approved, 1 on rejected/timed_out.
    """
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "approve":
        coro = approve_gate(
            workflow_id=args.workflow_id,
            reviewer=args.reviewer,
            notes=args.notes,
        )
    else:
        coro = reject_gate(
            workflow_id=args.workflow_id,
            reviewer=args.reviewer,
            notes=args.notes,
        )

    result = asyncio_run(coro)

    # Serialize HumanGateResult dataclass to JSON
    print(json.dumps(asdict(result), indent=2))

    sys.exit(0 if result.approved else 1)


if __name__ == "__main__":
    main()
