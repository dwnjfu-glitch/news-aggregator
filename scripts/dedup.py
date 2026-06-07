from difflib import SequenceMatcher
from datetime import datetime, timezone
import hashlib
import re


def _normalize(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    title = title.lower().strip()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def _title_similarity(a: str, b: str) -> float:
    """Return 0..1 similarity between two titles."""
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _url_key(url: str) -> str:
    """Normalize URL for comparison: strip protocol, www, trailing slash, query."""
    url = re.sub(r"^https?://(www\.)?", "", url.lower().strip())
    url = re.sub(r"\?.*$", "", url)
    url = url.rstrip("/")
    return hashlib.md5(url.encode()).hexdigest()


def deduplicate(articles: list[dict], title_threshold: float = 0.85) -> list[dict]:
    """
    Remove duplicate articles from a flat list.

    Strategy:
    1. Exact URL dedup (strongest signal).
    2. Title-similarity dedup (catches cross-posting).
    When two are duplicates, keep the one with the earlier pubDate.
    Sorts result by pubDate descending (newest first).
    """
    if not articles:
        return []

    # --- Pass 1: exact URL match ---
    seen_url_keys: dict[str, dict] = {}
    for a in articles:
        key = _url_key(a.get("link", ""))
        if not key:
            continue
        existing = seen_url_keys.get(key)
        if existing is None:
            seen_url_keys[key] = a
        else:
            # Keep the one with earlier pubDate
            if _earlier(a, existing):
                seen_url_keys[key] = a

    # --- Pass 2: title similarity (within same date window) ---
    unique_by_url = list(seen_url_keys.values())
    result: list[dict] = []
    used = [False] * len(unique_by_url)

    for i, a in enumerate(unique_by_url):
        if used[i]:
            continue
        best = a
        for j, b in enumerate(unique_by_url):
            if i == j or used[j]:
                continue
            if _title_similarity(a["title"], b["title"]) >= title_threshold:
                used[j] = True
                if _earlier(b, best):
                    best = b
        result.append(best)

    result.sort(key=lambda a: a.get("pubDate", ""), reverse=True)
    return result


def _earlier(a: dict, b: dict) -> bool:
    """Return True if a's pubDate is earlier (older) than b's."""
    da = _parse_date(a.get("pubDate", ""))
    db = _parse_date(b.get("pubDate", ""))
    if da is None:
        return False
    if db is None:
        return True
    return da < db


def _parse_date(s: str) -> datetime | None:
    """Try common RSS date formats."""
    if not s:
        return None
    # RFC 2822 (most common in RSS)
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(s)
    except (ValueError, TypeError):
        pass
    # ISO 8601
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S%z"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    # ISO with trailing Z
    try:
        return datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass
    return None
