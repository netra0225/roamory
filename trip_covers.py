from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "Roamory/1.0 (student travel planner; https://roamory-1.onrender.com)"

_BLOCKED_IMAGE_WORDS = {
    "map",
    "locator",
    "location",
    "flag",
    "coat of arms",
    "coat_of_arms",
    "logo",
    "emblem",
    "seal",
    "icon",
    "symbol",
}


def destination_cover_url(destination: str) -> str | None:
    """Return a representative landscape-sized image for a destination.

    The lookup is keyless and uses Wikipedia's public MediaWiki API. Exact page
    titles are tried first; a normal Wikipedia search is used as a fallback.
    """
    query = (destination or "").strip()
    if not query:
        return None

    candidates = []
    for value in (query, query.split(",")[0].strip()):
        if value and value.lower() not in {item.lower() for item in candidates}:
            candidates.append(value)

    for title in candidates:
        image = _page_image_for_title(title)
        if image:
            return image

    for search_query in candidates:
        image = _search_page_image(search_query)
        if image:
            return image

    for search_query in candidates:
        for commons_query in (
            f"{search_query} panorama",
            f"{search_query} city",
            search_query,
        ):
            image = _commons_search_image(commons_query)
            if image:
                return image

    return None


def _page_image_for_title(title: str) -> str | None:
    payload = _request(
        {
            "action": "query",
            "format": "json",
            "redirects": 1,
            "prop": "pageimages",
            "titles": title,
            "piprop": "thumbnail|original|name",
            "pithumbsize": 1600,
        }
    )
    pages = ((payload or {}).get("query") or {}).get("pages") or {}
    for page in pages.values():
        image = _image_from_page(page)
        if image:
            return image
    return None


def _search_page_image(query: str) -> str | None:
    payload = _request(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 0,
            "gsrlimit": 8,
            "prop": "pageimages",
            "piprop": "thumbnail|original|name",
            "pithumbsize": 1600,
        }
    )
    pages = ((payload or {}).get("query") or {}).get("pages") or {}
    ordered = sorted(
        pages.values(),
        key=lambda page: int(page.get("index", 9999)),
    )
    for page in ordered:
        image = _image_from_page(page)
        if image:
            return image
    return None


def _image_from_page(page: dict[str, Any]) -> str | None:
    image_name = str(page.get("pageimage") or "").lower()
    if image_name:
        normalised = image_name.replace("-", " ").replace("_", " ")
        if any(word in normalised for word in _BLOCKED_IMAGE_WORDS):
            return None

    thumbnail = page.get("thumbnail") or {}
    source = thumbnail.get("source")
    if source and "/wikipedia/commons/" in str(source):
        return str(source)

    original = page.get("original") or {}
    source = original.get("source")
    if source and "/wikipedia/commons/" in str(source):
        return str(source)

    return None


def _commons_search_image(query: str) -> str | None:
    payload = _request(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": 12,
            "prop": "imageinfo",
            "iiprop": "url|mime",
            "iiurlwidth": 1600,
        },
        base_url=COMMONS_API_URL,
    )
    pages = ((payload or {}).get("query") or {}).get("pages") or {}
    ordered = sorted(
        pages.values(),
        key=lambda page: int(page.get("index", 9999)),
    )

    for page in ordered:
        title = str(page.get("title") or "").lower()
        normalised = title.replace("-", " ").replace("_", " ")
        if any(word in normalised for word in _BLOCKED_IMAGE_WORDS):
            continue

        info_rows = page.get("imageinfo") or []
        if not info_rows:
            continue
        info = info_rows[0]
        mime = str(info.get("mime") or "")
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue

        source = info.get("thumburl") or info.get("url")
        if source:
            return str(source)

    return None


def _request(
    params: dict[str, Any],
    *,
    base_url: str = WIKIPEDIA_API_URL,
) -> dict[str, Any] | None:
    url = f"{base_url}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
