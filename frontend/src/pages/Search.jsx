import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { DIMS, EMPTY_FILTERS, countFilters, useMeta } from '../context.js'
import { ChipGroup, FilterSheet } from '../components/FilterBar.jsx'
import Icon from '../components/Icon.jsx'
import Logo from '../components/Logo.jsx'
import Tile from '../components/Tile.jsx'

const SUGGESTIONS = ['Spacetoon', 'Captain Majid', 'Fairuz', 'World Cup 1998', 'Nokia 3310', 'Matrix trailer',
  'Y2K fashion', 'Windows 98', 'Space Jam', 'MTV', 'Senna', 'Top Gear', 'Dragon Ball', 'Amr Diab',
  'Fresh Prince', 'Tamagotchi', 'Pepsi commercial', 'X-Files', 'El Chavo', 'Grendizer']

const readFilters = (params) => {
  const f = { ...EMPTY_FILTERS }
  DIMS.forEach((d) => { f[d] = (params.get(d) || '').split(',').filter(Boolean) })
  return f
}

export default function Search() {
  const meta = useMeta()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const filters = readFilters(params)
  const fkey = DIMS.map((d) => params.get(d) || '').join('|')
  const [text, setText] = useState(q)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sheet, setSheet] = useState(false)

  useEffect(() => setText(q), [q])

  useEffect(() => {
    if (!q) { setItems([]); return undefined }
    const ctrl = new AbortController()
    setLoading(true)
    setError('')
    api.search({ q, ...filters }, ctrl.signal)
      .then((r) => setItems(r.items))
      .catch((e) => { if (e.name !== 'AbortError') setError(e.message) })
      .finally(() => setLoading(false))
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, fkey])

  const go = (nextQ, nextF = filters) => {
    const p = {}
    if (nextQ.trim()) p.q = nextQ.trim()
    DIMS.forEach((d) => { if (nextF[d]?.length) p[d] = nextF[d].join(',') })
    setParams(p)
  }
  const n = countFilters(filters)

  return (
    <div className="page search-page">
      <form className="searchbox" onSubmit={(e) => { e.preventDefault(); go(text) }}>
        <Icon name="search" />
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Search the past: a song, a show, a cartoon, a match…"
          aria-label="Search" enterKeyHint="search" />
        {text && <button type="button" className="clear" onClick={() => { setText(''); go('') }} aria-label="Clear">×</button>}
      </form>
      <div className="filter-row">
        <button type="button" className={`chip filter-btn ${n ? 'on' : ''}`} onClick={() => setSheet(true)}>
          <Icon name="filter" size={16} /> {n ? `${n} filters` : 'Filters'}
        </button>
        <ChipGroup options={meta.eras || []} value={filters.era} allLabel="All eras" onChange={(era) => go(q, { ...filters, era })} />
      </div>

      {!q && (
        <section className="suggest">
          <h3 className="mono muted">Try</h3>
          <div className="chips wrap">
            {SUGGESTIONS.map((s) => <button key={s} type="button" className="chip" onClick={() => go(s)}>{s}</button>)}
          </div>
        </section>
      )}

      {loading && <div className="center pad"><Logo size={44} /><p className="mono muted">Searching the archives…</p></div>}
      {error && <p className="error center">{error}</p>}
      {!loading && q && !error && items.length === 0 && (
        <p className="center muted pad">Nothing from back then matches “{q}”. Try a broader word or fewer filters.</p>
      )}
      <div className="grid">
        {items.map((it, i) => (
          <Tile key={it.id} item={it} onOpen={(e) => {
            e.preventDefault()
            navigate(`/v/${it.id}`, { state: { items, index: i, from: 'search' } })
          }} />
        ))}
      </div>
      {sheet && <FilterSheet meta={meta} value={filters} onClose={() => setSheet(false)}
        onApply={(f) => { setSheet(false); go(q, f) }} />}
    </div>
  )
}
