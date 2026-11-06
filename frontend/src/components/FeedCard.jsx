import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { embedUrl, shareUrl } from '../embed.js'
import Icon from './Icon.jsx'

function RailButton({ icon, label, active, onClick, count }) {
  return (
    <button type="button" className={`rail-btn ${active ? 'on' : ''}`} onClick={onClick} aria-label={label} title={label}>
      <span className="rail-icon"><Icon name={icon} /></span>
      {count !== undefined && <span className="rail-count mono">{count}</span>}
    </button>
  )
}

export default function FeedCard({ item, index, active, near, muted, onToggleMute, onChange, onHide }) {
  const [interactive, setInteractive] = useState(false)
  const [toast, setToast] = useState('')
  const [ready, setReady] = useState(false)

  useEffect(() => { if (!active) { setInteractive(false); setReady(false) } }, [active])

  // Watch-time signals for ranking: a view after 2.5s, a skip if left within 1.5s.
  useEffect(() => {
    if (!active) return undefined
    const start = Date.now()
    let viewed = false
    const t = setTimeout(() => { viewed = true; api.interact(item.id, 'view').catch(() => {}) }, 2500)
    return () => {
      clearTimeout(t)
      if (!viewed && Date.now() - start < 1500) api.interact(item.id, 'skip').catch(() => {})
    }
  }, [active, item.id])

  useEffect(() => {
    if (!toast) return undefined
    const t = setTimeout(() => setToast(''), 1800)
    return () => clearTimeout(t)
  }, [toast])

  const toggle = async (kind) => {
    const on = kind === 'like' ? item.liked : item.saved
    const optimistic = kind === 'like'
      ? { ...item, liked: !on, likes: Math.max(0, item.likes + (on ? -1 : 1)) }
      : { ...item, saved: !on }
    onChange(optimistic)
    try {
      const r = await api.interact(item.id, on ? `un${kind}` : kind)
      onChange(r.item)
    } catch {
      onChange(item)
      setToast('Could not save that')
    }
  }

  const share = async () => {
    const url = shareUrl(item)
    api.interact(item.id, 'share').catch(() => {})
    try {
      if (navigator.share) await navigator.share({ title: item.title, url })
      else { await navigator.clipboard.writeText(url); setToast('Link copied') }
    } catch { /* share sheet dismissed */ }
  }

  const hide = () => {
    api.interact(item.id, 'hide').catch(() => {})
    onHide?.(item.id)
  }

  const src = active ? embedUrl(item, { muted }) : null
  const yearLabel = item.year ? String(item.year) : item.era_label

  return (
    <section className="card" data-index={index}>
      <div className="stage">
        <div className={`media ${item.source === 'tiktok' ? 'tall' : 'wide'}`}>
          {near && item.thumbnail && <img className="poster" src={item.thumbnail} alt="" loading="lazy" />}
          {src && (
            <iframe key={src} src={src} title={item.title}
              onLoad={() => setTimeout(() => setReady(true), 700)}
              style={{ opacity: ready ? 1 : 0, transition: 'opacity .25s ease' }}
              allow="autoplay; encrypted-media; picture-in-picture; fullscreen; clipboard-write"
              allowFullScreen referrerPolicy="strict-origin-when-cross-origin" />
          )}
          {active && !interactive && (
            <button type="button" className="shield" aria-label="Use video controls" onClick={() => setInteractive(true)} />
          )}
          {interactive && (
            <button type="button" className="pill back-scroll" onClick={() => setInteractive(false)}>
              <Icon name="up" size={14} /><Icon name="down" size={14} /> Back to scrolling
            </button>
          )}

          <div className="meta">
            <div className="badges">
              <span className="badge solid mono">{yearLabel}</span>
              <span className="badge mono">{item.category_label}</span>
              <span className="badge mono ghost">via {item.source_label}</span>
            </div>
            <h2 className="title">{item.title}</h2>
            {item.author && <p className="author">@{item.author}</p>}
          </div>
        </div>

        <div className="rail">
          <RailButton icon={muted ? 'mute' : 'volume'} label={muted ? 'Sound on' : 'Mute'} onClick={onToggleMute} />
          <RailButton icon="heart" label={item.liked ? 'Unlike' : 'Like'} active={item.liked} count={item.likes} onClick={() => toggle('like')} />
          <RailButton icon="bookmark" label={item.saved ? 'Remove from saved' : 'Save'} active={item.saved} onClick={() => toggle('save')} />
          <RailButton icon="share" label="Share" onClick={share} />
          <a className="rail-btn" href={item.url} target="_blank" rel="noopener noreferrer" aria-label={`Open on ${item.source_label}`} title={`Open on ${item.source_label}`}>
            <span className="rail-icon"><Icon name="external" /></span>
          </a>
          {onHide && <RailButton icon="eyeOff" label="Not interested" onClick={hide} />}
        </div>
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </section>
  )
}