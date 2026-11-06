import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { loadFilters, saveFilters, useAuth, useMeta } from '../context.js'
import { ChipGroup } from '../components/FilterBar.jsx'
import Tile from '../components/Tile.jsx'

function Collection() {
  const [tab, setTab] = useState('like')
  const [items, setItems] = useState(null)
  useEffect(() => {
    setItems(null)
    api.collection(tab).then((r) => setItems(r.items)).catch(() => setItems([]))
  }, [tab])
  return (
    <section className="panel">
      <div className="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === 'like'} className={tab === 'like' ? 'on' : ''} onClick={() => setTab('like')}>Liked</button>
        <button type="button" role="tab" aria-selected={tab === 'save'} className={tab === 'save' ? 'on' : ''} onClick={() => setTab('save')}>Saved</button>
      </div>
      {items === null ? <p className="muted mono pad">Loading…</p>
        : items.length === 0 ? <p className="muted pad">Nothing yet. Tap the {tab === 'like' ? 'heart' : 'bookmark'} on anything in the feed.</p>
          : <div className="grid">{items.map((it) => <Tile key={it.id} item={it} />)}</div>}
    </section>
  )
}

function Defaults() {
  const meta = useMeta()
  const { user, setUser } = useAuth()
  const [prefs, setPrefs] = useState(() => loadFilters(user))
  const [status, setStatus] = useState('')
  const save = async () => {
    saveFilters(prefs)
    try { setUser((await api.savePrefs(prefs)).user); setStatus('Saved') } catch (e) { setStatus(e.message) }
  }
  return (
    <section className="panel">
      <h3>Feed defaults</h3>
      <p className="muted small">What your feed opens with. You can always change it from the feed.</p>
      <label className="label mono">Eras</label>
      <ChipGroup options={meta.eras || []} value={prefs.era} allLabel="All eras" onChange={(era) => setPrefs({ ...prefs, era })} />
      <label className="label mono">Categories</label>
      <ChipGroup options={meta.categories || []} value={prefs.category} allLabel="Everything" onChange={(category) => setPrefs({ ...prefs, category })} />
      <label className="switch">
        <input type="checkbox" checked={prefs.reverse} onChange={(e) => setPrefs({ ...prefs, reverse: e.target.checked })} />
        <span>Start in rewind mode (scroll the opposite way)</span>
      </label>
      <div className="row">
        <button type="button" className="btn" onClick={save}>Save defaults</button>
        {status && <span className="mono muted small">{status}</span>}
      </div>
    </section>
  )
}

function Admin() {
  const [urls, setUrls] = useState('')
  const [msg, setMsg] = useState('')
  const [stats, setStats] = useState(null)
  const refresh = () => api.adminStats().then(setStats).catch(() => {})
  useEffect(() => { refresh() }, [])
  const addTikToks = async () => {
    const list = urls.split(/\s+/).filter((u) => u.includes('tiktok.com'))
    if (!list.length) { setMsg('Paste at least one TikTok video URL'); return }
    setMsg('Adding…')
    try { const r = await api.adminTikTok(list); setMsg(`Added ${r.added} of ${list.length}`); setUrls(''); refresh() } catch (e) { setMsg(e.message) }
  }
  const ingest = async () => {
    setMsg('Crawling sources…')
    try { const r = await api.adminIngest(); setMsg(`Ingest: ${JSON.stringify(r.stats)}`); refresh() } catch (e) { setMsg(e.message) }
  }
  return (
    <section className="panel">
      <h3>Curator</h3>
      {stats && <p className="mono muted small">{stats.total} items · {stats.breakdown.map((b) => `${b.source}/${b.era} ${b.count}`).join(' · ')}</p>}
      <label className="label mono" htmlFor="tt">Add TikTok videos (one URL per line)</label>
      <textarea id="tt" rows={4} value={urls} onChange={(e) => setUrls(e.target.value)} placeholder="https://www.tiktok.com/@creator/video/…" />
      <div className="row">
        <button type="button" className="btn" onClick={addTikToks}>Add TikToks</button>
        <button type="button" className="btn ghost" onClick={ingest}>Run ingest now</button>
      </div>
      {msg && <p className="mono small muted">{msg}</p>}
    </section>
  )
}

export default function Profile() {
  const { user, logout } = useAuth()
  return (
    <div className="page profile-page">
      <header className="profile-head">
        {user.avatar ? <img src={user.avatar} alt="" className="avatar" referrerPolicy="no-referrer" /> : <div className="avatar blank">{(user.name || '?')[0]}</div>}
        <div>
          <h1>{user.name || 'You'}</h1>
          <p className="mono muted small">{user.email}</p>
        </div>
        <button type="button" className="btn ghost push" onClick={logout}>Sign out</button>
      </header>
      <Collection />
      <Defaults />
      {user.is_admin && <Admin />}
    </div>
  )
}
