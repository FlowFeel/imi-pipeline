"""Tests for PushOutlet using a fake MagazineClientProtocol.

The fake magazine client replaces mwclient.Site entirely.
No mwclient dependency, no real wiki — pure protocol-based tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from phosphene.imi.clients.push_client import PushResult
from phosphene.imi.draft import Draft
from phosphene.imi.event import PublicationEvent
from phosphene.imi.outlets.push import PushOutlet


class FakeMagazineClient:
    """Test double for MagazineClientProtocol.

    Records page existence and returns deterministic URLs.
    """

    def __init__(self, base_url: str = "https://mag.test") -> None:
        self._existing: set[str] = set()
        self.base_url = base_url

    def add_page(self, title: str) -> None:
        """Simulate a page existing on the magazine wiki."""
        self._existing.add(title)

    def page_exists(self, title: str) -> bool:
        return title in self._existing

    def page_url(self, title: str) -> str:
        return f"{self.base_url}/wiki/{title.replace(' ', '_')}"


def make_event(title: str = "Test Article") -> PublicationEvent:
    draft = Draft(title=title, body="Body", author="Author", category="Test")
    return PublicationEvent(draft=draft, publisher_id="flow")


class TestPushOutlet:
    """Tests for PushOutlet using FakeMagazineClient."""

    def test_push_outlet_pushes_when_not_on_magazine(self) -> None:
        """Push fires when the page doesn't exist on the target."""
        push_client = MagicMock()
        push_client.push_page.return_value = PushResult(
            succeeded=True, title="Test Article"
        )
        magazine = FakeMagazineClient()
        # Simulate: page doesn't exist before push, exists after
        call_count = [0]

        def fake_exists(title: str) -> bool:
            call_count[0] += 1
            if call_count[0] == 1:
                return False  # idempotency check
            return True  # verification after push

        magazine.page_exists = fake_exists  # type: ignore[method-assign]

        outlet = PushOutlet(push_client=push_client, magazine_client=magazine)
        result = outlet.publish(make_event())
        push_client.push_page.assert_called_once_with("Test Article")
        assert result.succeeded is True

    def test_push_outlet_idempotent(self) -> None:
        """If the page already exists, no push is attempted."""
        push_client = MagicMock()
        magazine = FakeMagazineClient()
        magazine.add_page("Test Article")

        outlet = PushOutlet(push_client=push_client, magazine_client=magazine)
        result = outlet.publish(make_event())
        push_client.push_page.assert_not_called()
        assert result.succeeded is True
        assert result.metadata.get("idempotent") == "true"

    def test_push_outlet_fails_if_not_arrived(self) -> None:
        """Push reports success but page doesn't appear on target."""
        push_client = MagicMock()
        push_client.push_page.return_value = PushResult(succeeded=True, title="Article")
        magazine = FakeMagazineClient()
        # Page never appears — page_exists always False

        outlet = PushOutlet(push_client=push_client, magazine_client=magazine)
        result = outlet.publish(make_event())
        assert result.succeeded is False
        assert "not found" in (result.error or "").lower()

    def test_push_outlet_returns_full_url(self) -> None:
        """After successful push, the artifact is the magazine URL."""
        push_client = MagicMock()
        push_client.push_page.return_value = PushResult(succeeded=True, title="Article")
        magazine = FakeMagazineClient(base_url="https://observatory.wiki")

        # Simulate page appearing after push
        original_exists = magazine.page_exists
        call_count = [0]

        def side_effect(title: str) -> bool:
            call_count[0] += 1
            return call_count[0] > 1  # False first, True after

        magazine.page_exists = side_effect  # type: ignore[method-assign]

        outlet = PushOutlet(push_client=push_client, magazine_client=magazine)
        result = outlet.publish(make_event(title="Article"))
        assert result.artifact == "https://observatory.wiki/wiki/Article"

    def test_outlet_name_is_push(self) -> None:
        """Outlet name identifies itself correctly."""
        outlet = PushOutlet(
            push_client=MagicMock(), magazine_client=FakeMagazineClient()
        )
        assert outlet.name == "push"
