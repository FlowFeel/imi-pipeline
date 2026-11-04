"""HTTPS client and protocol for Crossref deposits and receipt checks.

@dft
- A1 (pure-io-separation): Transport adapter decoupled via CrossrefClientProtocol.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from phosphene.imi.crossref.generator import render_crossref_xml
from phosphene.imi.crossref.models import (
    CrossrefDepositBatch,
    DepositReceipt,
    DepositStatus,
)

DEFAULT_CROSSREF_ENDPOINT = "https://doi.crossref.org/servlet/deposit"


class CrossrefClientProtocol(Protocol):
    """Protocol for deposit operations with Crossref."""

    def deposit(
        self,
        batch: CrossrefDepositBatch,
        *,
        username: str = "",
        password: str = "",
    ) -> DepositReceipt:
        """Submit a deposit batch and return submission receipt."""
        ...

    def get_deposit_status(
        self,
        deposit_id: str,
        *,
        username: str = "",
        password: str = "",
    ) -> DepositReceipt:
        """Query status of a previously submitted deposit."""
        ...


def parse_deposit_receipt(raw_xml: str) -> DepositReceipt:
    """Parse Crossref XML response or receipt into a structured DepositReceipt."""
    # Find deposit id
    dep_match = re.search(r"<cr-dep-id>(.*?)</cr-dep-id>", raw_xml, re.IGNORECASE)
    if not dep_match:
        dep_match = re.search(r"<batch_id>(.*?)</batch_id>", raw_xml, re.IGNORECASE)
    deposit_id = dep_match.group(1).strip() if dep_match else ""

    # Find DOI
    doi_match = re.search(r"<doi>(.*?)</doi>", raw_xml, re.IGNORECASE)
    doi = doi_match.group(1).strip() if doi_match else ""

    # Find status
    status_match = re.search(r"<status>(.*?)</status>", raw_xml, re.IGNORECASE)
    status_str = status_match.group(1).strip().lower() if status_match else ""

    # Status classification
    if status_str in ("completed", "registered", "success"):
        status = DepositStatus.COMPLETED
    elif status_str in ("pending", "submitted"):
        status = DepositStatus.PENDING
    elif status_str in ("failed", "rejected", "error"):
        status = DepositStatus.FAILED
    else:
        # Default based on presence of deposit_id and doi
        status = DepositStatus.PENDING if deposit_id and doi else DepositStatus.FAILED

    return DepositReceipt(
        deposit_id=deposit_id,
        doi=doi,
        status=status,
        raw_response=raw_xml,
    )


class CrossrefHttpClient:
    """I/O Adapter implementing HTTP transport to Crossref or Crossref stub."""

    def __init__(self, endpoint_url: str = DEFAULT_CROSSREF_ENDPOINT) -> None:
        self._endpoint_url = endpoint_url

    def deposit(
        self,
        batch: CrossrefDepositBatch,
        *,
        username: str = "",
        password: str = "",
    ) -> DepositReceipt:
        """Post Crossref XML payload to deposit endpoint."""
        xml_data = render_crossref_xml(batch)

        # Crossref multipart or raw XML form submission
        # If posting to test stub or servlet
        data = urllib.parse.urlencode(
            {
                "operation": "doMDUpload",
                "login_id": username,
                "login_passwd": password,
                "fname": f"{batch.batch_id}.xml",
                "doi": batch.records[0].doi if batch.records else "",
                "data": xml_data,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            self._endpoint_url,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "IMI-Preprint-Pipeline/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")
                return parse_deposit_receipt(resp_body)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            return DepositReceipt(
                deposit_id="",
                doi="",
                status=DepositStatus.FAILED,
                raw_response=err_body,
                message=f"HTTP {e.code}: {e.reason}",
            )
        except Exception as e:
            return DepositReceipt(
                deposit_id="",
                doi="",
                status=DepositStatus.FAILED,
                raw_response=str(e),
                message=f"Network error: {e}",
            )

    def get_deposit_status(
        self,
        deposit_id: str,
        *,
        username: str = "",
        password: str = "",
    ) -> DepositReceipt:
        """Query deposit status."""
        base = self._endpoint_url.rsplit("/servlet", 1)[0]
        url = f"{base}/deposits/{urllib.parse.quote(deposit_id)}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                import json

                data = json.loads(body)
                status_raw = data.get("status", "pending")
                status = (
                    DepositStatus.COMPLETED
                    if status_raw in ("registered", "completed")
                    else DepositStatus.PENDING
                )
                return DepositReceipt(
                    deposit_id=deposit_id,
                    doi=data.get("doi", ""),
                    status=status,
                    raw_response=body,
                )
        except Exception as e:
            return DepositReceipt(
                deposit_id=deposit_id,
                doi="",
                status=DepositStatus.FAILED,
                raw_response=str(e),
                message=str(e),
            )
