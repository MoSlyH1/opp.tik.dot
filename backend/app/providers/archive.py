"""Internet Archive advanced search + metadata (official, free, no key).

Great for real period material: TV commercials, music videos, trailers, cartoons,
news broadcasts and channel idents, each with a real `year` and often a `language`.

Why v3 videos didn't play: the feed embedded archive.org/embed/<id>, a full page
player that starts *unmuted*, which every browser blocks without a tap, and that
is slow to boot. v4 asks the metadata API for the item's MP4 file and plays it in a
native <video> element instead: muted autoplay always works, it preloads like any
other file, and it starts instantly.
"""

import re
from urllib.parse import quote

import requests

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{}"
FIELDS = ["identifier", "title", "year", "description", "creator", "subject", "mediatype", "language"]
UA = {"User-Agent": "opp.tik.dot/4.0 (+https://github.com/MoSlyH1/opp.tik.dot)"}
_TAG_RE = re.compile(r"<[^>]+>")

# Browser-playable video derivatives, best first. "h.264" is the standard 480p derivative
# archive.org makes for every upload; "512Kb MPEG4" is the tiny legacy one.
VIDEO_FORMATS = {"h.264": 0, "h.264 ia": 0, "mpeg4": 1, "h.264 hd": 2, "512kb mpeg4": 3}
IMAGE_FORMATS = {"jpeg": 0, "png": 1, "jpeg 2000": 9}


def _first(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def _year(v):
    m = re.match(r"(\d{4})", str(_first(v)))
    return int(m.group(1)) if m else None


def _seconds(v) -> int | None:
    """'123.4' or '01:02:03' -> seconds."""
    if v in (None, ""):
        return None
    s = str(v)
    try:
        if ":" in s:
            parts = [float(p) for p in s.split(":")]
            total = 0.0
            for p in parts:
                total = total * 60 + p
            return int(total)
        return int(float(s))
    except ValueError:
        return None


def safe_terms(text: str) -> str:
    """Strip Lucene syntax from user text so it can't break or widen the query."""
    return " ".join(re.findall(r"[\w']+", text or ""))[:80]


def search(query: str, rows: int = 20, mediatype: str = "movies",
           year_from: int = 1930, year_to: int = 2009, timeout: int = 10,
           sort: str = "downloads desc", page: int = 1) -> list[dict]:
    q = f"({query}) AND mediatype:({mediatype}) AND year:[{year_from} TO {year_to}]"
    params = [("q", q), ("rows", rows), ("page", page), ("output", "json"), ("sort[]", sort)]
    params += [("fl[]", f) for f in FIELDS]
    r = requests.get(SEARCH_URL, params=params, headers=UA, timeout=timeout)
    r.raise_for_status()
    out = []
    for d in r.json().get("response", {}).get("docs", []):
        ident = d.get("identifier")
        if not ident:
            continue
        subjects = d.get("subject") or []
        if isinstance(subjects, str):
            subjects = [s.strip() for s in subjects.split(";")]
        desc = _TAG_RE.sub(" ", str(_first(d.get("description"))))[:2000]
        lang = d.get("language")
        lang = ";".join(lang) if isinstance(lang, list) else (lang or None)
        out.append({
            "source": "archive",
            "external_id": ident,
            "kind": "image" if d.get("mediatype") == "image" else "video",
            "url": f"https://archive.org/details/{ident}",
            "title": str(_first(d.get("title")))[:300] or ident,
            "author": str(_first(d.get("creator")))[:200] or None,
            "description": desc,
            "thumbnail": f"https://archive.org/services/img/{ident}",
            "tags": [s for s in subjects if s][:10],
            "year": _year(d.get("year")),
            "lang": lang[:16] if lang else None,
        })
    return out


def _kbps(size: int, length: int | None) -> int | None:
    return int(size * 8 / length / 1000) if size and length else None


def pick_file(files: list[dict], kind: str = "video") -> dict | None:
    """Choose the clip to play from an item's file list, plus every rendition of it.

    Prefers a standard derivative, then clips of feed-friendly length (a 40-file
    commercials compilation becomes one short commercial instead of a 2-hour reel),
    then the smallest file so it starts fast on mobile data.

    v6: archive.org usually makes several MP4s of the same clip (the 480p "h.264",
    the tiny legacy "512Kb MPEG4", sometimes "h.264 HD"). They share the same
    `original`, so they're grouped and all returned as `renditions` (lowest bitrate
    first). The player picks one per viewer from their connection speed."""
    table = VIDEO_FORMATS if kind == "video" else IMAGE_FORMATS
    groups: dict[str, list] = {}
    for f in files or []:
        name = f.get("name") or ""
        fmt = (f.get("format") or "").lower()
        if fmt not in table:
            continue
        if kind == "video" and not name.lower().endswith((".mp4", ".m4v")):
            continue
        if kind == "image" and ("_thumb" in name or name.startswith("__ia_thumb")):
            continue
        length = _seconds(f.get("length"))
        size = int(f.get("size") or 0)
        try:
            height = int(float(f.get("height") or 0))
        except ValueError:
            height = 0
        key = f.get("original") if f.get("source") == "derivative" and f.get("original") else name
        groups.setdefault(key, []).append({"rank": table[fmt], "name": name, "length": length, "size": size,
                                           "h": height, "kbps": _kbps(size, length)})
    if not groups:
        return None

    def group_key(g):
        length = max((x["length"] or 0 for x in g), default=0) or None
        fit = 0 if length and 15 <= length <= 600 else 1 if length and length <= 1800 else 2
        best = min(g, key=lambda x: (x["rank"], x["size"] or 10**12))
        return (best["rank"], fit, best["size"] or 10**12, best["name"])

    group = min(groups.values(), key=group_key)
    main = min(group, key=lambda x: (x["rank"], x["size"] or 10**12, x["name"]))
    length = main["length"] or max((x["length"] or 0 for x in group), default=0) or None
    rends = sorted(group, key=lambda x: (x["kbps"] if x["kbps"] is not None else 10**6, x["h"]))
    return {"name": main["name"], "duration": length,
            "renditions": [[x["name"], x["kbps"], x["h"]] for x in rends] if kind == "video" else []}


def resolve(identifier: str, kind: str = "video", timeout: int = 8) -> dict:
    """-> {"media_url": str ('' when nothing is playable), "duration": int|None, "media_info": dict|None}

    media_info = {"node": "ia800308.us.archive.org/21/items/<id>", "r": [[name, kbps, height], ...]}
    `node` is the storage server that holds the files right now. Playing from it directly
    skips the archive.org/download/ redirect (one slow round trip on every video start and,
    in some browsers, on every range request). If the item moves, the player falls back
    to the /download/ URL, which always works."""
    empty = {"media_url": "", "duration": None, "media_info": None}
    r = requests.get(METADATA_URL.format(quote(identifier, safe="")), headers=UA, timeout=timeout)
    r.raise_for_status()
    data = r.json() or {}
    if data.get("is_dark") or not data.get("files"):
        return empty
    meta = data.get("metadata") or {}
    if str(meta.get("access-restricted-item", "")).lower() == "true":
        return empty
    f = pick_file(data["files"], kind)
    if not f:
        return empty
    url = download_url(identifier, f["name"])
    server = data.get("server") or data.get("d1") or ""
    folder = data.get("dir") or ""
    node = f"{server}{folder}" if server and folder.startswith("/") else None
    info = {"node": node, "r": f.get("renditions") or []} if (node or f.get("renditions")) else None
    return {"media_url": url, "duration": f["duration"] or _seconds(meta.get("runtime")), "media_info": info}


def download_url(identifier: str, name: str) -> str:
    return f"https://archive.org/download/{quote(identifier, safe='')}/{quote(name)}"


def node_url(node: str, name: str) -> str:
    return f"https://{node}/{quote(name)}"
