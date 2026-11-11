// Start-up in parallel instead of in series.
//
// v5 booted as a chain: JS -> /api/meta -> render -> /api/auth/me -> Feed -> /api/feed ->
// YouTube API script -> first player. On Vercel each API hop can be a cold Python start.
// Now everything that doesn't depend on something else is requested the moment the JS
// runs: meta, the session, the first page of the feed (with the filters you used last
// time) and the YouTube player API. The first card can start loading while React is
// still rendering the shell.
import { api } from '../api.js'
import { loadYouTube } from '../embed.js'
import { getClipLength } from './clip.js'
import { tier } from './quality.js'
import { setDmPlayer } from '../embed.js'

const FILTER_KEY = 'opp.filters.v4'
const DIMS = ['era', 'topic', 'region', 'channel', 'source']

export const normFilters = (f) => JSON.stringify(DIMS.map((d) => [...(f?.[d] || [])].sort()))

const seed = Math.random().toString(36).slice(2, 10)
let saved = null
try { saved = JSON.parse(localStorage.getItem(FILTER_KEY)) } catch { /* storage blocked */ }
const filters = Object.fromEntries(DIMS.map((d) => [d, Array.isArray(saved?.[d]) ? saved[d] : []]))

export const boot = {
  meta: api.meta().then((m) => { setDmPlayer(m?.dm_player); return m }).catch(() => ({ offline: true })),
  me: api.me().catch(() => ({ user: null })),
  // 401 when signed out: harmless, it's just not used.
  feed: { key: saved ? normFilters(filters) : null, seed, used: false,
    promise: saved ? api.feed({ ...filters, exclude: [], seed, limit: 6, len: getClipLength(), tier: tier() }).catch(() => null) : Promise.resolve(null) },
}

loadYouTube().catch(() => {})

// The prefetched first page, if it was asked with the same filters. One use only.
export function takeFirstFeed(f) {
  const b = boot.feed
  if (b.used || !b.key || b.key !== normFilters(f)) return null
  b.used = true
  return b.promise.then((r) => (r && Array.isArray(r.items) ? { ...r, seed: b.seed } : null))
}
