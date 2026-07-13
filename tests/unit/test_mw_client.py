"""Tests for UrllibMWClient — MediaWiki bot auth via urllib.

TDD: these tests are written BEFORE the implementation.
All tests use unittest.mock to avoid real HTTP calls.
Verifies the MWClientProtocol contract plus login/CSRF flows.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from phosphene.imi.clients.mediawiki import UrllibMWClient


class TestMWConfigFromEnv:
    """MWConfig.from_env() reads MW_BASE_URL, MW_USERNAME, MW_PASSWORD."""

    def test_mwconfig_from_env_raises_on_missing_var(self) -> None:
        """from_env raises EnvironmentError on missing var."""
        from phosphene.imi.clients.mediawiki import MWConfig

        env = {
            "MW_BASE_URL": "https://observatory.wiki",
            "MW_USERNAME": "bot",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(EnvironmentError),
        ):
            MWConfig.from_env()

    def test_mwconfig_from_env_constructs_correctly(self) -> None:
        """from_env() returns a properly populated MWConfig."""
        from phosphene.imi.clients.mediawiki import MWConfig

        env = {
            "MW_BASE_URL": "https://observatory.wiki",
            "MW_USERNAME": "FlowBot",
            "MW_PASSWORD": "secret123",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = MWConfig.from_env()
        assert cfg.base_url == "https://observatory.wiki"
        assert cfg.username == "FlowBot"
        assert cfg.password == "secret123"


class TestPageExists:
    """page_exists() queries the MW API and checks 'missing' key."""

    def _make_client(self) -> UrllibMWClient:
        from phosphene.imi.clients.mediawiki import (
            MWConfig,
            UrllibMWClient,
        )

        cfg = MWConfig(
            base_url="https://observatory.wiki",
            username="bot",
            password="pass",
        )
        return UrllibMWClient(cfg)

    def test_page_exists_returns_true_when_found(self) -> None:
        """Returns True when API response has no 'missing' key."""
        client = self._make_client()
        api_response = {
            "query": {
                "pages": {
                    "123": {
                        "pageid": 123,
                        "ns": 0,
                        "title": "Test Page",
                    }
                }
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(api_response).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "urllib.request.OpenerDirector.open",
            return_value=mock_resp,
        ):
            assert client.page_exists("Test Page") is True

    def test_page_exists_returns_false_when_missing(self) -> None:
        """Returns False when API response has 'missing' key."""
        client = self._make_client()
        api_response = {
            "query": {
                "pages": {
                    "-1": {
                        "ns": 0,
                        "title": "Nonexistent",
                        "missing": "",
                    }
                }
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(api_response).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "urllib.request.OpenerDirector.open",
            return_value=mock_resp,
        ):
            assert client.page_exists("Nonexistent") is False


class TestPageUrl:
    """page_url() formats a canonical wiki URL from the title."""

    def test_page_url_format(self) -> None:
        """page_url returns base_url/wiki/Title_With_Underscores."""
        from phosphene.imi.clients.mediawiki import (
            MWConfig,
            UrllibMWClient,
        )

        cfg = MWConfig(
            base_url="https://observatory.wiki",
            username="bot",
            password="pass",
        )
        client = UrllibMWClient(cfg)
        url = client.page_url("My Test Page")
        assert url == "https://observatory.wiki/wiki/My_Test_Page"


class TestCreatePage:
    """create_page() sends action=edit with the CSRF token."""

    def _make_client(self) -> UrllibMWClient:
        from phosphene.imi.clients.mediawiki import (
            MWConfig,
            UrllibMWClient,
        )

        cfg = MWConfig(
            base_url="https://observatory.wiki",
            username="bot",
            password="pass",
        )
        return UrllibMWClient(cfg)

    def test_create_page_sends_correct_request(self) -> None:
        """Calls the edit API with title, text, summary, token."""
        client = self._make_client()
        client._csrf_token = "test_csrf+\\"

        edit_response = {
            "edit": {
                "result": "Success",
                "pageid": 456,
                "title": "New Page",
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(edit_response).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "urllib.request.OpenerDirector.open",
            return_value=mock_resp,
        ) as mock_open:
            result = client.create_page("New Page", "== Hello ==", summary="test edit")

        assert result["edit"]["result"] == "Success"
        mock_open.assert_called_once()
        call_args = mock_open.call_args
        req = call_args[0][0]
        assert b"action=edit" in req.data
        assert b"New+Page" in req.data or b"New%20Page" in req.data

    def test_create_page_uses_csrf_token(self) -> None:
        """create_page includes the CSRF token in the POST body."""
        client = self._make_client()
        client._csrf_token = "abc123+\\"

        edit_response = {"edit": {"result": "Success", "pageid": 789, "title": "T"}}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(edit_response).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "urllib.request.OpenerDirector.open",
            return_value=mock_resp,
        ) as mock_open:
            client.create_page("T", "content")

        call_args = mock_open.call_args
        req = call_args[0][0]
        assert b"abc123" in req.data


class TestEditPage:
    """edit_page() sends action=edit WITHOUT createonly — for V2 update support."""

    def _make_client(self) -> UrllibMWClient:
        from phosphene.imi.clients.mediawiki import (
            MWConfig,
            UrllibMWClient,
        )

        cfg = MWConfig(
            base_url="https://observatory.wiki",
            username="bot",
            password="pass",
        )
        return UrllibMWClient(cfg)

    def test_edit_page_omits_createonly(self) -> None:
        """edit_page does NOT include createonly — allows updates."""
        client = self._make_client()
        client._csrf_token = "test_csrf+\\"

        edit_response = {
            "edit": {"result": "Success", "pageid": 456, "title": "Existing"}
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(edit_response).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "urllib.request.OpenerDirector.open",
            return_value=mock_resp,
        ) as mock_open:
            result = client.edit_page("Existing", "== Updated ==", summary="update")

        assert result["edit"]["result"] == "Success"
        call_args = mock_open.call_args
        req = call_args[0][0]
        assert b"action=edit" in req.data
        assert b"createonly" not in req.data

    def test_edit_page_returns_error_dict_on_failure(self) -> None:
        """edit_page returns error dict on exception, never raises."""
        client = self._make_client()
        client._csrf_token = "token+\\"

        with patch(
            "urllib.request.OpenerDirector.open",
            side_effect=Exception("Connection timeout"),
        ):
            result = client.edit_page("Fail", "content")

        assert "error" in result
        assert "Connection timeout" in result["error"]

    def test_create_page_includes_createonly(self) -> None:
        """create_page includes createonly=true — refuses to overwrite."""
        client = self._make_client()
        client._csrf_token = "test_csrf+\\"

        edit_response = {
            "edit": {"result": "Success", "pageid": 789, "title": "New"}
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(edit_response).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "urllib.request.OpenerDirector.open",
            return_value=mock_resp,
        ) as mock_open:
            client.create_page("New", "== Hello ==")

        call_args = mock_open.call_args
        req = call_args[0][0]
        assert b"createonly" in req.data


class TestLoginTokenHandling:
    """Login uses logintoken — correct for MW 1.27+ including MW 1.43 (V2)."""

    def _make_client(self) -> UrllibMWClient:
        from phosphene.imi.clients.mediawiki import (
            MWConfig,
            UrllibMWClient,
        )

        cfg = MWConfig(
            base_url="https://observatory.wiki",
            username="FlowBot",
            password="secret",
        )
        return UrllibMWClient(cfg)

    def test_login_sends_logintoken_as_lgtoken(self) -> None:
        """Login step 2 sends the logintoken value as lgtoken param."""
        client = self._make_client()

        token_response = {
            "query": {"tokens": {"logintoken": "abc123token+\\"}}
        }
        login_response = {
            "login": {"result": "Success", "lgusername": "FlowBot"}
        }

        call_count = 0

        def mock_open_handler(req):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            if call_count == 1:
                mock_resp.read.return_value = json.dumps(token_response).encode()
            else:
                mock_resp.read.return_value = json.dumps(login_response).encode()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch(
            "urllib.request.OpenerDirector.open",
            side_effect=mock_open_handler,
        ) as mock_open:
            result = client.login()

        assert result["login"]["result"] == "Success"
        assert call_count == 2
        # Step 2 should include lgtoken
        step2_req = mock_open.call_args_list[1][0][0]
        assert b"lgtoken" in step2_req.data
        assert b"abc123token" in step2_req.data


class TestErrorHandling:
    """Client returns error dicts instead of raising exceptions."""

    def test_client_handles_api_error_gracefully(self) -> None:
        """On error, create_page returns an error dict, never raises."""
        from phosphene.imi.clients.mediawiki import (
            MWConfig,
            UrllibMWClient,
        )

        cfg = MWConfig(
            base_url="https://observatory.wiki",
            username="bot",
            password="pass",
        )
        client = UrllibMWClient(cfg)
        client._csrf_token = "token+\\"

        with patch(
            "urllib.request.OpenerDirector.open",
            side_effect=Exception("Connection refused"),
        ):
            result = client.create_page("Fail", "content")

        assert "error" in result
        assert "Connection refused" in result["error"]
