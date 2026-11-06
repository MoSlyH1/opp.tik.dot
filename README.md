# opp.tik.dot

**The feed, rewound.** A TikTok-style vertical feed filtered down to nostalgia: movies, music videos,
style, ads, TV, tech and games from the '90s, the 2000s and before. Swipe forward like TikTok, or flip
on **Rewind** and the whole feed runs the opposite direction.

- React (Vite) frontend · Flask API · PostgreSQL
- Google sign-in only
- Docker for local/self-hosting, Vercel + Neon for serverless hosting (one project)
- Works on phone and desktop (snap-scroll on touch, arrow keys / `j` `k` / buttons on desktop, `m` to mute)

---

## Where the content comes from (read this first)

TikTok has **no public API for the For You feed or for search**, and scraping the app breaks its
Terms of Service and gets blocked fast. So opp.tik.dot uses only official, allowed channels:

| Source | How | Key needed |
|---|---|---|
| **TikTok** | Curated video URLs → official oEmbed (title, author, thumbnail) → official Embed Player | none |
| **YouTube** | YouTube Data API v3 search → official embed | `YOUTUBE_API_KEY` |
| **Internet Archive** | Advanced Search API (real period footage with a real `year`) → official embed | none |

Nothing is downloaded or re-hosted; every video plays inside its platform's own player, so views and
credit go to the original creators.

**Adding TikToks:** sign in with an email listed in `ADMIN_EMAILS`, open **Profile → Curator**, paste
TikTok URLs (e.g. from #90s, #y2k, #throwback creators). Or put them in `backend/tiktok_seeds.txt`.
If TikTok later grants you the Research API or Display API, add a fetcher in
`backend/app/providers/tiktok.py` that returns the same dict shape; nothing else changes.

Instagram, Facebook and X don't offer search/feed APIs for this use either (their oEmbed endpoints
need a Meta/X app token). They can be added the same way as TikTok: curated URL → official embed.

## How "nostalgic" is decided

`backend/app/classifier.py` scores every item before it's stored:

- a real year (Archive metadata, or 1940–2009 in the title/description) is the strongest signal
- era words: `90s`, `y2k`, `noughties`, `eighties`…
- nostalgia vocabulary: `throwback`, `vhs`, `retro`, `childhood`…
- the curated query that found it
- penalties for clearly modern content (`2024 reaction`, `tier list`…)

It assigns an **era** (`classic` = before 1990, `90s`, `00s`) and a **category**
(movies, music, style, tv, ads, tech, games, culture). Items under the threshold are dropped.
Change the cut-off year with `MAX_YEAR`.

## Ranking

`GET /api/feed` takes a pool of the best 600 matching items and re-ranks them per user:
quality score + popularity + your taste (likes, saves, shares up; skips and "not interested" down)
− already watched + a per-session shuffle. Paging is stable within a session (`seed` + `cursor`).

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
| GET | `/api/feed?era=90s,00s&category=music&cursor=&seed=` | personalised feed |
| GET | `/api/search?q=&era=` | catalogue search, falls back to live YouTube/Archive search |
| GET | `/api/items/:id` · POST `/api/items/:id/interact` | `like unlike save unsave view skip hide share` |
| GET | `/api/me/collection?type=like\|save` · PUT `/api/me/prefs` | |
| POST | `/api/admin/tiktok` · `/api/admin/ingest` · GET `/api/admin/stats` · PATCH `/api/admin/items/:id` | admins |
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
