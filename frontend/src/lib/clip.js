// v9 "Snack mode": every video plays as a short clip of its best part.
//
// Why: on a slow link, the time to the first frame matters, and so does how much the
// phone downloads per video. A 30-second clip at 240p is ~1 MB instead of 5-15 MB for
// the whole video, the player only buffers what it needs, and the feed keeps moving:
// when the clip ends, the next video slides in by itself (like Reels / TikTok "auto scroll").
// "Watch full" on any clip lifts the limit for that one video.
//
// The viewer picks 30s / 1 min / 2 min / Full (chip in the top bar, ⋯ menu, Profile).

import { useSyncExternalStore } from 'react'

const KEY = 'opp.clip.v1'
export const LENGTHS = [
  { id: 30, label: '30s', hint: 'Fastest, lightest' },
  { id: 60, label: '1 min', hint: 'Short clips' },
  { id: 120, label: '2 min', hint: 'Longer clips' },
  { id: 0, label: 'Full', hint: 'Whole videos' },
]

let len = 30
try {
  const s = localStorage.getItem(KEY)
  if (s != null && LENGTHS.some((l) => String(l.id) === s)) len = Number(s)
} catch { /* storage blocked */ }

const subs = new Set()
export function getClipLength() { return len }
export function setClipLength(v) {
  const n = Number(v)
  if (!LENGTHS.some((l) => l.id === n) || n === len) return
  len = n
  try { localStorage.setItem(KEY, String(n)) } catch { /* ignore */ }
  subs.forEach((fn) => { try { fn() } catch { /* listener error */ } })
}
export function nextClipLength() {
  const i = LENGTHS.findIndex((l) => l.id === len)
  setClipLength(LENGTHS[(i + 1) % LENGTHS.length].id)
}
export const clipLabel = (n) => LENGTHS.find((l) => l.id === n)?.label || 'Full'
const subscribe = (fn) => { subs.add(fn); return () => subs.delete(fn) }
export function useClipLength() { return useSyncExternalStore(subscribe, () => len) }

/*
 * v11: a hosted clip (item.clip = {url, s, from, whole}) is a small 240p file of the video's best
 * `s` seconds, made by backend/app/clips.py and served by Cloudflare Pages (free, unlimited
 * bandwidth, close to Lebanon). It is used whenever the chosen length fits inside it (30 s and
 * 1 min by default), or when it already contains the whole video. Longer lengths and "Watch
 * full" play the original, from the same spot. If the hosted file ever fails, the player uses the
 * original instead.
 */
export function hostedWindow(item, length) {
  const c = item?.clip
  if (!c?.url || !c.s) return null
  const fits = length && length <= c.s + 1
  if (!fits && !c.whole) return null
  const whole = Boolean(c.whole && (!length || length >= c.s - 1))
  return { from: 0, to: length ? Math.min(length, c.s) : null, hosted: true, whole }
}

const MUSIC = new Set(['music', 'music_videos', 'musicvideo'])

/*
 * Which part of a video to play: { from, to } in the video's own seconds, or null
 * (play it whole and loop, like a normal short).
 *
 *  - Videos only a little longer than the clip play whole (cutting 35s to 30s is silly).
 *  - Music videos jump to ~a quarter in, where the first chorus usually is.
 *  - Long films / compilations keep the server's start point (past the logos and leader).
 *  - Everything else skips a short intro.
 *  - HLS copies on the CDN are already cut at their start point, so they start at 0.
 */
export function clipWindow(item, length) {
  if (!item || !length || item.kind === 'image') return null
  if (item.source === 'tiktok' || item.source === 'instagram' || item.source === 'x') return null   // already short
  const d = item.duration || 0
  if (d && d <= length * 1.25) return null
  let from
  if (item.hls) from = 0
  else if (item.start) from = item.start
  else if (!d) from = 0
  else if (item.topics?.some((t) => MUSIC.has(t.id)) || MUSIC.has(item.category)) from = Math.min(d * 0.26, 80)
  else from = d > 90 ? Math.min(d * 0.08, 20) : 0
  from = Math.max(0, Math.floor(d ? Math.min(from, d - length) : from))
  return { from, to: from + length }
}
