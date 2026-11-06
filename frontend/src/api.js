const BASE = (import.meta.env.VITE_API_BASE || '') + '/api'

async function request(path, { method = 'GET', body, signal } = {}) {
  const res = await fetch(BASE + path, {
    method,
    credentials: 'include',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    signal,
  })
  const data = await res.json().catch(() => ({}))
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
  feed: (params, signal) => request('/feed?' + qs(params), { signal }),
  search: (params, signal) => request('/search?' + qs(params), { signal }),
  item: (id) => request(`/items/${id}`),
  interact: (id, action) => request(`/items/${id}/interact`, { method: 'POST', body: { action } }),
  collection: (type) => request('/me/collection?' + qs({ type })),
  savePrefs: (prefs) => request('/me/prefs', { method: 'PUT', body: prefs }),
  adminTikTok: (urls) => request('/admin/tiktok', { method: 'POST', body: { urls } }),
  adminIngest: () => request('/admin/ingest', { method: 'POST' }),
  adminStats: () => request('/admin/stats'),
}
