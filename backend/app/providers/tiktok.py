"""TikTok via its official, public oEmbed endpoint.

TikTok offers no public API for the For You feed or for search, and scraping
the app violates its terms (and gets IP-blocked quickly). What IS allowed:
  * oEmbed: turn any public TikTok URL into title/author/thumbnail/video id.
  * The Embed Player (tiktok.com/player/v1/<id>) to play it inside our site.

So TikTok content enters opp.tik.dot as curated URLs (admin panel or
tiktok_seeds.txt). If you get access to TikTok's Research API or Display API
later, add a fetcher here that returns the same dict shape.
"""

import re

import requests

OEMBED_URL = "https://www.tiktok.com/oembed"
VIDEO_ID_RE = re.compile(r"/video/(\d{8,25})")
UA = {"User-Agent": "opp.tik.dot/1.0 (+https://github.com/)"}


def video_id_from_url(url: str) -> str | None:
    m = VIDEO_ID_RE.search(url or "")
    return m.group(1) if m else None


def fetch(url: str, timeout: int = 8) -> dict | None:
    url = (url or "").strip()
    if "tiktok.com" not in url:
        return None
    r = requests.get(OEMBED_URL, params={"url": url}, headers=UA, timeout=timeout)
    if r.status_code != 200:
        return None
    d = r.json()
    vid = d.get("embed_product_id") or video_id_from_url(url)
    if not vid:
        return None
    title = d.get("title") or ""
    author = d.get("author_name") or ""
    return {
        "source": "tiktok",
        "external_id": str(vid),
        "kind": "video",
        "url": f"https://www.tiktok.com/@{d.get('author_unique_id') or author}/video/{vid}" if author else url,
        "title": title[:300],
        "author": author,
        "description": title,
        "thumbnail": d.get("thumbnail_url"),
        "tags": re.findall(r"#(\w+)", title),
    }
