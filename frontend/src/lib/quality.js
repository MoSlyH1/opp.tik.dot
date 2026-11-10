// Playback quality engine.
//
// Short-video apps don't wait for the network to tell them how fast it is: they measure
// every start and every stall and adjust the *next* video before it loads. This does
// the same for the web, in three tiers:
//
//   low  - data saver: smallest Archive file (~240p), YouTube player box capped at ~240p,
//          only the next video's first bytes are fetched, and only once yours is playing.
//   mid  - ~480p files, YouTube capped at ~480p, the next video fully pre-buffered.
//   high - best file, YouTube uncapped, the next two videos warmed up.
//
// The viewer picks Auto / Data saver / HD (Profile, or the ⋯ menu on any video).
// Auto starts from the Network Information API where the browser has it (Chrome,
// Android), else from the device type (Safari has no such API), then moves one tier
// down after slow starts or repeated stalls and one tier up after a run of instant starts.

import { useSyncExternalStore } from 'react'
import { isSlow, onNetworkChange } from './network.js'

const KEY = 'opp.quality.v1'
export const MODES = [
  { id: 'auto', label: 'Auto', hint: 'Adjusts to your connection' },
  { id: 'saver', label: 'Data saver', hint: 'Lowest quality, starts fastest' },
  { id: 'hd', label: 'HD', hint: 'Best quality, needs fast internet' },
]
const TIERS = ['low', 'mid', 'high']
export const TIER_LABEL = { low: '240p', mid: '480p', high: 'HD' }

let mode = 'auto'
try { mode = localStorage.getItem(KEY) || 'auto' } catch { /* storage blocked */ }
if (!MODES.some((m) => m.id === mode)) mode = 'auto'

const starts = []       // ms from "this video is on screen" to its first frame
const stalls = []       // timestamps of rebuffering events
let bias = 0            // -2..+1, learned from starts and stalls
const subs = new Set()
const emit = () => subs.forEach((fn) => { try { fn() } catch { /* listener error */ } })

const conn = () => (typeof navigator !== 'undefined' ? navigator.connection || navigator.mozConnection || navigator.webkitConnection : null)
const touch = () => typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches

// Most viewers are in Lebanon / the Middle East, where international bandwidth is scarce and
// mobile data is metered: start one tier lower than elsewhere, and only go HD when the
// browser measures a genuinely fast link. Europe / UK / US viewers keep the normal start.
const tz = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || '' } catch { return '' } })()
const MENA = /^(Asia\/(Beirut|Damascus|Amman|Baghdad|Riyadh|Dubai|Kuwait|Qatar|Bahrain|Muscat|Aden|Gaza|Hebron|Tehran)|Africa\/(Cairo|Tripoli|Tunis|Algiers|Casablanca)|Europe\/Istanbul|Asia\/Nicosia)$/.test(tz)

function base() {
  const c = conn()
  if (c) {
    if (isSlow()) return 0
    if (c.downlink && c.downlink >= (MENA ? 10 : 6) && !/3g/.test(c.effectiveType || '')) return 2
    return MENA && c.downlink && c.downlink < 3 ? 0 : 1
  }
  // Safari/iOS has no connection API: assume mid on phones, and mid (not HD) in the region.
  return touch() || MENA ? 1 : 2
}

export function getMode() { return mode }
export function setMode(m) {
  if (!MODES.some((x) => x.id === m) || m === mode) return
  mode = m
  bias = 0
  try { localStorage.setItem(KEY, m) } catch { /* ignore */ }
  emit()
}

export function tier() {
  if (mode === 'saver') return 'low'
  if (mode === 'hd') return 'high'
  return TIERS[Math.max(0, Math.min(2, base() + bias))]
}

function relearn() {
  const now = Date.now()
  while (stalls.length && now - stalls[0] > 45000) stalls.shift()
  const recent = starts.slice(-4)
  const avg = recent.reduce((a, b) => a + b, 0) / (recent.length || 1)
  const before = tier()
  if (stalls.length >= 2 || (recent.length >= 2 && avg > 3200)) {
    bias = Math.max(-2, bias - 1)
    stalls.length = 0
    starts.length = 0
  } else if (recent.length >= 4 && avg < 900 && !stalls.length) {
    bias = Math.min(1, bias + 1)
    starts.length = 0
  }
  if (tier() !== before) emit()
}

// A video reached its first frame `ms` after it became the one on screen.
export function reportStart(ms) {
  if (!Number.isFinite(ms) || ms < 0 || ms > 60000) return
  starts.push(ms)
  if (starts.length > 8) starts.shift()
  relearn()
}

// The video on screen ran out of buffer.
export function reportStall() {
  stalls.push(Date.now())
  relearn()
}

export function subscribe(fn) {
  subs.add(fn)
  return () => subs.delete(fn)
}

onNetworkChange(() => emit())

// How hard to pre-load for a tier.
export const PLAN = {
  low: { warmFull: false, ahead: 1 },   // next video: first bytes only, after yours plays
  mid: { warmFull: true, ahead: 1 },    // next video fully buffered
  high: { warmFull: true, ahead: 2 },   // next two
}

// Pick the Archive file for a tier (renditions come lowest bitrate first).
export function pickRendition(list, t) {
  if (!list?.length) return 0
  if (t === 'low') return 0
  if (t === 'high') return list.length - 1
  let best = 0
  list.forEach((r, i) => { if (r.kbps == null || r.kbps <= 1400) best = i })
  return best
}

// YouTube doesn't let a site choose quality (setPlaybackQuality is a no-op now). Its
// automatic quality, though, never goes above what the player box can show, so on
// slower tiers the player is rendered smaller and scaled up to fill the screen.
// YouTube needs at least 200x200 CSS px, which bounds how low this can go.
export const YT_CAP = { low: 426, mid: 854, high: null }

// Opening the TCP+TLS connection to a video server ahead of time saves 1-3 round trips
// on the first byte of the next video.
const warmed = new Set()
export function preconnect(url, cors = false) {
  try {
    const origin = new URL(url).origin
    if (warmed.has(origin + cors)) return
    warmed.add(origin + cors)
    const l = document.createElement('link')
    l.rel = 'preconnect'
    l.href = origin   // plain <video> uses the credentialed pool; hls.js fetches with CORS
    if (cors) l.crossOrigin = 'anonymous'
    document.head.appendChild(l)
  } catch { /* bad url */ }
}

// React: re-render when the tier or the mode changes.
export function useQuality() {
  const t = useSyncExternalStore(subscribe, () => `${mode}:${tier()}`)
  const [m, tr] = t.split(':')
  return { mode: m, tier: tr }
}

// v7: archive.org has no CDN (one US server, slow to the Middle East). Our own Vercel
// project proxies and edge-caches those files (vercel.json rewrite /media/<node>/...), so
// after the first viewer anywhere in the region, everyone gets them from a nearby edge.
// If the proxy ever fails, the player falls back to the direct archive.org link.
// v10: with MEDIA_BASE set (the free Cloudflare Worker in edge-worker/) the same paths are
// served from Cloudflare's edge, which keeps a copy of every file; otherwise from our Vercel project.
let mediaBase = ''
let markReady
// Resolves once /api/meta has told us the edge address (or after 3 s), so the first feed page
// already gets its thumbnails from the right place.
export const mediaReady = Promise.race([new Promise((r) => { markReady = r }), new Promise((r) => setTimeout(r, 3000))])
export const setMediaBase = (b) => { mediaBase = typeof b === 'string' && b.startsWith('https://') ? b.replace(/\/$/, '') : ''; markReady?.() }
export const getMediaBase = () => mediaBase
export function viaEdge(url) {
  try {
    const u = new URL(url)
    if (/^ia\d+\.us\.archive\.org$/.test(u.hostname) && location.protocol.startsWith('http') && !/localhost|127\./.test(location.hostname))
      return `${mediaBase}/media/${u.hostname}${u.pathname}${u.search}`
  } catch { /* relative or bad url */ }
  return url
}
