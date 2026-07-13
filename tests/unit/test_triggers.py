"""Tests for IMI syndication trigger adapters.

Verifies each trigger's handle() produces correct SyndicationRequest output
given sample event dicts. All tests use DI only — no mocking.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import pytest

from phosphene.imi.request import SyndicationRequest
from phosphene.imi.triggers import APITrigger, AsanaTrigger, TelegramTrigger
from phosphene.imi.triggers.protocol import SyndicationTrigger

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestSyndicationTriggerProtocol:
    """Each concrete trigger satisfies the SyndicationTrigger protocol."""

    def test_api_trigger_satisfies_protocol(self) -> None:
        assert isinstance(APITrigger(), SyndicationTrigger)

    def test_telegram_trigger_satisfies_protocol(self) -> None:
        assert isinstance(TelegramTrigger(), SyndicationTrigger)

    def test_asana_trigger_satisfies_protocol(self) -> None:
        assert isinstance(AsanaTrigger(), SyndicationTrigger)


# ---------------------------------------------------------------------------
# APITrigger
# ---------------------------------------------------------------------------


class TestAPITrigger:
    """APITrigger converts POST body dict to SyndicationRequest verbatim."""

    @pytest.mark.asyncio
    async def test_full_event(self) -> None:
        trigger = APITrigger()
        event = {
            "title": "Cave Art in France",
            "body": "{{Article|Headline=Cave Art}}",
            "body_format": "wikitext",
            "author": "Jan",
            "outlets": {
                "wordpress": True,
                "salesforce": False,
                "mediawiki": True,
                "pardot": False,
            },
        }
        result = await trigger.handle(event)
        assert isinstance(result, SyndicationRequest)
        assert result.title == "Cave Art in France"
        assert result.body == "{{Article|Headline=Cave Art}}"
        assert result.author == "Jan"
        assert result.outlets["wordpress"] is True
        assert result.outlets["salesforce"] is False
        assert result.trigger_source == ""  # not set by APITrigger — set by caller

    @pytest.mark.asyncio
    async def test_minimal_event_uses_defaults(self) -> None:
        trigger = APITrigger()
        result = await trigger.handle({"title": "Minimum Test"})
        assert result.title == "Minimum Test"
        assert result.body == ""
        assert result.outlets["wordpress"] is True
        assert result.outlets["pardot"] is False

    @pytest.mark.asyncio
    async def test_idempotency_key_derived_from_title(self) -> None:
        trigger = APITrigger()
        result = await trigger.handle({"title": "My Great Article"})
        assert result.idempotency_key == "my-great-article"

    @pytest.mark.asyncio
    async def test_source_name(self) -> None:
        assert APITrigger().source_name == "api"


# ---------------------------------------------------------------------------
# TelegramTrigger
# ---------------------------------------------------------------------------


class TestTelegramTrigger:
    """TelegramTrigger parses /syndicate commands from Telegram messages."""

    @pytest.mark.asyncio
    async def test_simple_url(self) -> None:
        trigger = TelegramTrigger()
        event = {
            "message": "/syndicate https://observatory.wiki/Cave_Art_in_France",
            "sender_id": "user123",
        }
        result = await trigger.handle(event)
        assert isinstance(result, SyndicationRequest)
        assert result.source_url == "https://observatory.wiki/Cave_Art_in_France"
        assert result.trigger_source == "telegram"
        assert result.publisher_id == "user123"
        assert result.outlets["wordpress"] is True
        assert result.outlets["pardot"] is False

    @pytest.mark.asyncio
    async def test_url_with_outlets_flag(self) -> None:
        trigger = TelegramTrigger()
        event = {
            "message": "/syndicate --outlets=wordpress,pardot https://observatory.wiki/Test_Article",
            "sender_id": "user456",
        }
        result = await trigger.handle(event)
        assert result.outlets["wordpress"] is True
        assert result.outlets["pardot"] is True
        assert result.outlets["salesforce"] is False
        assert result.outlets["mediawiki"] is False

    @pytest.mark.asyncio
    async def test_title_extracted_from_slug(self) -> None:
        trigger = TelegramTrigger()
        event = {
            "message": "/syndicate https://observatory.wiki/Cave_Art_in_France",
            "sender_id": "x",
        }
        result = await trigger.handle(event)
        assert result.title == "Cave Art in France"

    @pytest.mark.asyncio
    async def test_title_with_hyphens(self) -> None:
        trigger = TelegramTrigger()
        event = {
            "message": "/syndicate https://observatory.wiki/climate-crisis-2026",
            "sender_id": "x",
        }
        result = await trigger.handle(event)
        assert result.title == "climate crisis 2026"

    @pytest.mark.asyncio
    async def test_body_is_empty_placeholder(self) -> None:
        trigger = TelegramTrigger()
        event = {
            "message": "/syndicate https://observatory.wiki/Test",
            "sender_id": "x",
        }
        result = await trigger.handle(event)
        assert result.body == ""

    @pytest.mark.asyncio
    async def test_missing_sender_id_defaults_to_unknown(self) -> None:
        trigger = TelegramTrigger()
        event = {"message": "/syndicate https://observatory.wiki/Test"}
        result = await trigger.handle(event)
        assert result.publisher_id == "unknown"

    @pytest.mark.asyncio
    async def test_source_name(self) -> None:
        assert TelegramTrigger().source_name == "telegram"

    @pytest.mark.asyncio
    async def test_unknown_outlets_ignored(self) -> None:
        trigger = TelegramTrigger()
        event = {
            "message": "/syndicate --outlets=wordpress,fakeoutlet https://observatory.wiki/Test",
            "sender_id": "x",
        }
        result = await trigger.handle(event)
        # fakeoutlet should be ignored; only wordpress selected
        assert result.outlets["wordpress"] is True
        assert result.outlets["salesforce"] is False
        assert "fakeoutlet" not in result.outlets


# ---------------------------------------------------------------------------
# AsanaTrigger
# ---------------------------------------------------------------------------


class TestAsanaTrigger:
    """AsanaTrigger converts Asana task dicts to SyndicationRequest."""

    @pytest.mark.asyncio
    async def test_basic_task(self) -> None:
        trigger = AsanaTrigger()
        event = {
            "task": {
                "name": "Publish: Cave Art Coverage",
                "notes": "Article notes here.",
                "assignee": {"name": "Jan", "gid": "111222333"},
                "due_on": "2026-07-01",
            }
        }
        result = await trigger.handle(event)
        assert result.title == "Publish: Cave Art Coverage"
        assert result.body == "Article notes here."
        assert result.author == "Jan"
        assert result.date == "2026-07-01"
        assert result.trigger_source == "asana"
        assert result.publisher_id == "111222333"

    @pytest.mark.asyncio
    async def test_default_outlets_when_none_specified(self) -> None:
        trigger = AsanaTrigger()
        event = {"task": {"name": "Test Article", "notes": ""}}
        result = await trigger.handle(event)
        assert result.outlets["wordpress"] is True
        assert result.outlets["salesforce"] is True
        assert result.outlets["mediawiki"] is True
        assert result.outlets["pardot"] is False

    @pytest.mark.asyncio
    async def test_custom_field_outlets(self) -> None:
        trigger = AsanaTrigger()
        event = {
            "task": {
                "name": "Custom Outlets Test",
                "notes": "",
                "custom_fields": [
                    {
                        "name": "Outlets",
                        "multi_enum_values": [
                            {"name": "wordpress"},
                            {"name": "pardot"},
                        ],
                    }
                ],
            }
        }
        result = await trigger.handle(event)
        assert result.outlets["wordpress"] is True
        assert result.outlets["pardot"] is True
        assert result.outlets["salesforce"] is False
        assert result.outlets["mediawiki"] is False

    @pytest.mark.asyncio
    async def test_bare_task_dict_without_task_key(self) -> None:
        """Event dict without a 'task' key is treated as the task itself."""
        trigger = AsanaTrigger()
        event = {"name": "Direct Task", "notes": "Direct notes."}
        result = await trigger.handle(event)
        assert result.title == "Direct Task"
        assert result.body == "Direct notes."

    @pytest.mark.asyncio
    async def test_no_assignee_uses_asana_publisher(self) -> None:
        trigger = AsanaTrigger()
        event = {"task": {"name": "No Assignee Task", "notes": ""}}
        result = await trigger.handle(event)
        assert result.publisher_id == "asana"

    @pytest.mark.asyncio
    async def test_source_name(self) -> None:
        assert AsanaTrigger().source_name == "asana"

    @pytest.mark.asyncio
    async def test_tag_based_outlet_selection(self) -> None:
        trigger = AsanaTrigger()
        event = {
            "task": {
                "name": "Tagged Task",
                "notes": "",
                "tags": [{"name": "wordpress"}, {"name": "salesforce"}],
            }
        }
        result = await trigger.handle(event)
        assert result.outlets["wordpress"] is True
        assert result.outlets["salesforce"] is True
        assert result.outlets["mediawiki"] is False
        assert result.outlets["pardot"] is False
