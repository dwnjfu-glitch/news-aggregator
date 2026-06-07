import json
import os
import sys
import time
from datetime import datetime, timezone

import feedparser
import requests

from dedup import deduplicate

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")
SOURCES_FILE = os.path.join(SCRIPT_DIR, "sources.json")
MAX_INDEX_ITEMS = 120

USER_AGENT = (
    "Mozilla/5.0 (compatible; NewsAggregator/1.0; +https://github.com/news-aggregator)"
)

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def load_sources() -> list[dict]:
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        sources = json.load(f)
    if not sources:
        print("⚠  sources.json is empty", file=sys.stderr)
    return sources


def fetch_source(source: dict) -> list[dict]:
    """Fetch articles from a single RSS source. Returns list of normalized dicts."""
    name = source.get("name", source["url"])
    url = source["url"]
    category = source.get("category", "general")
    articles: list[dict] = []

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ✗ {name}: request failed — {e}", file=sys.stderr)
        return articles

    feed = feedparser.parse(resp.text)
    if feed.bozo and not feed.entries:
        print(f"  ✗ {name}: parse error — {feed.bozo_exception}", file=sys.stderr)
        return articles

    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        pub = entry.get("published", "") or entry.get("updated", "")
        summary = entry.get("summary", "") or entry.get("description", "")
        # Strip HTML tags from summary
        import re
        summary = re.sub(r"<[^>]+>", " ", summary)
        summary = re.sub(r"\s+", " ", summary).strip()
        # Truncate
        if len(summary) > 300:
            summary = summary[:297] + "..."

        articles.append({
            "title": title,
            "link": link,
            "summary": summary,
            "pubDate": pub,
            "source": name,
            "category": category,
        })

    print(f"  ✓ {name}: {len(articles)} articles")
    return articles


def load_existing_urls() -> set[str]:
    """Scan data/*.json for previously seen URLs so we can filter."""
    seen = set()
    if not os.path.isdir(DATA_DIR):
        return seen
    from dedup import _url_key
    for fname in os.listdir(DATA_DIR):
        if not fname.startswith("news_") or not fname.endswith(".json"):
            continue
        fpath = os.path.join(DATA_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                items = json.load(f)
            for item in items:
                key = _url_key(item.get("link", ""))
                if key:
                    seen.add(key)
        except (json.JSONDecodeError, OSError):
            pass
    return seen


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    sources = load_sources()
    print(f"Fetching {len(sources)} sources...\n")

    # 1. Fetch all sources
    all_articles: list[dict] = []
    stats: dict[str, dict] = {}
    existing_urls = load_existing_urls()
    from dedup import _url_key

    for src in sources:
        start = time.time()
        articles = fetch_source(src)
        elapsed = round(time.time() - start, 2)
        total_from_feed = len(articles)

        # Filter out URLs we already have from any date
        new_count = 0
        fresh: list[dict] = []
        for a in articles:
            if _url_key(a.get("link", "")) not in existing_urls:
                fresh.append(a)
                existing_urls.add(_url_key(a.get("link", "")))
                new_count += 1
        articles = fresh

        stats[src["name"]] = {
            "total": total_from_feed,
            "new": new_count,
            "elapsed": elapsed,
            "last_fetch": datetime.now(timezone.utc).isoformat(),
        }
        all_articles.extend(articles)

    # 2. Deduplicate across sources
    total_before = len(all_articles)
    deduped = deduplicate(all_articles)
    print(f"\nDedup: {total_before} → {len(deduped)} articles")

    # 3. Write daily file
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_path = os.path.join(DATA_DIR, f"news_{today}.json")
    existing_today: list[dict] = []
    if os.path.exists(daily_path):
        try:
            with open(daily_path, "r", encoding="utf-8") as f:
                existing_today = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    # Merge: prepend new items, keep unique by URL
    merged = deduped + existing_today
    seen = set()
    merged_uniq = []
    for a in merged:
        key = _url_key(a.get("link", ""))
        if key not in seen:
            seen.add(key)
            merged_uniq.append(a)
    merged_uniq.sort(key=lambda a: a.get("pubDate", ""), reverse=True)
    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(merged_uniq, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(merged_uniq)} articles to {daily_path}")

    # 4. Update index.json (latest N across all daily files)
    all_time = []
    for fname in os.listdir(DATA_DIR):
        if not fname.startswith("news_") or not fname.endswith(".json"):
            continue
        fpath = os.path.join(DATA_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                all_time.extend(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    # Dedup by URL across all time
    seen_urls = set()
    all_time_uniq = []
    for a in sorted(all_time, key=lambda a: a.get("pubDate", ""), reverse=True):
        key = _url_key(a.get("link", ""))
        if key not in seen_urls:
            seen_urls.add(key)
            all_time_uniq.append(a)
    index = all_time_uniq[:MAX_INDEX_ITEMS]
    index_path = os.path.join(DATA_DIR, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"Updated index.json ({len(index)} items)")

    # 5. Write stats
    stats_path = os.path.join(DATA_DIR, "stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump({
            "updated": datetime.now(timezone.utc).isoformat(),
            "total_indexed": len(all_time_uniq),
            "sources": stats,
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
