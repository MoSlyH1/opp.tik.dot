// v7: adaptive streaming for clips we host on the CDN.
// hls.js light build (~95 KB gz: no subtitles/DRM, which we don't use) is loaded only when the first HLS video is near the screen.
// Safari / iOS without MSE play HLS natively, so they never download it.

let mod = null
export function loadHls() {
  mod ||= import('hls.js/dist/hls.light.mjs').then((m) => m.default)
  return mod
}

let mode = null
export function hlsMode() {
  if (mode) return mode
  const ms = typeof window !== 'undefined' && (window.ManagedMediaSource || window.MediaSource)
  const ok = ms && typeof ms.isTypeSupported === 'function' && ms.isTypeSupported('video/mp4; codecs="avc1.4d401e,mp4a.40.2"')
  mode = ok ? 'mse' : 'native'
  if (mode === 'mse') loadHls()   // warm the chunk early
  return mode
}

// Bandwidth guess (bits/s) for the first chunk, per tier; hls.js measures from there.
export const HLS_EST = { low: 300_000, mid: 900_000, high: 2_500_000 }
