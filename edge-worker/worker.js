// opp.tik.dot edge cache: a free Cloudflare Worker in front of archive.org. No bucket, no keys,
// no domain, no GitHub secrets, and no 10 GB limit: it stores nothing itself, it just makes
// Cloudflare's CDN keep a copy of each file you stream (cacheEverything).
//
// Why it helps: archive.org serves every file from one server in the US, slowly to Lebanon.
// With this Worker, the first viewer's request goes archive.org -> Cloudflare (datacenter to
// datacenter, fast) -> the viewer; from then on that file is served from a Cloudflare server
// near the viewers. Free: 100,000 requests/day (a video is a handful of requests).
//
// Setup (about 3 minutes, dashboard only):
//   Cloudflare -> Workers & Pages -> Create -> "Hello World" -> name it opp-edge -> Deploy
//   -> Edit code -> paste this whole file -> Deploy.
//   Copy the address (https://opp-edge.<you>.workers.dev) into Vercel as MEDIA_BASE, redeploy.

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
  'Access-Control-Allow-Headers': 'Range',
  'Access-Control-Expose-Headers': 'Content-Length, Content-Range, Accept-Ranges',
  'Access-Control-Max-Age': '86400',
}
const NODE = /^(ia|dn)\d+\.us\.archive\.org$/           // archive.org storage servers only: not an open proxy
const ID = /^[A-Za-z0-9._-]+$/
const YEAR = 31536000

export default {
  async fetch(request) {
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS })
    if (request.method !== 'GET' && request.method !== 'HEAD') return new Response('Method not allowed', { status: 405, headers: CORS })

    const path = new URL(request.url).pathname
    let upstream = null
    let m = path.match(/^\/media\/([^/]+)(\/.+)$/)                  // /media/<node>/<path>
    if (m && NODE.test(m[1]) && !m[2].includes('..')) upstream = `https://${m[1]}${m[2]}${new URL(request.url).search}`
    m = path.match(/^\/thumb\/([^/]+)$/)                           // /thumb/<archive id>
    if (m && ID.test(m[1])) upstream = `https://archive.org/services/img/${m[1]}`
    if (!upstream) return new Response('Not found', { status: 404, headers: CORS })

    const headers = new Headers()
    const range = request.headers.get('Range')
    if (range) headers.set('Range', range)
    const res = await fetch(upstream, {
      method: request.method, headers,
      cf: { cacheEverything: true, cacheTtl: YEAR, cacheTtlByStatus: { '200-299': YEAR, 404: 60, '500-599': 0 } },
    })
    const out = new Headers(res.headers)
    for (const [k, v] of Object.entries(CORS)) out.set(k, v)
    out.set('Accept-Ranges', 'bytes')
    out.set('Cache-Control', 'public, max-age=86400')
    out.delete('set-cookie')
    return new Response(res.body, { status: res.status, headers: out })
  },
}
