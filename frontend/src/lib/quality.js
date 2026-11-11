// Playback quality engine (v12).
//
// The viewer picks one of three modes (Profile, or the ⋯ menu on any video):
//
//   Data saver  144p, always. The tiny 144p hosted clip, the smallest Archive file, and
//               YouTube's player box shrunk so its automatic quality stays as low as it allows.
//   Auto        240p or higher. Starts at 240p (the hosted 240p clip, which starts fastest),
//               steps up to 360p / 480p / 720p after a run of instant starts, and back down
//               after slow starts or stalls. Never below 240p.
//   HD          480p or higher. Starts at 480p, steps up to 720p when starts are instant.
//               Never below 480p.
//
// Short-video apps don't wait for the network to say how fast it is: they measure every start
// and every stall and adjust the *next* video before it loads. Auto and HD do the same.

import { useSyncExternalStore } from 'react'
import { isSlow, onNetworkChange } from './network.js'

const KEY = 'opp.quality.v1'
export const MODES = [
  { id: 'saver', label: 'Data saver', hint: '144p · starts fastest' },
  { id: 'auto', label: 'Auto', hint: '240p or higher' },
  { id: 'hd', label: 'HD', hint: '480p or higher' },
]
export const LADDER = [144, 240, 360, 480, 720]
const RANGE = { saver: [0, 0], auto: [1, 4], hd: [3, 4] }   // indexes into LADDER

let mode = 'auto'
try { mode = localStorage.getItem(KEY) || 'auto' } catch { /* storage blocked */ }
if (!MODES.some((m) => m.id === mode)) mode = 'auto'

const starts = []       // ms from "this video is on screen" to its first frame
const stalls = []       // timestamps of rebuffering events
let bias = 0            // learned from starts and stalls, in ladder steps
const subs = new Set()
const emit = () => subs.forEach((fn) => { try { fn() } catch { /* listener error */ } })

const conn = () => (typeof navigator !== 'undefined' ? navigator.connection || navigator.mozConnection || navigator.webkitConnection : null)

// Where Auto / HD start. Most viewers are in Lebanon / the Middle East: Auto starts at 240p
// (fastest first frame) unless the browser measures a genuinely fast link.
function startLevel() {
  const [lo, hi] = RANGE[mode]
  if (lo === hi) return lo
  const c = conn()
  const fast = c && !isSlow() && c.downlink >= 10 && !/3g/.test(c.effectiveType || '')
  return Math.min(hi, lo + (fast ? 1 : 0))
}

function level() {
  const [lo, hi] = RANGE[mode]
  return Math.max(lo, Math.min(hi, startLevel() + bias))
}

export function getMode() { return mode }
export function setMode(m) {
  if (!MODES.some((x) => x.id === m) || m === mode) return
  mode = m
  bias = 0
  starts.length = 0
  stalls.length = 0
  try { localStorage.setItem(KEY, m) } catch { /* ignore */ }
  emit()
}

/** Target height in pixels for the next video. */
export function height() { return LADDER[level()] }
/** Lowest height the current mode allows (144 / 240 / 480). */
export function floor() { return LADDER[RANGE[mode][0]] }

// Preloading plan, and the value the feed API ranks with ('low' leans on fast sources harder).
export function tier() {
  const h = height()
  return h <= 144 ? 'low' : h <= 360 ? 'mid' : 'high'
}

function relearn() {
  const now = Date.now()
  while (stalls.length && now - stalls[0] > 45000) stalls.shift()
  const recent = starts.slice(-4)
  const avg = recent.reduce((a, b) => a + b, 0) / (recent.length || 1)
  const before = level()
  const [lo, hi] = RANGE[mode]
  const s = startLevel()
  if (stalls.length >= 2 || (recent.length >= 2 && avg > 3000)) {
    bias = Math.max(lo - s, bias - 1)
    stalls.length = 0
    starts.length = 0
  } else if (recent.length >= 4 && avg < 900 && !stalls.length) {
    bias = Math.min(hi - s, bias + 1)
    starts.length = 0
  }
  if (level() !== before) emit()
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

// How hard to pre-load. 'low' = Data saver: the next video gets its first bytes only, and only
// once yours is playing. Higher: the next one is fully buffered (two of them on fast links).
export const PLAN = {
  low: { warmFull: false, ahead: 1 },
  mid: { warmFull: true, ahead: 1 },
  high: { warmFull: true, ahead: 2 },
}

// Height of an Archive file: stored by the server, else guessed from its bitrate.
const hOf = (r) => r.h || (r.kbps == null ? 480 : r.kbps <= 350 ? 240 : r.kbps <= 900 ? 360 : r.kbps <= 1700 ? 480 : 720)

// Pick the Archive file for a target height (renditions come lowest bitrate first): the biggest
// one not above the target; if every file is bigger, the smallest. HD: at least 480p when there is one.
export function pickRendition(list, h = 240, min = 0) {
  if (!list?.length) return 0
  let best = -1
  list.forEach((r, i) => { if (hOf(r) <= h) best = i })
  if (best < 0) best = 0
  if (min >= 480 && hOf(list[best]) < min) {
    const up = list.findIndex((r) => hOf(r) >= min)
    if (up >= 0) best = up
  }
  return best
}
// Lowest file index a mode may step down to after stalls (never below the mode's floor).
export function lowestRendition(list, min = 0) {
  if (!list?.length || min <= 144) return 0
  const i = list.findIndex((r) => hOf(r) >= min)
  return i < 0 ? list.length - 1 : i
}

// YouTube doesn't let a site choose quality (setPlaybackQuality is a no-op now). Its automatic
// quality, though, never goes above what the player box can show, so the player is rendered
// at the width of the target quality and scaled up to fill the screen. YouTube needs at least
// 200x200 CSS px, which bounds how low this can go on large phones. null = uncapped.
const YT_WIDTH = { 144: 256, 240: 426, 360: 640, 480: 854, 720: 1280 }
export function ytCap(h, m) {
  if (m === 'hd' && h >= 720) return null
  return YT_WIDTH[h] || null
}

// Dailymotion's player does take a quality.
export function dmQuality(h) {
  return h <= 144 ? '144' : h <= 240 ? '240' : h <= 360 ? '380' : h <= 480 ? '480' : '720'
}

// Opening the TCP+TLS connection to a video server ahead of time saves 1-3 round trips
// on the first byte of the next video.
const warmed = new Set()
export function preconnect(url) {
  try {
    const origin = new URL(url, location.href).origin
    if (origin === location.origin || warmed.has(origin)) return
    warmed.add(origin)
    const l = document.createElement('link')
    l.rel = 'preconnect'
    l.href = origin
    document.head.appendChild(l)
  } catch { /* bad url */ }
}

// React: re-render when the mode or the target height changes.
export function useQuality() {
  const t = useSyncExternalStore(subscribe, () => `${mode}:${level()}`)
  const m = t.split(':')[0]
  const h = LADDER[Number(t.split(':')[1])]
  return { mode: m, h, min: LADDER[RANGE[m][0]], tier: h <= 144 ? 'low' : h <= 360 ? 'mid' : 'high' }
}

export const qualityLabel = (m, h) => (m === 'saver' ? 'Data saver · 144p' : m === 'hd' ? `HD · ${h}p` : `Auto · ${h}p`)

// Archive.org files go through our own Vercel project (vercel.json rewrite /media/<server>/...),
// which keeps a copy at the edge after the first viewer. If that ever fails, the player falls
// back to the direct archive.org link by itself.
export function viaEdge(url) {
  try {
    const u = new URL(url)
    if (/^ia\d+\.us\.archive\.org$/.test(u.hostname) && location.protocol.startsWith('http') && !/localhost|127\./.test(location.hostname))
      return `/media/${u.hostname}${u.pathname}${u.search}`
  } catch { /* relative or bad url */ }
  return url
}
