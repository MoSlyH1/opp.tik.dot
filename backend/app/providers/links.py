"""Turn any pasted video link into a provider dict (used by the Curator panel)."""

import re

from . import dailymotion, social, tiktok, youtube


def from_url(url: str, config) -> dict | None:
    url = (url or "").strip()
    if not url.startswith("http"):
        return None
    token = config.get("META_ACCESS_TOKEN", "")

    if youtube.video_id(url):
        return youtube.oembed(url) or youtube.item(youtube.video_id(url))
    if "tiktok.com" in url:
        return tiktok.fetch(url)
    if dailymotion.video_id(url):
        return dailymotion.fetch(url)
    if "archive.org/details/" in url:
        ident = url.split("archive.org/details/")[1].split("/")[0].split("?")[0]
        return {"source": "archive", "external_id": ident, "kind": "video",
                "url": f"https://archive.org/details/{ident}", "title": ident.replace("_", " "),
                "thumbnail": f"https://archive.org/services/img/{ident}", "tags": []}
    if (code := social.ig_code(url)):
        o = social.meta_oembed(url, token)
        return {"source": "instagram", "external_id": code, "kind": "video",
                "url": f"https://www.instagram.com/reel/{code}/", "title": (o.get("title") or "Instagram reel")[:300],
                "author": o.get("author_name"), "thumbnail": o.get("thumbnail_url"), "tags": []}
    if "facebook.com" in url or "fb.watch" in url:
        o = social.meta_oembed(url, token)
        m = re.search(r"(?:videos|reel|v)[/=](\d+)", url)
        ext = m.group(1) if m else re.sub(r"\W+", "", url)[-40:]
        return {"source": "facebook", "external_id": ext, "kind": "video", "url": url,
                "title": (o.get("title") or "Facebook video")[:300], "author": o.get("author_name"),
                "thumbnail": o.get("thumbnail_url"), "tags": []}
    if (m := social.X_ID_RE.search(url)):
        return {"source": "x", "external_id": m.group(1), "kind": "video",
                "url": f"https://x.com/i/status/{m.group(1)}", "title": "Post on X", "tags": []}
    return None
