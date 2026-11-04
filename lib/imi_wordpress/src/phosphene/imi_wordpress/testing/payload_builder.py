"""Payload builder for WordPress REST API test fixtures.

Provides fluent factory methods for constructing valid, minimal,
draft, and mutated payloads from golden fixture files.

@dft
- A1 (pure-io-separation): I/O wiring module — reads fixture files (allowed).
  The payload construction logic (``valid()``, ``draft()``, etc.) is pure
  once the fixture is loaded.
- A2 (determinism): no datetime/random/uuid. Same fixtures → same payloads.
- A6 (check-result): all methods return payload dicts (the proof).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


class PayloadBuilder:
    """Build REST API payloads from golden fixture files."""

    def __init__(self, fixture_dir: Path | None = None) -> None:
        """Load golden fixtures from fixture_dir.

        Args:
            fixture_dir: Path to fixtures directory. Defaults to
                tests/fixtures/ relative to this file's grandparent.
        """
        if fixture_dir is None:
            # Resolve relative to package: testing/ -> imi_wordpress/ -> phosphene/
            # -> src/ -> project_root/ -> tests/fixtures/
            fixture_dir = Path(__file__).resolve().parents[4] / "tests" / "fixtures"

        golden_path = fixture_dir / "golden-payload.json"
        minimal_path = fixture_dir / "golden-payload-minimal.json"

        with open(golden_path) as f:
            self._golden: dict[str, Any] = json.load(f)

        with open(minimal_path) as f:
            self._minimal: dict[str, Any] = json.load(f)

    def valid(self) -> dict[str, Any]:
        """Return a deep copy of the full golden payload."""
        return copy.deepcopy(self._golden)

    def minimal(self) -> dict[str, Any]:
        """Return a deep copy of the minimal valid payload."""
        return copy.deepcopy(self._minimal)

    def draft(self) -> dict[str, Any]:
        """Return a valid payload with status=draft and no declaration."""
        payload = self.valid()
        payload["status"] = "draft"
        payload["meta"].pop("reg_declaration", None)
        return payload

    def without_field(self, field: str) -> dict[str, Any]:
        """Return a valid payload with one meta field removed.

        Args:
            field: The meta field key to remove.
        """
        payload = self.valid()
        payload["meta"].pop(field, None)
        return payload

    def with_override(self, key: str, value: Any) -> dict[str, Any]:
        """Return a valid payload with a top-level key overridden.

        Args:
            key: Top-level key to set.
            value: Value to assign.
        """
        payload = self.valid()
        payload[key] = value
        return payload

    def with_meta_override(self, field: str, value: Any) -> dict[str, Any]:
        """Return a valid payload with a meta field overridden.

        Args:
            field: Meta field key to set.
            value: Value to assign.
        """
        payload = self.valid()
        payload["meta"][field] = value
        return payload

    def with_empty_required(self, field: str) -> dict[str, Any]:
        """Return a valid payload with a meta field set to empty string.

        Args:
            field: Meta field key to blank out.
        """
        payload = self.valid()
        payload["meta"][field] = ""
        return payload
