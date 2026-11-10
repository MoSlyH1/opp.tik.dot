"""v7: re-encode Internet Archive clips into HLS and put them on a CDN.

Why: archive.org serves every MP4 from one storage server in the US, with no CDN and
throughput that is often a few hundred KB/s from the Middle East. TikTok / Reels feel
instant because they stream small 2-second chunks from an edge server near you, start
on a low-bitrate rung and climb as the connection allows (adaptive bitrate). This does
the same for our archive items, which are public-domain / openly licensed and may be
re-hosted. (YouTube and TikTok items stay as embeds: re-hosting those isn't allowed.)

Per clip: up to CLIP_SECONDS from the item's start point, a 3-rung ladder
(144p / 240p / 360p / 540p), 4 s segments with a keyframe at every segment start, uploaded to
any S3-compatible bucket (Cloudflare R2 recommended: zero egress fees). The playlist URL
is stored in item.media_info["hls"].

Run where ffmpeg exists and runs can be long (GitHub Actions, Docker, your PC) - NOT
on Vercel:   python -m app.transcode --limit 40
Env: DATABASE_URL, S3_ENDPOINT, S3_BUCKET, S3_KEY, S3_SECRET, CDN_BASE
"""

import argparse
import logging
import mimetypes
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy.orm.attributes import flag_modified

from . import create_app
from .extensions import db
from .models import Item

log = logging.getLogger("transcode")
CLIP_SECONDS = int(os.environ.get("HLS_CLIP_SECONDS", "150"))
# name, height, video kbps, audio kbps
# 144p is the "bad mobile data" rung: ~170 kbps total, starts even on 3G.
LADDER = [("144p", 144, 120, 48), ("240p", 240, 300, 48), ("360p", 360, 650, 64), ("540p", 540, 1300, 96)]
# 4 s chunks: half the requests of 2 s chunks, which keeps the free Cloudflare Worker
# (100k requests/day) comfortable and cuts per-request round trips on high-latency links.
# The first chunk is still small (~85 KB at 144p, ~190 KB at 240p), so starts stay fast.
SEG = int(os.environ.get("HLS_SEGMENT_SECONDS", "4"))


def _has_audio(src: str) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=index", "-of", "csv=p=0", src], capture_output=True, text=True, timeout=60)
    return bool(r.stdout.strip())


def _ffmpeg(src: str, start: int, out: Path) -> None:
    audio = _has_audio(src)
    n = len(LADDER)
    split = f"[0:v]split={n}" + "".join(f"[v{i}]" for i in range(n)) + ";"
    scales = ";".join(f"[v{i}]scale=-2:{h}:flags=bicubic[o{i}]" for i, (_, h, _, _) in enumerate(LADDER))
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-ss", str(start), "-t", str(CLIP_SECONDS), "-i", src,
           "-filter_complex", split + scales]
    for i, (_, h, vk, ak) in enumerate(LADDER):
        cmd += ["-map", f"[o{i}]", f"-c:v:{i}", "libx264", f"-b:v:{i}", f"{vk}k",
                f"-maxrate:v:{i}", f"{int(vk * 1.2)}k", f"-bufsize:v:{i}", f"{vk * 2}k"]
        if audio:
            cmd += ["-map", "0:a:0", f"-c:a:{i}", "aac", f"-b:a:{i}", f"{ak}k"]
    streams = " ".join(f"v:{i}" + (f",a:{i}" if audio else "") + f",name:{nm}"
                       for i, (nm, *_r) in enumerate(LADDER))
    cmd += (["-ac", "2"] if audio else []) + [
            "-preset", "veryfast", "-profile:v", "main", "-pix_fmt", "yuv420p",
            "-sc_threshold", "0", "-force_key_frames", f"expr:gte(t,n_forced*{SEG})",
            "-f", "hls", "-hls_time", str(SEG), "-hls_playlist_type", "vod",
            "-hls_flags", "independent_segments", "-hls_segment_type", "mpegts",
            "-master_pl_name", "master.m3u8", "-var_stream_map", streams,
            "-hls_segment_filename", str(out / "%v" / "s%03d.ts"), str(out / "%v" / "index.m3u8")]
    subprocess.run(cmd, check=True, timeout=900)


def _client():
    import boto3  # only needed by this job
    return boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"],
                        aws_access_key_id=os.environ["S3_KEY"],
                        aws_secret_access_key=os.environ["S3_SECRET"], region_name="auto")


def _upload(s3, folder: Path, prefix: str) -> None:
    bucket = os.environ["S3_BUCKET"]
    for f in folder.rglob("*"):
        if not f.is_file():
            continue
        key = f"{prefix}/{f.relative_to(folder).as_posix()}"
        ctype = "application/vnd.apple.mpegurl" if f.suffix == ".m3u8" else (mimetypes.guess_type(f.name)[0] or "video/mp2t")
        s3.upload_file(str(f), bucket, key, ExtraArgs={
            "ContentType": ctype,
            # Files never change once written (new encode = new prefix): cache forever at the edge.
            "CacheControl": "public, max-age=31536000, immutable"})


ENCODE_VERSION = "v2"   # bump to re-encode everything with new settings


def source_url(it: Item) -> str | None:
    """Best input file: the highest rendition up to ~480p is plenty for a 540p top rung."""
    r = it.renditions()
    if r:
        pick = [x for x in r if (x.get("h") or 0) <= 576] or r
        return pick[-1]["fallback"] or pick[-1]["url"]
    return it.media_url or None


def run(limit: int = 40) -> dict:
    cdn = os.environ["CDN_BASE"].rstrip("/")
    s3 = _client()
    q = (Item.query.filter(Item.source == "archive", Item.hidden.is_(False), Item.broken < 3,
                           Item.media_url.isnot(None), Item.media_url != "")
         .order_by(Item.engagement.desc(), Item.score.desc()))
    done = failed = 0
    for it in q.limit(limit * 4):
        if done >= limit:
            break
        info = dict(it.media_info or {})
        if info.get("hls") and info.get("hls_v") == ENCODE_VERSION:
            continue
        src = source_url(it)
        if not src:
            continue
        tmp = Path(tempfile.mkdtemp(prefix="hls-"))
        try:
            start = it.start_at()
            _ffmpeg(src, start, tmp)
            prefix = f"{ENCODE_VERSION}/{it.id}"
            _upload(s3, tmp, prefix)
            info.update(hls=f"{cdn}/{prefix}/master.m3u8", hls_start=start, hls_v=ENCODE_VERSION)
            it.media_info = info
            flag_modified(it, "media_info")
            db.session.commit()
            done += 1
            log.info("ok %s %s", it.id, it.title[:60])
        except Exception as e:  # noqa: BLE001 - one bad clip must not stop the batch
            db.session.rollback()
            failed += 1
            log.warning("fail %s: %s", it.id, e)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return {"encoded": done, "failed": failed}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=40)
    a = p.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found")
    with create_app().app_context():
        log.info("done: %s", run(a.limit))


if __name__ == "__main__":
    main()
