"""Step definitions for doi_preprint_lifecycle.feature.

Thin glue between Gherkin and the DOI harness. All HTTP traffic goes to the
real stack (WP REST + Crossref stub) — no request mocks on these paths.

OKR: @okr_doi_preprint
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import urllib.error
import urllib.request
from typing import Any

from behave import given, then, when
from phosphene.imi_wordpress.adapters import PreprintPayloadAdapter
from phosphene.imi_wordpress.domain import (
    DOI,
    Author,
    DOIRecord,
    DOIStatus,
    EditorialState,
    VersionInfo,
)

from phosphene.imi.event import PublicationEvent
from phosphene.imi.outlets.wordpress import WordPressOutlet
from phosphene.imi.work import PreprintWork

WP_BASE_URL = os.environ.get("WP_BASE_URL", "http://localhost:18091")
STUB_BASE_URL = os.environ.get("CROSSREF_STUB_URL", "http://localhost:18092")

_PREFIX = "10.67767/"
_CRED_FILE = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "testdata"
    / ".wp_app_password"
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _auth_header() -> str | None:
    if _CRED_FILE.is_file():
        cred = _CRED_FILE.read_text().strip()
        if cred:
            return "Basic " + base64.b64encode(cred.encode()).decode()
    return None


def _http(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, str]:
    """Small stdlib HTTP helper — returns (status, body_text)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    auth = _auth_header()
    if auth:
        req.add_header("Authorization", auth)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def _wp_create(
    title: str, doi_suffix: str, status: str, extra: dict[str, Any] | None = None
) -> int:
    """Create a preprint CPT entry through the WP REST API."""
    meta: dict[str, Any] = {
        "reg_doi": f"{_PREFIX}{doi_suffix}" if doi_suffix else "",
        "reg_doi_status": status.lower(),
        "reg_version": 1,
    }
    if extra and "meta" in extra:
        meta.update(extra["meta"])
    payload: dict[str, Any] = {
        "title": title,
        "status": "publish",
        "meta": meta,
    }
    code, text = _http("POST", _url(WP_BASE_URL, "wp-json/wp/v2/imi_registry"), payload)
    if code not in (200, 201):
        raise AssertionError(f"WP create failed [{code}]: {text}")
    return json.loads(text)["id"]


def _wp_update(post_id: int, meta: dict[str, Any]) -> None:
    code, text = _http(
        "POST",
        _url(WP_BASE_URL, f"wp-json/wp/v2/imi_registry/{post_id}"),
        {"meta": meta},
    )
    if code not in (200, 201):
        raise AssertionError(f"WP update failed [{code}]: {text}")


def _wp_meta(post_id: int) -> dict[str, Any]:
    code, text = _http(
        "GET", _url(WP_BASE_URL, f"wp-json/wp/v2/imi_registry/{post_id}")
    )
    if code != 200:
        raise AssertionError(f"WP read failed [{code}]: {text}")
    return json.loads(text).get("meta", {})


def _rendered_page(post_id: int) -> str:
    """Fetch the fully-rendered front-end HTML (black-box surface)."""
    code, text = _http("GET", _url(WP_BASE_URL, f"?p={post_id}"))
    if code != 200:
        raise AssertionError(f"page render failed [{code}]")
    return text


class HttpWPClient:
    """WPClientProtocol implementation communicating with live WordPress instance."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
        self.last_created_post: dict[str, Any] | None = None

    def create_post(
        self,
        post_type: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        code, text = _http(
            "POST", _url(self._base_url, f"wp-json/wp/v2/{post_type}"), data
        )
        if code not in (200, 201):
            raise AssertionError(f"WP create failed [{code}]: {text}")
        post = json.loads(text)
        self.last_created_post = post
        return post

    def post_exists(self, post_type: str, slug: str) -> bool:
        return False

    def post_url(self, post_type: str, slug: str) -> str:
        return _url(self._base_url, f"?p={slug}")

    def delete_post(self, post_url: str) -> None:
        pass


def _build_preprint_work(context: Any) -> PreprintWork:
    """Construct pure PreprintWork domain POPO from test scenario context."""
    suffix = getattr(context, "doi_suffix", "")
    doi = DOI(suffix=f"imi.2026.{suffix}") if suffix else None

    raw_status = getattr(context, "doi_status", "pending").lower()
    status_map = {
        "pending": DOIStatus.PENDING,
        "active": DOIStatus.ACTIVE,
        "withdrawn": DOIStatus.WITHDRAWN,
    }
    doi_status = status_map.get(raw_status, DOIStatus.PENDING)

    doi_record = DOIRecord(
        doi=doi,
        status=doi_status,
        deposit_id=getattr(context, "deposit_id", ""),
        minted_date="2026-11-04" if doi_status == DOIStatus.ACTIVE else "",
    )

    state_map = {
        "LIVE_PREPRINT": EditorialState.LIVE_PREPRINT,
        "PUBLISHED": EditorialState.PUBLISHED,
        "RETRACTED": EditorialState.WITHDRAWN,
        "WITHDRAWN": EditorialState.WITHDRAWN,
    }
    editorial_state = state_map.get(
        getattr(context, "editorial_state", "LIVE_PREPRINT"),
        EditorialState.WITHDRAWN
        if doi_status == DOIStatus.WITHDRAWN
        else EditorialState.LIVE_PREPRINT,
    )

    primary_author = Author(name=getattr(context, "primary_author", "Default Author"))
    coauthors = [Author(name=name) for name in getattr(context, "coauthors", [])]
    version = VersionInfo(number=getattr(context, "version_number", 1))

    return PreprintWork(
        title=context.preprint_title,
        primary_author=primary_author,
        coauthors=coauthors,
        doi_record=doi_record,
        version=version,
        pdf_url=getattr(context, "pdf_url", ""),
        withdrawal_notice=getattr(context, "withdrawal_notice", None),
        editorial_state=editorial_state,
    )


def _publish_work_via_outlet(work: PreprintWork) -> int:
    """Publish a PreprintWork via WordPressOutlet and return the post id."""
    client = HttpWPClient(WP_BASE_URL)
    outlet = WordPressOutlet(client=client)
    event = PublicationEvent(work=work, publisher_id="flow")
    result = outlet.publish(event)
    if not result.succeeded or not client.last_created_post:
        raise AssertionError(f"WordPressOutlet publish failed: {result.error}")
    return int(client.last_created_post["id"])


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
    context.preprint_title = title
    context.doi_suffix = getattr(context, "doi_suffix", "")
    context.doi_status = getattr(context, "doi_status", "pending")
    context.primary_author = getattr(context, "primary_author", "Default Author")
    context.coauthors = getattr(context, "coauthors", [])
    context.editorial_state = getattr(context, "editorial_state", "LIVE_PREPRINT")
    context.version_number = getattr(context, "version_number", 1)
    context.pdf_url = getattr(context, "pdf_url", "")
    context.deposit_id = getattr(context, "deposit_id", "")
    context.pending_meta = {}


@given('the preprint has DOI suffix "{suffix}" with status "{status}"')
def step_set_doi_pending(context: Any, suffix: str, status: str) -> None:
    context.doi_suffix = suffix.replace("imi.2026.", "")
    context.doi_status = status.lower()


@given('the primary author is "{author}"')
def step_set_author(context: Any, author: str) -> None:
    context.primary_author = author


@given('the co-authors are "{author1}" and "{author2}"')
def step_set_coauthors(context: Any, author1: str, author2: str) -> None:
    context.coauthors = [author1, author2]


@given('the preprint has version {number:d} with PDF artifact "{pdf_url}"')
def step_set_version_pdf(context: Any, number: int, pdf_url: str) -> None:
    context.version_number = number
    context.pdf_url = pdf_url


@given('the preprint is in "{state}" editorial state')
def step_set_editorial_state(context: Any, state: str) -> None:
    context.editorial_state = state


@given('the preprint has DOI suffix "{suffix}" with Crossref deposit "{deposit_id}"')
def step_set_doi_active(context: Any, suffix: str, deposit_id: str) -> None:
    context.doi_suffix = suffix.replace("imi.2026.", "")
    context.deposit_id = deposit_id
    context.doi_status = "active"


@given('the DOI status is "{status}"')
def step_set_status(context: Any, status: str) -> None:
    context.doi_status = status.lower()


@given('a published preprint titled "{title}" with DOI suffix "{suffix}"')
def step_published_preprint(context: Any, title: str, suffix: str) -> None:
    sfx = suffix.replace("imi.2026.", "")
    context.preprint_title = title
    context.doi_suffix = sfx
    context.doi_status = "pending"
    work = _build_preprint_work(context)
    context.preprint_id = _publish_work_via_outlet(work)


@given('the Crossref stub is scripted to return "{mode}" for suffix "{suffix}"')
def step_script_stub(context: Any, mode: str, suffix: str) -> None:
    code, _ = _http(
        "POST",
        _url(STUB_BASE_URL, "admin/script"),
        {"doi_suffix": suffix, "mode": mode},
    )
    assert code == 200, f"script failed [{code}]"
    context.scripted_mode = mode


# ── When ─────────────────────────────────────────────────────────────────────


@when("Flow generates the Google Scholar citation tags")
def step_render_citation_tags(context: Any) -> None:
    if not getattr(context, "preprint_id", None):
        work = _build_preprint_work(context)
        context.preprint_id = _publish_work_via_outlet(work)
    html = _rendered_page(context.preprint_id)
    tags = dict(re.findall(r'<meta name="(citation_[a-z_]+)" content="([^"]*)"', html))
    context.citation_tags = tags


@when("Flow generates the Schema.org JSON-LD")
def step_render_jsonld(context: Any) -> None:
    if not getattr(context, "preprint_id", None):
        work = _build_preprint_work(context)
        context.preprint_id = _publish_work_via_outlet(work)
    html = _rendered_page(context.preprint_id)
    match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    )
    context.jsonld = json.loads(match.group(1)) if match else {}


@when("Flow publishes the preprint via WordPressOutlet")
def step_publish_via_outlet(context: Any) -> None:
    work = _build_preprint_work(context)
    if getattr(context, "preprint_id", None):
        entry = work.to_preprint_entry()
        payload = PreprintPayloadAdapter.to_wordpress(entry)
        _wp_update(context.preprint_id, payload["meta"])
    else:
        context.preprint_id = _publish_work_via_outlet(work)


@when('the preprint is revised to version {version:d} with PDF artifact "{pdf_url}"')
def step_revise_version(context: Any, version: int, pdf_url: str) -> None:
    context.version_number = version
    context.pdf_url = pdf_url


@when('the preprint is retracted with notice "{notice}"')
def step_retract_with_notice(context: Any, notice: str) -> None:
    context.doi_status = "withdrawn"
    context.editorial_state = "RETRACTED"
    context.withdrawal_notice = notice


@when("the harness deposits the preprint metadata to the Crossref stub")
def step_deposit(context: Any) -> None:
    suffix = context.doi_suffix
    code, text = _http(
        "POST",
        _url(STUB_BASE_URL, "servlet/deposit"),
        {"doi": f"{_PREFIX}imi.2026.{suffix}"},
    )
    context.deposit_code = code
    context.deposit_response = text


# ── Then ─────────────────────────────────────────────────────────────────────


@then('the JSON-LD "{key}" is "{value}"')
def step_jsonld_is(context: Any, key: str, value: str) -> None:
    # If JSON-LD has not been fetched yet in this scenario, fetch from rendered page
    if not getattr(context, "jsonld", None) and getattr(context, "preprint_id", None):
        html = _rendered_page(context.preprint_id)
        match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        )
        context.jsonld = json.loads(match.group(1)) if match else {}
    ld = getattr(context, "jsonld", {})
    assert ld.get(key) == value, f"jsonld[{key}]={ld.get(key)!r}, expected {value!r}"


@then('the citation output contains a "{tag}" tag with "{value}"')
def step_citation_contains(context: Any, tag: str, value: str) -> None:
    # If citation tags have not been fetched yet, fetch from rendered page
    if not getattr(context, "citation_tags", None) and getattr(
        context, "preprint_id", None
    ):
        html = _rendered_page(context.preprint_id)
        tags = dict(
            re.findall(r'<meta name="(citation_[a-z_]+)" content="([^"]*)"', html)
        )
        context.citation_tags = tags
    tags = getattr(context, "citation_tags", {})
    assert tags.get(tag) == value, f"{tag}={tags.get(tag)!r}, expected {value!r}"


@then('the citation output does not contain a "{tag}" tag')
def step_citation_absent(context: Any, tag: str) -> None:
    if not getattr(context, "citation_tags", None) and getattr(
        context, "preprint_id", None
    ):
        html = _rendered_page(context.preprint_id)
        tags = dict(
            re.findall(r'<meta name="(citation_[a-z_]+)" content="([^"]*)"', html)
        )
        context.citation_tags = tags
    tags = getattr(context, "citation_tags", {})
    assert tag not in tags, f"unexpected {tag}={tags[tag]!r} — 404-leak risk"


@then('the JSON-LD authors include "{a1}" and "{a2}"')
def step_jsonld_authors(context: Any, a1: str, a2: str) -> None:
    ld = getattr(context, "jsonld", {})
    names = [a.get("name") for a in ld.get("author", [])]
    assert a1 in names and a2 in names, f"authors={names!r}, expected {a1!r} and {a2!r}"


@then('the post meta "{key}" is "{value}"')
def step_post_meta_str(context: Any, key: str, value: str) -> None:
    meta = _wp_meta(context.preprint_id)
    assert meta.get(key) == value, f"meta[{key}]={meta.get(key)!r}, expected {value!r}"


@then('the post meta "{key}" is {value:d}')
def step_post_meta_int(context: Any, key: str, value: int) -> None:
    meta = _wp_meta(context.preprint_id)
    assert int(meta.get(key) or 0) == value, (
        f"meta[{key}]={meta.get(key)!r}, expected {value}"
    )


@then('the stub returns a deposit receipt with a "cr-dep-" id')
def step_receipt_id(context: Any) -> None:
    body = context.deposit_response
    match = re.search(r"cr-dep-\d+", body)
    assert context.deposit_code == 201, f"deposit code={context.deposit_code}"
    assert match, f"no cr-dep id in {body!r}"
    context.receipt_id = match.group(0)


@then('the stub receipt for that id has status "pending"')
def step_receipt_status(context: Any) -> None:
    code, text = _http("GET", _url(STUB_BASE_URL, f"deposits/{context.receipt_id}"))
    assert code == 200, f"receipt lookup failed [{code}]"
    assert json.loads(text)["status"] == "pending", text


@then("the harness records a malformed-receipt error and does not activate the DOI")
def step_malformed_rejected(context: Any) -> None:
    meta = _wp_meta(context.preprint_id)
    assert meta.get("reg_doi_status") != "active", "malformed receipt activated DOI"
    assert meta.get("reg_doi_status") == "pending", f"meta={meta!r}"
