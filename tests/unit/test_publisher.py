"""Tests for ObservatoryPublisher — V2 URL derivation and publish flow.

Verifies that canonical URLs are derived from the api_url rather than
being hardcoded to observatory.wiki. This ensures V2 portability.
"""

from __future__ import annotations

from phosphene.imi.publisher import ObservatoryPublisher


class TestUrlDerivation:
    """ObservatoryPublisher derives canonical URLs from api_url."""

    def test_derive_wiki_base_standard_path(self) -> None:
        """Standard /w/api.php path derives /wiki/ base."""
        base = ObservatoryPublisher._derive_wiki_base(
            "https://observatory.wiki/w/api.php"
        )
        assert base == "https://observatory.wiki/wiki/"

    def test_derive_wiki_base_bare_api(self) -> None:
        """Bare /api.php path (no /w/) derives /wiki/ base."""
        base = ObservatoryPublisher._derive_wiki_base("http://localhost:8085/api.php")
        assert base == "http://localhost:8085/wiki/"

    def test_derive_wiki_base_with_port(self) -> None:
        """API URL with port derives correct wiki base."""
        base = ObservatoryPublisher._derive_wiki_base("http://localhost:8085/w/api.php")
        assert base == "http://localhost:8085/wiki/"

    def test_canonical_url_uses_derived_base(self) -> None:
        """publish() in dry_run uses derived base, not hardcoded observatory.wiki."""
        from phosphene.imi.draft import Draft

        publisher = ObservatoryPublisher(
            api_url="http://localhost:8085/w/api.php",
            username="Bot",
            password="secret",
            dry_run=True,
        )

        draft = Draft(
            title="Test Article",
            body="Content body",
            author="Flow",
            category="Science",
        )

        url = publisher.publish(draft)
        assert url == "http://localhost:8085/wiki/Test_Article"
        assert "observatory.wiki" not in url

    def test_canonical_url_observatory_wiki(self) -> None:
        """publish() with observatory.wiki API URL still works correctly."""
        from phosphene.imi.draft import Draft

        publisher = ObservatoryPublisher(
            api_url="https://observatory.wiki/w/api.php",
            username="Bot",
            password="secret",
            dry_run=True,
        )

        draft = Draft(
            title="My Article",
            body="Hello world",
            author="Jan",
            category="Research",
        )

        url = publisher.publish(draft)
        assert url == "https://observatory.wiki/wiki/My_Article"
