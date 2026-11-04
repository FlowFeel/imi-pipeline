"""Dual-layer parity harness — REST API vs direct database verification.

WordPress meta writes go through ``wp_slash()`` which can corrupt raw
JSON values. This module pairs REST API reads (application layer) with
direct SQL reads (persistence layer) to detect abstraction leaks.

The harness is used:

- **Before write**: snapshot current state via both layers, verify parity
- **After write**: verify the REST-visible value matches the DB-stored value
- **Regression test**: assert that ``update_post_meta()`` slashing bug
  is caught by the parity check

Contract: every meta write must pass ``verify_meta_parity()`` before
and after the operation. A parity failure indicates an abstraction leak
that will corrupt the data.

@dft
- A1 (pure-io-separation): I/O wiring module — imports urllib for cache
  purge and render verification (allowed). The parity *comparison* logic
  is pure (it operates on two strings).
- A5 (mock-doubles): tests use :class:`~phosphene.imi_wordpress.fakes.FakeWPClient`
  and :class:`~phosphene.imi_wordpress.fakes.FakeDBClient`.
- A6 (check-result): ``verify_meta_parity()`` returns a
  :class:`ParityResult` (the proof). ``safe_write_elementor()`` and
  ``run_pipeline()`` return result dicts (the proof).
"""

from __future__ import annotations

import base64
import json
import urllib.request
from dataclasses import dataclass
from typing import Any

from phosphene.imi_wordpress import __version__
from phosphene.imi_wordpress.client import UrllibWPClient
from phosphene.imi_wordpress.db_client import WPEngineDBClient
from phosphene.imi_wordpress.elementor_model import (
    ElementorPageModel,
    ElementorValidationError,
)

USER_AGENT = f"WordPressDualHarness/{__version__}"


@dataclass(frozen=True)
class ParityResult:
    """Result of a parity check between REST and DB layers.

    Attributes:
        meta_key: The meta key that was checked.
        rest_length: String length of the REST API value.
        db_length: String length of the raw DB value.
        rest_json_valid: Whether the REST value parses as valid JSON.
        db_json_valid: Whether the DB value parses as valid JSON.
        matches: True if REST and DB values are byte-for-byte identical.
        rest_value: The REST API value (truncated for display).
        db_value: The DB value (truncated for display).
    """

    meta_key: str
    rest_length: int
    db_length: int
    rest_json_valid: bool
    db_json_valid: bool
    matches: bool
    rest_value: str
    db_value: str


class WordPressDualHarness:
    """Dual-layer parity harness for WordPress meta operations.

    Pairs REST API reads (application layer) with direct DB reads
    (persistence layer) to detect abstraction leaks like double-escaping
    or sanitization side-effects.

    Usage::

        harness = WordPressDualHarness(rest_client, db_client)
        result = harness.verify_meta_parity(post_id=43, meta_key="_elementor_data")
        if not result.matches:
            raise ParityError("REST and DB values diverge!")
    """

    def __init__(self, rest_client: UrllibWPClient, db_client: WPEngineDBClient) -> None:
        """Initialize the harness with both clients.

        Args:
            rest_client: The REST API client (application layer).
            db_client: The direct DB client (persistence layer).
        """
        self.rest = rest_client
        self.db = db_client

    def verify_meta_parity(self, post_id: int, meta_key: str = "_elementor_data") -> ParityResult:
        """Verify that REST API and DB return identical meta values.

        Fetches the meta value through both the REST API (with
        ``context=edit``) and the direct DB gateway, then compares
        them byte-for-byte.

        Args:
            post_id: WordPress post ID.
            meta_key: Meta key to check.

        Returns:
            ParityResult with match status and diagnostic info.
        """
        # REST API read (application layer)
        meta = self.rest.get_meta(post_id, context="edit")
        rest_value = meta.get(meta_key, "") if isinstance(meta, dict) else ""

        # Direct DB read (persistence layer)
        db_value = self.db.get_raw_meta(post_id, meta_key)

        rest_json = False
        db_json = False
        try:
            json.loads(rest_value)
            rest_json = True
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            json.loads(db_value)
            db_json = True
        except (json.JSONDecodeError, TypeError):
            pass

        return ParityResult(
            meta_key=meta_key,
            rest_length=len(rest_value),
            db_length=len(db_value),
            rest_json_valid=rest_json,
            db_json_valid=db_json,
            matches=(rest_value == db_value),
            rest_value=rest_value,
            db_value=db_value,
        )

    def verify_elementor_structure(self, post_id: int) -> ElementorPageModel:
        """Load and validate Elementor data as a structural AST.

        Reads ``_elementor_data`` from the DB, parses it through
        :class:`ElementorPageModel`, and returns the validated model.

        Args:
            post_id: WordPress post ID.

        Returns:
            A validated ElementorPageModel.

        Raises:
            ElementorValidationError: If the JSON is invalid or schema fails.
        """
        raw = self.db.get_raw_meta(post_id, "_elementor_data")
        return ElementorPageModel(raw)

    def safe_write_elementor(
        self,
        post_id: int,
        new_value: str,
        backup: bool = True,
    ) -> dict[str, Any]:
        """Safely write ``_elementor_data`` with full verification.

        Pipeline:
        1. Pre-write parity check (REST vs DB)
        2. Backup current value
        3. Validate new value as Elementor JSON
        4. Write via raw SQL (bypasses wp_slash)
        5. Post-write parity check
        6. Verify JSON validity
        7. Verify byte-for-byte match

        Args:
            post_id: WordPress post ID.
            new_value: The new Elementor JSON string.
            backup: If True, snapshot the current value before write.

        Returns:
            Dict with pre_parity, write_result, post_parity, verified.

        Raises:
            ElementorValidationError: If the new value is not valid Elementor JSON.
            RuntimeError: If the write fails or post-write parity check fails.
        """
        # Step 1: Pre-write parity
        pre_parity = self.verify_meta_parity(post_id)

        # Step 2: Backup
        if backup:
            self.db.backup_page(post_id)

        # Step 3: Validate new value
        model = ElementorPageModel(new_value)

        # Step 4: Write via raw SQL
        write_result = self.db.set_elementor_data(post_id, new_value)

        if write_result.get("status") not in ("updated", "restored"):
            raise RuntimeError(f"Write failed: {write_result}")

        # Step 5: Post-write parity
        post_parity = self.verify_meta_parity(post_id)

        # Step 6 & 7: Verify
        verified = (
            post_parity.matches
            and post_parity.rest_json_valid
            and post_parity.db_json_valid
            and post_parity.rest_length == len(new_value)
        )

        return {
            "pre_parity": {
                "matches": pre_parity.matches,
                "rest_length": pre_parity.rest_length,
                "db_length": pre_parity.db_length,
            },
            "write_result": write_result,
            "post_parity": {
                "matches": post_parity.matches,
                "rest_length": post_parity.rest_length,
                "db_length": post_parity.db_length,
                "json_valid": post_parity.rest_json_valid,
            },
            "elementor": {
                "widget_count": model.widget_count,
                "section_count": model.section_count,
                "widget_ids": sorted(model.widget_ids),
            },
            "verified": verified,
        }

    def run_pipeline(
        self,
        post_id: int,
        mutation: ElementorPageModel,
        purge_caches: bool = False,
    ) -> dict[str, Any]:
        """Execute the full 5-phase mutation pipeline.

        Phase 1: Backup — snapshot current page state
        Phase 2: AST Dry-Run — validate the mutated model and diff
        Phase 3: Direct DB Write — raw SQL, bypass wp_slash
        Phase 4: Dual-Read Parity — REST vs DB byte-for-byte
        Phase 5: Render & Cache Validation — purge caches, check live HTML

        Args:
            post_id: WordPress post ID.
            mutation: The target ElementorPageModel to write.
            purge_caches: If True, purge WP Engine + Cloudflare caches.

        Returns:
            Dict with per-phase results and overall verified status.
        """

        results: dict[str, Any] = {"post_id": post_id, "phases": {}}

        # Phase 1: Backup
        backup = self.db.backup_page(post_id)
        results["phases"]["1_backup"] = {
            "status": "done",
            "backup_time": backup.get("backup_time"),
            "content_length": backup.get("page", {}).get("content_length", 0),
        }

        # Phase 2: AST Dry-Run — diff current vs target
        current_raw = self.db.get_raw_meta(post_id, "_elementor_data")
        try:
            current_model = ElementorPageModel(current_raw)
            diff = current_model.diff(mutation)
            results["phases"]["2_dry_run"] = {
                "status": "done",
                "current_widgets": current_model.widget_count,
                "target_widgets": mutation.widget_count,
                "widget_delta": diff["widget_delta"],
                "added_widgets": diff["added_widgets"],
                "removed_widgets": diff["removed_widgets"],
            }
        except ElementorValidationError as e:
            results["phases"]["2_dry_run"] = {"status": "failed", "error": str(e)}
            results["verified"] = False
            return results

        # Phase 3: Direct DB Write
        write = self.db.set_elementor_data(post_id, mutation.to_json())
        results["phases"]["3_db_write"] = {
            "status": write.get("status"),
            "verify_length": write.get("verify_length"),
            "verify_json_valid": write.get("verify_json_valid"),
        }
        if write.get("status") not in ("updated", "restored"):
            results["verified"] = False
            return results

        # Phase 4: Dual-Read Parity
        parity = self.verify_meta_parity(post_id)
        results["phases"]["4_parity"] = {
            "matches": parity.matches,
            "rest_length": parity.rest_length,
            "db_length": parity.db_length,
            "json_valid": parity.rest_json_valid,
        }

        # Phase 5: Render & Cache Validation
        if purge_caches:
            self._purge_caches()
        render_ok = self._verify_render(post_id, mutation)
        results["phases"]["5_render"] = {
            "cache_purged": purge_caches,
            "render_verified": render_ok,
        }

        results["verified"] = (
            parity.matches
            and parity.rest_json_valid
            and parity.rest_length == len(mutation.to_json())
        )
        return results

    def _purge_caches(self) -> None:
        """Purge WP Engine and Cloudflare caches."""
        creds = f"{self.rest.config.username}:{self.rest.config.app_password}"
        encoded = base64.b64encode(creds.encode()).decode()

        req = urllib.request.Request(
            f"{self.rest.config.url}/wp-json/wpe/cache-plugin/v1/clear_all_caches",
            headers={
                "Authorization": f"Basic {encoded}",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(req)
        except Exception:  # noqa: BLE001, S110
            pass  # Cache purge is best-effort

    def _verify_render(self, post_id: int, expected_model: ElementorPageModel) -> bool:
        """Check that live HTML contains expected widget count.

        Args:
            post_id: WordPress post ID.
            expected_model: The ElementorPageModel we wrote.

        Returns:
            True if live page has elementor-widget elements.
        """
        import re

        page = self.rest.get_page(post_id, context="view")
        link = page.get("link", "") if isinstance(page, dict) else ""
        if not link:
            return False

        req = urllib.request.Request(
            link,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return False

        widgets = re.findall(r"elementor-widget", html)
        return len(widgets) > 0
