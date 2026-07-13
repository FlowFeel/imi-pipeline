from unittest.mock import MagicMock

from phosphene.imi.clients.push_client import PushClient


class TestPushClient:
    def test_push_page_calls_site_api_push(self) -> None:
        site = MagicMock()
        site.api.return_value = {"push": {}}
        client = PushClient(site=site, target_name="The Observatory")
        result = client.push_page("Test Article")
        site.api.assert_called_once_with(
            "push", titles="Test Article", targets="The Observatory"
        )
        assert result.succeeded is True

    def test_push_page_passes_correct_target_name(self) -> None:
        site = MagicMock()
        site.api.return_value = {"push": {}}
        client = PushClient(site=site, target_name="My Target")
        client.push_page("Title")
        _, kwargs = site.api.call_args
        assert kwargs["targets"] == "My Target"

    def test_push_page_returns_success_result(self) -> None:
        site = MagicMock()
        site.api.return_value = {"push": {"success": True}}
        client = PushClient(site=site, target_name="The Observatory")
        result = client.push_page("Article")
        assert result.succeeded is True
        assert result.title == "Article"
        assert result.error is None

    def test_push_page_never_raises(self) -> None:
        site = MagicMock()
        site.api.side_effect = RuntimeError("network error")
        client = PushClient(site=site, target_name="The Observatory")
        result = client.push_page("Article")
        assert result.succeeded is False
        assert "network error" in result.error

    def test_push_page_handles_api_errors(self) -> None:
        site = MagicMock()
        site.api.return_value = {
            "push": {"errors": [{"message": "Permission denied"}]}
        }
        client = PushClient(site=site, target_name="The Observatory")
        result = client.push_page("Article")
        assert result.succeeded is False
        assert result.error is not None
