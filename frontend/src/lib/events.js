// Watch events for the ranker. Batched, and sent with sendBeacon so they survive tab closes.
import { BASE } from '../api.js'

const queue = []
let timer = null

export function track(ev) {
  queue.push(ev)
  clearTimeout(timer)
  if (queue.length >= 6) flush()
  else timer = setTimeout(flush, 4000)
}

// `wait`: resolve once the server has the events (used right before asking for the next page,
// so the ranking already knows about the video you just watched).
export function flush({ wait = false } = {}) {
  clearTimeout(timer)
  if (!queue.length) return Promise.resolve()
  const body = JSON.stringify({ events: queue.splice(0) })
  const url = BASE + '/events'
  if (!wait && navigator.sendBeacon) {
    try {
      if (navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }))) return Promise.resolve()
    } catch { /* fall through */ }
  }
  return fetch(url, { method: 'POST', body, credentials: 'include', keepalive: true,
    headers: { 'Content-Type': 'application/json' } }).catch(() => {})
}

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => flush())
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush() })
}
