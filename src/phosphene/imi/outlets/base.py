"""PublicationOutlet — the abstract base for all distribution targets.

Every outlet in the publish pipeline implements this interface.
Adding a new distribution target means adding one new outlet class.
The pipeline DAG gets a new node. Nothing else changes.

The outlet contract:
  - Receives a PublicationEvent (read-only)
  - Returns an OutletResult
  - Never raises — errors are captured in OutletResult.error
  - Is independently testable
  - Has no knowledge of other outlets

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from phosphene.imi.event import OutletResult, PublicationEvent


class PublicationOutlet(ABC):
    """Abstract base for all publication outlets.

    Subclass this to add a new distribution target.
    Override publish() with the outlet-specific logic.

    The name property identifies this outlet in reports and logs.
    It should be a short lowercase slug: 'observatory', 'salesforce', etc.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short slug identifying this outlet."""
        ...

    @abstractmethod
    def publish(self, event: PublicationEvent) -> OutletResult:
        """Publish the event to this outlet.

        Must never raise. Capture all errors in OutletResult.error.

        Args:
            event: The publication event carrying the draft and context.

        Returns:
            OutletResult with succeeded=True if the outlet completed,
            or succeeded=False with error populated if it failed.
        """
        ...

    def __repr__(self) -> str:
        """Human-readable representation."""
        return f"{self.__class__.__name__}(name={self.name!r})"
