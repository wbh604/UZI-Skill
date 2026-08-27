"""Optional X sentiment source backed by the public Xquik Python SDK."""
from __future__ import annotations

import os
from collections.abc import Callable


def build_stock_query(code: str, name: str, market: str) -> str:
    """Build an X search query from the canonical ticker and company name."""
    clean_code = code.strip().upper()
    clean_name = name.strip().replace('"', "")
    terms: list[str] = []
    if clean_name and clean_name.upper() != clean_code:
        terms.append(f'"{clean_name}"')
    terms.append(f"${clean_code}" if market == "U" else f'"{clean_code}"')
    return " OR ".join(dict.fromkeys(terms))


def _value(record: object, key: str, default: object = None) -> object:
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _to_snippet(tweet: object) -> dict[str, str]:
    tweet_id = str(_value(tweet, "id", "") or "")
    text = str(_value(tweet, "text", "") or "").strip()
    author = _value(tweet, "author")
    username = str(_value(author, "username", "") or "").strip()
    url = str(_value(tweet, "url", "") or "").strip()
    if not url and tweet_id:
        url = f"https://x.com/i/status/{tweet_id}"
    return {
        "title": f"@{username}" if username else "X post",
        "body": text[:300],
        "url": url,
    }


def fetch_x_sentiment(
    query: str,
    *,
    limit: int = 20,
    api_key: str | None = None,
    client_factory: Callable[..., object] | None = None,
) -> dict:
    """Search X when credentials and the optional SDK are available."""
    key = api_key or os.environ.get("X_TWITTER_SCRAPER_API_KEY")
    if not key:
        return {"status": "not_configured", "query": query, "total_hits": 0, "snippets": []}

    if client_factory is None:
        try:
            from x_twitter_scraper import XTwitterScraper
        except ImportError:
            return {"status": "sdk_missing", "query": query, "total_hits": 0, "snippets": []}
        client_factory = XTwitterScraper

    client: object | None = None
    try:
        client = client_factory(api_key=key, max_retries=1, timeout=12.0)
        x_resource = _value(client, "x")
        tweets_resource = _value(x_resource, "tweets")
        search = _value(tweets_resource, "search")
        if not callable(search):
            raise TypeError("Xquik client does not expose tweet search")
        response = search(q=query, limit=max(1, min(limit, 50)), query_type="Latest")
        tweets = _value(response, "tweets", [])
        snippets = [_to_snippet(tweet) for tweet in tweets if _value(tweet, "text")]
        return {
            "status": "ok",
            "query": query,
            "total_hits": len(snippets),
            "snippets": snippets,
        }
    except Exception as exc:
        return {
            "status": "error",
            "query": query,
            "error_type": type(exc).__name__,
            "total_hits": 0,
            "snippets": [],
        }
    finally:
        close = _value(client, "close") if client is not None else None
        if callable(close):
            try:
                close()
            except Exception:
                pass
