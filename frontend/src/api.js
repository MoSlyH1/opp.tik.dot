export const BASE = (import.meta.env.VITE_API_BASE || '') + '/api'

const EDGE = typeof location !== 'undefined' && location.protocol.startsWith('http') && !/localhost|127\./.test(location.hostname)

async function request(path, { method = 'GET', body, signal } = {}) {
  const res = await fetch(BASE + path, {
    method,
    credentials: 'include',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    signal,
  })
  let data = {}
  try {
    let text = await res.text()
    // archive.org thumbnails are slow and uncached from the Middle East; load them through our
    // own edge cache (vercel.json rewrite /thumb/<id>) when we're on a real host.
    // v12: no more waiting for /api/meta first (that held the first feed page back up to 3 s).
    if (EDGE) text = text.replaceAll('https://archive.org/services/img/', '/thumb/')
    data = JSON.parse(text)
  } catch { /* not JSON */ }
  if (!res.ok) {
    const err = new Error(data.error || res.statusText || 'Request failed')
    err.status = res.status
    throw err
  }
  return data
}

const qs = (params) => {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (Array.isArray(v)) v.length && p.set(k, v.join(','))
    else if (v !== undefined && v !== null && v !== '') p.set(k, v)
  })
  return p.toString()
}

export const api = {
  meta: () => request('/meta'),
  preview: () => request('/preview'),
  me: () => request('/auth/me'),
  loginGoogle: (credential) => request('/auth/google', { method: 'POST', body: { credential } }),
  loginDev: () => request('/auth/dev', { method: 'POST', body: {} }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  feed: (body, signal) => request('/feed', { method: 'POST', body, signal }),
  count: (filters, signal) => request('/feed/count?' + qs(filters), { signal }),
  search: (params, signal) => request('/search?' + qs(params), { signal }),
  item: (id) => request(`/items/${id}`),
  interact: (id, action) => request(`/items/${id}/interact`, { method: 'POST', body: { action } }),
  collection: (type) => request('/me/collection?' + qs({ type })),
  savePrefs: (prefs) => request('/me/prefs', { method: 'PUT', body: prefs }),
  follow: (body) => request('/me/follow', { method: 'POST', body }),
  adminArchiveUpgrade: () => request('/admin/archive-upgrade', { method: 'POST' }),
  adminLinks: (body) => request('/admin/links', { method: 'POST', body }),
  adminIngest: () => request('/admin/ingest', { method: 'POST' }),
  adminReclassify: () => request('/admin/reclassify', { method: 'POST' }),
  adminStats: () => request('/admin/stats'),
}
