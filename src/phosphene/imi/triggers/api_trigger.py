"""APITrigger — HTTP POST body → SyndicationRequest.

The simplest possible trigger: the caller provides all content in the
request body. No content fetching, no parsing. Used by the FastAPI endpoint
at POST /api/syndicate.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi.request import SyndicationRequest


class APITrigger:
    """HTTP POST body → SyndicationRequest.

    Simplest possible trigger: body fields map directly to SyndicationRequest.
    Any fields not supplied use SyndicationRequest defaults.
    """

    source_name = "api"

    async def handle(self, event: dict) -> SyndicationRequest:
        """Convert an API POST body dict into a SyndicationRequest.

        Args:
            event: POST body as dict. Must include at least ``title``.
                   All other fields are optional (defaults apply).

        Returns:
            SyndicationRequest constructed from the event dict.
        """
        return SyndicationRequest(**event)
