import { createContext, useContext } from 'react'

export const AuthContext = createContext(null)
export const MetaContext = createContext({})

export const useAuth = () => useContext(AuthContext)
export const useMeta = () => useContext(MetaContext)

const FILTER_KEY = 'opp.filters'
const DEFAULT_FILTERS = { era: [], category: [], reverse: false }

export function loadFilters(user) {
  try {
    const saved = JSON.parse(localStorage.getItem(FILTER_KEY))
    if (saved) return { ...DEFAULT_FILTERS, ...saved }
  } catch { /* storage unavailable */ }
  return { ...DEFAULT_FILTERS, ...(user?.prefs || {}) }
}

export function saveFilters(filters) {
  try { localStorage.setItem(FILTER_KEY, JSON.stringify(filters)) } catch { /* ignore */ }
}
