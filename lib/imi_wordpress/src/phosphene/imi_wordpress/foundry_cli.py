#!/usr/bin/env python3
"""Foundry CLI — validate the imi-wordpress package against DFT axioms.

Usage:
    python -m phosphene.imi_wordpress.foundry_cli validate [src_dir]
    python -m phosphene.imi_wordpress.foundry_cli check [file.py]

@dft
- The pure validator is in ``foundry.py``. This CLI is thin I/O wiring.
"""

from __future__ import annotations

import sys
from pathlib import Path

from phosphene.imi_wordpress.foundry import (
    format_violations,
    has_errors,
    validate_module,
    validate_package,
)


def cmd_validate(src_dir: str | None = None) -> int:
    """Validate all Python files in the source directory."""
    if src_dir is None:
        # Default: src/phosphene/imi_wordpress relative to this file
        src_dir = str(Path(__file__).parent)
    src_path = Path(src_dir)
    if not src_path.exists():
        print(f"Source directory not found: {src_path}", file=sys.stderr)
        return 1

    violations = validate_package(src_path)
    print(format_violations(violations))
    return 1 if has_errors(violations) else 0


def cmd_check(file_path: str) -> int:
    """Validate a single Python file."""
    path = Path(file_path)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    source = path.read_text(encoding="utf-8")
    violations = validate_module(file_path, source)
    print(format_violations(violations))
    return 1 if has_errors(violations) else 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("Usage: foundry_cli <validate|check> [path]", file=sys.stderr)
        return 1

    command = args[0]
    if command in ("--version", "-v", "version"):
        from phosphene.imi_wordpress import __version__

        print(f"imi-wordpress {__version__}")
        return 0
    elif command == "validate":
        return cmd_validate(args[1] if len(args) > 1 else None)
    elif command == "check":
        if len(args) < 2:
            print("Usage: foundry_cli check <file.py>", file=sys.stderr)
            return 1
        return cmd_check(args[1])
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print("Usage: foundry_cli <validate|check|version> [path]", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
