"""v11: one small hosted clip per Internet Archive video, served free by Cloudflare Pages.

Why: archive.org serves every file from a single server in the US. TikTok / Reels are fast
because each video is a tiny file on a server near you. This makes that tiny file: the best
CLIP_SECONDS (default 60) of the video, 240p, ~200 kbps (about 2 MB), MP4 with the index at
the front so playback starts after the first few KB.

Where the files go: a git branch called `clips` of your own repo, which Cloudflare Pages
deploys (unlimited bandwidth, 20,000 files, 25 MB per file, no bucket, no API keys).
The GitHub Action in .github/workflows/clips.yml does all of it. See the README.

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
CLIP_SECONDS = int(os.environ.get("CLIP_SECONDS", "60"))
MAX_CLIPS = int(os.environ.get("MAX_CLIPS", "2400"))     # ~5 GB at 2 MB: keeps the repo healthy
HEIGHT = int(os.environ.get("CLIP_HEIGHT", "240"))
ENCODE_V = 1                                              # bump to re-encode everything


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


def encode(src: str, dst: Path, start: float, seconds: float = CLIP_SECONDS) -> float:
    """src (file or URL) -> small faststart MP4. Returns the clip length in seconds.

    ffmpeg seeks straight to `start` over HTTP range requests (archive.org supports them).
    If that fails (a server without range support, or an index at the end of the file), the
    video is downloaded once and cut locally."""
    try:
        return _encode(src, dst, start, seconds)
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
            return _encode(str(local), dst, start, seconds)


def _encode(src: str, dst: Path, start: float, seconds: float) -> float:
    audio = _has_audio(src)
    # short side = HEIGHT (so portrait clips aren't blown up), even dimensions, never upscale
    vf = (f"scale='if(gt(iw,ih),-2,min({HEIGHT},iw))':'if(gt(iw,ih),min({HEIGHT},ih),-2)':flags=bicubic,"
          "format=yuv420p")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-ss", str(start), "-t", str(seconds), "-i", src,
           "-map", "0:v:0", "-vf", vf, "-fpsmax", "24",
           "-c:v", "libx264", "-preset", "slow", "-profile:v", "main", "-level", "3.0",
           "-crf", "29", "-maxrate", "230k", "-bufsize", "460k",
           "-x264-params", "keyint=48:min-keyint=24:scenecut=0"]
    if audio:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "40k", "-ac", "1", "-ar", "32000"]
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


def run(limit: int, out: Path) -> list[dict]:
    have = Item.query.filter(Item.source == "archive").all()
    done_n = sum(1 for i in have if (i.media_info or {}).get("clip", {}).get("v") == ENCODE_V)
    q = (Item.query.filter(Item.source == "archive", Item.hidden.is_(False), Item.broken < 3,
                           Item.media_url.isnot(None), Item.media_url != "")
         .order_by(Item.engagement.desc(), Item.score.desc(), Item.id))
    results = []
    failed = 0
    for it in q:
        if len(results) >= limit or done_n + len(results) >= MAX_CLIPS:
            break
        if (it.media_info or {}).get("clip", {}).get("v") == ENCODE_V or it.kind == "image":
            continue
        src = source_url(it)
        if not src:
            continue
        start = clip_from(it)
        dst = out / f"{it.id}.mp4"
        try:
            secs = encode(src, dst, start)
            if secs < 2:
                raise RuntimeError("empty output")
            d = it.duration or 0
            reached_end = secs < CLIP_SECONDS - 1
            whole = start == 0 and (reached_end or (d and secs >= d - 1))
            results.append({"id": it.id, "from": start, "s": round(secs, 1), "whole": bool(whole), "bytes": dst.stat().st_size})
            log.info("ok %s %.0fs %.1f MB %s", it.id, secs, dst.stat().st_size / 1e6, it.title[:50])
        except Exception as e:  # noqa: BLE001 - one bad video must not stop the batch
            failed += 1
            dst.unlink(missing_ok=True)
            log.warning("fail %s: %s", it.id, e)
    log.info("encoded %d, failed %d, already done %d", len(results), failed, done_n)
    return results


def apply(manifest: list[dict]) -> int:
    n = 0
    for r in manifest:
        it = db.session.get(Item, r["id"])
        if not it:
            continue
        info = dict(it.media_info or {})
        info["clip"] = {"v": ENCODE_V, "from": r["from"], "s": r["s"], "whole": r["whole"]}
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
        res = run(a.limit, a.out)
        a.manifest.write_text(json.dumps(res))


if __name__ == "__main__":
    main()
