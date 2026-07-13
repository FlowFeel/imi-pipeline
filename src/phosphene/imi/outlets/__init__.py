"""Publication outlets — one per distribution target.

Each outlet implements PublicationOutlet and handles one destination.
Outlets are independent: they do not know about each other.
The pipeline DAG defines ordering and dependencies.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations
