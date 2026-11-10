// opp.tik.dot video CDN — a free Cloudflare Worker in front of the R2 bucket.
//
// Why: R2's public r2.dev link is rate-limited (testing only) and a custom domain needs a
// domain you own. A Worker on the free *.workers.dev address needs neither, is free up to
// 100,000 requests/day, and serves from Cloudflare's edge (there is one in Beirut).
//
// Setup (dashboard, no CLI): Workers & Pages -> Create -> "Hello World" Worker -> name it
// opp-video -> Deploy -> Edit code -> paste this file -> Deploy.
// Then Settings -> Bindings -> Add -> R2 bucket -> Variable name VIDEO -> bucket opp-video.
// Your CDN_BASE is the Worker URL, e.g. https://opp-video.<you>.workers.dev

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
  'Access-Control-Allow-Headers': 'Range',
  'Access-Control-Expose-Headers': 'Content-Length, Content-Range, Accept-Ranges',
  'Access-Control-Max-Age': '86400',
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS })
    if (request.method !== 'GET' && request.method !== 'HEAD') return new Response('Method not allowed', { status: 405, headers: CORS })

    const key = decodeURIComponent(new URL(request.url).pathname.slice(1))
    if (!key || key.includes('..')) return new Response('Not found', { status: 404, headers: CORS })

    const obj = await env.VIDEO.get(key, { range: request.headers, onlyIf: request.headers })
    if (obj === null) return new Response('Not found', { status: 404, headers: CORS })

    const headers = new Headers(CORS)
    obj.writeHttpMetadata(headers)
    headers.set('etag', obj.httpEtag)
    headers.set('Accept-Ranges', 'bytes')
    // Encodes never change (a new encode gets a new folder): let browsers keep them forever.
    if (!headers.has('Cache-Control')) headers.set('Cache-Control', 'public, max-age=31536000, immutable')
    if (key.endsWith('.m3u8')) headers.set('Content-Type', 'application/vnd.apple.mpegurl')
    else if (key.endsWith('.ts')) headers.set('Content-Type', 'video/mp2t')

    // Conditional request matched (browser already has it).
    if (!('body' in obj)) return new Response(null, { status: 304, headers })

    let status = 200
    if (obj.range && request.headers.has('range')) {
      const r = obj.range
      const offset = 'suffix' in r ? obj.size - r.suffix : r.offset ?? 0
      const length = 'suffix' in r ? r.suffix : r.length ?? obj.size - offset
      headers.set('Content-Range', `bytes ${offset}-${offset + length - 1}/${obj.size}`)
      headers.set('Content-Length', String(length))
      status = 206
    } else {
      headers.set('Content-Length', String(obj.size))
    }
    return new Response(request.method === 'HEAD' ? null : obj.body, { status, headers })
  },
}
