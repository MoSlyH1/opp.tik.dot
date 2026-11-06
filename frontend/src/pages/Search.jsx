import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { useMeta } from '../context.js'
import { ChipGroup } from '../components/FilterBar.jsx'
import Icon from '../components/Icon.jsx'
import Logo from '../components/Logo.jsx'
import Tile from '../components/Tile.jsx'

const SUGGESTIONS = ['Spice Girls', 'Nokia 3310', 'Matrix trailer', 'Y2K fashion', 'Windows 98',
  'Space Jam', 'MTV', 'Tamagotchi', 'Game Boy', 'Fresh Prince', 'Britney', 'Pepsi commercial']

export default function Search() {
  const meta = useMeta()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const era = (params.get('era') || '').split(',').filter(Boolean)
  const [text, setText] = useState(q)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => setText(q), [q])

  useEffect(() => {
    if (!q) { setItems([]); return undefined }
    const ctrl = new AbortController()
    setLoading(true)
    setError('')
    api.search({ q, era }, ctrl.signal)
      .then((r) => setItems(r.items))
      .catch((e) => { if (e.name !== 'AbortError') setError(e.message) })
      .finally(() => setLoading(false))
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, params.get('era')])

  const go = (nextQ, nextEra = era) => {
    const p = {}
    if (nextQ.trim()) p.q = nextQ.trim()
    if (nextEra.length) p.era = nextEra.join(',')
    setParams(p)
  }

  return (
    <div className="page search-page">
      <form className="searchbox" onSubmit={(e) => { e.preventDefault(); go(text) }}>
        <Icon name="search" />
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Search the past: a song, a show, a gadget…"
          aria-label="Search" enterKeyHint="search" />
        {text && <button type="button" className="clear" onClick={() => { setText(''); go('') }} aria-label="Clear">×</button>}
      </form>
      <ChipGroup options={meta.eras || []} value={era} allLabel="All eras" onChange={(e) => go(q, e)} />

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
        <p className="center muted pad">Nothing from back then matches “{q}”. Try a broader word.</p>
      )}
      <div className="grid">{items.map((it) => <Tile key={it.id} item={it} />)}</div>
    </div>
  )
}
