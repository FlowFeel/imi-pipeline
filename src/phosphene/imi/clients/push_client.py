"""PushClient -- calls the MW Push extension API action via mwclient.

The MW Push extension adds action=push to the MediaWiki API.
This client connects to the SOURCE (editorial) wiki and triggers replication.
The extension authenticates to the target and creates the page there.

This client never touches the target wiki directly -- it fires the push action
on the source and trusts the extension to handle replication. Verification of
arrival is the caller's responsibility (PushOutlet uses mwclient.page.exists).
"""

from __future__ import annotations

from dataclasses import dataclass

import mwclient


@dataclass(frozen=True)
class PushResult:
    """Result of a single push operation."""

    succeeded: bool
    title: str = ""
    error: str | None = None


class PushClient:
    """Client for the MW Push extension API action.

    Args:
        site: An authenticated mwclient.Site connected to the SOURCE wiki.
        target_name: The push target name as configured in the Push extension.
    """

    def __init__(self, site: mwclient.Site, target_name: str) -> None:
        self._site = site
        self._target_name = target_name

    def push_page(self, title: str) -> PushResult:
        """Push a single page to the configured target.

        Never raises. All errors are captured in PushResult.error.

        Args:
            title: The page title to push.

        Returns:
            PushResult with succeeded=True on success, or
            succeeded=False with error populated on failure.
        """
        try:
            result = self._site.api("push", titles=title, targets=self._target_name)
            errors = result.get("push", {}).get("errors", [])
            if errors:
                return PushResult(
                    succeeded=False, title=title, error=str(errors[0])
                )
            return PushResult(succeeded=True, title=title)
        except Exception as exc:
            return PushResult(succeeded=False, title=title, error=str(exc))
