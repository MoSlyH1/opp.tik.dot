# opp.tik.dot

**The feed, rewound.** A TikTok-style vertical feed filtered down to nostalgia: movies, music videos,
style, ads, TV, tech and games from the '90s, the 2000s and before. Swipe forward like TikTok, or flip
on **Rewind** and the whole feed runs the opposite direction.

- React (Vite) frontend · Flask API · PostgreSQL
- Google sign-in only
- Docker for local/self-hosting, Vercel + Neon for serverless hosting (one project)
- Works on phone and desktop (snap-scroll on touch, arrow keys / `j` `k` / buttons on desktop, `m` to mute)

---

## What's new in v12 — quality you choose, Dailymotion fixed, no Cloudflare, logo loading card

**Quality modes** (⋯ menu on any video, or Profile):

| Mode | Plays | Archive | YouTube | Dailymotion |
|---|---|---|---|---|
| **Data saver** | 144p | 144p hosted clip, else the smallest file | player shrunk to the 144p width | 144p |
| **Auto** | 240p or higher | 240p hosted clip (fastest start), else 240p → 720p file | 240p width, grows to 360/480/720p after instant starts | 240p → 720p |
| **HD** | 480p or higher | original file, 480p or more | 480p width, uncapped at the top | 480p → 720p |

Auto starts at 240p, moves up one step after four instant starts in a row and back down after
slow starts or two stalls, and never goes below 240p. HD never goes below 480p.
YouTube doesn't let any site *force* a quality: the app caps it by the size of the player, which
YouTube respects, but YouTube itself may still pick lower on a very bad connection.

**Dailymotion plays again.** Dailymotion retired the old embed address
(`www.dailymotion.com/embed/video/...`) in September 2025: it now redirects to a new player and
ignores the old settings, so those videos stopped loading. v12 uses Dailymotion's official Player
Library (`geo.dailymotion.com`), pooled per card like YouTube (one player per slot, reused, the next
one warmed up before you swipe), with real play / time / error events so the feed knows when it
actually starts. If an ad blocker stops the library, the plain new-style embed plays instead.
Optional: `DM_PLAYER_ID` (a Player you create in Dailymotion Studio -> Players) to choose your own
player settings, such as no controls or no ads.

**Cloudflare removed.** `cdn-worker/`, `edge-worker/`, the R2 / HLS transcode job, hls.js
(~90 KB less to download), `MEDIA_BASE` and `CDN_BASE` are gone. You can delete those variables from
Vercel. Archive files still go through Vercel's own edge cache (`/media`), as before.

**Hosted clips now on GitHub Pages** (free, no new account). Same `clips` branch and the same
GitHub Action, which now makes two files per video: `c/<id>.mp4` (240p, ~0.6 MB, for Auto) and
`c/<id>-144.mp4` (144p, ~0.35 MB, for Data saver). Clips made by v11 keep working; the Action only
adds the missing 144p file. GitHub Pages sites must stay under 1 GB, so the Action stops at
`CLIPS_MAX_MB` (950) and gives clips to the most-watched videos first (roughly 800-900 videos).
GitHub Pages is free for **public** repos (a private repo needs GitHub Pro).

Setup, once (5 minutes):
1. GitHub repo -> Settings -> Secrets and variables -> Actions: `DATABASE_URL` = your Neon link (if not there yet).
2. Actions -> **clips** -> Run workflow (limit 300). The first run creates / updates the `clips` branch.
3. Settings -> **Pages** -> Source: *Deploy from a branch* -> branch **`clips`**, folder **/ (root)** -> Save.
   After a minute it shows the address: `https://<your-user>.github.io/<repo>/`.
4. Vercel -> Settings -> Environment Variables -> `CLIPS_BASE` = that address **without** the last slash,
   e.g. `https://moslyh1.github.io/opp.tik.dot` -> redeploy.
5. Check: open `CLIPS_BASE/c/<a number>.mp4` (any file on the `clips` branch): it should play.

If you had connected Cloudflare Pages in v11, you can delete that Cloudflare project.

**Loading card with your logo.** If a video takes more than about a second to start, its card
shows the thumbnail, your logo turning in the middle, the year and title, and a small
**Sponsored** box at the bottom. It disappears the moment the video plays. Your logo is also the
loading sign everywhere else (app start, mid-video buffering, loading more, search, refresh).
It's inlined in the app (~2.5 KB), so it never waits for a download. Fill the Sponsored box from
Vercel environment variables, no rebuild needed:
`SPONSOR_TITLE`, `SPONSOR_TEXT`, `SPONSOR_URL` (https), `SPONSOR_IMAGE` (https, square).
Empty = a house ad for opp.tik.dot with your logo. For an ad network later, render its unit in
`frontend/src/components/Sponsor.jsx`.

**Sound on from the second video.** The first swipe, arrow or key press turns sound on (unless you muted it yourself with the sound button). If the browser refuses sound without a tap, the video plays muted and shows "Tap for sound".

**Faster start, less waste**
- Every API call used to wait for `/api/meta` (up to 3 s on a cold start) before it could finish,
  including the first page of the feed. Not any more.
- The phone no longer stores video chunks (the old cache is deleted on the next visit).
- Preconnects to Dailymotion and to the clips host, so the first byte comes sooner.

Files: `frontend/src/lib/quality.js` (rewritten), `components/players/Player.jsx` (Dailymotion engine,
quality picks, no HLS), `embed.js`, `lib/clip.js`, `components/FeedCard.jsx`, `LoadingLogo.jsx`,
`Sponsor.jsx`, `brand.js`, `api.js`, `boot.js`, `Pager.jsx`, `public/sw.js`, `styles.css`;
`backend/app/clips.py`, `models.py`, `routes.py`, `config.py`, `.github/workflows/clips.yml`.

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

