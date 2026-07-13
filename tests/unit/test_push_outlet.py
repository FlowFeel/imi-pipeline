from unittest.mock import MagicMock

from phosphene.imi.clients.push_client import PushResult
from phosphene.imi.draft import Draft
from phosphene.imi.event import PublicationEvent
from phosphene.imi.outlets.push import PushOutlet


def make_event(title: str = "Test Article") -> PublicationEvent:
    draft = Draft(title=title, body="Body", author="Author", category="Test")
    return PublicationEvent(draft=draft, publisher_id="flow")


class TestPushOutlet:
    def test_push_outlet_pushes_when_not_on_magazine(self) -> None:
        push_client = MagicMock()
        push_client.push_page.return_value = PushResult(
            succeeded=True, title="Test Article"
        )
        magazine_site = MagicMock()
        # After push, page.exists becomes True on re-fetch
        page_mock = MagicMock()
        page_mock.exists = True
        page_mock.full_url.return_value = "http://mag/wiki/Test_Article"
        magazine_site.pages.__getitem__.side_effect = [
            MagicMock(exists=False),  # idempotency check
            page_mock,  # verification after push
        ]
        outlet = PushOutlet(
            push_client=push_client, magazine_site=magazine_site
        )
        result = outlet.publish(make_event())
        push_client.push_page.assert_called_once_with("Test Article")
        assert result.succeeded is True

    def test_push_outlet_idempotent(self) -> None:
        push_client = MagicMock()
        magazine_site = MagicMock()
        page = MagicMock()
        page.exists = True
        page.full_url.return_value = "http://mag/wiki/Test"
        magazine_site.pages.__getitem__.return_value = page
        outlet = PushOutlet(
            push_client=push_client, magazine_site=magazine_site
        )
        result = outlet.publish(make_event())
        push_client.push_page.assert_not_called()
        assert result.succeeded is True
        assert result.metadata.get("idempotent") == "true"

    def test_push_outlet_fails_if_not_arrived(self) -> None:
        push_client = MagicMock()
        push_client.push_page.return_value = PushResult(
            succeeded=True, title="Article"
        )
        magazine_site = MagicMock()
        # page.exists always False -- push "succeeded" but never arrived
        magazine_site.pages.__getitem__.return_value.exists = False
        outlet = PushOutlet(
            push_client=push_client, magazine_site=magazine_site
        )
        result = outlet.publish(make_event())
        assert result.succeeded is False
        assert "not found" in result.error.lower()

    def test_push_outlet_returns_full_url(self) -> None:
        push_client = MagicMock()
        push_client.push_page.return_value = PushResult(
            succeeded=True, title="Article"
        )
        magazine_site = MagicMock()
        page_before = MagicMock(exists=False)
        page_after = MagicMock(exists=True)
        page_after.full_url.return_value = (
            "https://observatory.wiki/wiki/Article"
        )
        magazine_site.pages.__getitem__.side_effect = [
            page_before,
            page_after,
        ]
        outlet = PushOutlet(
            push_client=push_client, magazine_site=magazine_site
        )
        result = outlet.publish(make_event(title="Article"))
        assert result.artifact == "https://observatory.wiki/wiki/Article"

    def test_outlet_name_is_push(self) -> None:
        outlet = PushOutlet(
            push_client=MagicMock(), magazine_site=MagicMock()
        )
        assert outlet.name == "push"
