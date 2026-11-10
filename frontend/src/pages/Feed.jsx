import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { loadFilters, saveFilters, useAuth, useMeta } from '../context.js'
import { flush } from '../lib/events.js'
import { takeFirstFeed } from '../lib/boot.js'
import { getClipLength } from '../lib/clip.js'
import { tier } from '../lib/quality.js'
import Pager from '../components/Pager.jsx'
import FilterBar from '../components/FilterBar.jsx'

const dedupe = (list) => {
  const seen = new Set()
  return list.filter((i) => (seen.has(i.id) ? false : seen.add(i.id)))
}
const newSeed = () => Math.random().toString(36).slice(2, 10)

export default function Feed() {
  const { user } = useAuth()
  const meta = useMeta()
  const [filters, setFilters] = useState(() => loadFilters(user, meta))
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)
  const [gen, setGen] = useState(0)          // bumps when the list is replaced -> pager goes to the top
  const [rewind, setRewind] = useState(false)

  const served = useRef([])                   // every id shown this session: never repeated
  const busy = useRef(false)
  const reqId = useRef(0)
  const seed = useRef(newSeed())
  const filtersRef = useRef(filters)
  filtersRef.current = filters

  useEffect(() => saveFilters(filters), [filters])
  const [chrome, setChrome] = useState(false)

  const load = useCallback(async (reset) => {
    if (!reset && busy.current) return undefined
    const id = ++reqId.current
    busy.current = true
    setLoading(true)
    try {
      // First page: usually already on its way since the app started (lib/boot.js).
      const early = reset && !served.current.length ? takeFirstFeed(filtersRef.current) : null
      let r = early && await early
      if (r) seed.current = r.seed
      else {
        // so the ranking already knows what you just watched, but never wait long on a slow link
        await Promise.race([flush({ wait: true }), new Promise((res) => setTimeout(res, 800))])
        r = await api.feed({ ...filtersRef.current, exclude: served.current.slice(-350), seed: seed.current,
          limit: reset ? 6 : 8, len: getClipLength(), tier: tier() })
      }
      if (id !== reqId.current) return undefined
      if (reset && !r.items.length && served.current.length) {
        // Seen everything for these filters: start over rather than show an empty feed.
        served.current = []
        busy.current = false
        return load(true)
      }
      served.current.push(...r.items.map((i) => i.id))
      setItems((prev) => (reset ? r.items : dedupe([...prev, ...r.items])))
      if (reset) setGen((n) => n + 1)
      setDone(r.done)
      setError(null)
    } catch (e) {
      if (id === reqId.current) setError(e.message)
    } finally {
      if (id === reqId.current) { busy.current = false; setLoading(false) }
    }
    return undefined
  }, [])

  // Filters changed: new list (debounced so tapping several chips is one request).
  const filterKey = JSON.stringify(filters)
  const first = useRef(true)
  useEffect(() => {
    setRewind(false)
    const t = setTimeout(() => {
      seed.current = newSeed()
      served.current = []
      setDone(false)
      if (!first.current) setItems([])
      first.current = false
      load(true)
    }, first.current ? 0 : 250)
    return () => clearTimeout(t)
  }, [filterKey, load])

  // Pull-to-refresh / tapping "Feed" again: a fresh ranking, without what you've already seen.
  const refresh = useCallback(async () => {
    seed.current = newSeed()
    setRewind(false)
    setDone(false)
    await load(true)
  }, [load])
  useEffect(() => {
    const onHome = () => refresh()
    window.addEventListener('opp:home', onHome)
    return () => window.removeEventListener('opp:home', onHome)
  }, [refresh])

  const loadMore = useCallback(() => load(false), [load])
  const updateItem = useCallback((it) => setItems((prev) => prev.map((p) => (p.id === it.id ? { ...p, ...it } : p))), [])
  const hideItem = useCallback((id) => setItems((prev) => prev.filter((p) => p.id !== id)), [])
  const endRewind = useCallback(() => setRewind(false), [])

  return (
    <div className={`feed-page ${rewind ? 'rewinding' : ''} ${chrome || rewind ? 'chrome-on' : 'clean'}`}>
      <FilterBar meta={meta} value={filters} onChange={setFilters} rewind={rewind} onRewind={() => setRewind((r) => !r)} />
      <Pager
        items={items} loading={loading} done={done} error={error} resetKey={gen}
        onMore={loadMore} onRefresh={refresh} onItemChange={updateItem} onHide={hideItem}
        onRetry={() => load(true)} rewind={rewind} onRewindEnd={endRewind} onChrome={setChrome} />
    </div>
  )
}
