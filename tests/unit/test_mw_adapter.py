"""Tests for MWClientAdapter — mwclient-based MediaWiki adapter.

TDD-first: these tests define the contract before implementation exists.
Mock mwclient.Site via unittest.mock. site.pages.__getitem__ returns mock Page.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from phosphene.imi.clients.mw_adapter import MWClientAdapter


class TestMWClientAdapter:
    """MWClientAdapter satisfies MWClientProtocol via mwclient."""

    def _make_adapter(self, site_mock: MagicMock) -> MWClientAdapter:
        from phosphene.imi.clients.mw_adapter import MWClientAdapter

        return MWClientAdapter(site=site_mock, base_url="http://localhost:8085/w")

    def test_page_exists_true(self) -> None:
        """site.pages[title].exists=True -> adapter returns True."""
        site = MagicMock()
        page = MagicMock()
        page.exists = True
        site.pages.__getitem__.return_value = page

        adapter = self._make_adapter(site)
        assert adapter.page_exists("Test Page") is True
        site.pages.__getitem__.assert_called_once_with("Test Page")

    def test_page_exists_false(self) -> None:
        """site.pages[title].exists=False -> adapter returns False."""
        site = MagicMock()
        page = MagicMock()
        page.exists = False
        site.pages.__getitem__.return_value = page

        adapter = self._make_adapter(site)
        assert adapter.page_exists("Missing Page") is False
        site.pages.__getitem__.assert_called_once_with("Missing Page")

    def test_create_page_calls_page_edit(self) -> None:
        """adapter.create_page() calls page.edit(text, summary)."""
        site = MagicMock()
        page = MagicMock()
        site.pages.__getitem__.return_value = page

        adapter = self._make_adapter(site)
        result = adapter.create_page("New Page", "== Content ==", summary="init")

        # pages[title] called at least once (create_page + page_url)
        site.pages.__getitem__.assert_any_call("New Page")
        page.edit.assert_called_once_with("== Content ==", "init")
        assert "url" in result

    def test_page_url_uses_full_url(self) -> None:
        """adapter.page_url() returns the page's full_url()."""
        site = MagicMock()
        page = MagicMock()
        page.page_url = "http://localhost:8085/w/index.php/Test_Page"
        site.pages.__getitem__.return_value = page

        adapter = self._make_adapter(site)
        url = adapter.page_url("Test Page")

        site.pages.__getitem__.assert_called_once_with("Test Page")
        # full_url is a property on mwclient Page objects; we mock it
        assert url == page.page_url

    def test_connect_mwclient_calls_site_login(self) -> None:
        """connect_mwclient() calls site.login(user, pass)."""
        with patch("mwclient.Site") as MockSite:
            mock_site = MagicMock()
            MockSite.return_value = mock_site

            from phosphene.imi.clients.mw_adapter import connect_mwclient

            result = connect_mwclient(
                base_url="http://localhost:8085/w",
                username="Bot",
                password="secret",
            )

            MockSite.assert_called_once_with(
                "localhost:8085", path="/w/", scheme="http"
            )
            mock_site.login.assert_called_once_with("Bot", "secret")
            assert result is mock_site
