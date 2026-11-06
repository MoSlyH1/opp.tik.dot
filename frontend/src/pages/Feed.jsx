import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { loadFilters, saveFilters, useAuth, useMeta } from '../context.js'
import FeedScroller from '../components/FeedScroller.jsx'
import FilterBar from '../components/FilterBar.jsx'

const dedupe = (list) => {
  const seen = new Set()
  return list.filter((i) => (seen.has(i.id) ? false : seen.add(i.id)))
}

export default function Feed() {
  const { user } = useAuth()
  const meta = useMeta()
  const [filters, setFilters] = useState(() => loadFilters(user))
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)

  const cursor = useRef(0)
  const busy = useRef(false)
  const reqId = useRef(0)
  const seed = useRef('')
  const filterKey = JSON.stringify([filters.era, filters.category])

  useEffect(() => saveFilters(filters), [filters])

  const load = useCallback(async (reset) => {
    if (!reset && (busy.current || cursor.current === null)) return
    const id = ++reqId.current
    busy.current = true
    setLoading(true)
    try {
      const r = await api.feed({
        era: filters.era, category: filters.category,
        cursor: reset ? 0 : cursor.current, seed: seed.current, limit: 8,
      })
      if (id !== reqId.current) return
      setItems((prev) => (reset ? r.items : dedupe([...prev, ...r.items])))
      cursor.current = r.next_cursor
      setDone(r.next_cursor === null)
      setError(null)
    } catch (e) {
      if (id === reqId.current) setError(e.message)
    } finally {
      if (id === reqId.current) { busy.current = false; setLoading(false) }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey])

  useEffect(() => {
    seed.current = Math.random().toString(36).slice(2, 10)
    cursor.current = 0
    setItems([])
    setDone(false)
    load(true)
  }, [load])

  const loadMore = useCallback(() => load(false), [load])
  const updateItem = useCallback((it) => setItems((prev) => prev.map((p) => (p.id === it.id ? { ...p, ...it } : p))), [])
  const hideItem = useCallback((id) => setItems((prev) => prev.filter((p) => p.id !== id)), [])

  return (
    <div className="feed-page">
      <FilterBar meta={meta} value={filters} onChange={setFilters} />
      <FeedScroller
        items={items} reverse={filters.reverse} loading={loading} done={done} error={error}
        resetKey={filterKey} onMore={loadMore} onItemChange={updateItem} onHide={hideItem}
        onRetry={() => load(true)} />
    </div>
  )
}
