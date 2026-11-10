// opp.tik.dot service worker: free caching on the viewer's own phone.
//
//  - App files (/assets/*, hashed by Vite)   -> cache-first, forever. Second visit opens instantly.
//  - Thumbnails (/thumb/*)                   -> served from cache, refreshed in the background.
//  - Video chunks from our CDN (.m3u8 / .ts) -> cache-first. Swiping back, looping or re-opening
//                                               a video costs zero data and starts instantly.
//  - The page itself                         -> network first, cached copy if offline.
// Never touches /api, /media (archive MP4 byte ranges) or third-party embeds.

const V = 'v1'
const SHELL = `shell-${V}`, ASSETS = `assets-${V}`, THUMBS = `thumbs-${V}`, VIDEO = `video-${V}`
const LIMIT = { [THUMBS]: 400, [VIDEO]: 300 }   // ~300 chunks ~ 30-60 MB at most

self.addEventListener('install', (e) => {
  self.skipWaiting()
  e.waitUntil(caches.open(SHELL).then((c) => c.add('/')).catch(() => {}))
})

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keep = new Set([SHELL, ASSETS, THUMBS, VIDEO])
    for (const k of await caches.keys()) if (!keep.has(k)) await caches.delete(k)
    await self.clients.claim()
  })())
})

async function trim(name) {
  const max = LIMIT[name]
  if (!max) return
  const c = await caches.open(name)
  const keys = await c.keys()
  for (let i = 0; i < keys.length - max; i++) await c.delete(keys[i])   // oldest first
}

const okToStore = (r) => r && r.status === 200 && r.type !== 'opaque'

async function cacheFirst(req, name) {
  const c = await caches.open(name)
  const hit = await c.match(req)
  if (hit) return hit
  const res = await fetch(req)
  if (okToStore(res)) c.put(req, res.clone()).then(() => trim(name)).catch(() => {})
  return res
}

async function staleWhileRevalidate(req, name, ev) {
  const c = await caches.open(name)
  const hit = await c.match(req)
  const net = fetch(req).then((res) => {
    if (okToStore(res)) c.put(req, res.clone()).then(() => trim(name)).catch(() => {})
    return res
  })
  if (hit) { ev.waitUntil(net.catch(() => {})); return hit }
  return net
}

async function networkFirstPage(req) {
  try {
    const res = await fetch(req)
    if (okToStore(res)) caches.open(SHELL).then((c) => c.put('/', res.clone())).catch(() => {})
    return res
  } catch {
    return (await caches.match('/')) || Response.error()
  }
}

self.addEventListener('fetch', (e) => {
  const req = e.request
  if (req.method !== 'GET' || req.headers.has('range')) return
  const url = new URL(req.url)
  const same = url.origin === self.location.origin

  if (same && (url.pathname.startsWith('/api/') || url.pathname.startsWith('/media/'))) return
  if (req.mode === 'navigate') { e.respondWith(networkFirstPage(req)); return }
  if (same && url.pathname.startsWith('/assets/')) { e.respondWith(cacheFirst(req, ASSETS)); return }
  if (same && url.pathname.startsWith('/thumb/')) { e.respondWith(staleWhileRevalidate(req, THUMBS, e)); return }
  if (!same && /\.(m3u8|ts|m4s)$/.test(url.pathname)) { e.respondWith(cacheFirst(req, VIDEO)); return }
})
