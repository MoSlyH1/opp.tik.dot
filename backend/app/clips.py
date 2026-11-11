"""Small hosted clips for Internet Archive videos, served free by GitHub Pages.

Why: archive.org serves every file from a single server in the US. TikTok / Reels are fast
because each video is a tiny file on a server near you. This makes those tiny files: the best
CLIP_SECONDS (default 30) of the video, MP4 with the index at the front so playback starts
after the first few KB, in two sizes:

  c/<id>.mp4      240p, ~230 kbps  (~0.6 MB)  -> Auto
  c/<id>-144.mp4  144p, ~110 kbps  (~0.35 MB) -> Data saver

Where the files go: a git branch called `clips` of your own repo, published by GitHub Pages
(free, served from Fastly's CDN, no bucket, no API keys, no Cloudflare). GitHub Pages sites
must stay under 1 GB, so the job stops at CLIPS_MAX_MB (default 950) and gives the clips to
the most-watched videos first. The GitHub Action in .github/workflows/clips.yml does all of it.

  python -m app.clips --limit 150 --out ../clips-repo/c --manifest ../clips-manifest.json
  python -m app.clips --apply ../clips-manifest.json        # after the files are pushed

Archive items are public-domain / openly licensed and may be re-hosted. YouTube, Dailymotion
and TikTok items stay as embeds: re-hosting those isn't allowed.
Run where ffmpeg exists (GitHub Actions, Docker, your PC), NOT on Vercel.
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from sqlalchemy.orm.attributes import flag_modified

from .extensions import db
from .models import Item

log = logging.getLogger("clips")
CLIP_SECONDS = int(os.environ.get("CLIP_SECONDS", "30"))     # the feed's default length
WORKERS = int(os.environ.get("CLIP_WORKERS", "4"))           # encodes at the same time (GitHub runners have 4 cores)
MAX_CLIPS = int(os.environ.get("MAX_CLIPS", "2400"))      # videos with a hosted clip, at most
MAX_MB = float(os.environ.get("CLIPS_MAX_MB", "950"))      # GitHub Pages sites must stay under 1 GB
ENCODE_V = 1                                               # bump to re-encode everything

# One file per size. 240p keeps the v11 name (c/<id>.mp4), so clips made before still work.
VARIANTS = {
    240: {"suffix": "", "crf": 29, "maxrate": "230k", "bufsize": "460k", "abr": "40k", "ar": "32000", "fps": 24},
    144: {"suffix": "-144", "crf": 30, "maxrate": "110k", "bufsize": "220k", "abr": "32k", "ar": "22050", "fps": 20},
}
WANT = [q for q in (int(x) for x in os.environ.get("CLIP_QUALITIES", "240,144").split(",") if x.strip()) if q in VARIANTS]
EST_MB = {240: 0.75, 144: 0.4}     # budget estimate before a file exists (30 s)


def have(info: dict | None) -> list[int]:
    """Sizes already hosted for an item (clips from v11 are 240p only)."""
    c = (info or {}).get("clip") or {}
    if c.get("v") != ENCODE_V:
        return []
    return list(c.get("q") or [240])


def file_name(item_id: int, q: int) -> str:
    return f"{item_id}{VARIANTS[q]['suffix']}.mp4"


def clip_from(it: Item) -> int:
    """Where the best part starts (same rules as frontend/src/lib/clip.js)."""
    d = it.duration or 0
    labels = it.labels or ""
    if it.start_at():
        start = it.start_at()
    elif "|t:music|" in labels or it.category == "music":
        start = min(d * 0.26, 80) if d else 0
    elif d > 90:
        start = min(d * 0.08, 20)
    else:
        start = 0
    if d:
        start = min(start, max(0, d - CLIP_SECONDS))
    return max(0, int(start))


def _probe(path: str, entry: str = "format=duration") -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entry, "-of", "csv=p=0", path],
                       capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip().split(",")[0])
    except ValueError:
        return 0.0


def _has_audio(src: str) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=index", "-of", "csv=p=0", src], capture_output=True, text=True, timeout=60)
    return bool(r.stdout.strip())


MAX_DOWNLOAD = 600 * 1024 * 1024      # fallback download cap per video


def encode(src: str, dst: Path, start: float, seconds: float = CLIP_SECONDS, height: int = 240) -> float:
    """src (file or URL) -> small faststart MP4. Returns the clip length in seconds.

    ffmpeg seeks straight to `start` over HTTP range requests (archive.org supports them).
    If that fails (a server without range support, or an index at the end of the file), the
    video is downloaded once and cut locally."""
    try:
        return _encode(src, dst, start, seconds, height)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        if not src.startswith("http"):
            raise
        import tempfile

        import requests
        with tempfile.TemporaryDirectory(prefix="clipsrc-") as td:
            local = Path(td) / "src.mp4"
            got = 0
            with requests.get(src, stream=True, timeout=60) as r, open(local, "wb") as f:
                r.raise_for_status()
                for chunk in r.iter_content(1 << 20):
                    got += len(chunk)
                    if got > MAX_DOWNLOAD:
                        raise RuntimeError("source too big to download")
                    f.write(chunk)
            return _encode(str(local), dst, start, seconds, height)


def _encode(src: str, dst: Path, start: float, seconds: float, height: int = 240) -> float:
    v = VARIANTS[height]
    audio = _has_audio(src)
    # short side = height (so portrait clips aren't blown up), even dimensions, never upscale
    # both sides are forced to even numbers (libx264 refuses odd sizes such as 320x213)
    vf = (f"scale=w='if(gt(iw,ih),-2,min({height},trunc(iw/2)*2))':"
          f"h='if(gt(iw,ih),min({height},trunc(ih/2)*2),-2)':flags=bicubic,format=yuv420p")
    gop = v["fps"] * 2
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-ss", str(start), "-t", str(seconds), "-i", src,
           "-map", "0:v:0", "-vf", vf, "-fpsmax", str(v["fps"]),
           "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "main", "-level", "3.0",
           "-crf", str(v["crf"]), "-maxrate", v["maxrate"], "-bufsize", v["bufsize"],
           "-x264-params", f"keyint={gop}:min-keyint={gop // 2}:scenecut=0"]
    if audio:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", v["abr"], "-ac", "1", "-ar", v["ar"]]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", "-f", "mp4", str(dst)]
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True, timeout=900)
    return _probe(str(dst))


def source_url(it: Item) -> str | None:
    """Input: the biggest file up to ~480p (plenty for 240p output; the Action's network is fast)."""
    r = it.renditions()
    if r:
        pick = [x for x in r if (x.get("h") or 0) <= 576] or r
        return pick[-1]["fallback"] or pick[-1]["url"]
    return it.media_url or None


BATCH = 25


def used_mb(infos) -> float:
    """Megabytes already on the clips site (estimated for clips made before sizes were recorded)."""
    total = 0.0
    for info in infos:
        c = (info or {}).get("clip") or {}
        if c.get("v") != ENCODE_V:
            continue
        total += c["b"] / 1e6 if c.get("b") else sum(EST_MB.get(q, 0.75) for q in (c.get("q") or [240]))
    return total


def _specs(limit: int) -> tuple[list[dict], int]:
    """Plain values for the clips to make (no ORM objects, so the database can be released).
    Most-watched videos first; videos that already have a clip only get the sizes they lack,
    cut from the same start so switching quality keeps the same moment."""
    infos = [mi for (mi,) in db.session.query(Item.media_info).filter(Item.source == "archive")]
    budget = MAX_MB - used_mb(infos)
    done_n = sum(1 for mi in infos if have(mi))
    q = (Item.query.filter(Item.source == "archive", Item.hidden.is_(False), Item.broken < 3,
                           Item.media_url.isnot(None), Item.media_url != "")
         .order_by(Item.engagement.desc(), Item.score.desc(), Item.id))
    out = []
    for it in q:
        if len(out) >= limit:
            break
        if it.kind == "image":
            continue
        got = have(it.media_info)
        need = [x for x in WANT if x not in got]
        if not need or (not got and done_n >= MAX_CLIPS):
            continue
        cost = sum(EST_MB[x] for x in need)
        if cost > budget:
            continue
        src = source_url(it)
        if not src:
            continue
        c = (it.media_info or {}).get("clip") or {}
        start = c["from"] if got else clip_from(it)
        out.append({"id": it.id, "src": src, "start": start, "duration": it.duration or 0, "need": need,
                    "s": c.get("s") if got else None, "whole": c.get("whole") if got else None})
        budget -= cost
        done_n += 0 if got else 1
    return out, done_n


def _make_one(sp: dict, out: Path) -> dict | None:
    made, size = [], 0
    secs, whole = sp.get("s"), sp.get("whole")
    try:
        for q in sp["need"]:
            dst = out / file_name(sp["id"], q)
            try:
                got = encode(sp["src"], dst, sp["start"], CLIP_SECONDS, q)
                if got < 2:
                    raise RuntimeError("empty output")
            except Exception:
                dst.unlink(missing_ok=True)
                raise
            made.append(q)
            size += dst.stat().st_size
            if secs is None:
                secs = got
                d = sp["duration"]
                reached_end = got < CLIP_SECONDS - 1
                whole = sp["start"] == 0 and (reached_end or (d and got >= d - 1))
        log.info("ok %s %ss %s %.2f MB", sp["id"], secs, made, size / 1e6)
    except Exception as e:  # noqa: BLE001 - one bad video must not stop the batch
        log.warning("fail %s: %s", sp["id"], str(e)[:200])
        if not made:
            return None
    return {"id": sp["id"], "from": sp["start"], "s": round(secs, 1), "whole": bool(whole), "q": made, "bytes": size}


def run(limit: int, out: Path, manifest: Path) -> list[dict]:
    """Encode up to `limit` videos. The database is released before the first encode (a 30+ minute
    job would otherwise lose its connection), and the manifest is saved after every batch, so
    a crash or a timeout keeps everything finished so far."""
    specs, done_n = _specs(limit)
    db.session.remove()
    manifest.write_text("[]")
    from concurrent.futures import ThreadPoolExecutor
    results, failed = [], 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for i in range(0, len(specs), BATCH):
            chunk = specs[i:i + BATCH]
            for r in pool.map(lambda sp: _make_one(sp, out), chunk):
                if r:
                    results.append(r)
                else:
                    failed += 1
            manifest.write_text(json.dumps(results))      # saved after every batch
            log.info("progress %d/%d: %d made, %d failed", min(i + BATCH, len(specs)), len(specs), len(results), failed)
    log.info("encoded %d, failed %d, videos with clips before this run %d", len(results), failed, done_n)
    return results


def apply(manifest: list[dict]) -> int:
    n = 0
    for r in manifest:
        it = db.session.get(Item, r["id"])
        if not it:
            continue
        info = dict(it.media_info or {})
        old = info.get("clip") or {}
        prev = have(info)
        q = sorted(set(prev) | set(r.get("q") or [240]), reverse=True)
        b = (old.get("b") or (sum(EST_MB.get(x, 0.75) for x in prev) * 1e6 if prev else 0)) + (r.get("bytes") or 0)
        info["clip"] = {"v": ENCODE_V, "from": r["from"], "s": r["s"], "whole": r["whole"], "q": q, "b": int(b)}
        it.media_info = info
        flag_modified(it, "media_info")
        n += 1
    db.session.commit()
    return n


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=150)
    p.add_argument("--out", type=Path, default=Path("clips-out/c"))
    p.add_argument("--manifest", type=Path, default=Path("clips-manifest.json"))
    p.add_argument("--apply", type=Path, help="write a finished manifest to the database")
    a = p.parse_args()
    from . import create_app
    with create_app().app_context():
        if a.apply:
            log.info("database updated for %d clips", apply(json.loads(a.apply.read_text())))
            return
        if not shutil.which("ffmpeg"):
            raise SystemExit("ffmpeg not found")
        run(a.limit, a.out, a.manifest)


if __name__ == "__main__":
    main()