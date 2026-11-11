import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { cleanFilters, saveFilters, useAuth, useMeta } from '../context.js'
import { FilterSections } from '../components/FilterBar.jsx'
import Tile from '../components/Tile.jsx'
import { MODES, setMode, useQuality } from '../lib/quality.js'
import { LENGTHS, setClipLength, useClipLength } from '../lib/clip.js'

function Playback() {
  const { mode, h } = useQuality()
  const length = useClipLength()
  return (
    <>
    <section className="panel">
      <h3>Playback quality</h3>
      <p className="muted small">Data saver plays 144p. Auto plays 240p or higher and moves up when your videos start instantly. HD plays 480p or higher.</p>
      <div className="q-options wide">
        {MODES.map((m) => (
          <button key={m.id} type="button" className={`q-opt ${mode === m.id ? 'on' : ''}`} onClick={() => setMode(m.id)}>
            <strong>{m.id === mode && m.id !== 'saver' ? `${m.label} · now ${h}p` : m.label}</strong>
            <span>{m.hint}</span>
          </button>
        ))}
      </div>
    </section>
    <section className="panel">
      <h3>Clip length</h3>
      <p className="muted small">Each video plays its best part, then the next one slides in. Shorter clips load faster and use less data. Tap "Watch full" on any clip to keep going.</p>
      <div className="q-options wide four">
        {LENGTHS.map((l) => (
          <button key={l.id} type="button" className={`q-opt ${length === l.id ? 'on' : ''}`} onClick={() => setClipLength(l.id)}>
            <strong>{l.label}</strong>
            <span>{l.hint}</span>
          </button>
        ))}
      </div>
    </section>
    </>
  )
}

function Following() {
  const { user, setUser } = useAuth()
  const list = user.prefs?.follows || []
  const [busy, setBusy] = useState('')
  if (!list.length) return null
  const unfollow = async (key) => {
    const [source, author] = key.split('|')
    setBusy(key)
    try { setUser((await api.follow({ source, author, on: false })).user) } catch { /* keep */ }
    setBusy('')
  }
  return (
    <section className="panel">
      <h3>Following</h3>
      <p className="muted small">Creators you follow show up more often in your feed.</p>
      <div className="chips wrap">
        {list.map((k) => {
          const [source, author] = k.split('|')
          return (
            <button key={k} type="button" className="chip" disabled={busy === k} onClick={() => unfollow(k)} title="Unfollow">
              @{author} <span className="mono muted small">{source}</span> ✕
            </button>
          )
        })}
      </div>
    </section>
  )
}

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
  const [prefs, setPrefs] = useState(() => cleanFilters(user.prefs || {}, meta))
  const [status, setStatus] = useState('')
  const save = async () => {
    saveFilters(prefs)
    try { setUser((await api.savePrefs(prefs)).user); setStatus('Saved') } catch (e) { setStatus(e.message) }
  }
  return (
    <section className="panel">
      <h3>Feed defaults</h3>
      <p className="muted small">What your feed opens with. You can always change it from the feed.</p>
      <FilterSections meta={meta} value={prefs} onChange={setPrefs} sources={false} />
      <div className="row">
        <button type="button" className="btn" onClick={save}>Save defaults</button>
        {status && <span className="mono muted small">{status}</span>}
      </div>
    </section>
  )
}

function Admin() {
  const meta = useMeta()
  const [urls, setUrls] = useState('')
  const [hint, setHint] = useState({ era: '', topic: '', region: '' })
  const [msg, setMsg] = useState('')
  const [stats, setStats] = useState(null)
  const refresh = () => api.adminStats().then(setStats).catch(() => {})
  useEffect(() => { refresh() }, [])
  const addLinks = async () => {
    const list = urls.split(/\s+/).filter((u) => u.startsWith('http'))
    if (!list.length) { setMsg('Paste at least one video link'); return }
    setMsg('Adding…')
    try {
      const r = await api.adminLinks({ urls: list, ...hint })
      setMsg(`Added ${r.added} of ${list.length}`); setUrls(''); refresh()
    } catch (e) { setMsg(e.message) }
  }
  const run = async (fn, label) => {
    setMsg(label)
    try { const r = await fn(); setMsg(JSON.stringify(r.stats || r)); refresh() } catch (e) { setMsg(e.message) }
  }
  const sel = (key, opts, all) => (
    <select value={hint[key]} onChange={(e) => setHint({ ...hint, [key]: e.target.value })} aria-label={all}>
      <option value="">{all}</option>
      {opts.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
    </select>
  )
  return (
    <section className="panel">
      <h3>Curator</h3>
      {stats && (
        <p className="mono muted small">
          {stats.total} items · {stats.unresolved_archive} archive files still to look up ·
          sources on: {Object.entries(stats.sources || {}).filter(([, v]) => v).map(([k]) => k).join(', ')}
        </p>
      )}
      <label className="label mono" htmlFor="tt">Add videos (one link per line: TikTok, YouTube, Instagram, Facebook, X, Dailymotion, Archive)</label>
      <textarea id="tt" rows={4} value={urls} onChange={(e) => setUrls(e.target.value)}
        placeholder={'https://www.tiktok.com/@creator/video/…\nhttps://www.instagram.com/reel/…'} />
      <div className="row">
        {sel('era', meta.eras || [], 'Era: auto')}
        {sel('topic', meta.topics || [], 'Topic: auto')}
        {sel('region', meta.regions || [], 'Culture: auto')}
      </div>
      <div className="row">
        <button type="button" className="btn" onClick={addLinks}>Add links</button>
        <button type="button" className="btn ghost" onClick={() => run(api.adminIngest, 'Crawling sources…')}>Run ingest now</button>
        <button type="button" className="btn ghost" onClick={() => run(api.adminReclassify, 'Re-labelling…')}>Re-label catalogue</button>
        <button type="button" className="btn ghost" onClick={() => run(api.adminArchiveUpgrade, 'Finding faster Archive files…')}
          title="Re-reads Archive items saved by older versions: adds low-quality files and the direct server">
          Speed up Archive videos{stats?.legacy_archive ? ` (${stats.legacy_archive} left)` : ''}
        </button>
      </div>
      {msg && <p className="mono small muted wrap-any">{msg}</p>}
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
      <Playback />
      <Following />
      <Defaults />
      {user.is_admin && <Admin />}
    </div>
  )
}
