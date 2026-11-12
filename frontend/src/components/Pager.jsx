import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { track as trackEvent } from '../lib/events.js'
import { PLAN, useQuality } from '../lib/quality.js'
import FeedCard from './FeedCard.jsx'
import Icon from './Icon.jsx'
import Logo from './Logo.jsx'
import LoadingLogo from './LoadingLogo.jsx'

/*
 * The vertical feed, built like TikTok / Reels / Shorts rather than on browser scroll:
 *
 *  - The track follows your finger 1:1 (GPU transform, no layout), and a flick or a
 *    20% drag pages exactly one video. No CSS scroll-snap, so it never stops between
 *    two videos, and fast scroll-wheel / trackpad inertia can't skip five at once.
 *  - The new video starts the moment you let go (not when the animation ends).
 *  - v6: a POOL of 4 card slots (previous, current, next, the one after) is recycled as
 *    you swipe, like a native RecyclerView. The slot that scrolls out the back is re-used
 *    for the video coming up, so its YouTube player / <video> element is reused instead of
 *    torn down and rebuilt. Booting players is what made v5 slow.
 *  - The video on screen gets the network first: the next one only starts buffering once
 *    yours is playing (or after a short grace period).
 *  - Controls are hidden; a tap reveals them and they fade away after a few seconds.
 *  - Pull down on the first video to refresh, like Reels and TikTok.
 *  - Rewind: forward is locked where you are; swipe DOWN to watch everything you've
 *    already seen in reverse, back to where the session started.
 */

const SNAP_MS = 320
const EASE = 'cubic-bezier(.22,.8,.22,1)'
const PULL_TRIGGER = 72
const POOL = 4
const CHROME_MS = 3200
const WARM_GRACE_MS = 2200

const rubber = (d, k = 0.35, max = 140) => Math.sign(d) * Math.min(max, Math.abs(d) * k)

// Recycle the pool: videos still in the window keep their slot; slots whose video left
// the window are handed to the newcomers. Pure function of (pool, items, positions), so
// running it twice (StrictMode) gives the same answer.
function assignSlots(pool, parked, items, positions) {
  const want = positions.filter((k) => k >= 0 && k < items.length)
  const ids = new Set(want.map((k) => items[k].id))
  const free = []
  pool.forEach((id, s) => { if (id == null || !ids.has(id)) free.push(s) })
  want.forEach((k) => {
    const id = items[k].id
    if (!pool.includes(id)) pool[free.shift()] = id
  })
  const at = new Map(want.map((k) => [items[k].id, k]))
  return pool.map((id, slot) => {
    if (id != null && at.has(id)) {
      const k = at.get(id)
      parked[slot] = items[k]
      return { slot, k, item: items[k], parked: false }
    }
    return parked[slot] ? { slot, k: -1, item: parked[slot], parked: true } : null
  }).filter(Boolean)
}

export default function Pager({
  items, startIndex = 0, loading = false, done = false, error = null, resetKey,
  onMore, onRefresh, onItemChange, onHide, onRetry, empty,
  rewind = false, onRewindEnd, onIndex, onChrome,
}) {
  const vp = useRef(null)
  const track = useRef(null)
  const pullEl = useRef(null)
  const [h, setH] = useState(0)
  const [index, setIndex] = useState(startIndex)
  const [muted, setMuted] = useState(true)
  const [paused, setPaused] = useState(false)
  const [notice, setNotice] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [hint, setHint] = useState(true)
  const [readyId, setReadyId] = useState(null)   // id of the video that is actually playing now
  const [grace, setGrace] = useState(false)       // current video had its head start
  const [chrome, setChrome] = useState(false)     // controls visible
  const { tier } = useQuality()
  const idx = useRef(index)
  idx.current = index
  const live = useRef({})
  live.current = { items, rewind, refreshing, done, loading, h }
  const pool = useRef(Array(POOL).fill(null))          // item id held by each slot
  const parkedItems = useRef(Array(POOL).fill(null))   // last item each slot showed

  // ---------------------------------------------------------------- layout
  useLayoutEffect(() => {
    const el = vp.current
    if (!el) return undefined
    const ro = new ResizeObserver(() => setH(el.clientHeight))
    ro.observe(el)
    setH(el.clientHeight)
    return () => ro.disconnect()
  }, [items.length > 0])

  const setY = useCallback((y, animate) => {
    const t = track.current
    if (!t) return
    t.style.transition = animate ? `transform ${SNAP_MS}ms ${EASE}` : 'none'
    t.style.transform = `translate3d(0, ${y}px, 0)`
  }, [])
  const setPull = useCallback((y, animate, spin) => {
    const p = pullEl.current
    if (!p) return
    p.style.transition = animate ? `transform ${SNAP_MS}ms ${EASE}, opacity ${SNAP_MS}ms` : 'none'
    p.style.transform = `translate3d(-50%, ${Math.min(y, 110) - 56}px, 0) rotate(${spin ? 0 : -y * 3}deg)`
    p.style.opacity = String(Math.min(1, y / PULL_TRIGGER))
  }, [])

  useLayoutEffect(() => { setY(-index * h, false) }, [h]) // eslint-disable-line react-hooks/exhaustive-deps

  // Items removed or inserted above you (a skipped video, "not interested"): stay on the
  // same video instead of jumping.
  const activeId = useRef(null)
  useLayoutEffect(() => {
    const id = activeId.current
    if (id == null) return
    const pos = items.findIndex((it) => it.id === id)
    if (pos >= 0 && pos !== idx.current) {
      setIndex(pos)
      setY(-pos * (live.current.h || 0), false)
    } else if (pos < 0 && idx.current > items.length - 1 + (done ? 1 : 0)) {
      const last = Math.max(0, items.length - 1)
      setIndex(last)
      setY(-last * (live.current.h || 0), false)
    }
  }, [items]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { activeId.current = items[index]?.id ?? null }, [index, items])

  // New list (filters changed / refreshed): back to the top, no animation.
  useEffect(() => {
    setIndex(startIndex)
    setPaused(false)
    setY(-startIndex * (live.current.h || 0), false)
    setHint(true)
  }, [resetKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const flashNotice = useCallback((text, icon) => {
    setNotice({ text, icon, id: Date.now() })
  }, [])
  useEffect(() => {
    if (!notice) return undefined
    const t = setTimeout(() => setNotice(null), 2200)
    return () => clearTimeout(t)
  }, [notice])

  // ---------------------------------------------------------------- controls (tap to reveal)
  const hideT = useRef(null)
  const pausedRef = useRef(paused)
  pausedRef.current = paused
  const scheduleHide = useCallback(() => {
    clearTimeout(hideT.current)
    hideT.current = setTimeout(() => { if (!pausedRef.current) setChrome(false) }, CHROME_MS)
  }, [])
  const poke = useCallback(() => { setChrome(true); scheduleHide() }, [scheduleHide])
  const toggleChrome = useCallback(() => {
    setHint(false)
    setChrome((c) => {
      if (c) clearTimeout(hideT.current)
      else scheduleHide()
      return !c
    })
  }, [scheduleHide])
  useEffect(() => { setChrome(false); clearTimeout(hideT.current) }, [index])
  useEffect(() => { if (!paused && chrome) scheduleHide() }, [paused]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => clearTimeout(hideT.current), [])
  useEffect(() => { onChrome?.(chrome || paused) }, [chrome, paused]) // eslint-disable-line react-hooks/exhaustive-deps

  // The video on screen gets a head start before anything else loads.
  useEffect(() => {
    setGrace(false)
    const t = setTimeout(() => setGrace(true), WARM_GRACE_MS)
    return () => clearTimeout(t)
  }, [index, resetKey])

  // ---------------------------------------------------------------- moving
  // v12: sound is on from the second video. The first swipe / key / arrow is the viewer's own
  // gesture, which is what lets browsers play with sound. Unless they muted it themselves.
  const wantSound = useRef(true)
  const touched = useRef(false)
  useEffect(() => {
    const first = () => {
      touched.current = true
      if (wantSound.current) setMuted(false)
      ;['pointerup', 'touchend', 'keydown', 'click'].forEach((ev) => window.removeEventListener(ev, first, true))
    }
    ;['pointerup', 'touchend', 'keydown', 'click'].forEach((ev) => window.addEventListener(ev, first, true))
    return () => ['pointerup', 'touchend', 'keydown', 'click'].forEach((ev) => window.removeEventListener(ev, first, true))
  }, [])
  const go = useCallback((target, { fromDrag = false, auto = false } = {}) => {
    const { items: list, rewind: rw, done: dn, h: hh } = live.current
    const cur = idx.current
    const max = list.length - 1 + (dn ? 1 : 0)  // +1: the "you're all caught up" card
    if (rw && target > cur) {
      flashNotice('Rewind is on. Swipe down to go back through your feed.', 'down')
      setY(-cur * hh, true)
      return false
    }
    const next = Math.max(0, Math.min(max, target))
    setY(-next * hh, true)
    if (next !== cur) {
      // Remember which video we're moving to right now: a feed update landing before React
      // re-renders must not "keep you on the old video" and snap you back.
      activeId.current = list[next]?.id ?? null
      setIndex(next)
      setPaused(false)
      setHint(false)
      // v13: sound stays on as you scroll, auto-advance included, once you've touched the page
      // (browsers allow sound after the first gesture). A video that refused sound only muted itself.
      if (wantSound.current && (!auto || touched.current)) setMuted(false)
      if (navigator.vibrate && fromDrag) { try { navigator.vibrate(4) } catch { /* not allowed */ } }
    }
    return next !== cur
  }, [flashNotice, setY])

  const toggleMute = useCallback(() => setMuted((m) => { wantSound.current = m; return !m }), [])
  const next = useCallback(() => go(idx.current + 1), [go])
  const prev = useCallback(() => go(idx.current - 1), [go])

  useEffect(() => {
    onIndex?.(index)
    if (!done && !loading && items.length && index >= items.length - 4) onMore?.()
  }, [index, items.length, done, loading]) // eslint-disable-line react-hooks/exhaustive-deps

  // Rewind finished: we're back where the session started.
  useEffect(() => {
    if (!rewind) return
    if (index === 0) {
      flashNotice(items.length > 1 ? 'Back where you started. Rewind complete.' : 'Nothing to rewind yet. Watch a few first.', 'rewind')
      onRewindEnd?.()
    } else if (index > 0) {
      flashNotice(`Rewinding from here · swipe down`, 'down')
    }
  }, [rewind]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (rewind && index === 0) {
      flashNotice('Back where you started. Rewind complete.', 'rewind')
      onRewindEnd?.()
    }
  }, [index]) // eslint-disable-line react-hooks/exhaustive-deps

  // Posters are tiny: fetch the next few in advance so a swipe never lands on a black screen.
  useEffect(() => {
    const step = live.current.rewind ? -1 : 1
    for (let k = 1; k <= 4; k++) {
      const src = items[index + k * step]?.thumbnail
      if (src) { const im = new Image(); im.decoding = 'async'; im.src = src }
    }
  }, [index, items, rewind]) // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = useCallback(async () => {
    if (!onRefresh) return
    setRefreshing(true)
    setY(PULL_TRIGGER - 8, true)
    setPull(PULL_TRIGGER, true, true)
    try { await onRefresh() } finally {
      setRefreshing(false)
      setY(0, true)
      setPull(0, true)
    }
  }, [onRefresh, setPull, setY])

  // ---------------------------------------------------------------- touch / mouse drag
  const g = useRef(null)
  const suppressClick = useRef(false)
  const onPointerDown = (e) => {
    if (e.button !== undefined && e.button !== 0) return
    if (live.current.refreshing) return
    g.current = { id: e.pointerId, y0: e.clientY, x0: e.clientX, t0: performance.now(), pts: [[e.clientY, performance.now()]],
      dragging: false, dy: 0 }
  }
  const lastHover = useRef(0)
  const onPointerMove = (e) => {
    const s = g.current
    if (!s && e.pointerType === 'mouse') {            // desktop: moving the mouse shows controls
      const now = performance.now()
      if (now - lastHover.current > 250) { lastHover.current = now; poke() }
      return
    }
    if (!s || s.id !== e.pointerId) return
    const dy = e.clientY - s.y0
    const dx = e.clientX - s.x0
    if (!s.dragging) {
      if (Math.abs(dy) < 8 || Math.abs(dx) > Math.abs(dy)) return
      s.dragging = true
      try { vp.current.setPointerCapture(e.pointerId) } catch { /* ok */ }
    }
    s.pts.push([e.clientY, performance.now()])
    if (s.pts.length > 6) s.pts.shift()
    const { rewind: rw, items: list, done: dn, h: hh } = live.current
    const cur = idx.current
    const max = list.length - 1 + (dn ? 1 : 0)
    let off = dy
    if (dy > 0 && cur === 0) {
      off = rubber(dy, 0.42, 150)                         // pull to refresh / top edge
      if (!rw && onRefresh) setPull(off, false)
    } else if (dy < 0 && (rw || cur >= max)) {
      off = rubber(dy, rw ? 0.18 : 0.3, rw ? 60 : 120)   // rewind lock / end of feed
    }
    s.dy = off
    setY(-cur * hh + off, false)
  }
  const onPointerUp = (e) => {
    const s = g.current
    g.current = null
    if (!s || !s.dragging) return
    suppressClick.current = true
    setTimeout(() => { suppressClick.current = false }, 60)
    const [y1, t1] = s.pts[0]
    const [y2, t2] = s.pts[s.pts.length - 1]
    const v = (y2 - y1) / Math.max(1, t2 - t1)             // px/ms, negative = flick up
    const { h: hh, rewind: rw } = live.current
    const cur = idx.current
    if (cur === 0 && s.dy > 0 && !rw && onRefresh) {
      if (s.dy >= PULL_TRIGGER) { refresh(); return }
      setPull(0, true)
      setY(0, true)
      return
    }
    const far = Math.abs(s.dy) > hh * 0.2
    const fast = Math.abs(v) > 0.45
    if ((far || fast) && Math.sign(s.dy || -v) < 0) go(cur + 1, { fromDrag: true })
    else if ((far || fast) && Math.sign(s.dy || -v) > 0) go(cur - 1, { fromDrag: true })
    else setY(-cur * hh, true)
    if (e?.type === 'pointercancel') setPull(0, true)
  }

  // ---------------------------------------------------------------- wheel / trackpad / keys
  useEffect(() => {
    const el = vp.current
    if (!el) return undefined
    let acc = 0
    let locked = false
    let idle = null
    let pull = 0
    const onWheel = (e) => {
      if (e.ctrlKey) return
      e.preventDefault()
      clearTimeout(idle)
      idle = setTimeout(() => {
        acc = 0; locked = false
        if (pull && !live.current.refreshing) { pull = 0; setPull(0, true); setY(-idx.current * live.current.h, true) }
      }, 180)
      if (locked || live.current.refreshing) return
      acc += e.deltaY
      if (idx.current === 0 && acc < 0 && !live.current.rewind && onRefresh) {
        pull = rubber(-acc, 0.35, 120)
        setPull(pull, false)
        setY(pull, false)
        if (pull >= PULL_TRIGGER) { locked = true; pull = 0; refresh() }
        return
      }
      if (Math.abs(acc) > 50) {
        locked = true
        if (acc > 0) next(); else prev()
        acc = 0
      }
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => { el.removeEventListener('wheel', onWheel); clearTimeout(idle) }
  }, [next, prev, refresh, onRefresh, setPull, setY, items.length > 0])

  useEffect(() => {
    const onKey = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName) || e.metaKey || e.ctrlKey) return
      if (['ArrowDown', 'j', 'PageDown'].includes(e.key)) { e.preventDefault(); next() }
      else if (['ArrowUp', 'k', 'PageUp'].includes(e.key)) { e.preventDefault(); prev() }
      else if (e.key === 'm') toggleMute()
      else if (e.key === ' ') { e.preventDefault(); setPaused((p) => !p); poke() }
      else if (e.key === 'r' && idx.current === 0) refresh()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, prev, refresh, poke, toggleMute])

  // ---------------------------------------------------------------- card callbacks (stable for memo)
  const togglePause = useCallback(() => setPaused((p) => !p), [])
  const autoMuted = useCallback(() => setMuted(true), [])
  const started = useCallback((id) => setReadyId(id), [])
  // A video that can't play (removed, not embeddable, dead file) is reported and skipped
  // automatically: the next one slides into its place and starts.
  // v9: a clip finished -> slide to the next video by itself (Reels / TikTok "auto scroll"),
  // unless the viewer is busy with the controls, then the clip just loops.
  const chromeRef = useRef(chrome)
  chromeRef.current = chrome
  const clipEnded = useCallback((id) => {
    const { items: list, rewind: rw } = live.current
    if (list[idx.current]?.id !== id || chromeRef.current || pausedRef.current) return false
    return go(idx.current + (rw ? -1 : 1), { auto: true })
  }, [go])
  // A video that shows nothing for a long time on a weak link: move on (it stays in the
  // catalogue; it's probably the connection, not the video).
  const skipSlow = useCallback((id) => {
    const { items: list, rewind: rw } = live.current
    if (list[idx.current]?.id !== id || pausedRef.current) return
    if (go(idx.current + (rw ? -1 : 1), { auto: true })) flashNotice('Skipped a slow video', 'down')
  }, [go, flashNotice])
  const failed = useCallback((item, code) => {
    trackEvent({ type: 'broken', item_id: item.id, code })
    if (live.current.items[idx.current]?.id === item.id) flashNotice('Skipped a video that is no longer available', 'down')
    onHide?.(item.id)
  }, [flashNotice, onHide])

  // ---------------------------------------------------------------- render
  if (!items.length) {
    return (
      <div className="feed-empty">
        {loading ? (
          <><LoadingLogo size={72} /><p className="mono muted">Rewinding the tape…</p></>
        ) : error ? (
          <><p>{error}</p><button type="button" className="btn" onClick={onRetry}>Try again</button></>
        ) : empty || (
          <><Logo size={56} animate={false} /><p>Nothing in this corner of time yet.</p>
            <p className="muted">Try other filters, or check back once the archive has been crawled.</p></>
        )}
      </div>
    )
  }

  const dir = rewind ? -1 : 1
  const atEnd = done && index === items.length
  const cur = items[index]
  // Slow link: the next video only starts buffering after the current one is playing,
  // so the two never fight over the same few kbit/s. Fast link: after a short head start.
  const headStart = readyId === cur?.id || (PLAN[tier].warmFull && grace) || atEnd
  const view = assignSlots(pool.current, parkedItems.current, items, [index - dir, index, index + dir, index + 2 * dir])

  return (
    <div className="feed-wrap">
      <div ref={vp} className="pager" onPointerDown={onPointerDown} onPointerMove={onPointerMove}
        onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
        onClickCapture={(e) => { if (suppressClick.current) { e.stopPropagation(); e.preventDefault() } }}>
        <div ref={track} className="track">
          {h > 0 && view.map(({ slot, k, item, parked }) => (
            <div key={`slot${slot}`} className={`slot ${parked ? 'parked' : ''}`}
              style={{ top: parked ? -3 * h : k * h, height: h }} aria-hidden={parked || k !== index}>
              <FeedCard item={item} parked={parked}
                active={!parked && k === index && !atEnd}
                warm={!parked && k === index + dir && headStart}
                ahead={!parked && k === index + 2 * dir && headStart}
                near={!parked && Math.abs(k - index) <= 1}
                canBoot={headStart}
                muted={muted} paused={!parked && k === index && paused} rewind={rewind}
                chrome={!parked && k === index && chrome}
                onTogglePause={togglePause} onToggleMute={toggleMute} onAutoMuted={autoMuted}
                onToggleChrome={toggleChrome} onPoke={poke}
                onChange={onItemChange} onHide={onHide} onFail={failed} onStarted={started}
                onClipEnd={clipEnded} onSkip={skipSlow} />
            </div>
          ))}
          {h > 0 && done && (
            <div className="slot end-card" style={{ top: items.length * h, height: h }}>
              <Logo size={64} animate={false} />
              <p>You're all caught up for these filters.</p>
              <p className="muted small">Pull down at the top for a fresh feed, or widen your filters.</p>
              {onRefresh && <button type="button" className="btn" onClick={() => { go(0); refresh() }}>Refresh feed</button>}
            </div>
          )}
          {h > 0 && loading && !done && index >= items.length - 1 && (
            <div className="slot end-card" style={{ top: items.length * h, height: h }}>
              <LoadingLogo size={60} /><p className="mono muted">Loading more…</p>
            </div>
          )}
        </div>
      </div>

      {onRefresh && (
        <div ref={pullEl} className={`pull ${refreshing ? 'spinning' : ''}`} aria-hidden={!refreshing}>
          {refreshing ? <LoadingLogo size={30} /> : <Logo size={34} animate={false} />}
          {refreshing && <span className="mono">Fresh feed…</span>}
        </div>
      )}

      {rewind && (
        <div className="rewind-banner mono" role="status">
          <Icon name="rewind" size={16} /> Rewinding · {index} to go · swipe <Icon name="down" size={14} />
        </div>
      )}

      {notice && (
        <div key={notice.id} className="notice" role="status">
          {notice.icon && <Icon name={notice.icon} size={18} />} {notice.text}
        </div>
      )}

      {hint && !chrome && !rewind && items.length > 1 && index === 0 && (
        <div className="swipe-hint"><Icon name="up" size={16} /> {window.matchMedia?.('(pointer: fine)').matches ? 'Scroll or ↓ for next' : 'Swipe up · tap for controls'}</div>
      )}

      <div className="nav-arrows">
        <button type="button" className="arrow" aria-label="Previous" disabled={index === 0} onClick={prev}>
          <Icon name="up" />
        </button>
        <button type="button" className={`arrow ${rewind ? 'locked' : ''}`} aria-label="Next"
          disabled={!rewind && index >= items.length - 1 + (done ? 1 : 0)} onClick={next}>
          <Icon name="down" />
        </button>
      </div>
    </div>
  )
}