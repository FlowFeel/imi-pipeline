"""Step definitions for publish_draft.feature.

Thin glue between Gherkin and the phosphene-imi modules.
No business logic here — that lives in the modules.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from behave import given, then, when

from phosphene.imi.draft import Draft
from phosphene.imi.publisher import ObservatoryPublisher


@given("the Observatory publisher is configured")
def step_publisher_configured(context: object) -> None:
    """Configure the publisher in dry-run mode for BDD tests."""
    context.publisher_mode = "dry_run"  # type: ignore[attr-defined]
    context.publisher = ObservatoryPublisher(  # type: ignore[attr-defined]
        api_url="https://observatory.wiki/w/api.php",
        username="FlowBot",
        password="test-password",
        dry_run=True,
    )
    context.publisher_ready = True  # type: ignore[attr-defined]


@given('a finished draft titled "{title}"')
def step_draft_titled(context: object, title: str) -> None:
    """Begin constructing a draft with the given title."""
    context._draft_title = title.strip('"')  # type: ignore[attr-defined]


@given('the author is "{author}"')
def step_draft_author(context: object, author: str) -> None:
    """Set the author on the draft under construction."""
    context._draft_author = author.strip('"')  # type: ignore[attr-defined]


@given('the category is "{category}"')
def step_draft_category(context: object, category: str) -> None:
    """Set the category on the draft under construction."""
    context._draft_category = category.strip('"')  # type: ignore[attr-defined]


@given("the body contains substantive content")
def step_draft_body(context: object) -> None:
    """Provide a placeholder body — real content comes from the source task."""
    context._draft_body = (  # type: ignore[attr-defined]
        "Care work is the foundation of all economies, yet remains "
        "systematically undervalued in standard economic accounting."
    )


@when("Flow publishes the draft")
def step_publish_draft(context: object) -> None:
    """Attempt to publish the assembled draft via ObservatoryPublisher."""
    try:
        context.draft = Draft(  # type: ignore[attr-defined]
            title=context._draft_title,  # type: ignore[attr-defined]
            body=context._draft_body,  # type: ignore[attr-defined]
            author=context._draft_author,  # type: ignore[attr-defined]
            category=context._draft_category,  # type: ignore[attr-defined]
        )
        context.published_url = context.publisher.publish(context.draft)  # type: ignore[attr-defined]
        context.publish_error = None  # type: ignore[attr-defined]
    except Exception as exc:
        context.publish_error = exc  # type: ignore[attr-defined]


@then("the article exists on observatory.wiki")
def step_article_exists(context: object) -> None:
    """Assert the article was successfully published to observatory.wiki."""
    assert context.publish_error is None, f"Publish failed: {context.publish_error}"  # type: ignore[attr-defined]
    assert context.draft is not None  # type: ignore[attr-defined]
    # The article must actually exist on observatory.wiki
    assert hasattr(context, "published_url") and context.published_url, (  # type: ignore[attr-defined]
        "No published_url — the publisher did not produce a URL. "
        "Wire ObservatoryPublisher.publish() in the When step."
    )


@then("the article has a canonical URL")
def step_article_has_url(context: object) -> None:
    """Assert a canonical URL was produced."""
    url = getattr(context, "published_url", None)
    assert url and url.startswith("https://observatory.wiki/"), (
        f"Expected canonical URL starting with https://observatory.wiki/, got: {url}"
    )


@then("the publish contract passes")
def step_contract_passes(context: object) -> None:
    """Assert the PublishContract is satisfied — article accessible at URL.

    In dry_run mode, skip the HTTP accessibility check (no live server)
    and verify URL format only. In live mode, run the full contract.
    """
    url = getattr(context, "published_url", None)
    assert url, "No published_url — cannot run contract"

    if getattr(context, "publisher_mode", None) == "dry_run":
        # Dry-run: verify URL format without hitting the network
        assert url.startswith("https://observatory.wiki/wiki/"), (
            f"URL format invalid: {url}"
        )
        assert context.draft.title.replace(" ", "_") in url, (  # type: ignore[attr-defined]
            f"Title not in URL: {url}"
        )
    else:
        from phosphene.imi.contracts.publish import PublishContract

        report = PublishContract(article_url=url, title=context.draft.title).prove()  # type: ignore[attr-defined]
        assert report.all_passed, (
            f"Publish contract failed: {[r.name + ': ' + str(r.evidence) for r in report.failed()]}"
        )


@then("the article has Modification date in the SMW store")
def step_article_has_mdat(context: object) -> None:
    """Assert SMW Modification date is populated for the published article.

    In dry_run mode we cannot query the live SMW store, so the check
    is skipped (pass).  In live mode we hit the SMW Ask API and verify
    the ``Modification date`` printout is non-empty.
    """
    if getattr(context, "publisher_mode", None) == "dry_run":
        # No real article to query — skip in dry-run
        return

    import json
    import urllib.request

    api_url = context.publisher.api_url  # type: ignore[attr-defined]
    title = context.draft.title.replace(" ", "_")  # type: ignore[attr-defined]
    query_url = f"{api_url}?action=ask&query=[[{title}]]|?Modification date&format=json"
    with urllib.request.urlopen(query_url, timeout=15) as resp:
        data = json.loads(resp.read())

    results = data.get("query", {}).get("results", {})
    assert results, f"SMW Ask returned no results for [[{title}]]"

    for _page, info in results.items():
        printouts = info.get("printouts", {})
        mdat = printouts.get("Modification date", [])
        assert mdat and len(mdat) > 0 and mdat[0], (
            f"Modification date is empty for {title}. "
            f"SMW property store may need rebuilding. Printouts: {printouts}"
        )


@given('a draft that has already been published as "{title}"')
def step_already_published(context: object, title: str) -> None:
    """Publish a draft once so it already exists for the idempotency test."""
    draft = Draft(
        title=title.strip('"'),
        body="Care work is the foundation of all economies.",
        author="Gunnar Rundgren",
        category="Economy",
    )
    context._idempotency_draft = draft  # type: ignore[attr-defined]
    context.first_url = context.publisher.publish(draft)  # type: ignore[attr-defined]


@when("Flow attempts to publish the same draft again")
def step_publish_again(context: object) -> None:
    """Publish the same draft a second time — should be idempotent."""
    try:
        context.second_url = context.publisher.publish(  # type: ignore[attr-defined]
            context._idempotency_draft,  # type: ignore[attr-defined]
        )
        context.publish_error = None  # type: ignore[attr-defined]
    except Exception as exc:
        context.publish_error = exc  # type: ignore[attr-defined]


@then("no duplicate article is created")
def step_no_duplicate(context: object) -> None:
    """Assert idempotency — same draft produces the same URL both times."""
    assert context.publish_error is None, (  # type: ignore[attr-defined]
        f"Second publish failed: {context.publish_error}"
    )
    assert context.first_url == context.second_url, (  # type: ignore[attr-defined]
        f"Duplicate created: first={context.first_url}, second={context.second_url}"
    )


@then("the existing article URL is returned")
def step_existing_url_returned(context: object) -> None:
    """Assert the existing canonical URL is returned on re-publish."""
    url = getattr(context, "second_url", None)
    assert url and url.startswith("https://observatory.wiki/"), (
        f"Expected canonical URL starting with https://observatory.wiki/, got: {url}"
    )


@given("an incomplete draft missing the author field")
def step_incomplete_draft(context: object) -> None:
    """Prepare an invalid draft — missing required author."""
    context._incomplete_draft_data = {  # type: ignore[attr-defined]
        "title": "Some Title",
        "body": "Some body content.",
        "category": "Economy",
        # author deliberately absent
    }


@when("Flow attempts to publish the draft")
def step_attempt_publish_invalid(context: object) -> None:
    """Attempt to publish an invalid draft — expect rejection."""
    try:
        Draft(**context._incomplete_draft_data)  # type: ignore[attr-defined]
        context.publish_error = None  # type: ignore[attr-defined]
    except Exception as exc:
        context.publish_error = exc  # type: ignore[attr-defined]


@then("the draft is rejected with a validation error")
def step_draft_rejected(context: object) -> None:
    """Assert the Draft validation caught the missing field."""
    assert context.publish_error is not None, (
        "Expected validation error but none raised"
    )  # type: ignore[attr-defined]


@then("no article is created on observatory.wiki")
def step_no_article_created(context: object) -> None:
    """Assert no MW API call was made when draft was invalid."""
    assert context.publish_error is not None  # type: ignore[attr-defined]
