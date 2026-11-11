import { memo, useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { useAuth } from '../context.js'
import { fmtTime, frameFor, isTall, playerKind, shareUrl } from '../embed.js'
import { track } from '../lib/events.js'
import { MODES, qualityLabel, reportStall, reportStart, setMode, useQuality } from '../lib/quality.js'
import { LENGTHS, clipWindow, hostedWindow, setClipLength, useClipLength } from '../lib/clip.js'
import Icon from './Icon.jsx'
import LoadingLogo from './LoadingLogo.jsx'
import Sponsor from './Sponsor.jsx'
import Player from './players/Player.jsx'

/*
 * One card of the feed. Two layers:
 *
 *  - FeedCard: lives in a recycled pool slot (see Pager), owns the player and the
 *    watch-time bookkeeping. It is NOT remounted when a new video lands in the slot,
 *    so the player inside it can be reused.
 *  - CardUI: everything you see on top of the video. Remounted per video (key=item.id)
 *    so hearts, menus and the intro caption always start fresh.
 *
 * The screen is clean by default: just the video, a hairline progress bar and a short
 * intro caption. Tap once and the controls fade in (like, save, follow, share, sound,
 * more, play/pause, title, scrubber); they fade out again after a few seconds.
 * Double-tap anywhere likes. With a mouse: move to show controls, click to pause.
 */

const P0 = { started: false, buffering: false, t: 0, d: 0 }

// State that resets by itself whenever a different video lands in this slot.
function useItemState(id, init) {
  const [s, setS] = useState({ id, v: init })
  const idRef = useRef(id)
  idRef.current = id
  const set = useCallback((u) => setS((prev) => {
    const base = prev.id === idRef.current ? prev.v : init
    const v = typeof u === 'function' ? u(base) : u
    return v === base && prev.id === idRef.current ? prev : { id: idRef.current, v }
  }), []) // eslint-disable-line react-hooks/exhaustive-deps
  return [s.id === id ? s.v : init, set]
}

const compact = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(n >= 1e4 ? 0 : 1)}K` : String(n || 0))

function Action({ icon, label, on, onClick, count, children }) {
  return (
    <button type="button" className={`act ${on ? 'on' : ''}`} onClick={onClick} aria-label={label} aria-pressed={on} title={label}>
      <span className="act-icon">{children || <Icon name={icon} size={24} />}</span>
      {count !== undefined && <span className="act-count mono">{count}</span>}
    </button>
  )
}

function CardUI({
  item, active, chrome, muted, paused, play, onTogglePause, onToggleMute, onToggleChrome, onPoke,
  onChange, onHide, seek, clip, onFull, slow, late, onSkip,
}) {
  const { user, setUser } = useAuth() || {}
  const length = useClipLength()
  const { mode, h } = useQuality()
  const [hearts, setHearts] = useState([])
  const [toast, setToast] = useState('')
  const [flash, setFlash] = useState(null)
  const [sheet, setSheet] = useState(false)
  const [scrub, setScrub] = useState(null)       // seconds while dragging the scrubber
  const [followOverride, setFollowOverride] = useState(null)
  const wrap = useRef(null)

  const followKey = item.author ? `${item.source}|${item.author.trim().toLowerCase().slice(0, 60)}` : null
  const following = followOverride ?? Boolean(followKey && user?.prefs?.follows?.includes(followKey))

  useEffect(() => {
    if (!toast) return undefined
    const t = setTimeout(() => setToast(''), 1800)
    return () => clearTimeout(t)
  }, [toast])
  useEffect(() => { if (!active) setSheet(false) }, [active])

  const toggle = async (kind, forceOn = false) => {
    onPoke?.()
    const on = kind === 'like' ? item.liked : item.saved
    if (forceOn && on) return
    const optimistic = kind === 'like'
      ? { ...item, liked: !on, likes: Math.max(0, item.likes + (on ? -1 : 1)) }
      : { ...item, saved: !on }
    onChange?.(optimistic)
    if (kind === 'save') setToast(on ? 'Removed from saved' : 'Saved to your profile')
    try {
      const r = await api.interact(item.id, on ? `un${kind}` : kind)
      onChange?.(r.item)
    } catch {
      onChange?.(item)
      setToast('Could not save that')
    }
  }

  const follow = async () => {
    onPoke?.()
    if (!followKey) return
    const next = !following
    setFollowOverride(next)
    setToast(next ? `Following ${item.author}` : `Unfollowed ${item.author}`)
    try {
      const r = await api.follow({ source: item.source, author: item.author, on: next })
      setUser?.(r.user)
      setFollowOverride(null)
    } catch {
      setFollowOverride(!next)
      setToast('Could not follow right now')
    }
  }

  const share = async () => {
    onPoke?.()
    const url = shareUrl(item)
    api.interact(item.id, 'share').catch(() => {})
    try {
      if (navigator.share) await navigator.share({ title: item.title, url })
      else { await navigator.clipboard.writeText(url); setToast('Link copied') }
    } catch { /* share sheet dismissed */ }
  }

  const copyLink = async () => {
    try { await navigator.clipboard.writeText(shareUrl(item)); setToast('Link copied') } catch { setToast('Could not copy') }
    setSheet(false)
  }

  const hide = () => {
    setSheet(false)
    api.interact(item.id, 'hide').catch(() => {})
    onHide?.(item.id)
  }

  // Tap: show / hide controls (touch) or pause (mouse). Double tap: like, with a heart
  // where you tapped.
  const lastTap = useRef(0)
  const single = useRef(null)
  const ptr = useRef('touch')
  const onTap = (e) => {
    const now = Date.now()
    const rect = wrap.current.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    if (now - lastTap.current < 280) {
      clearTimeout(single.current)
      lastTap.current = 0
      const id = now
      setHearts((h) => [...h, { id, x, y, r: Math.round(Math.random() * 40 - 20) }])
      setTimeout(() => setHearts((h) => h.filter((p) => p.id !== id)), 900)
      toggle('like', true)
      return
    }
    lastTap.current = now
    const mouse = ptr.current === 'mouse'
    single.current = setTimeout(() => {
      if (mouse) {
        setFlash(paused ? 'play' : 'pause')
        setTimeout(() => setFlash(null), 500)
        onTogglePause?.()
        onPoke?.()
      } else onToggleChrome?.()
    }, 240)
  }
  useEffect(() => () => clearTimeout(single.current), [])

  const centerPlay = () => {
    setFlash(paused ? 'play' : 'pause')
    setTimeout(() => setFlash(null), 500)
    onTogglePause?.()
    onPoke?.()
  }

  // Scrubber: drag along the bar to seek (doesn't start a swipe).
  const bar = useRef(null)
  const d = play.d || item.duration || 0
  const posFrom = (e) => {
    const r = bar.current.getBoundingClientRect()
    return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * d
  }
  const scrubDown = (e) => {
    if (!d) return
    e.stopPropagation()
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* ok */ }
    if (clip && !clip.hosted) onFull?.()      // seeking past a cut of the original means they want this one
    setScrub(posFrom(e))
    onPoke?.()
  }
  const scrubMove = (e) => { if (scrub != null) { e.stopPropagation(); setScrub(posFrom(e)); onPoke?.() } }
  const scrubUp = (e) => {
    if (scrub == null) return
    e.stopPropagation()
    seek?.(posFrom(e))
    setScrub(null)
  }

  const yearLabel = item.year ? String(item.year) : item.era_label
  const culture = item.regions?.find((r) => !['asian', 'european', 'arabic', 'latin'].includes(r.id)) || item.regions?.[0]
  const interactive = playerKind(item) === 'frame' && frameFor(item)?.interactive
  const showChrome = active && (chrome || paused || scrub != null)
  const clipFrac = clip ? Math.max(0, Math.min(1, (play.t - clip.from) / (clip.to - clip.from))) : null
  const frac = scrub != null && d ? scrub / d : clip ? clipFrac : d ? Math.min(1, play.t / d) : 0
  // "Watch full" teaser: shows in the last seconds of a clip (and whenever controls are up).
  const teaser = clip && !clip.whole && active && play.started && (showChrome || play.t >= clip.to - 7)
  const waiting = active && !play.started && !paused        // not started yet
  const loading = waiting || (active && play.buffering && !paused)
  const qLabel = qualityLabel(mode, h)

  return (
    <div ref={wrap} className={`ui ${showChrome ? 'show' : ''}`}>
      <button type="button" className={`shield ${interactive ? 'partial' : ''}`}
        aria-label={showChrome ? 'Hide controls' : 'Show controls'}
        onPointerDown={(e) => { ptr.current = e.pointerType || 'touch' }} onClick={onTap} />

      {/* v12 loading card: only when a video takes more than ~1 s to start. The thumbnail stays
          behind it, your logo turns in the middle, a "Sponsored" box sits at the bottom.
          Gone the moment the video plays. */}
      {waiting && late && (
        <div className="load-card" aria-live="polite">
          <LoadingLogo size={76} />
          <div className="load-label" aria-hidden="true">
            <span className="badge solid mono">{yearLabel}</span>
            <span className="intro-title">{item.title}</span>
          </div>
          <Sponsor />
        </div>
      )}
      {/* Mid-video buffering: just the logo. */}
      {active && play.started && play.buffering && !paused && (
        <div className="loader" aria-hidden="true"><LoadingLogo size={52} /></div>
      )}
      {active && slow && !play.started && !paused && (
        <button type="button" className="slow-chip" onClick={(e) => { e.stopPropagation(); onSkip?.() }}>
          Slow one · Next <Icon name="down" size={16} />
        </button>
      )}
      {teaser && (
        <button type="button" className={`full-chip mono ${showChrome ? 'up' : ''}`}
          onClick={(e) => { e.stopPropagation(); onFull?.(); onPoke?.() }}>
          <Icon name="play" size={14} /> Watch full{(item.duration || (!clip.hosted && d)) ? ` · ${fmtTime(item.duration || d)}` : ''}
        </button>
      )}
      <div className="scrim" aria-hidden="true" />

      {active && !showChrome && play.started && (
        <div className="intro" aria-hidden="true">
          <span className="badge solid mono">{yearLabel}</span>
          <span className="intro-title">{item.title}</span>
        </div>
      )}

      {active && (
        <button type="button" className={`center-play ${showChrome && !loading ? 'on' : ''}`} onClick={centerPlay}
          aria-label={paused ? 'Play' : 'Pause'} tabIndex={showChrome ? 0 : -1}>
          <Icon name={paused ? 'play' : 'pause'} size={34} />
        </button>
      )}
      {flash && <div className={`flash-icon ${flash}`} aria-hidden="true"><Icon name={flash} size={56} /></div>}
      {hearts.map((h) => (
        <span key={h.id} className="burst" style={{ left: h.x, top: h.y, '--r': `${h.r}deg` }} aria-hidden="true">
          <Icon name="heart" size={96} />
        </span>
      ))}

      <aside className="actions" aria-hidden={!showChrome}>
        {item.author && (
          <button type="button" className={`act follow ${following ? 'on' : ''}`} onClick={follow}
            aria-label={following ? `Unfollow ${item.author}` : `Follow ${item.author}`} title={following ? 'Following' : 'Follow'}>
            <span className="avatar-ring">{item.author.trim()[0]?.toUpperCase() || '?'}</span>
            <span className="follow-badge"><Icon name={following ? 'check' : 'plus'} size={14} /></span>
          </button>
        )}
        <Action icon="heart" label={item.liked ? 'Unlike' : 'Like'} on={item.liked} count={compact(item.likes)} onClick={() => toggle('like')} />
        <Action icon="bookmark" label={item.saved ? 'Remove from saved' : 'Save'} on={item.saved} count={item.saved ? 'Saved' : 'Save'} onClick={() => toggle('save')} />
        <Action icon="share" label="Share" count="Share" onClick={share} />
        <Action icon={muted ? 'mute' : 'volume'} label={muted ? 'Sound on' : 'Mute'} count={muted ? 'Off' : 'On'}
          onClick={() => { onToggleMute?.(); onPoke?.() }} />
        <Action icon="more" label="More" count="More" onClick={() => { setSheet(true); onPoke?.() }} />
      </aside>

      <footer className="info" aria-hidden={!showChrome}>
        <div className="badges">
          <span className="badge solid mono">{yearLabel}</span>
          <span className="badge mono">{item.category_label}</span>
          {culture && <span className="badge mono">{culture.label}</span>}
          {item.channels?.[0] && <span className="badge mono">{item.channels[0].label}</span>}
        </div>
        <h2 className="title">{item.title}</h2>
        <p className="author">
          {item.author && <strong>@{item.author}</strong>}
          <span className="via mono">{item.author ? ' · ' : ''}via {item.source_label}</span>
        </p>
        {item.reason && <p className="reason mono">{item.reason}</p>}
        <div className="scrubber" ref={bar} onPointerDown={scrubDown} onPointerMove={scrubMove}
          onPointerUp={scrubUp} onPointerCancel={() => setScrub(null)}>
          <div className="scrub-track"><span style={{ transform: `scaleX(${frac})` }} /><i style={{ left: `${frac * 100}%` }} /></div>
          <div className="scrub-time mono">
            <span>{fmtTime(scrub ?? play.t)}</span>
            <button type="button" className="q-chip" onClick={(e) => { e.stopPropagation(); setSheet(true) }}>{qLabel}</button>
            <span>{d ? fmtTime(d) : '--:--'}</span>
          </div>
        </div>
      </footer>

      {active && !showChrome && (
        <div className="hairline" aria-hidden="true"><span style={{ transform: `scaleX(${frac})` }} /></div>
      )}
      {active && !showChrome && muted && play.started && (
        <button type="button" className="sound-chip" onClick={() => onToggleMute?.()} aria-label="Turn sound on">
          <Icon name="mute" size={16} /><span>Tap for sound</span>
        </button>
      )}

      {sheet && (
        <div className="card-sheet-backdrop" onClick={() => setSheet(false)} onPointerDown={(e) => e.stopPropagation()}>
          <div className="card-sheet" role="dialog" aria-label="More options" onClick={(e) => e.stopPropagation()}>
            <div className="grabber" />
            <h4 className="mono">Playback quality</h4>
            <div className="q-options">
              {MODES.map((m) => (
                <button key={m.id} type="button" className={`q-opt ${mode === m.id ? 'on' : ''}`} onClick={() => setMode(m.id)}>
                  <strong>{m.id === mode && m.id !== 'saver' ? `${m.label} · ${h}p` : m.label}</strong>
                  <span>{m.hint}</span>
                </button>
              ))}
            </div>
            <h4 className="mono">Clip length</h4>
            <div className="q-options four">
              {LENGTHS.map((l) => (
                <button key={l.id} type="button" className={`q-opt ${length === l.id ? 'on' : ''}`} onClick={() => setClipLength(l.id)}>
                  <strong>{l.label}</strong>
                  <span>{l.hint}</span>
                </button>
              ))}
            </div>
            <div className="sheet-list">
              {onHide && <button type="button" onClick={hide}><Icon name="eyeOff" size={20} /> Not interested</button>}
              <a href={item.url} target="_blank" rel="noopener noreferrer" onClick={() => setSheet(false)}>
                <Icon name="external" size={20} /> Open on {item.source_label}
              </a>
              <button type="button" onClick={copyLink}><Icon name="link" size={20} /> Copy link</button>
            </div>
            <button type="button" className="btn ghost sheet-close" onClick={() => setSheet(false)}>Close</button>
          </div>
        </div>
      )}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  )
}

function FeedCard({
  item, active, warm, ahead, near, parked, muted, paused, rewind, chrome, canBoot,
  onTogglePause, onToggleMute, onAutoMuted, onToggleChrome, onPoke,
  onChange, onHide, onFail, onStarted, onClipEnd, onSkip,
}) {
  const [play, setPlay] = useItemState(item.id, P0)
  const [full, setFull] = useItemState(item.id, false)   // "Watch full" tapped for this video
  const [slow, setSlow] = useItemState(item.id, false)   // no first frame after a few seconds
  const [late, setLate] = useItemState(item.id, false)   // no first frame after ~1 s: loading card
  const length = useClipLength()
  const { mode } = useQuality()
  // A hosted clip (144p saver / 240p auto) when the chosen length fits in it, else a window of the original.
  const hosted = full ? null : hostedWindow(item, length, mode)
  let win = hosted || clipWindow(item, length)
  // Length unknown until the player reports it: a short video turns out to need no clip.
  if (win && !hosted && !item.duration && play.d && play.d <= length * 1.25) win = null
  // "Watch full" removes the end. After a hosted clip it continues in the original, from the same spot.
  if (full && full.at != null) win = { ...(win || {}), from: Math.floor(full.at) }
  const clip = win && { ...win, to: full ? null : win.to }
  const clipped = clip && clip.to != null ? clip : null
  const clipLen = clipped ? clipped.to - clipped.from : 0
  const control = useRef({})

  // ---- impression (watch time) bookkeeping for the ranker
  const imp = useRef(null)
  const tick = () => {
    const s = imp.current
    if (s?.since) { s.watch += performance.now() - s.since; s.since = null }
  }
  const finish = () => {
    const s = imp.current
    if (!s) return
    tick()
    imp.current = null
    if (s.watch > 0 || s.played) {
      track({ type: 'impression', item_id: s.id, watch_ms: Math.round(s.watch), duration_ms: Math.round((s.dur || 0) * 1000),
        loops: s.loops, unmuted: s.unmuted, rewind: s.rewind, clip_ms: s.clip ? s.clip * 1000 : undefined })
    }
  }
  const startT = useRef(null)     // when this video came on screen (for the quality engine)
  const stallT = useRef(null)
  useEffect(() => {
    if (!active) return undefined
    imp.current = { id: item.id, watch: 0, since: null, loops: 0, dur: item.duration || 0, unmuted: !muted, rewind, played: false }
    startT.current = performance.now()
    const onHidden = () => { if (document.visibilityState === 'hidden') finish() }
    window.addEventListener('pagehide', finish)
    document.addEventListener('visibilitychange', onHidden)
    return () => {
      window.removeEventListener('pagehide', finish)
      document.removeEventListener('visibilitychange', onHidden)
      finish()
      startT.current = null
      clearTimeout(stallT.current)
      setPlay(P0)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, item.id])
  useEffect(() => { if (active && !muted && imp.current) imp.current.unmuted = true }, [muted, active])
  useEffect(() => { if (paused) tick() }, [paused])
  // The ranker judges completion against what was actually offered: the clip, not the film.
  useEffect(() => { if (active && imp.current) imp.current.clip = clipLen || 0 }, [active, item.id, clipLen])

  // Slow start: after a few seconds without a first frame offer "Next", and after a while
  // move on by itself, so a weak connection never leaves you staring at a spinner.
  useEffect(() => {
    if (!active || play.started || paused) return undefined
    const t0 = setTimeout(() => setLate(true), 1000)
    const t1 = setTimeout(() => setSlow(true), 4500)
    const t2 = setTimeout(() => onSkip?.(item.id), 12000)
    return () => { clearTimeout(t0); clearTimeout(t1); clearTimeout(t2) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, item.id, play.started, paused])

  const live = useRef({})
  live.current = { active, paused, started: play.started, item, clip: clipped }
  const cb = {
    onPlaying: (on) => {
      if (on) {
        setPlay((p) => (p.started && !p.buffering ? p : { ...p, started: true, buffering: false }))
        onStarted?.(live.current.item.id)
        if (live.current.active && startT.current != null) {
          reportStart(performance.now() - startT.current)
          startT.current = null
        }
        clearTimeout(stallT.current)
        const s = imp.current
        if (s && !s.since && !live.current.paused) { s.since = performance.now(); s.played = true }
      } else tick()
    },
    onProgress: (t, d) => {
      if (d > 0) {
        setPlay((p) => (Math.abs(p.t - t) < 0.2 && p.d === d ? p : { ...p, t, d }))
        if (imp.current) imp.current.dur = d
      }
    },
    onBuffering: (on) => {
      setPlay((p) => (p.buffering === on ? p : { ...p, buffering: on }))
      clearTimeout(stallT.current)
      // A real stall (not a blip) on the video you're watching teaches the quality engine.
      if (on && live.current.active && live.current.started) stallT.current = setTimeout(reportStall, 700)
    },
    onLoop: () => { if (imp.current) imp.current.loops += 1 },
    // End of a clip: true = the feed moved on to the next video; false = loop the clip.
    onClipEnd: () => {
      if (!live.current.clip || !live.current.active) return false
      if (imp.current) imp.current.loops += 1     // watched the whole clip
      return Boolean(onClipEnd?.(live.current.item.id))
    },
    onAutoMuted,
    onFail: (code) => onFail?.(live.current.item, code),
  }

  const tall = isTall(item)
  const kind = playerKind(item)
  const showVideo = active && play.started

  return (
    <section className="card">
      <div className="stage">
        <div className={`media ${tall ? 'tall' : 'wide'}`}>
          {near && item.thumbnail && <img className="backdrop" src={item.thumbnail} alt="" aria-hidden="true" />}
          {!parked && item.thumbnail && (
            <img className={`poster ${active && !play.started ? 'kenburns' : ''}`} src={item.thumbnail} alt="" decoding="async" />
          )}
          <div className={`player ${kind} ${tall ? 'tall' : 'wide'}`} style={{ opacity: showVideo ? 1 : 0 }}>
            <Player item={item} active={active} warm={warm} ahead={ahead} near={near} muted={muted} paused={paused}
              cb={cb} control={control} canBoot={canBoot} clip={clip} />
          </div>
          {!parked && (
            <CardUI key={item.id} item={item} active={active} chrome={chrome} muted={muted} paused={paused} play={play}
              onTogglePause={onTogglePause} onToggleMute={onToggleMute} onToggleChrome={onToggleChrome} onPoke={onPoke}
              onChange={onChange} onHide={onHide} seek={(s) => control.current.seek?.(s)}
              clip={clipped} onFull={() => setFull({ at: item.clip ? item.clip.from + (play.t || 0) : null })} slow={slow} late={late} onSkip={() => onSkip?.(item.id)} />
          )}
        </div>
      </div>
    </section>
  )
}

export default memo(FeedCard)
