"""Dailymotion Data API (official, free, no key for public search).

Dailymotion is where a lot of European and Arabic TV from the '80s-2000s lives:
French/Italian/German ads, Egyptian films, Lebanese shows, Spacetoon cartoons.
The API supports language and country filters, which feed the culture filters.
"""

import re

import requests

API = "https://api.dailymotion.com"
FIELDS = "id,title,description,thumbnail_720_url,thumbnail_480_url,duration,owner.screenname,language,country,allow_embed,tags,private"
# v12.3: Dailymotion blocks many videos by country (and the player answers 403). Our server is in the
# US, where they look fine, so the viewer's country is checked from the `geoblocking` field.
HOME = "lb"          # most viewers are in Lebanon
GEO = ",geoblocking"
ID_RE = re.compile(r"(?:dailymotion\.com/(?:embed/)?video/|dai\.ly/)([a-zA-Z0-9]+)")
UA = {"User-Agent": "opp.tik.dot/4.0"}


def video_id(url: str) -> str | None:
    m = ID_RE.search(url or "")
    return m.group(1) if m else None


def blocked_in(geo, country: str = HOME) -> bool:
    """`geoblocking` is ["allow", "us", "fr"] (only these) or ["deny", "lb"] (everywhere but these).
    Anything we don't understand counts as not blocked."""
    if isinstance(geo, str):
        geo = [g.strip() for g in geo.split(",") if g.strip()]
    if not isinstance(geo, list) or not geo:
        return False
    mode = str(geo[0]).lower()
    countries = {str(c).lower() for c in (geo[1:] if mode in ("allow", "deny") else geo)}
    if not countries:
        return False                    # a bare "allow" / empty list means allowed everywhere
    listed = country.lower() in countries
    return listed if mode == "deny" else not listed


def _item(v: dict) -> dict | None:
    if not v.get("id") or v.get("allow_embed") is False or v.get("private") or blocked_in(v.get("geoblocking")):
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
    params = {"search": query, "fields": FIELDS + GEO, "limit": max(1, min(limit, 100)), "sort": "relevance",
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
    if r.status_code == 400:                      # the API didn't accept the geo field: search without it
        params["fields"] = FIELDS
        r = requests.get(f"{API}/videos", params=params, headers=UA, timeout=timeout)
    r.raise_for_status()
    return [i for i in (_item(v) for v in r.json().get("list", [])) if i]


def fetch(url: str, timeout: int = 8) -> dict | None:
    vid = video_id(url)
    if not vid:
        return None
    r = requests.get(f"{API}/video/{vid}", params={"fields": FIELDS + GEO}, headers=UA, timeout=timeout)
    if r.status_code == 400:
        r = requests.get(f"{API}/video/{vid}", params={"fields": FIELDS}, headers=UA, timeout=timeout)
    return _item(r.json()) if r.status_code == 200 else None


def unplayable(ids: list[str], timeout: int = 8) -> set[str]:
    """Of these Dailymotion ids, the ones that can't be shown in Lebanon (country block, embedding
    turned off, private) or no longer exist. Any API trouble -> empty set: never hide on a guess."""
    bad: set[str] = set()
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        try:
            r = requests.get(f"{API}/videos", params={"ids": ",".join(chunk), "limit": len(chunk),
                             "fields": "id,allow_embed,private,geoblocking"}, headers=UA, timeout=timeout)
            if r.status_code != 200:
                continue
            seen = set()
            for v in r.json().get("list", []):
                seen.add(v.get("id"))
                if v.get("allow_embed") is False or v.get("private") or blocked_in(v.get("geoblocking")):
                    bad.add(v["id"])
            bad |= {x for x in chunk if x not in seen}      # deleted
        except (requests.RequestException, ValueError):
            continue
    return bad