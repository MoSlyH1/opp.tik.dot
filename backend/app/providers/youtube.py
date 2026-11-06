"""YouTube Data API v3 (official). Needs YOUTUBE_API_KEY.

Quota note: one search costs 100 units of the default 10,000/day, so ~100
searches a day. Everything we fetch is stored, so repeat searches hit our DB.
"""

import html

import requests

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def search(api_key: str, query: str, max_results: int = 15, timeout: int = 8) -> list[dict]:
    if not api_key:
        return []
    params = {
        "part": "snippet",
        "type": "video",
        "q": query,
        "maxResults": max(1, min(max_results, 50)),
        "videoEmbeddable": "true",
        "safeSearch": "moderate",
        "key": api_key,
    }
    r = requests.get(SEARCH_URL, params=params, timeout=timeout)
    r.raise_for_status()
    out = []
    for it in r.json().get("items", []):
        vid = (it.get("id") or {}).get("videoId")
        sn = it.get("snippet") or {}
        if not vid:
            continue
        thumbs = sn.get("thumbnails") or {}
        thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
        out.append({
            "source": "youtube",
            "external_id": vid,
            "kind": "video",
            "url": f"https://www.youtube.com/watch?v={vid}",
            "title": html.unescape(sn.get("title", ""))[:300],
            "author": html.unescape(sn.get("channelTitle", "")),
            "description": html.unescape(sn.get("description", "")),
            "thumbnail": thumb,
            "tags": [],
        })
    return out
