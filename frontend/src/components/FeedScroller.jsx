import { useCallback, useEffect, useRef, useState } from 'react'
import FeedCard from './FeedCard.jsx'
import Icon from './Icon.jsx'
import Logo from './Logo.jsx'

/**
 * Vertical snap feed. In rewind mode the list is laid out with
 * `column-reverse`: the first item sits at the bottom and you scroll UP
 * the screen... by swiping DOWN. Time literally runs the other way.
 */
export default function FeedScroller({
  items, reverse = false, loading = false, done = false, error = null,
  resetKey, onMore, onItemChange, onHide, onRetry, empty,
}) {
  const ref = useRef(null)
  const [active, setActive] = useState(0)
  const [muted, setMuted] = useState(true)
  const [showHint, setShowHint] = useState(true)

  // Back to the first item when filters or direction change.
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = 0
    setActive(0)
    setShowHint(true)
  }, [resetKey, reverse])

  // Track which card is on screen.
  useEffect(() => {
    const root = ref.current
    if (!root) return undefined
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) setActive(Number(e.target.dataset.index)) })
    }, { root, threshold: 0.6 })
    root.querySelectorAll('.card').forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [items])

  // Prefetch when close to the end.
  useEffect(() => {
    if (active > 0) setShowHint(false)
    if (!done && !loading && items.length && active >= items.length - 3) onMore?.()
  }, [active, items.length, done, loading, onMore])

  const goTo = useCallback((i) => {
    const el = ref.current?.querySelector(`[data-index="${i}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  useEffect(() => {
    const onKey = (e) => {
      if (['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return
      const fwd = reverse ? ['ArrowUp', 'k'] : ['ArrowDown', 'j']
      const bwd = reverse ? ['ArrowDown', 'j'] : ['ArrowUp', 'k']
      if (fwd.includes(e.key)) { e.preventDefault(); goTo(Math.min(active + 1, items.length - 1)) }
      else if (bwd.includes(e.key)) { e.preventDefault(); goTo(Math.max(active - 1, 0)) }
      else if (e.key === 'm') setMuted((m) => !m)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, items.length, reverse, goTo])

  if (!items.length) {
    return (
      <div className="feed-empty">
        {loading ? (
          <><Logo size={56} /><p className="mono muted">Rewinding the tape…</p></>
        ) : error ? (
          <><p>{error}</p><button type="button" className="btn" onClick={onRetry}>Try again</button></>
        ) : empty || (
          <><Logo size={56} animate={false} /><p>Nothing in this corner of time yet.</p>
            <p className="muted">Try another era, or check back once the archive has been crawled.</p></>
        )}
      </div>
    )
  }

  const nextIcon = reverse ? 'up' : 'down'
  const prevIcon = reverse ? 'down' : 'up'

  return (
    <div className="feed-wrap">
      <div ref={ref} className={`scroller ${reverse ? 'reverse' : ''}`}>
        {items.map((it, i) => (
          <FeedCard key={it.id} item={it} index={i}
            active={i === active} near={Math.abs(i - active) <= 2} preload={Math.abs(i - active) <= 1}
            muted={muted} onToggleMute={() => setMuted((m) => !m)}
            onChange={onItemChange} onHide={onHide} />
        ))}
        <div className="feed-end mono muted">
          {loading ? 'Loading more…' : done ? 'You reached the start of time.' : ''}
        </div>
      </div>

      {showHint && items.length > 1 && (
        <div className={`swipe-hint ${reverse ? 'reverse' : ''}`}>
          <Icon name={reverse ? 'down' : 'up'} size={16} />
          {reverse ? 'Rewind mode · swipe down' : 'Swipe up'}
        </div>
      )}

      <div className="nav-arrows">
        <button type="button" className="arrow" aria-label="Previous" disabled={active === 0} onClick={() => goTo(active - 1)}>
          <Icon name={prevIcon} />
        </button>
        <button type="button" className="arrow" aria-label="Next" disabled={active >= items.length - 1} onClick={() => goTo(active + 1)}>
          <Icon name={nextIcon} />
        </button>
      </div>
    </div>
  )
}