"""KellyContractValidators — Python projection of Kelly's structured-data rules.

Five static validation methods, each returning a deterministic result
(list of violation paths for no_hollow_fields, bool for the rest).
Shared across Salesforce, WordPress, and Observatory integration tests.

Source of truth: team/platform/seo/jsonld-golden-output.md
(null-omission rules section).

Null-omission rules being asserted:
  1. No hollow fields (empty string, empty dict, empty list).
  4. Author is always Person.
  4a. Only three primary types are valid: Article, ScholarlyArticle, Report.
  5. Dates end in Z (full ISO 8601 with UTC designator).
  Rule: sameAs is an array, not a bare string.

E-09 compliance: no LLM output assertions — all validators test deterministic shapes.
OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from typing import Any

# The three valid primary schema types for Observatory.
# BlogPosting and NewsArticle are explicitly out of scope.
_VALID_SCHEMA_TYPES: frozenset[str] = frozenset(
    {"Article", "ScholarlyArticle", "Report"}
)

# Date fields checked by dates_are_z_form.
_DATE_FIELDS: tuple[str, ...] = ("datePublished", "dateModified", "dateCreated")


class KellyContractValidators:
    """Static validation methods for Kelly's structured-data contract.

    Each method tests a single rule from the golden output contract.
    Methods are pure, deterministic, and independent — they can be
    called individually or composed via validate_all().

    Return conventions:
      - no_hollow_fields: returns list[str] of violation paths (empty = pass).
      - all others: returns bool (True = pass, False = fail).
    """

    @staticmethod
    def no_hollow_fields(jsonld: dict[str, Any]) -> list[str]:
        """Rule 1/3: No hollow fields — empty string, empty dict, or empty list.

        Walks all values recursively. Hollow means:
          - empty string ``""``
          - empty dict ``{}``
          - empty list ``[]``

        Args:
            jsonld: The JSON-LD payload to validate.

        Returns:
            List of dot-path strings for each hollow field found.
            Empty list means the payload is clean.
        """
        violations: list[str] = []
        _collect_hollow(jsonld, path="", violations=violations)
        return violations

    @staticmethod
    def same_as_is_array(jsonld: dict[str, Any]) -> bool:
        """Rule: sameAs must be a list (array), not a bare string.

        sameAs is optional — if absent, returns True.

        Args:
            jsonld: The JSON-LD payload to validate.

        Returns:
            True if sameAs is absent or a list; False if it is a bare string
            or any other non-list type.
        """
        if "sameAs" not in jsonld:
            return True
        return isinstance(jsonld["sameAs"], list)

    @staticmethod
    def author_is_person(jsonld: dict[str, Any]) -> bool:
        """Rule 4: Author @type must be Person, never Organization.

        The WikiSEO defect credited the org as author. The correct
        output credits the individual.

        Author is optional — if absent, returns True.

        Args:
            jsonld: The JSON-LD payload to validate.

        Returns:
            True if author is absent or has @type == "Person"; False otherwise.
        """
        author = jsonld.get("author")
        if author is None:
            return True
        if not isinstance(author, dict):
            return False
        return author.get("@type") == "Person"

    @staticmethod
    def dates_are_z_form(jsonld: dict[str, Any]) -> bool:
        """Rule 5: All date fields must end with 'Z' (UTC designator).

        Checks datePublished, dateModified, and dateCreated.
        All are optional — missing date fields pass.

        Args:
            jsonld: The JSON-LD payload to validate.

        Returns:
            True if all present date fields end with 'Z'; False otherwise.
        """
        for field_name in _DATE_FIELDS:
            value = jsonld.get(field_name)
            if value is not None:
                if not str(value).endswith("Z"):
                    return False
        return True

    @staticmethod
    def schema_type_is_valid(jsonld: dict[str, Any]) -> bool:
        """Rule 4a: @type must be Article, ScholarlyArticle, or Report.

        BlogPosting and NewsArticle are explicitly out of scope.
        Observatory does not publish blog or news content.

        @type is optional — if absent, returns True.
        @type may be a list — at least one element must be in the valid set.

        Args:
            jsonld: The JSON-LD payload to validate.

        Returns:
            True if @type is absent or contains only valid types;
            False if @type contains a type outside the valid set (unless
            the list also contains a valid primary type, for mixed arrays
            like ["Article", "LearningResource"]).
        """
        schema_type = jsonld.get("@type")
        if schema_type is None:
            return True
        if isinstance(schema_type, list):
            # List form: valid if at least one primary type is valid
            has_valid = any(t in _VALID_SCHEMA_TYPES for t in schema_type)
            return has_valid
        # String form
        return schema_type in _VALID_SCHEMA_TYPES

    @classmethod
    def validate_all(cls, jsonld: dict[str, Any]) -> None:
        """Run all five validators against a payload.

        Convenience method for integration tests that want full
        contract validation in one call.

        Args:
            jsonld: The JSON-LD payload to validate.

        Raises:
            AssertionError: On first validation failure, with message
                            indicating which rule failed.
        """
        violations = cls.no_hollow_fields(jsonld)
        assert not violations, f"Hollow fields found: {violations}"

        assert cls.same_as_is_array(jsonld), (
            f"sameAs must be an array, got: {jsonld.get('sameAs')!r}"
        )
        assert cls.author_is_person(jsonld), (
            f"author.@type must be 'Person', got: {jsonld.get('author', {}).get('@type')!r}"
        )
        assert cls.dates_are_z_form(jsonld), (
            "One or more date fields are not in Z form"
        )
        assert cls.schema_type_is_valid(jsonld), (
            f"@type is not in valid set {_VALID_SCHEMA_TYPES}, got: {jsonld.get('@type')!r}"
        )


def _collect_hollow(
    obj: Any,
    path: str,
    violations: list[str],
) -> None:
    """Recursively collect paths to hollow values.

    A hollow value is:
      - empty string ``""``
      - empty dict ``{}``
      - empty list ``[]``

    Args:
        obj: The object to inspect.
        path: Current dot-path (used for error messages).
        violations: Mutable list that accumulates violation paths.
    """
    if isinstance(obj, dict):
        if not obj and path:
            violations.append(path)
            return
        for key, value in obj.items():
            child_path = f"{path}.{key}" if path else key
            _collect_hollow(value, child_path, violations)
    elif isinstance(obj, list):
        if not obj and path:
            violations.append(path)
            return
        for i, item in enumerate(obj):
            _collect_hollow(item, f"{path}[{i}]", violations)
    elif obj == "":
        violations.append(path)
