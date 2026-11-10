"""Dailymotion Data API (official, free, no key for public search).

Dailymotion is where a lot of European and Arabic TV from the '80s-2000s lives:
French/Italian/German ads, Egyptian films, Lebanese shows, Spacetoon cartoons.
The API supports language and country filters, which feed the culture filters.
"""

import re

import requests

API = "https://api.dailymotion.com"
FIELDS = "id,title,description,thumbnail_720_url,thumbnail_480_url,duration,owner.screenname,language,country,allow_embed,tags,private"
ID_RE = re.compile(r"(?:dailymotion\.com/(?:embed/)?video/|dai\.ly/)([a-zA-Z0-9]+)")
UA = {"User-Agent": "opp.tik.dot/4.0"}


def video_id(url: str) -> str | None:
    m = ID_RE.search(url or "")
    return m.group(1) if m else None


def _item(v: dict) -> dict | None:
    if not v.get("id") or v.get("allow_embed") is False or v.get("private"):
        return None
    return {
        "source": "dailymotion", "external_id": v["id"], "kind": "video",
        "url": f"https://www.dailymotion.com/video/{v['id']}",
        "title": (v.get("title") or "")[:300], "author": v.get("owner.screenname"),
        "description": (v.get("description") or "")[:2000],
        "thumbnail": v.get("thumbnail_720_url") or v.get("thumbnail_480_url"),
        "tags": (v.get("tags") or [])[:10], "lang": v.get("language"), "country": v.get("country"),
        "duration": v.get("duration"),
    }


def search(query: str, limit: int = 20, lang: str | None = None, country: str | None = None,
           kids: bool = False, timeout: int = 8, max_minutes: int | None = 20) -> list[dict]:
    params = {"search": query, "fields": FIELDS, "limit": max(1, min(limit, 100)), "sort": "relevance",
              "family_filter": "true", "private": "false", "password_protected": "false"}
    if lang:
        params["languages"] = lang
    if country:
        params["country"] = country
    if kids:
        params["is_created_for_kids"] = "true"
    if max_minutes:
        params["shorter_than"] = max_minutes
    r = requests.get(f"{API}/videos", params=params, headers=UA, timeout=timeout)
    r.raise_for_status()
    return [i for i in (_item(v) for v in r.json().get("list", [])) if i]


def fetch(url: str, timeout: int = 8) -> dict | None:
    vid = video_id(url)
    if not vid:
        return None
    r = requests.get(f"{API}/video/{vid}", params={"fields": FIELDS}, headers=UA, timeout=timeout)
    return _item(r.json()) if r.status_code == 200 else None
