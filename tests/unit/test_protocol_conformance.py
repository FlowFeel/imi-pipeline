"""Protocol conformance tests — verify fakes satisfy their protocols.

These are boundary contract tests. They verify that the test doubles
(FakeMWClient, FakeWPClient, FakeSFClient) structurally satisfy the
protocols they claim to implement. If a protocol adds a method and the
fake doesn't implement it, this test catches it before the outlet tests
silently pass with a missing method.

No Docker required. Pure isinstance checks.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi.fakes import FakeMWClient, FakeSFClient, FakeWPClient
from phosphene.imi.protocols import (
    MWClientProtocol,
    SFClientProtocol,
    WPClientProtocol,
)


class TestProtocolConformance:
    """Fakes must structurally satisfy their protocols."""

    def test_fake_mw_satisfies_protocol(self) -> None:
        """FakeMWClient satisfies MWClientProtocol."""
        assert isinstance(FakeMWClient(), MWClientProtocol)

    def test_fake_wp_satisfies_protocol(self) -> None:
        """FakeWPClient satisfies WPClientProtocol."""
        assert isinstance(FakeWPClient(), WPClientProtocol)

    def test_fake_sf_satisfies_protocol(self) -> None:
        """FakeSFClient satisfies SFClientProtocol."""
        assert isinstance(FakeSFClient(), SFClientProtocol)

    def test_mw_protocol_has_delete_page(self) -> None:
        """MWClientProtocol defines delete_page for saga compensation."""
        assert hasattr(MWClientProtocol, "delete_page")

    def test_wp_protocol_has_delete_post(self) -> None:
        """WPClientProtocol defines delete_post for saga compensation."""
        assert hasattr(WPClientProtocol, "delete_post")

    def test_sf_protocol_has_delete_record(self) -> None:
        """SFClientProtocol defines delete_record for saga compensation."""
        assert hasattr(SFClientProtocol, "delete_record")

    def test_urllib_mw_client_satisfies_protocol(self) -> None:
        """UrllibMWClient satisfies MWClientProtocol."""
        from phosphene.imi.clients.mediawiki import MWConfig, UrllibMWClient

        cfg = MWConfig(base_url="https://test.wiki", username="u", password="p")
        client = UrllibMWClient(cfg)
        assert isinstance(client, MWClientProtocol)
