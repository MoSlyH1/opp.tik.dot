import { createContext, useContext } from 'react'

export const AuthContext = createContext(null)
export const MetaContext = createContext({})

export const useAuth = () => useContext(AuthContext)
export const useMeta = () => useContext(MetaContext)

const FILTER_KEY = 'opp.filters.v4'
export const DIMS = ['era', 'topic', 'region', 'channel', 'source']
export const EMPTY_FILTERS = { era: [], topic: [], region: [], channel: [], source: [] }

// Drop ids the server no longer knows (v3 eras like "classic", renamed topics...).
export function cleanFilters(f, meta) {
  const allowed = {
    era: meta?.eras, topic: meta?.topics, region: meta?.regions, channel: meta?.channels, source: meta?.sources,
  }
  const out = { ...EMPTY_FILTERS }
  DIMS.forEach((d) => {
    const ids = new Set((allowed[d] || []).map((o) => o.id))
    const v = Array.isArray(f?.[d]) ? f[d] : d === 'topic' && Array.isArray(f?.category) ? f.category : []
    out[d] = allowed[d] ? v.filter((x) => ids.has(x)) : v
  })
  return out
}

export const countFilters = (f) => DIMS.reduce((n, d) => n + (f[d]?.length || 0), 0)

export function loadFilters(user, meta) {
  try {
    const saved = JSON.parse(localStorage.getItem(FILTER_KEY))
    if (saved) return cleanFilters(saved, meta)
  } catch { /* storage unavailable */ }
  return cleanFilters(user?.prefs || {}, meta)
}

export function saveFilters(filters) {
  try { localStorage.setItem(FILTER_KEY, JSON.stringify(filters)) } catch { /* ignore */ }
}
