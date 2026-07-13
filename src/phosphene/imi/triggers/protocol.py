"""SyndicationTrigger protocol — the adapter interface for all IMI trigger sources.

Any system that can initiate a syndication implements this protocol:
  - AsanaTrigger
  - TelegramTrigger
  - APITrigger
  - MWHookTrigger

Triggers are adapters: they translate external events into a SyndicationRequest.
They do NOT know about outlet internals, failure handling, or content transformation.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from phosphene.imi.request import SyndicationRequest


@runtime_checkable
class SyndicationTrigger(Protocol):
    """Any system that can initiate a syndication.

    Triggers are adapters: they translate external events (Asana task
    created, Telegram command received, API POST, MW hook) into a
    SyndicationRequest.

    Responsibilities:
    1. Extract content (title, body, author, etc.)
    2. Determine outlet selection (from user input or defaults)
    3. Build the SyndicationRequest

    Non-responsibilities:
    - Outlet internals
    - Outlet failure handling (that's the saga's job)
    - Content transformation for specific outlets (outlet's job)
    """

    async def handle(self, event: dict) -> SyndicationRequest:
        """Parse an external event into a SyndicationRequest.

        Args:
            event: Raw event data from the trigger source.

        Returns:
            A fully populated SyndicationRequest.
        """
        ...

    @property
    def source_name(self) -> str:
        """Short identifier for this trigger source (e.g. 'asana', 'telegram')."""
        ...
