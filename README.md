# opp.tik.dot

**The feed, rewound.** A TikTok-style vertical feed filtered down to nostalgia: movies, music videos,
style, ads, TV, tech and games from the '90s, the 2000s and before. Swipe forward like TikTok, or flip
on **Rewind** and the whole feed runs the opposite direction.

- React (Vite) frontend · Flask API · PostgreSQL
- Google sign-in only
- Docker for local/self-hosting, Vercel + Neon for serverless hosting (one project)
- Works on phone and desktop (snap-scroll on touch, arrow keys / `j` `k` / buttons on desktop, `m` to mute)

---

## What's new in v11 — a small hosted clip for every Archive video, free on Cloudflare Pages

Archive.org serves every file from one server in the US, so Archive videos are slow from Lebanon
(YouTube and Dailymotion are not: they stream from nearby Google / Dailymotion servers).
TikTok and Reels are fast because each video is a tiny file on a nearby server. v11 does that
for your Archive videos, with no bucket and no API keys:

- `backend/app/clips.py` makes **one small MP4 per Archive video**: its best 60 seconds, 240p,
  about 270 kbps (**roughly 2 MB**), index at the front so it starts after the first few KB.
  Music videos start around the first chorus; long films skip the logos.
- A GitHub Action (`.github/workflows/clips.yml`) runs it on GitHub's free servers and saves the
  files on a branch called `clips` of this same repo. **Cloudflare Pages** serves that branch:
  unlimited bandwidth, no 10 GB cap (Pages allows 20,000 files, up to 25 MB each).
- The app plays the hosted clip when the chosen length fits in it (**30 s** and **1 min**), and the
  original for **2 min / Full** and for **Watch full** (continuing from the same spot).
  If a hosted file ever fails, the original plays instead; nobody sees an error.
- The feed prefers videos that have a hosted clip, and a viewer's first video is always a fast one.

### Setup (about 10 minutes, once)
1. GitHub repo -> Settings -> Secrets and variables -> Actions -> New repository secret:
   `DATABASE_URL` = your Neon link.
2. GitHub repo -> Actions -> **clips** -> Run workflow (limit 150). The first run creates the `clips` branch.
3. Cloudflare (free account) -> Workers & Pages -> Create -> **Pages** -> Connect to Git -> pick this repo ->
   production branch **`clips`** -> framework "None", build command empty, output directory empty (or `/`) -> Deploy.
   Copy the address (`https://<project>.pages.dev`).
4. Vercel -> your project -> Settings -> Environment Variables -> `CLIPS_BASE` = that address -> redeploy.
5. Check: open `https://<project>.pages.dev/c/<number>.mp4` for any clip the Action made (see the
   `clips` branch on GitHub): it should play.

After that it runs by itself every day (150 clips/run) and the app picks new clips up automatically.
To do the first batch faster, run the Action several times with a bigger limit (e.g. 250).
1,310 videos is about 2.6 GB; the cap is `MAX_CLIPS` (default 2400, about 5 GB, GitHub's comfortable
repo size). `CLIP_SECONDS=30` (Action env) halves the size if you ever need room.

Only Archive videos are re-hosted (they are public-domain / openly licensed). YouTube, Dailymotion and
TikTok stay as embeds: re-hosting those isn't allowed.

The v8 R2 + Worker setup and the v10 `edge-worker/` are **not needed** any more (the daily R2 workflow
was removed). The code is still in the repo, unused.

## What's new in v10 — free edge cache for Archive videos (3-minute setup, no bucket)

Archive.org serves every file from one server in the US, which is the slow part from Lebanon.
`edge-worker/worker.js` is a ~50-line Cloudflare Worker that sits in front of it and makes
Cloudflare's CDN keep a copy of each file people stream. It stores nothing itself: no R2 bucket,
no API keys, no GitHub secrets, no 10 GB limit. Free up to 100,000 requests/day.

1. Cloudflare (free account) -> Workers & Pages -> Create -> Hello World -> name `opp-edge` -> Deploy
   -> Edit code -> paste `edge-worker/worker.js` -> Deploy. Copy its address (`https://opp-edge.<you>.workers.dev`).
2. Vercel -> your project -> Settings -> Environment Variables -> `MEDIA_BASE` = that address -> redeploy.
3. Check: open `<address>/media/<node>/<path>` of any clip twice (or look at the `cf-cache-status`
   header in the browser's network tab): the second time it should say `HIT`.

Without `MEDIA_BASE` everything works as in v9 (files go through Vercel). If the Worker is ever
unreachable the player falls back to archive.org by itself.

## What's new in v9 — Snack mode: short clips that load fast (no setup)

No accounts, no Cloudflare, nothing to configure: push and it works.

- **Clips instead of whole videos.** Every video plays its best 30 seconds by default (music
  videos jump to the first chorus, about a quarter in; films skip the logos). When the clip ends,
  the next video slides in by itself. A 30 s clip at low quality is about 1 MB instead of
  5-15 MB for the full video, so it starts sooner and uses less data.
- **Pick the length:** the clock chip in the top bar (tap the screen to show it) switches
  30s → 1 min → 2 min → Full. Also in the ⋯ menu and Profile. Remembered per phone.
- **"Watch full · 3:45"** appears in the last seconds of every clip: one tap and the same video
  keeps playing, no reload. Dragging the scrubber does the same.
- **Never stuck on a spinner:** while a video loads you see its year and title over a slowly
  moving thumbnail; after 4.5 s a "Slow one · Next" button appears; after 12 s it moves on by itself.
- **Fast sources first on slow connections:** on Data saver / Auto, the ranking leans towards
  YouTube (served from Google servers near the viewer) and away from plain Archive files (one US
  server) and third-party embeds. The first video of every session is always a fast-starting one.
- **Fair ranking for clips:** watch time is compared with the clip's length, not the whole film's.

Files: `frontend/src/lib/clip.js` (new), `Player.jsx`, `FeedCard.jsx`, `Pager.jsx`, `FilterBar.jsx`,
`Profile.jsx`, `Feed.jsx`, `boot.js`, `styles.css`; `backend/app/ranking.py`, `routes.py`.

The v8 Cloudflare setup below is now **optional**. If you ever do it: at 30 s / 240p a clip is
~1 MB, so the free 10 GB holds roughly 10,000 clips.

## What's new in v8 — free CDN without a domain + device caching

- **`cdn-worker/`**: a free Cloudflare Worker that serves the R2 bucket at
  `https://opp-video.<you>.workers.dev`. No domain needed, free up to 100k requests/day, served
  from Cloudflare's edge (incl. Beirut). This replaces step 2 of the setup below.
- **Encodes v2**: 4 s chunks (half the requests), plus a 144p rung (~170 kbps) for weak mobile
  data. Old v1 encodes keep working; the job re-encodes them over time.
- **Service worker (`frontend/public/sw.js`)**: caches app files, thumbnails and video chunks on
  the viewer's phone. Second visits open instantly; swiping back or looping costs zero data.
- **Long cache headers** for `/assets/*` on Vercel; **hls.js light** build (~35 KB smaller).
- Quality caps: Data saver tops at 240p, Auto (mid) at 360p, HD uncapped.

### Free setup, start to finish (~20 minutes)
1. Cloudflare (free account) -> R2 -> enable (free plan, 10 GB) -> create bucket `opp-video`.
2. Workers & Pages -> Create -> Worker -> name `opp-video` -> Deploy -> Edit code -> paste
   `cdn-worker/worker.js` -> Deploy. Settings -> Bindings -> Add -> R2 bucket:
   variable `VIDEO`, bucket `opp-video`. Copy the Worker URL: that is `CDN_BASE`.
3. R2 -> Manage API tokens -> Create (Object Read & Write, bucket `opp-video`):
   gives `S3_KEY`, `S3_SECRET`, and `S3_ENDPOINT` = `https://<account-id>.r2.cloudflarestorage.com`.
4. GitHub repo -> Settings -> Secrets and variables -> Actions -> add `DATABASE_URL` (Neon),
   `S3_ENDPOINT`, `S3_BUCKET` (= `opp-video`), `S3_KEY`, `S3_SECRET`, `CDN_BASE`.
5. GitHub -> Actions -> `transcode` -> Run workflow (limit 40). Then it runs daily.
6. Check: open `CDN_BASE/v2/<an item id>/master.m3u8` in the browser; it should download a playlist.

## What's new in v6 — speed + tap-to-reveal

**Videos start faster**
- **Player pool.** The feed recycles 4 card slots (previous, current, next, the one after). A
  YouTube player is created once per slot and reused with `cueVideoById` / `loadVideoById`, so a
  swipe no longer boots a fresh YouTube iframe (the biggest delay in v5).
- **The video on screen loads first.** The next video starts buffering only once yours is
  playing (or after a 2s head start on fast connections), so they don't share bandwidth.
- **Adaptive quality: Auto / Data saver / HD** (⋯ menu on any video, or Profile). Auto starts from
  the browser's network info and then learns from every video start and stall. Data saver plays
  the smallest Archive file (~240p), keeps YouTube's player small so its auto-quality stays low,
  and fetches only the first bytes of the next video.
- **Internet Archive:** every rendition of a clip is stored (`items.media_info`), and files play
  straight from the storage server instead of going through the `archive.org/download/` redirect.
  If a file is slow to start or stalls twice, the player steps down to a smaller file and keeps
  your position. If the server moved, it falls back to the `/download/` link.
- **Parallel boot:** meta, session, first feed page and the YouTube API all load at once.
  `/api/meta` is cached on Vercel's CDN, and the feed never waits more than ~2s on archive.org.

**Cleaner screen**
- Only the video, a thin progress line and a short title caption. Tap once to show like, save,
  follow, share, sound, ⋯, play/pause and a draggable scrubber; they hide after 3 seconds.
  Double-tap to like. On desktop, moving the mouse shows them and clicking pauses.
- **Follow creators** (`POST /api/me/follow`): their videos get their own pool and a boost in
  the ranking. Listed in Profile.

After deploying, sign in as an admin → Profile → **Speed up Archive videos** (repeat until 0 left)
so items saved by older versions get their renditions. The daily cron also does 120 per run.

## What's new in v4

- **Internet Archive videos play.** v3 embedded archive.org's page player, which starts unmuted
  (blocked by every browser) and boots slowly. v4 looks up each item's MP4 through the Archive
  metadata API and plays it in a native `<video>`: instant, muted autoplay, preloaded like a file.
  Long multi-file items pick a feed-length clip. Items with no playable file never reach the feed.
- **Filters in four dimensions:** era (`'50s` to `2000s`), 25 topics (kids & cartoons, anime,
  documentaries, football, F1, wrestling, sci-fi, horror, cars, commercials, channel idents...),
  20+ cultures (Arabic, Lebanese, Egyptian, Gulf, Maghreb, Turkish, Latin, Mexican, Brazilian,
  European, British, French, German, Italian, Japanese, Korean, Chinese, Indian, African...) and
  ~30 TV channels (MTV, Spacetoon, LBC, Future TV, Cartoon Network, MBC...). OR inside a group,
  AND across groups. The classifier reads English, Arabic, French, Spanish, Portuguese, German, Turkish.
- **New feed engine:** finger-following swipe pager (no scroll-snap), autoplay on every swipe,
  pull-to-refresh, double-tap to like, progress bar, dead videos skipped automatically.
- **Rewind:** locks forward motion where you are and plays your session backwards with swipe-down.
- **Ranking:** `backend/app/ranking.py` (see below).
- **Sources:** + Dailymotion (keyless), Reddit, Instagram hashtags, X search (official APIs, optional
  keys), and paste-any-link curation for TikTok / Instagram / Facebook / X / YouTube.

After deploying, sign in as an admin, open Profile and press **Re-label catalogue** (applies the new
filters to existing items), then **Run ingest now**. Schema changes are applied automatically at boot.

## Where the content comes from (read this first)

None of these platforms allow scraping their search bars or hashtag pages, and from Vercel's shared
IPs it gets blocked within minutes. opp.tik.dot uses only official, allowed channels:

| Source | How | Key needed |
|---|---|---|
| **YouTube** | Data API v3 search (+ language/region) → IFrame Player API | `YOUTUBE_API_KEY` |
| **Internet Archive** | Advanced Search + Metadata API (real `year`, `language`) → native MP4 | none |
| **Dailymotion** | Data API search with language filters → official embed | none |
| **TikTok** | Curated URLs → oEmbed → Embed Player | none |
| **Instagram** | Graph API Hashtag Search (30 tags / 7 days) → native video, embed fallback | `META_ACCESS_TOKEN`, `IG_USER_ID` |
| **X** | API v2 recent search `#90s has:videos` → native MP4 | `X_BEARER_TOKEN` (paid tier) |
| **Reddit** | Top posts of r/90s, r/nostalgia, r/2000s... linking to embeddable videos | `REDDIT_CLIENT_ID/SECRET` |
| **Facebook** | Curated URLs → official video plugin | optional `META_ACCESS_TOKEN` |

Nothing is downloaded or re-hosted; views and credit go to the original creators.

## How "nostalgic" is decided

`backend/app/classifier.py` scores every item before it's stored:

- a real year (Archive metadata, or 1940–2009 in the title/description) is the strongest signal
- era words: `90s`, `y2k`, `noughties`, `eighties`…
- nostalgia vocabulary: `throwback`, `vhs`, `retro`, `childhood`…
- the curated query that found it
- penalties for clearly modern content (`2024 reaction`, `tier list`…)

It assigns an **era** (`classic` = before 1990, `90s`, `00s`) and a **category**
plus topics, cultures and channels (see `backend/app/taxonomy.py`). Items under the threshold are dropped.
Change the cut-off year with `MAX_YEAR`.

## Ranking

`backend/app/ranking.py`, documented inline with its sources. Per request: read the user's last
600 events → decayed per-feature affinities (topic, culture, channel, era, source, uploader; 72h
half-life, x2 for the last 45 min) → candidates from four pools (taste, popular, fresh, random) →
score = personal affinity + Thompson-sampled item quality + nostalgia score + length fit − already
seen → MMR re-rank for variety, every 4th slot exploring. The player reports watch time, length,
loops, unmute and rewind per card (`POST /api/events`, batched with `sendBeacon`), and the next page
is ranked with them.

---

## Run locally with Docker

```bash
cp .env.example .env        # fill GOOGLE_CLIENT_ID, SECRET_KEY, ADMIN_EMAILS (+ YOUTUBE_API_KEY)
docker compose up --build
```

Open http://localhost:8080. The `worker` service fills the catalogue on first start (a full crawl
takes a few minutes) and then refreshes every `INGEST_INTERVAL_HOURS`.

No Google client yet? Set `DEV_LOGIN=1` in `.env` for a local-only sign-in button.

### Without Docker

```bash
# API
cd backend && pip install -r requirements.txt -r requirements-dev.txt
export DATABASE_URL=postgresql://opp:opp@localhost:5432/opptik GOOGLE_CLIENT_ID=... SECRET_KEY=...
python wsgi.py                    # http://localhost:5000
python -m app.ingest              # fill the catalogue once

# Web
cd frontend && npm install && npm run dev    # http://localhost:5173 (proxies /api to :5000)
```

Tests: `cd backend && pip install -r requirements-dev.txt && pytest`

## Google sign-in setup

1. Google Cloud Console → APIs & Services → **Credentials** → Create **OAuth client ID** → *Web application*.
2. **Authorized JavaScript origins:** `http://localhost:8080`, `http://localhost:5173`, and your production URL.
3. Put the client ID in `GOOGLE_CLIENT_ID`. The frontend reads it from `/api/meta`, so it's set in one place.

The browser gets a Google ID token, the API verifies it with Google's keys, then issues its own
30-day session in an `HttpOnly` cookie.

## Deploy to Vercel + Neon (one project)

The root `vercel.json` deploys everything as **one Vercel project**: Vite builds `frontend/` into
static files, and `api/index.py` runs the Flask app from `backend/` as a Python function. Every
`/api/*` request goes to Flask; everything else is served by the React app. Same domain, so cookies
just work and no CORS setup is needed. Docker is still there for local dev or container hosts.

1. Create a Neon database and copy the **pooled** connection string.
2. Vercel → *Add New Project* → import the repo. **Root Directory: leave it as the repo root (`./`)**,
   Framework Preset: **Other**. Don't override the build settings; `vercel.json` sets them.
3. Environment variables: `DATABASE_URL`, `SECRET_KEY`, `GOOGLE_CLIENT_ID`, `YOUTUBE_API_KEY`,
   `ADMIN_EMAILS`, `CRON_SECRET`, `COOKIE_SECURE=1`.
4. Deploy, then open `https://<project>.vercel.app/api/health` → `{"ok": true}`.
5. Add the site URL to the Google client's **Authorized JavaScript origins**.
6. Sign in as an admin and press **Run ingest now** (or wait for the daily cron at 04:00 UTC).

Python deps for Vercel come from the root `requirements.txt` (keep it in sync with
`backend/requirements.txt`, which Docker uses). Tables are created on first boot under a Postgres
advisory lock, so parallel cold starts don't collide.

Vercel Hobby allows one cron run per day; on Pro you can change the schedule in `vercel.json`.

## API

| Method | Path | |
|---|---|---|
| POST | `/api/auth/google` | `{credential}` → session cookie |
| GET | `/api/auth/me` · POST `/api/auth/logout` | |
| POST | `/api/feed` `{era, topic, region, channel, source, exclude, seed, limit}` | personalised feed (GET still works) |
| GET | `/api/feed/count?...filters` | number of matching items |
| POST | `/api/events` `{events:[...]}` | watch signals / broken-video reports |
| GET | `/api/search?q=&era=` | catalogue search, falls back to live YouTube/Archive search |
| GET | `/api/items/:id` · POST `/api/items/:id/interact` | `like unlike save unsave view skip hide share` |
| GET | `/api/me/collection?type=like\|save` · PUT `/api/me/prefs` · POST `/api/me/follow` `{source, author, on}` | |
| POST | `/api/admin/links` · `/api/admin/ingest` · `/api/admin/reclassify` · GET `/api/admin/stats` · PATCH `/api/admin/items/:id` | admins |
| GET | `/api/cron/ingest` | `Authorization: Bearer $CRON_SECRET` |

## Project layout

```
backend/app/
  classifier.py   era + category + nostalgia score
  providers/      tiktok.py (oEmbed) · youtube.py · archive.py
  store.py        classify + upsert
  ingest.py       curated seed queries · worker.py loop
  auth.py         Google sign-in, JWT cookie
  routes.py       feed, search, interactions, admin, cron
frontend/src/
  components/     Logo (counter-clockwise watch), FeedScroller, FeedCard, FilterBar…
  pages/          Login, Feed, Search, Profile, ItemPage
```

## Scaling roadmap (v2+)

- Alembic migrations instead of `create_all`
- Redis cache for feed pools and search results; rate limiting on live search
- pgvector embeddings for "more like this" and better era detection
- Move ranking into SQL once the catalogue passes ~100k items
- Moderation queue for curated TikToks; user-submitted suggestions
- PWA install + offline shell

## Fast video (v7): HLS on a CDN

**Why videos were slow:** archive.org serves each MP4 from one storage server in the US, with
no CDN, often at a few hundred KB/s to Lebanon. Vercel is not the cause: video bytes never pass
through Vercel. TikTok / Reels are fast because they stream 2-second chunks from an edge server
near you and start on a low quality, climbing as the connection allows (adaptive bitrate).

v7 does the same for archive clips (public domain / openly licensed, so re-hosting is allowed;
YouTube and TikTok items stay as embeds):

1. `python -m app.transcode` encodes each clip (up to 150 s from its start point) into
   240p / 360p / 540p HLS with 2 s chunks and uploads it to an S3-compatible bucket.
2. The API returns `hls` for those items; the player streams it with hls.js (Safari: natively),
   buffers only the next video's first 2 chunks, and falls back to the archive MP4 on any error.
3. The feed ranks CDN-streamed clips slightly higher, so the first screens start instantly.

### One-time setup (Cloudflare R2, zero egress fees, 10 GB free)
1. Cloudflare dashboard -> R2 -> create bucket `opp-video`.
2. Bucket -> Settings -> Custom domain: connect e.g. `video.yourdomain.com` (needs the domain on
   Cloudflare; the `r2.dev` URL is rate-limited and only for testing). That URL is `CDN_BASE`.
3. Bucket -> Settings -> CORS policy:
   `[{"AllowedOrigins":["https://YOUR-APP.vercel.app","*"],"AllowedMethods":["GET","HEAD"],"AllowedHeaders":["*"],"MaxAgeSeconds":86400}]`
   (replace with your Vercel domain; `*` is fine since the files are public).
4. R2 -> Manage API tokens -> create an Object Read & Write token: gives `S3_KEY`, `S3_SECRET`,
   and the endpoint `https://<account-id>.r2.cloudflarestorage.com` = `S3_ENDPOINT`.
5. GitHub repo -> Settings -> Secrets -> Actions: add those + `DATABASE_URL` (Neon).
6. Actions tab -> `transcode` -> Run workflow (limit 40). It then runs daily by itself.

Rough size: ~25 MB per 150 s clip for all three rungs, so 400 clips ~ 10 GB (R2's free tier).
