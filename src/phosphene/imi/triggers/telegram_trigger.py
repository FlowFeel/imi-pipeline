"""TelegramTrigger — parse /syndicate commands from Telegram messages.

Parses commands in the format:
  /syndicate https://observatory.wiki/Article_Title
  /syndicate --outlets=wordpress,pardot https://observatory.wiki/Article

Content body fetching is a later step — this trigger creates a minimal
SyndicationRequest with the URL and outlet selection populated.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.utils.text import extract_url_title, parse_command_line

from phosphene.imi.request import SyndicationRequest

# Default outlets when none are specified in the command
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


class TelegramTrigger:
    """Parse /syndicate commands from Telegram messages.

    Translates Telegram bot commands into SyndicationRequests.
    Content fetching (body field) is deferred to the workflow activities —
    this trigger populates source_url and outlet selection only.
    """

    source_name = "telegram"

    async def handle(self, event: dict) -> SyndicationRequest:
        """Convert a Telegram message event into a SyndicationRequest.

        Args:
            event: Telegram event dict with at least a ``message`` key
                   containing the command text, and optionally ``sender_id``.

        Returns:
            SyndicationRequest with source_url, outlets, and publisher_id set.
            Body is empty — content fetching is a later pipeline step.
        """
        text = event.get("message", "")
        url, outlets = self._parse_command(text)
        return SyndicationRequest(
            title=self._extract_title(url),
            body="",  # placeholder — will be fetched by workflow activity
            source_url=url,
            outlets=outlets,
            trigger_source="telegram",
            publisher_id=event.get("sender_id", "unknown"),
        )

    def _parse_command(self, text: str) -> tuple[str, dict[str, bool]]:
        """Parse '/syndicate [--outlets=x,y] <url>' format.

        Extracts the optional --outlets flag and the URL from the command text.
        If --outlets is absent, all default outlets apply.

        Args:
            text: Raw command text, e.g.
                  '/syndicate --outlets=wordpress,pardot https://observatory.wiki/Foo'

        Returns:
            Tuple of (url, outlets_dict). url may be empty if not found.
        """
        url, flags = parse_command_line(text)
        outlets = dict(_DEFAULT_OUTLETS)
        if "outlets" in flags:
            selected = {o.strip().lower() for o in flags["outlets"].split(",")}
            # Allow only known outlets; unknown ones are silently dropped
            valid_selected = selected & _KNOWN_OUTLETS
            outlets = {name: (name in valid_selected) for name in _KNOWN_OUTLETS}

        return url, outlets

    def _extract_title(self, url: str) -> str:
        r"""Extract an article title from an Observatory URL slug.

        Converts a URL path like '/Cave_Art_in_France' to 'Cave Art in France\.
        Falls back to the raw URL if no path is found.

        Args:
            url: Observatory article URL.

        Returns:
            Human-readable title derived from the URL path, or the URL itself.
        """
        return extract_url_title(url)
