"""AsanaTrigger — Asana task → SyndicationRequest.

Reads from Asana task fields:
- Task name → title
- Task description (notes) → body
- Custom field 'Outlets' (multi-select) → outlet selection
  (falls back to all outlets if not present)
- Assignee → author + publisher_id
- Due date → date

Outlet selection is parsed from the 'custom_fields' list on the task,
looking for a field named 'Outlets' or 'outlets'. Falls back to all
outlets if the field is absent or empty.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi.request import SyndicationRequest

# Default outlets when none are specified in the Asana task
_DEFAULT_OUTLETS: dict[str, bool] = {
    "wordpress": True,
    "salesforce": True,
    "mediawiki": True,
    "pardot": False,
}

# All known outlet names for validation
_KNOWN_OUTLETS: frozenset[str] = frozenset(
    ["wordpress", "salesforce", "mediawiki", "pardot"]
)


class AsanaTrigger:
    """Asana task → SyndicationRequest.

    Reads outlet selection from Asana custom fields or tags.
    If no outlet field is present, defaults to all outlets (pardot opt-in).
    """

    source_name = "asana"

    async def handle(self, event: dict) -> SyndicationRequest:
        """Convert an Asana webhook event or task dict into a SyndicationRequest.

        Args:
            event: Asana event dict. May be a raw webhook event with a
                   nested ``task`` key, or a bare task dict directly.

        Returns:
            SyndicationRequest populated from the Asana task fields.
        """
        task = event.get("task", event)
        return SyndicationRequest(
            title=task.get("name", ""),
            body=task.get("notes", ""),
            author=task.get("assignee", {}).get("name", ""),
            date=task.get("due_on", ""),
            outlets=self._parse_outlets(task),
            trigger_source="asana",
            publisher_id=self._resolve_publisher(task),
        )

    def _parse_outlets(self, task: dict) -> dict[str, bool]:
        """Parse outlet selection from Asana custom fields or tags.

        Looks for a custom field named 'Outlets' or 'outlets' and reads
        its multi-select values. Falls back to default (all outlets minus
        pardot) if the field is absent or has no recognised values.

        Args:
            task: Asana task dict, may include a ``custom_fields`` list.

        Returns:
            Outlet selection dict with bool values per outlet name.
        """
        custom_fields = task.get("custom_fields", [])
        for field in custom_fields:
            field_name = field.get("name", "").lower()
            if field_name in ("outlets", "outlet"):
                # Multi-select enum values
                multi_values = field.get("multi_enum_values", [])
                if multi_values:
                    selected = {v.get("name", "").lower() for v in multi_values}
                    valid = selected & _KNOWN_OUTLETS
                    if valid:
                        return {name: (name in valid) for name in _KNOWN_OUTLETS}

        # Check tags as fallback
        tags = task.get("tags", [])
        tag_names = {t.get("name", "").lower() for t in tags}
        tag_outlets = tag_names & _KNOWN_OUTLETS
        if tag_outlets:
            return {name: (name in tag_outlets) for name in _KNOWN_OUTLETS}

        # Default: all outlets (pardot opt-in only)
        return dict(_DEFAULT_OUTLETS)

    def _resolve_publisher(self, task: dict) -> str:
        """Resolve a publisher ID from the Asana task.

        Uses assignee GID if available, falls back to 'asana'.

        Args:
            task: Asana task dict.

        Returns:
            Publisher identifier string.
        """
        assignee = task.get("assignee", {})
        return assignee.get("gid", "asana") or "asana"
