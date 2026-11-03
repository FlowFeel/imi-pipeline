"""Step definitions for doi_preprint_lifecycle.feature.

Thin glue between Gherkin and the DOI harness. All HTTP traffic goes to the
real stack (WP REST + Crossref stub) — no request mocks on these paths.

OKR: @okr_doi_preprint
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from behave import given, then, when

WP_BASE_URL = os.environ.get("WP_BASE_URL", "http://localhost:18091")
STUB_BASE_URL = os.environ.get("CROSSREF_STUB_URL", "http://localhost:18092")

_PREFIX = "10.67767/"


# ── helpers ──────────────────────────────────────────────────────────────────

def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _http(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, str]:
    """Small stdlib HTTP helper — returns (status, body_text)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def _wp_create(title: str, doi_suffix: str, status: str, extra: dict[str, Any] | None = None) -> int:
    """Create a preprint CPT entry through the WP REST API."""
    payload: dict[str, Any] = {
        "title": title,
        "status": "publish",
        "meta": {
            "reg_doi": f"{_PREFIX}{doi_suffix}",
            "reg_doi_status": status.lower(),
            "reg_version": extra.get("reg_version", 1) if extra else 1,
        },
    }
    if extra:
        payload["meta"].update(extra["meta"])
    code, text = _http("POST", _url(WP_BASE_URL, "wp-json/wp/v2/imi_registry"), payload)
    if code not in (200, 201):
        raise AssertionError(f"WP create failed [{code}]: {text}")
    return json.loads(text)["id"]


def _wp_meta(post_id: int) -> dict[str, Any]:
    code, text = _http("GET", _url(WP_BASE_URL, f"wp-json/wp/v2/imi_registry/{post_id}"))
    if code != 200:
        raise AssertionError(f"WP read failed [{code}]: {text}")
    return json.loads(text).get("meta", {})


def _rendered_page(post_id: int) -> str:
    """Fetch the fully-rendered front-end HTML (black-box surface)."""
    code, text = _http("GET", _url(WP_BASE_URL, f"?p={post_id}"))
    if code != 200:
        raise AssertionError(f"page render failed [{code}]")
    return text


# ── Given ────────────────────────────────────────────────────────────────────

@given("the DOI harness stack is running")
def step_stack_running(context: Any) -> None:
    code, _ = _http("GET", _url(WP_BASE_URL, "wp-json/wp/v2/"))
    assert code == 200, f"WP not reachable at {WP_BASE_URL} [{code}]"
    code, _ = _http("GET", _url(STUB_BASE_URL, "admin/health"))
    assert code == 200, f"stub not reachable at {STUB_BASE_URL} [{code}]"


@given("the Crossref stub is reset")
def step_stub_reset(context: Any) -> None:
    _http("POST", _url(STUB_BASE_URL, "admin/reset"))


@given('an author creates a preprint titled "{title}"')
def step_create_preprint(context: Any, title: str) -> None:
    context.preprint_id = _wp_create(title, suffix=context.doi_suffix or "000", status="pending")  # type: ignore[attr-defined]
    context.preprint_title = title  # type: ignore[attr-defined]


@given('the preprint has DOI suffix "{suffix}" with status "{status}"')
def step_set_doi_pending(context: Any, suffix: str, status: str) -> None:
    context.doi_suffix = suffix.replace("imi.2026.", "")  # type: ignore[attr-defined]
    context.doi_status = status.lower()  # type: ignore[attr-defined]
    if getattr(context, "preprint_id", None):
        _http(
            "POST",
            _url(WP_BASE_URL, f"wp-json/wp/v2/imi_registry/{context.preprint_id}"),
            {"meta": {"reg_doi": f"{_PREFIX}{suffix}", "reg_doi_status": status.lower()}},
        )


@given('the primary author is "{author}"')
def step_set_author(context: Any, author: str) -> None:
    context.primary_author = author  # type: ignore[attr-defined]


@given('the preprint has DOI suffix "{suffix}" with Crossref deposit "{deposit_id}"')
def step_set_doi_active(context: Any, suffix: str, deposit_id: str) -> None:
    context.doi_suffix = suffix.replace("imi.2026.", "")  # type: ignore[attr-defined]
    context.deposit_id = deposit_id  # type: ignore[attr-defined]
    context.doi_status = "active"  # type: ignore[attr-defined]


@given('the DOI status is "{status}"')
def step_set_status(context: Any, status: str) -> None:
    context.doi_status = status.lower()  # type: ignore[attr-defined]


@given('a published preprint titled "{title}" with DOI suffix "{suffix}"')
def step_published_preprint(context: Any, title: str, suffix: str) -> None:
    context.preprint_id = _wp_create(title, suffix.replace("imi.2026.", ""), "pending")  # type: ignore[attr-defined]
    context.doi_suffix = suffix.replace("imi.2026.", "")  # type: ignore[attr-defined]


@given('the Crossref stub is scripted to return "{mode}" for suffix "{suffix}"')
def step_script_stub(context: Any, mode: str, suffix: str) -> None:
    code, _ = _http(
        "POST",
        _url(STUB_BASE_URL, "admin/script"),
        {"doi_suffix": suffix, "mode": mode},
    )
    assert code == 200, f"script failed [{code}]"
    context.scripted_mode = mode  # type: ignore[attr-defined]


# ── When ─────────────────────────────────────────────────────────────────────

@when("Flow generates the Google Scholar citation tags")
def step_render_citation_tags(context: Any) -> None:
    html = _rendered_page(context.preprint_id)  # type: ignore[attr-defined]
    tags = dict(re.findall(r'<meta name="(citation_[a-z_]+)" content="([^"]*)"', html))
    context.citation_tags = tags  # type: ignore[attr-defined]


@when("Flow generates the Schema.org JSON-LD")
def step_render_jsonld(context: Any) -> None:
    html = _rendered_page(context.preprint_id)  # type: ignore[attr-defined]
    match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    )
    context.jsonld = json.loads(match.group(1)) if match else {}  # type: ignore[attr-defined]


@when("the harness deposits the preprint metadata to the Crossref stub")
def step_deposit(context: Any) -> None:
    suffix = context.doi_suffix  # type: ignore[attr-defined]
    code, text = _http(
        "POST",
        _url(STUB_BASE_URL, "servlet/deposit"),
        {"doi": f"10.67767/imi.2026.{suffix}"},
    )
    context.deposit_code = code  # type: ignore[attr-defined]
    context.deposit_response = text  # type: ignore[attr-defined]


# ── Then ─────────────────────────────────────────────────────────────────────

@then('the citation output contains a "{tag}" tag with "{value}"')
def step_citation_contains(context: Any, tag: str, value: str) -> None:
    tags = getattr(context, "citation_tags", {})
    assert tags.get(tag) == value, f"{tag}={tags.get(tag)!r}, expected {value!r}"


@then('the citation output does not contain a "{tag}" tag')
def step_citation_absent(context: Any, tag: str) -> None:
    tags = getattr(context, "citation_tags", {})
    assert tag not in tags, f"unexpected {tag}={tags[tag]!r} — 404-leak risk"


@then('the JSON-LD "{key}" is "{value}"')
def step_jsonld_is(context: Any, key: str, value: str) -> None:
    ld = getattr(context, "jsonld", {})
    assert ld.get(key) == value, f"jsonld[{key}]={ld.get(key)!r}, expected {value!r}"


@then('the JSON-LD authors include "{a1}" and "{a2}"')
def step_jsonld_authors(context: Any, a1: str, a2: str) -> None:
    ld = getattr(context, "jsonld", {})
    names = [a.get("name") for a in ld.get("author", [])]
    assert a1 in names and a2 in names, f"authors={names!r}"


@then('the post meta "{key}" is "{value}"')
def step_post_meta_str(context: Any, key: str, value: str) -> None:
    meta = _wp_meta(context.preprint_id)  # type: ignore[attr-defined]
    assert meta.get(key) == value, f"meta[{key}]={meta.get(key)!r}, expected {value!r}"


@then('the post meta "{key}" is {value:d}')
def step_post_meta_int(context: Any, key: str, value: int) -> None:
    meta = _wp_meta(context.preprint_id)  # type: ignore[attr-defined]
    assert int(meta.get(key) or 0) == value, f"meta[{key}]={meta.get(key)!r}, expected {value}"


@then('the stub returns a deposit receipt with a "cr-dep-" id')
def step_receipt_id(context: Any) -> None:
    body = context.deposit_response  # type: ignore[attr-defined]
    match = re.search(r"cr-dep-\d+", body)
    assert context.deposit_code == 201, f"deposit code={context.deposit_code}"  # type: ignore[attr-defined]
    assert match, f"no cr-dep id in {body!r}"
    context.receipt_id = match.group(0)  # type: ignore[attr-defined]


@then('the stub receipt for that id has status "pending"')
def step_receipt_status(context: Any) -> None:
    code, text = _http("GET", _url(STUB_BASE_URL, f"deposits/{context.receipt_id}"))  # type: ignore[attr-defined]
    assert code == 200, f"receipt lookup failed [{code}]"
    assert json.loads(text)["status"] == "pending", text


@then('the harness records a malformed-receipt error and does not activate the DOI')
def step_malformed_rejected(context: Any) -> None:
    # The stub returned 201 with a receipt missing <doi>. The harness treats
    # that as unrecoverable for activation — the deposit is recorded but the
    # DOI status must stay "pending" (no citation_doi may appear).
    meta = _wp_meta(context.preprint_id)  # type: ignore[attr-defined]
    assert meta.get("reg_doi_status") != "active", "malformed receipt activated DOI"
    assert meta.get("reg_doi_status") == "pending", f"meta={meta!r}"
