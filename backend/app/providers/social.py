"""Instagram, X, Facebook and Reddit, through their official APIs only.

None of these sites allow scraping their search bars or hashtag pages (and from
Vercel's shared IPs you'd be blocked within minutes anyway). What they DO allow:

| Platform  | Discovery (hashtags / search)                              | Needs                                   |
|-----------|------------------------------------------------------------|-----------------------------------------|
| Instagram | Graph API Hashtag Search: top & recent media for a hashtag | META_ACCESS_TOKEN + IG_USER_ID          |
|           | (30 different hashtags per rolling 7 days)                 | (Instagram Business/Creator account)    |
| X         | API v2 recent search: "#90s has:videos -is:retweet"        | X_BEARER_TOKEN (Basic tier or above)    |
| Reddit    | r/90s, r/nostalgia, r/2000s... posts linking to videos     | REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET |
| Facebook  | no public video search; curated URLs + official embed      | META_ACCESS_TOKEN for titles (optional) |

Every function returns [] when its keys are missing, so the app runs without them.
"""

import logging
import re
import time

import requests

from . import archive, dailymotion, tiktok, youtube

log = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com/v21.0"
UA = {"User-Agent": "opp.tik.dot/4.0 (by /u/opp_tik_dot)"}

IG_CODE_RE = re.compile(r"instagram\.com/(?:[\w.]+/)?(?:p|reel|reels|tv)/([\w-]+)")
X_ID_RE = re.compile(r"(?:twitter|x)\.com/[\w]+/status/(\d+)")


def ig_code(url: str) -> str | None:
    m = IG_CODE_RE.search(url or "")
    return m.group(1) if m else None


# ---------------------------------------------------------------- Instagram

_ig_tag_ids: dict[str, str] = {}


def instagram_hashtag(tag: str, token: str, ig_user: str, limit: int = 25, timeout: int = 8) -> list[dict]:
    if not (token and ig_user):
        return []
    tag = tag.lstrip("#").lower()
    if tag not in _ig_tag_ids:
        r = requests.get(f"{GRAPH}/ig_hashtag_search", params={"user_id": ig_user, "q": tag, "access_token": token},
                         timeout=timeout)
        r.raise_for_status()
        data = r.json().get("data") or []
        if not data:
            return []
        _ig_tag_ids[tag] = data[0]["id"]
    out = []
    for edge in ("top_media", "recent_media"):
        r = requests.get(f"{GRAPH}/{_ig_tag_ids[tag]}/{edge}", timeout=timeout, params={
            "user_id": ig_user, "access_token": token, "limit": limit,
            "fields": "id,caption,media_type,media_url,permalink,timestamp,like_count"})
        if r.status_code != 200:
            continue
        for m in r.json().get("data") or []:
            code = ig_code(m.get("permalink"))
            if m.get("media_type") != "VIDEO" or not code:
                continue
            cap = (m.get("caption") or "").strip()
            out.append({
                "source": "instagram", "external_id": code, "kind": "video",
                "url": m["permalink"], "title": cap.split("\n")[0][:300] or f"#{tag}",
                "author": None, "description": cap[:2000], "thumbnail": None,
                # Signed CDN URL: plays natively but expires after a while; the player then
                # falls back to Instagram's own embed.
                "media_url": m.get("media_url"), "tags": re.findall(r"#(\w+)", cap)[:10],
            })
    return out


def meta_oembed(url: str, token: str, timeout: int = 8) -> dict:
    """Title/author/thumbnail for a public Instagram or Facebook post (Meta oEmbed Read)."""
    if not token:
        return {}
    kind = "instagram_oembed" if "instagram.com" in url else "oembed_video"
    r = requests.get(f"{GRAPH}/{kind}", params={"url": url, "access_token": token, "omitscript": "true"},
                     timeout=timeout)
    return r.json() if r.status_code == 200 else {}


# ---------------------------------------------------------------- X

def x_search(query: str, bearer: str, limit: int = 25, timeout: int = 10) -> list[dict]:
    if not bearer:
        return []
    r = requests.get("https://api.x.com/2/tweets/search/recent", timeout=timeout,
                     headers={"Authorization": f"Bearer {bearer}"}, params={
                         "query": f"({query}) has:videos -is:retweet -is:reply",
                         "max_results": max(10, min(limit, 100)),
                         "expansions": "attachments.media_keys,author_id",
                         "media.fields": "type,preview_image_url,duration_ms,variants",
                         "user.fields": "username", "tweet.fields": "lang"})
    r.raise_for_status()
    data = r.json()
    media = {m["media_key"]: m for m in (data.get("includes") or {}).get("media", [])}
    users = {u["id"]: u for u in (data.get("includes") or {}).get("users", [])}
    out = []
    for t in data.get("data") or []:
        keys = (t.get("attachments") or {}).get("media_keys") or []
        m = next((media[k] for k in keys if k in media and media[k].get("type") == "video"), None)
        if not m:
            continue
        mp4s = [v for v in m.get("variants") or [] if v.get("content_type") == "video/mp4"]
        mp4s.sort(key=lambda v: abs((v.get("bit_rate") or 0) - 1_500_000))  # ~720p: good + quick
        user = users.get(t.get("author_id"), {})
        text = t.get("text") or ""
        out.append({
            "source": "x", "external_id": t["id"], "kind": "video",
            "url": f"https://x.com/{user.get('username', 'i')}/status/{t['id']}",
            "title": re.sub(r"https://t\.co/\w+", "", text).strip()[:300], "author": user.get("username"),
            "description": text, "thumbnail": m.get("preview_image_url"),
            "media_url": mp4s[0]["url"] if mp4s else None,
            "duration": int(m["duration_ms"] / 1000) if m.get("duration_ms") else None,
            "tags": re.findall(r"#(\w+)", text)[:10], "lang": t.get("lang"),
        })
    return out


# ---------------------------------------------------------------- Reddit (discovery only)

_reddit_token = {"value": None, "exp": 0}


def _reddit_auth(cid: str, secret: str) -> str | None:
    if _reddit_token["value"] and _reddit_token["exp"] > time.time() + 60:
        return _reddit_token["value"]
    r = requests.post("https://www.reddit.com/api/v1/access_token", auth=(cid, secret), headers=UA,
                      data={"grant_type": "client_credentials"}, timeout=8)
    r.raise_for_status()
    d = r.json()
    _reddit_token.update(value=d.get("access_token"), exp=time.time() + int(d.get("expires_in", 3600)))
    return _reddit_token["value"]


def reddit_links(sub: str, cid: str, secret: str, limit: int = 50, period: str = "month") -> list[dict]:
    """Top posts of a nostalgia subreddit that link to a video we can embed (YouTube,
    Dailymotion, Archive, TikTok). Reddit's own v.redd.it files have no audio track, so
    those are skipped. The Reddit title is often better than the video's own."""
    if not (cid and secret):
        return []
    token = _reddit_auth(cid, secret)
    r = requests.get(f"https://oauth.reddit.com/r/{sub}/top", params={"t": period, "limit": limit},
                     headers={**UA, "Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    out = []
    for child in (r.json().get("data") or {}).get("children", []):
        p = child.get("data") or {}
        if p.get("over_18"):
            continue
        url = p.get("url_overridden_by_dest") or p.get("url") or ""
        raw = None
        if (vid := youtube.video_id(url)):
            raw = youtube.item(vid, p.get("title"), None, p.get("selftext") or "")
        elif (vid := dailymotion.video_id(url)):
            raw = {"source": "dailymotion", "external_id": vid, "kind": "video",
                   "url": f"https://www.dailymotion.com/video/{vid}", "title": p.get("title", "")[:300],
                   "thumbnail": f"https://www.dailymotion.com/thumbnail/video/{vid}", "tags": []}
        elif "archive.org/details/" in url:
            ident = url.split("archive.org/details/")[1].split("/")[0].split("?")[0]
            raw = {"source": "archive", "external_id": ident, "kind": "video", "url": f"https://archive.org/details/{ident}",
                   "title": p.get("title", "")[:300], "thumbnail": f"https://archive.org/services/img/{ident}", "tags": []}
        elif "tiktok.com" in url and (vid := tiktok.video_id_from_url(url)):
            raw = {"source": "tiktok", "external_id": vid, "kind": "video", "url": url,
                   "title": p.get("title", "")[:300], "thumbnail": None, "tags": []}
        if raw:
            raw["description"] = f"{raw.get('description') or ''} r/{sub} {p.get('link_flair_text') or ''}".strip()
            out.append(raw)
    return out


__all__ = ["instagram_hashtag", "meta_oembed", "x_search", "reddit_links", "ig_code", "archive"]
