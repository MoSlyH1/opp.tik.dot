import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { EMPTY_FILTERS, countFilters } from '../context.js'
import Icon from './Icon.jsx'
import { clipLabel, nextClipLength, useClipLength } from '../lib/clip.js'

export function ChipGroup({ options, value, onChange, allLabel }) {
  const toggle = (id) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id])
  return (
    <div className="chips" role="group">
      {allLabel && (
        <button type="button" className={`chip ${value.length === 0 ? 'on' : ''}`} onClick={() => onChange([])}>
          {allLabel}
        </button>
      )}
      {options.map((o) => (
        <button type="button" key={o.id} className={`chip ${value.includes(o.id) ? 'on' : ''}`}
          aria-pressed={value.includes(o.id)} onClick={() => toggle(o.id)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

function Grouped({ options, groups, value, onChange }) {
  return groups.map((g) => {
    const opts = options.filter((o) => o.group === g)
    if (!opts.length) return null
    return (
      <div className="sheet-group" key={g}>
        <span className="sheet-sub mono">{g}</span>
        <div className="chips wrap"><ChipGroup options={opts} value={value} onChange={onChange} /></div>
      </div>
    )
  })
}

// Every filter dimension; used by the sheet, the Search page and Profile defaults.
export function FilterSections({ meta, value, onChange, sources = true }) {
  const set = (patch) => onChange({ ...value, ...patch })
  return (
    <>
      <section className="sheet-sec">
        <h4>Era</h4>
        <div className="chips wrap"><ChipGroup options={meta.eras || []} value={value.era} allLabel="All eras" onChange={(era) => set({ era })} /></div>
      </section>
      <section className="sheet-sec">
        <h4>What</h4>
        <Grouped options={meta.topics || []} groups={meta.topic_groups || []} value={value.topic} onChange={(topic) => set({ topic })} />
      </section>
      <section className="sheet-sec">
        <h4>Cultures &amp; regions</h4>
        <Grouped options={meta.regions || []} groups={meta.region_groups || []} value={value.region} onChange={(region) => set({ region })} />
      </section>
      <section className="sheet-sec">
        <h4>Channels</h4>
        <div className="chips wrap"><ChipGroup options={meta.channels || []} value={value.channel} onChange={(channel) => set({ channel })} /></div>
      </section>
      {sources && (meta.sources || []).length > 1 && (
        <section className="sheet-sec">
          <h4>Where from</h4>
          <div className="chips wrap"><ChipGroup options={meta.sources} value={value.source} allLabel="Everywhere" onChange={(source) => set({ source })} /></div>
        </section>
      )}
    </>
  )
}

export function FilterSheet({ meta, value, onApply, onClose }) {
  const [draft, setDraft] = useState(value)
  const [count, setCount] = useState(null)
  useEffect(() => {
    const ctrl = new AbortController()
    const t = setTimeout(() => {
      api.count(draft, ctrl.signal).then((r) => setCount(r.count)).catch(() => {})
    }, 200)
    return () => { clearTimeout(t); ctrl.abort() }
  }, [draft])
  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Filters" onClick={(e) => e.stopPropagation()}>
        <header className="sheet-head">
          <h3>Filters</h3>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close" /></button>
        </header>
        <div className="sheet-body">
          <FilterSections meta={meta} value={draft} onChange={setDraft} />
        </div>
        <footer className="sheet-foot">
          <button type="button" className="btn ghost" onClick={() => setDraft(EMPTY_FILTERS)}>Reset</button>
          <button type="button" className="btn" disabled={count === 0} onClick={() => onApply(draft)}>
            {count === null ? 'Show videos' : count === 0 ? 'No videos match' : `Show ${count.toLocaleString()} ${count === 1 ? 'video' : 'videos'}`}
          </button>
        </footer>
      </div>
    </div>
  )
}

export default function FilterBar({ meta, value, onChange, rewind, onRewind }) {
  const [open, setOpen] = useState(false)
  const n = countFilters(value)
  const quick = useMemo(() => meta.quick || [], [meta])
  const isOn = (q) => value[q.dim]?.includes(q.id)
  const flip = (q) => onChange({ ...value, [q.dim]: isOn(q) ? value[q.dim].filter((v) => v !== q.id) : [...value[q.dim], q.id] })
  const length = useClipLength()
  const toggleEra = (id) => onChange({ ...value, era: value.era.includes(id) ? value.era.filter((e) => e !== id) : [...value.era, id] })
  return (
    <div className="filterbar">
      <div className="filter-row">
        <button type="button" className={`chip filter-btn ${n ? 'on' : ''}`} onClick={() => setOpen(true)} aria-label="All filters">
          <Icon name="filter" size={16} /> {n ? n : 'Filters'}
        </button>
        <div className="chips">
          <button type="button" className={`chip ${n === 0 ? 'on' : ''}`} onClick={() => onChange(EMPTY_FILTERS)}>For you</button>
          {quick.map((q) => (
            <button type="button" key={q.dim + q.id} className={`chip ${isOn(q) ? 'on' : ''}`} aria-pressed={isOn(q)} onClick={() => flip(q)}>
              {q.label}
            </button>
          ))}
        </div>
        <button type="button" className="chip rewind len-chip" onClick={nextClipLength}
          title="Clip length: tap to switch between 30s, 1 min, 2 min and full videos" aria-label={`Clip length ${clipLabel(length)}`}>
          <Icon name="clock" size={15} /> {clipLabel(length)}
        </button>
        <button type="button" className={`chip rewind ${rewind ? 'on' : ''}`} aria-pressed={rewind} onClick={onRewind}
          title="Rewind: stop here and watch your feed backwards">
          <Icon name="rewind" size={16} /> {rewind ? 'Stop' : 'Rewind'}
        </button>
      </div>
      <div className="filter-row eras">
        <div className="chips">
          {(meta.eras || []).map((e) => (
            <button type="button" key={e.id} className={`chip mini ${value.era.includes(e.id) ? 'on' : ''}`} onClick={() => toggleEra(e.id)}>
              {e.label}
            </button>
          ))}
        </div>
      </div>
      {open && <FilterSheet meta={meta} value={value} onClose={() => setOpen(false)} onApply={(f) => { onChange(f); setOpen(false) }} />}
    </div>
  )
}
