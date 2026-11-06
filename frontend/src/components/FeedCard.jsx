import { useEffect, useRef, useState } from 'react'
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

export default function FeedCard({ item, index, active, near, preload, muted, onToggleMute, onChange, onHide }) {
  const [toast, setToast] = useState('')
  const [ready, setReady] = useState(false)       // player answered us (YouTube/TikTok API)
  const [playing, setPlaying] = useState(false)   // player reported "playing"
  const [paused, setPaused] = useState(false)     // user tapped to pause
  const [fallback, setFallback] = useState(false) // player ignored postMessage -> plain autoplay URL
  const [shown, setShown] = useState(false)       // archive / fallback embeds: reveal after load
  const frame = useRef(null)
  const activeRef = useRef(active)
  const mutedRef = useRef(muted)
  activeRef.current = active
  mutedRef.current = muted
  const scripted = item.source === 'youtube' || item.source === 'tiktok'

  useEffect(() => { if (!active) { setPaused(false); setShown(false) } }, [active])

  // Players are mounted for this card and its neighbours, so the next one is already buffered.
  const mounted = scripted ? (active || preload) : active
  const src = mounted ? embedUrl(item, { autoplay: fallback || !scripted }) : null
  useEffect(() => { setReady(false); setPlaying(false) }, [src])

  const send = (cmd, arg) => {
    const w = frame.current?.contentWindow
    if (!w) return
    if (item.source === 'youtube') {
      const func = { play: 'playVideo', pause: 'pauseVideo', mute: 'mute', unMute: 'unMute', seekTo: 'seekTo' }[cmd]
      w.postMessage(JSON.stringify({ event: 'command', func, args: cmd === 'seekTo' ? [arg, true] : [] }), '*')
    } else {
      w.postMessage({ 'x-tiktok-player': true, type: cmd, ...(arg !== undefined ? { value: arg } : {}) }, '*')
    }
  }
  const sendMute = (m) => send(m ? 'mute' : 'unMute')

  // Player -> us. Any message means the player API is alive. Neighbour cards are "warmed up":
  // played muted for a moment so they buffer, then paused at 0 — the swipe then starts instantly.
  useEffect(() => {
    if (!scripted) return undefined
    const onMsg = (e) => {
      if (!frame.current || e.source !== frame.current.contentWindow) return
      let d = e.data
      if (typeof d === 'string') { try { d = JSON.parse(d) } catch { return } }
      if (!d || typeof d !== 'object') return
      if (item.source === 'youtube' && !d.event) return
      if (item.source === 'tiktok' && !d['x-tiktok-player']) return
      setReady(true)
      const yt = d.event === 'onStateChange' ? d.info : d.event === 'infoDelivery' ? d.info?.playerState : undefined
      const tt = d['x-tiktok-player'] && d.type === 'onStateChange' ? d.value : undefined
      const state = yt ?? tt
      if (state === 1) {
        if (!activeRef.current) { send('mute'); send('pause'); send('seekTo', 0); return }
        setPlaying(true)
      } else if (state === 2 && !activeRef.current) setPlaying(false)
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scripted, item.source])

  // YouTube only starts talking after a "listening" handshake, and ignores it until the player
  // has booted — so keep knocking until it answers.
  const onFrameLoad = () => {
    if (!scripted) { setTimeout(() => setShown(true), 600); return }
    if (fallback) { setTimeout(() => setShown(true), 400); return }
    if (item.source !== 'youtube') return
    let n = 0
    const knock = () => {
      frame.current?.contentWindow?.postMessage(JSON.stringify({ event: 'listening', id: index, channel: 'widget' }), '*')
    }
    knock()
    const t = setInterval(() => { if (++n > 40 || !frame.current) clearInterval(t); else knock() }, 150)
    frame.current._knock = t
  }
  useEffect(() => { if (ready && frame.current?._knock) clearInterval(frame.current._knock) }, [ready])
  useEffect(() => () => { if (frame.current?._knock) clearInterval(frame.current._knock) }, [])

  // Active -> play (retry until it confirms). Inactive -> paused, muted, rewound.
  useEffect(() => {
    if (!scripted || !ready || fallback) return undefined
    if (!active) {
      sendMute(true)
      if (playing) { send('pause'); send('seekTo', 0); setPlaying(false) }
      else send('play') // warm-up; onMsg pauses it as soon as it starts
      return undefined
    }
    if (paused) { send('pause'); return undefined }
    let tries = 0
    const go = () => {
      sendMute(mutedRef.current)
      send('play')
      if (++tries >= 20) clearInterval(t)
    }
    const t = setInterval(go, 200)
    go()
    if (playing) clearInterval(t)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, ready, paused, playing, fallback, src])

  // Mute toggle while playing.
  useEffect(() => { if (scripted && ready && active) sendMute(muted) }, [muted]) // eslint-disable-line

  // Safety net: if the player never answers, fall back to a plain autoplay URL.
  useEffect(() => {
    if (!scripted || !active || playing || fallback || paused) return undefined
    const t = setTimeout(() => setFallback(true), ready ? 6000 : 4000)
    return () => clearTimeout(t)
  }, [scripted, active, playing, fallback, paused, ready])

  // The iframe is only revealed once frames are actually moving, so you never see the
  // embed's own play / pause chrome — just the poster, then the video.
  const visible = active && (scripted && !fallback ? (playing || paused) : shown)

  const tap = () => { if (scripted && !fallback) setPaused((p) => !p) }

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

  const yearLabel = item.year ? String(item.year) : item.era_label

  return (
    <section className="card" data-index={index}>
      <div className="stage">
        <div className={`media ${item.source === 'tiktok' ? 'tall' : 'wide'}`}>
          {near && item.thumbnail && <img className="poster" src={item.thumbnail} alt="" loading="lazy" />}
          {src && (
            <iframe key={src} ref={frame} src={src} title={item.title} onLoad={onFrameLoad}
              tabIndex={-1}
              style={{ opacity: visible ? 1 : 0, pointerEvents: 'none', transition: 'opacity .18s ease' }}
              allow="autoplay; encrypted-media; picture-in-picture; fullscreen; clipboard-write"
              allowFullScreen referrerPolicy="strict-origin-when-cross-origin" />
          )}
          {active && (
            <button type="button" className="shield" aria-label={paused ? 'Play' : 'Pause'} onClick={tap} />
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