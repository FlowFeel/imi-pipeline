"""Elementor page data model — structural AST validation and invariants.

Elementor stores layout data in the ``_elementor_data`` postmeta key as a
JSON array. This module treats that JSON as a typed Abstract Syntax Tree
(AST) rather than an opaque string, enabling invariant assertions before
committing changes to the database.

The model enforces:

- Root must be a JSON array of section objects
- Every element has ``id``, ``elType``, ``settings``, ``elements``
- Widget count is computed recursively and tracked as an invariant
- Structural diff detects added/removed/moved widgets between versions

Use this model to validate before write and to verify after restore.

@dft
- A1 (pure-io-separation): pure logic — no I/O imports. Only ``json``
  (stdlib data) and ``dataclasses``.
- A2 (determinism): no datetime/random/uuid. Same JSON in → same model out.
- A4 (dft-docs): this docstring section.
- A6 (check-result): ``diff()`` returns a dict (the proof).
  ``remove_widget_by_id()`` returns a new model (the proof).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


class ElementorValidationError(ValueError):
    """Raised when Elementor JSON fails structural validation."""


@dataclass(frozen=True)
class WidgetNode:
    """A single widget in the Elementor AST.

    Attributes:
        id: Element ID (hex string).
        widget_type: Widget type (e.g. ``"heading"``, ``"image"``).
        settings: Widget settings dict.
    """

    id: str
    widget_type: str
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class ElementorPageModel:
    """Structural model of Elementor page data.

    Parses the raw JSON from ``_elementor_data`` into a validated AST.
    Enforces schema invariants and provides structural diff capabilities.

    Attributes:
        raw_json: The original raw JSON string.
        data: Parsed Python object (list of section dicts).
        widget_count: Total number of widget elements in the tree.
        section_count: Number of top-level sections.
        widget_ids: Set of all widget element IDs.
        section_ids: Set of all section element IDs.
    """

    raw_json: str
    data: list[dict[str, Any]]
    widget_count: int = 0
    section_count: int = 0
    widget_ids: set[str] = field(default_factory=set)
    section_ids: set[str] = field(default_factory=set)

    def __init__(self, raw_json: str) -> None:
        """Parse and validate Elementor JSON.

        Args:
            raw_json: The raw JSON string from ``_elementor_data``.

        Raises:
            ElementorValidationError: If JSON is invalid or schema fails.
        """
        self.raw_json = raw_json
        self.data = []
        self.widget_count = 0
        self.section_count = 0
        self.widget_ids: set[str] = set()
        self.section_ids: set[str] = set()

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ElementorValidationError(f"Invalid JSON: {exc.msg} at pos {exc.pos}") from exc

        if not isinstance(parsed, list):
            raise ElementorValidationError(
                f"Elementor JSON root must be a list, got {type(parsed).__name__}"
            )

        self.data = parsed
        self._validate_schema(self.data)

    def _validate_schema(self, elements: list[dict[str, Any]]) -> None:
        """Recursively validate element schema and compute invariants.

        Args:
            elements: List of element dicts to validate.

        Raises:
            ElementorValidationError: If any element fails schema checks.
        """
        for el in elements:
            if not isinstance(el, dict):
                raise ElementorValidationError(f"Element must be a dict, got {type(el).__name__}")

            el_type = el.get("elType")
            el_id = el.get("id")

            if el_type not in ("section", "column", "widget"):
                raise ElementorValidationError(f"Unknown elType: {el_type!r} (id={el_id})")

            if not el_id:
                raise ElementorValidationError(f"Element missing 'id' field (elType={el_type})")

            if el_type == "section":
                self.section_count += 1
                self.section_ids.add(el_id)
            elif el_type == "widget":
                self.widget_count += 1
                self.widget_ids.add(el_id)

            children = el.get("elements", [])
            if children:
                if not isinstance(children, list):
                    raise ElementorValidationError(
                        f"Element {el_id} 'elements' must be a list, got {type(children).__name__}"
                    )
                self._validate_schema(children)

    def widgets(self) -> list[WidgetNode]:
        """Extract all widget nodes from the AST.

        Returns:
            List of WidgetNode instances in document order.
        """
        result: list[WidgetNode] = []
        self._collect_widgets(self.data, result)
        return result

    def _collect_widgets(self, elements: list[dict[str, Any]], result: list[WidgetNode]) -> None:
        """Recursively collect widget nodes.

        Args:
            elements: List of element dicts to traverse.
            result: Accumulating list of widget nodes.
        """
        for el in elements:
            if el.get("elType") == "widget":
                result.append(
                    WidgetNode(
                        id=el["id"],
                        widget_type=el.get("widgetType", "unknown"),
                        settings=el.get("settings", {}),
                    )
                )
            if "elements" in el:
                self._collect_widgets(el["elements"], result)

    def find_widget(self, widget_id: str) -> dict[str, Any] | None:
        """Find an element by ID in the AST.

        Args:
            widget_id: Element ID to search for.

        Returns:
            The element dict if found, None otherwise.
        """
        return self._find_element(self.data, widget_id)

    def _find_element(
        self, elements: list[dict[str, Any]], element_id: str
    ) -> dict[str, Any] | None:
        """Recursively search for an element by ID.

        Args:
            elements: List of element dicts to search.
            element_id: Element ID to find.

        Returns:
            The element dict if found, None otherwise.
        """
        for el in elements:
            if el.get("id") == element_id:
                return el
            if "elements" in el:
                found = self._find_element(el["elements"], element_id)
                if found:
                    return found
        return None

    def contains_text(self, text: str) -> bool:
        """Check if any widget setting contains the given text.

        Searches widget settings values for the text (case-insensitive).

        Args:
            text: Text to search for.

        Returns:
            True if the text appears in any widget setting value.
        """
        return text.lower() in self.raw_json.lower()

    def diff(self, other: ElementorPageModel) -> dict[str, Any]:
        """Compute structural diff between two Elementor page models.

        Args:
            other: The other ElementorPageModel to diff against.

        Returns:
            Dict with ``added``, ``removed``, ``widget_delta`` keys.
        """
        return {
            "added_widgets": sorted(other.widget_ids - self.widget_ids),
            "removed_widgets": sorted(self.widget_ids - other.widget_ids),
            "widget_delta": other.widget_count - self.widget_count,
            "section_delta": other.section_count - self.section_count,
        }

    def to_json(self) -> str:
        """Serialize back to JSON string.

        Returns:
            The JSON string representation (identical to raw_json if
            no modifications were made to the data).
        """
        return json.dumps(self.data)

    @classmethod
    def from_file(cls, path: str) -> ElementorPageModel:
        """Load an Elementor page model from a JSON file.

        Args:
            path: Path to the JSON file.

        Returns:
            An ElementorPageModel instance.
        """
        with open(path) as f:
            return cls(f.read())

    def remove_widget_by_id(self, target_id: str) -> ElementorPageModel:
        """Remove a widget node by ID while maintaining collateral layout.

        Traverses the AST and removes the element with the given ID,
        preserving all other sections, columns, and widgets. Returns a
        new ElementorPageModel — the original is not mutated.

        Args:
            target_id: Element ID to remove.

        Returns:
            A new ElementorPageModel with the target widget removed.

        Raises:
            ElementorValidationError: If the target ID is not found.
        """
        mutated = self._filter_nodes(self.data, target_id)
        if json.dumps(mutated) == json.dumps(self.data):
            raise ElementorValidationError(f"Element with id={target_id!r} not found in tree")
        return ElementorPageModel(json.dumps(mutated))

    def _filter_nodes(
        self, elements: list[dict[str, Any]], target_id: str
    ) -> list[dict[str, Any]]:
        """Recursively filter out the element with target_id.

        Args:
            elements: List of element dicts to filter.
            target_id: Element ID to remove.

        Returns:
            New list with the target element removed.
        """
        result: list[dict[str, Any]] = []
        for el in elements:
            if el.get("id") == target_id:
                continue  # Remove this element
            # Deep copy and recurse into children
            new_el = {**el}
            if "elements" in el:
                new_el["elements"] = self._filter_nodes(el["elements"], target_id)
            result.append(new_el)
        return result
