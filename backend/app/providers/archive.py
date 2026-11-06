"""Internet Archive advanced search (official, free, no key).

Great for real period material: TV commercials, music videos, trailers,
cartoons and photo collections, each with a real `year` in its metadata.
"""

import re

import requests

SEARCH_URL = "https://archive.org/advancedsearch.php"
FIELDS = ["identifier", "title", "year", "description", "creator", "subject", "mediatype"]
UA = {"User-Agent": "opp.tik.dot/1.0"}
_TAG_RE = re.compile(r"<[^>]+>")


def _first(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def _year(v):
    m = re.match(r"(\d{4})", str(_first(v)))
    return int(m.group(1)) if m else None


def safe_terms(text: str) -> str:
    """Strip Lucene syntax from user text so it can't break or widen the query."""
    return " ".join(re.findall(r"[\w']+", text or ""))[:80]


def search(query: str, rows: int = 20, mediatype: str = "movies",
           year_from: int = 1940, year_to: int = 2009, timeout: int = 10) -> list[dict]:
    q = f"({query}) AND mediatype:({mediatype}) AND year:[{year_from} TO {year_to}]"
    params = [("q", q), ("rows", rows), ("page", 1), ("output", "json"), ("sort[]", "downloads desc")]
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
        })
    return out
