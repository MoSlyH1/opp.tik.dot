"""YouTube Data API v3 (official). Needs YOUTUBE_API_KEY.

Quota: a search costs 100 units of the default 10,000/day (~100 searches a day);
`details` costs 1 unit per 50 videos. Everything we fetch is stored, so repeat
searches hit our DB. Keyless oEmbed is used for curated links.
"""

import html
import re

import requests

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
OEMBED_URL = "https://www.youtube.com/oembed"
ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([\w-]{11})")
ISO_DUR = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def video_id(url: str) -> str | None:
    m = ID_RE.search(url or "")
    return m.group(1) if m else None


def _iso_seconds(s: str) -> int | None:
    m = ISO_DUR.fullmatch(s or "")
    if not m:
        return None
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def thumb(vid: str) -> str:
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"


def item(vid, title="", author="", description="", thumbnail=None, tags=None, lang=None, duration=None):
    return {
        "source": "youtube", "external_id": vid, "kind": "video",
        "url": f"https://www.youtube.com/watch?v={vid}",
        "title": html.unescape(title or "")[:300], "author": html.unescape(author or "") or None,
        "description": html.unescape(description or ""), "thumbnail": thumbnail or thumb(vid),
        "tags": tags or [], "lang": lang, "duration": duration,
    }


def search(api_key: str, query: str, max_results: int = 15, timeout: int = 8,
           lang: str | None = None, region: str | None = None, duration: str | None = None) -> list[dict]:
    """`duration`: 'short' (<4 min) / 'medium' (4-20) / 'long' - YouTube's own buckets."""
    if not api_key:
        return []
    params = {
        "part": "snippet", "type": "video", "q": query,
        "maxResults": max(1, min(max_results, 50)),
        "videoEmbeddable": "true", "videoSyndicated": "true", "safeSearch": "moderate", "key": api_key,
    }
    if lang:
        params["relevanceLanguage"] = lang
    if region:
        params["regionCode"] = region
    if duration:
        params["videoDuration"] = duration
    r = requests.get(SEARCH_URL, params=params, timeout=timeout)
    r.raise_for_status()
    out = []
    for it in r.json().get("items", []):
        vid = (it.get("id") or {}).get("videoId")
        sn = it.get("snippet") or {}
        if not vid:
            continue
        thumbs = sn.get("thumbnails") or {}
        t = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
        out.append(item(vid, sn.get("title"), sn.get("channelTitle"), sn.get("description"), t,
                        lang=sn.get("defaultAudioLanguage")))
    try:
        return enrich(api_key, out, timeout)
    except Exception:  # details are a bonus; keep the search results
        return out


def enrich(api_key: str, items: list[dict], timeout: int = 8) -> list[dict]:
    """Add duration, tags and language; drop videos that can't be embedded (1 unit per 50)."""
    if not api_key or not items:
        return items
    by_id = {i["external_id"]: i for i in items}
    keep = []
    ids = list(by_id)
    for n in range(0, len(ids), 50):
        r = requests.get(VIDEOS_URL, params={"part": "contentDetails,status,snippet", "id": ",".join(ids[n:n + 50]),
                                             "key": api_key}, timeout=timeout)
        r.raise_for_status()
        for v in r.json().get("items", []):
            it = by_id.get(v.get("id"))
            st, cd, sn = v.get("status") or {}, v.get("contentDetails") or {}, v.get("snippet") or {}
            if not it or not st.get("embeddable", True) or st.get("privacyStatus") not in (None, "public"):
                continue
            it["duration"] = _iso_seconds(cd.get("duration"))
            it["tags"] = (sn.get("tags") or [])[:10]
            it["lang"] = (sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or it.get("lang") or "")[:16] or None
            if sn.get("description"):
                it["description"] = sn["description"][:2000]
            keep.append(it)
    return keep


def oembed(url: str, timeout: int = 8) -> dict | None:
    vid = video_id(url)
    if not vid:
        return None
    r = requests.get(OEMBED_URL, params={"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"},
                     timeout=timeout)
    if r.status_code != 200:
        return None
    d = r.json()
    return item(vid, d.get("title"), d.get("author_name"), "", d.get("thumbnail_url"))
