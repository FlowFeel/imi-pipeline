"""IMI Syndication Triggers — adapters that translate external events to SyndicationRequest.

Exports:
- SyndicationTrigger — structural Protocol that all triggers satisfy
- APITrigger — HTTP POST body → SyndicationRequest (simplest trigger)
- TelegramTrigger — /syndicate command → SyndicationRequest
- AsanaTrigger — Asana task → SyndicationRequest
"""

from phosphene.imi.triggers.api_trigger import APITrigger
from phosphene.imi.triggers.asana_trigger import AsanaTrigger
from phosphene.imi.triggers.protocol import SyndicationTrigger
from phosphene.imi.triggers.telegram_trigger import TelegramTrigger

__all__ = [
    "SyndicationTrigger",
    "APITrigger",
    "TelegramTrigger",
    "AsanaTrigger",
]
