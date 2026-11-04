"""Domain-agnostic text manipulation and parsing utilities.

Pure functions with zero domain dependencies.
All regular expressions are precompiled at module load time.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import urlsplit

# Precompiled regex patterns
_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")
_FLAG_PATTERN = re.compile(r"--([\w-]+)(?:=([^\s]+))?")
_URL_PATTERN = re.compile(r"https?://\S+")
_URL_PATH_TOKEN = re.compile(r"/([^/?#]+)(?:[?#].*)?$")


def slugify(text: str, max_length: int | None = None) -> str:
    """Convert an arbitrary string into a deterministic, URL-safe ASCII slug.

    Normalizes Unicode via NFKD, replaces non-alphanumeric characters with hyphens,
    collapses consecutive hyphens, and strips leading/trailing hyphens.

    Args:
        text: Input string (e.g. article title).
        max_length: Optional length cap on the generated slug.

    Returns:
        Lowercase ASCII slug string.
    """
    if not text:
        return ""
    # Normalize unicode to decompose accents (e.g., 'é' -> 'e' + combining accent)
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_INVALID_CHARS.sub("-", ascii_text).strip("-")
    if max_length is not None and max_length > 0:
        slug = slug[:max_length].rstrip("-")
    return slug


def join_delimited(items: Iterable[str], delimiter: str = ", ") -> str:
    """Join a collection of strings with strict null-omission.

    Strips whitespace from each element, filters out empty strings, and
    joins the remaining non-empty elements.

    Args:
        items: Iterable of strings.
        delimiter: Separator string. Defaults to ', '.

    Returns:
        Joined string, or empty string if no valid items.
    """
    cleaned = [s.strip() for s in items if s and s.strip()]
    return delimiter.join(cleaned)


def parse_command_line(text: str) -> tuple[str, dict[str, str]]:
    """Parse a CLI or chat command into a primary URL and key-value flags.

    Extracts flags formatted as '--key=value' or '--key' (boolean true).
    Extracts the last HTTP(S) URL as the primary target.

    Args:
        text: Raw command string (e.g. '/syndicate --outlets=wp,sf https://observatory.wiki/Foo').

    Returns:
        Tuple of (url, flags_dict).
    """
    flags: dict[str, str] = {}
    for match in _FLAG_PATTERN.finditer(text):
        key = match.group(1).lower()
        val = match.group(2) if match.group(2) is not None else "true"
        flags[key] = val

    # Find last URL in text
    urls = _URL_PATTERN.findall(text)
    url = urls[-1] if urls else ""

    return url, flags


def extract_url_slug(url: str) -> str:
    """Extract the last path slug from an HTTP(S) URL, stripping query and hash.

    Args:
        url: Full URL string.

    Returns:
        The extracted path segment (e.g. 'Cave_Art_in_France'), or the url itself if no path.
    """
    parsed = urlsplit(url)
    path = parsed.path.strip("/")
    if not path:
        return url
    return path.split("/")[-1]


_SLUG_SEPARATOR = re.compile(r"[_-]+")


def humanize_slug(slug: str) -> str:
    """Convert a slug with hyphens or underscores into a space-separated string.

    Args:
        slug: Slug or identifier (e.g. 'Cave_Art_in_France' or 'climate-crisis-2026').

    Returns:
        Human-readable space-separated string.
    """
    if not slug:
        return ""
    return _SLUG_SEPARATOR.sub(" ", slug).strip()


def extract_url_title(url: str) -> str:
    """Extract and humanize the final path segment of a URL into a title.

    Args:
        url: Full URL string.

    Returns:
        Humanized title or the original URL if no path segment exists.
    """
    slug = extract_url_slug(url)
    if slug == url:
        return url
    return humanize_slug(slug)
