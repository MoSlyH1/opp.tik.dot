import { Component, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { dmIds, dmLibId, dmReport, frameFor, loadDailymotion, loadYouTube, playerKind, tiktokUrl } from '../../embed.js'
import { PLAN, dmQuality, lowestRendition, pickRendition, preconnect, useQuality, viaEdge, ytCap } from '../../lib/quality.js'

/*
 * One component, six engines. Every engine follows the same contract so the feed
 * never has to care where a video comes from:
 *
 *   active  -> play NOW (from `item.start`), with the current mute state
 *   warm    -> the next video: buffer quietly so the swipe to it starts instantly
 *   ahead   -> the one after: connect + fetch its first bytes (fast tiers only)
 *   paused  -> the viewer tapped to pause
 *   cb.onPlaying(bool) / onProgress(t, d) / onBuffering(bool) / onLoop() / onFail(code) / onAutoMuted()
 *   control.current = { seek(seconds) }
 *
 * v6: the feed recycles a pool of 4 card slots (Pager.jsx), and this component lives
 * inside a slot. So a YouTube player is created ONCE per slot and then reused with
 * cueVideoById / loadVideoById for every YouTube video that lands in that slot. Booting
 * a YouTube iframe (HTML + ~1 MB of player JS, parsed per iframe) was the single biggest
 * delay in v5; switching the video inside a live player skips all of it.
 */

const useLatest = (v) => { const r = useRef(v); r.current = v; return r }

// ---------------------------------------------------------------- YouTube (IFrame Player API, pooled)
function YouTube({ item, active, warm, ahead, near, muted, paused, cb, control, canBoot, q, clip }) {
  const box = useRef(null)
  const host = useRef(null)
  const player = useRef(null)
  const [ready, setReady] = useState(false)
  const [dims, setDims] = useState(null)
  const vid = useRef(null)          // video currently loaded in the player
  const state = useRef(-1)
  const ever = useRef(false)
  const warmed = useRef(false)
  const was = useRef(false)
  const want = item?.external_id || null
  // v9: clips play [from, to) of the video; the end is checked in the progress loop
  // (not YouTube's endSeconds), so "Watch full" just keeps going without reloading.
  const start = clip ? clip.from : item?.start || 0
  const end = clip?.to ?? null
  const live = useLatest({ active, muted, paused, want, start, end })
  const clipDone = useRef(false)
  const calls = useLatest(cb)

  // Create the player the first time this slot needs a YouTube video, then keep it.
  const [boot, setBoot] = useState(false)
  if (!boot && want && (active || (canBoot && (warm || near || ahead)))) setBoot(true)

  useEffect(() => {
    if (!boot) return undefined
    let dead = false
    loadYouTube().then((YT) => {
      if (dead || !host.current) return
      const el = document.createElement('div')
      host.current.appendChild(el)
      const first = live.current.want
      vid.current = first
      player.current = new YT.Player(el, {
        host: 'https://www.youtube-nocookie.com',
        videoId: first, width: '100%', height: '100%',
        playerVars: { autoplay: 0, mute: 1, controls: 0, playsinline: 1, rel: 0, modestbranding: 1,
          iv_load_policy: 3, disablekb: 1, fs: 0, cc_load_policy: 0, start: live.current.start,
          origin: window.location.origin },
        events: {
          onReady: () => { if (!dead) setReady(true) },
          onError: (e) => { if (live.current.want) calls.current.onFail?.(`yt:${e.data}`) },
          onStateChange: (e) => {
            const p = player.current
            // Late events from the previous video in this slot: ignore.
            const id = p?.getVideoData?.()?.video_id
            if (id && id !== vid.current) return
            state.current = e.data
            const L = live.current
            if (L.active && L.want) calls.current.onBuffering?.(e.data === 3)
            if (e.data === 1) {
              ever.current = true
              if (!L.active || !L.want) {          // warm-up buffer done: park it at the start
                warmed.current = true
                p.pauseVideo(); p.seekTo(L.start, true)
                return
              }
              calls.current.onPlaying?.(true)
            } else if (e.data === 0) {             // ended -> next clip, or loop like TikTok
              if (L.active && calls.current.onClipEnd?.()) return
              p.seekTo(L.start, true); p.playVideo()
              calls.current.onLoop?.()
            } else if (e.data === 2) {
              if (L.active && L.want && !L.paused) p.playVideo() // paused by YouTube, not by us
              else calls.current.onPlaying?.(false)
            }
          },
        },
      })
    }).catch(() => calls.current.onFail?.('yt:api'))
    return () => {
      dead = true
      try { player.current?.destroy() } catch { /* already gone */ }
      player.current = null
      if (host.current) host.current.innerHTML = ''
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boot])

  // A different video landed in this slot: swap it inside the live player.
  useEffect(() => {
    const p = player.current
    if (!ready || !p) return
    if (!want) { try { p.pauseVideo(); p.mute() } catch { /* not ready */ } return }
    if (want === vid.current) return
    vid.current = want
    state.current = -1
    clipDone.current = false
    ever.current = false
    warmed.current = false
    was.current = false
    if (live.current.active) {
      if (live.current.muted) p.mute(); else p.unMute()
      p.loadVideoById({ videoId: want, startSeconds: start })
    } else {
      p.mute()
      p.cueVideoById({ videoId: want, startSeconds: start })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [want, ready])

  // Buffer the next video in advance (muted, invisible), then park it at the start.
  useEffect(() => {
    const p = player.current
    if (!ready || !p || !want || active || !warm || warmed.current || !PLAN[q.tier].warmFull) return
    p.mute(); p.playVideo()
  }, [ready, warm, active, want, q.tier])

  useEffect(() => {
    const p = player.current
    if (!ready || !p || !want) return undefined
    if (!active) { was.current = false; if (state.current === 1 || state.current === 3) p.pauseVideo(); p.mute(); return undefined }
    if (paused) { p.pauseVideo(); return undefined }
    if (live.current.muted) p.mute(); else p.unMute()
    if (!was.current && state.current !== -1) p.seekTo(start, true)
    was.current = true
    p.playVideo()
    // Sound refused by the browser? Retry muted rather than show a play button.
    const t1 = setTimeout(() => {
      if (state.current !== 1 && state.current !== 3 && !p.isMuted?.()) { p.mute(); p.playVideo(); calls.current.onAutoMuted?.() }
    }, 2500)
    const t2 = setTimeout(() => { if (state.current !== 1) p.playVideo() }, 3500)
    const t3 = setTimeout(() => { if (!ever.current && state.current !== 3) calls.current.onFail?.('yt:stall') }, 15000)
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, ready, paused, want])

  useEffect(() => {
    const p = player.current
    if (ready && active && want && p) { if (muted) p.mute(); else p.unMute() }
  }, [muted, ready, active, want])

  useEffect(() => {
    if (!ready || !active || !want) return undefined
    control.current = { seek: (s) => player.current?.seekTo(s, true) }
    const t = setInterval(() => {
      const p = player.current
      if (!p?.getCurrentTime) return
      const now = p.getCurrentTime()
      calls.current.onProgress?.(now, p.getDuration())
      const L = live.current
      if (L.end == null || state.current !== 1) return
      if (now < L.end - 2) clipDone.current = false
      else if (now >= L.end - 0.3 && !clipDone.current) {
        clipDone.current = true
        if (!calls.current.onClipEnd?.()) { p.seekTo(L.start, true); calls.current.onLoop?.() }
      }
    }, 250)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, active, want])

  // Quality cap: YouTube's automatic quality follows the size of the player box, so render the
  // iframe at the width of the target quality (144p / 240p / ...) and scale it up to fill the screen.
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return undefined
    const ro = new ResizeObserver(() => setDims({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  let style
  const cap = ytCap(q.h, q.mode)
  if (cap && dims?.w && dims?.h) {
    const dpr = window.devicePixelRatio || 1
    let s = cap / (dims.w * dpr)
    s = Math.max(s, 200 / Math.min(dims.w, dims.h))   // YouTube's minimum player size
    if (s < 0.98) style = { width: dims.w * s, height: dims.h * s, transform: `scale(${1 / s})` }
  }

  return (
    <div ref={box} className="yt-box" style={{ visibility: want ? 'visible' : 'hidden' }}>
      <div ref={host} className={`yt-host ${style ? 'capped' : ''}`} style={style} />
    </div>
  )
}

// ---------------------------------------------------------------- Dailymotion (Player Library, pooled)
// Same contract as YouTube: one player per slot, created once, then reused with loadContent().
function Dailymotion({ item, active, warm, muted, paused, cb, control, canBoot, q, clip }) {
  const host = useRef(null)
  const player = useRef(null)
  const [ready, setReady] = useState(false)
  const vid = useRef(null)
  const st = useRef({ playing: false, ever: false, ad: false, clipDone: false, q: false, buf: false })
  const was = useRef(false)
  const want = item?.external_id || null
  const start = Math.floor(clip ? clip.from : item?.start || 0)
  const end = clip?.to ?? null
  const live = useLatest({ active, muted, paused, want, start, end, h: q.h })
  const calls = useLatest(cb)

  const [boot, setBoot] = useState(false)
  if (!boot && want && (active || (canBoot && warm))) setBoot(true)

  const safe = (fn) => { try { return fn() } catch { return undefined } }
  // A video that won't play: strike against this player ID, skip the video, and if the player
  // got benched, move this slot to the plain embed with the next backup ID.
  const bad = (code) => {
    const pid = dmLibId()
    dmReport(pid, false)
    calls.current.onFail?.(code)
    if (pid && dmIds()[0] !== pid) calls.current.onLibFail?.()
  }

  useEffect(() => {
    if (!boot) return undefined
    let dead = false
    let made = null
    const id = `dm-${Math.random().toString(36).slice(2, 10)}`
    const el = document.createElement('div')
    el.id = id
    el.className = 'dm-root'
    host.current.appendChild(el)
    loadDailymotion().then((dm) => {
      if (dead) return null
      const L = live.current
      vid.current = L.want
      return dm.createPlayer(id, {
        video: L.want,
        params: { startTime: L.start, mute: true, loop: false, aspectRatio: 'inherit', scaleMode: 'fit' },
        referrerPolicy: 'strict-origin-when-cross-origin',
      }).then((p) => {
        made = p
        if (dead) { safe(() => p.destroy?.()); return }
        player.current = p
        const E = dm.events || {}
        const on = (name, fn) => { if (E[name]) p.on(E[name], fn) }
        // Late events from the previous video in this slot: ignore.
        const mine = (s) => !s?.videoId || s.videoId === vid.current
        const quality = () => {
          if (st.current.q) return
          st.current.q = true
          safe(() => p.setQuality?.(dmQuality(live.current.h)))
        }
        on('VIDEO_PLAYING', (s) => {
          if (!mine(s)) return
          const S = st.current
          S.playing = true; S.ever = true; S.ad = false; S.buf = false
          dmReport(dmLibId(), true)
          quality()
          const Lv = live.current
          if (!Lv.active || !Lv.want) { safe(() => p.pause()); return }   // warm-up: park it
          calls.current.onBuffering?.(false)
          calls.current.onPlaying?.(true)
        })
        // A pre-roll ad is what's playing: show it rather than a loading screen.
        on('AD_START', () => {
          st.current.ad = true
          if (live.current.active && live.current.want) calls.current.onPlaying?.(true)
          else safe(() => p.pause())
        })
        on('AD_END', () => { st.current.ad = false })
        on('VIDEO_PAUSE', (s) => {
          if (!mine(s)) return
          st.current.playing = false
          const Lv = live.current
          if (Lv.active && Lv.want && !Lv.paused) safe(() => p.play())     // paused by the player, not by us
          else calls.current.onPlaying?.(false)
        })
        on('VIDEO_BUFFERING', (s) => { if (!mine(s)) return; st.current.buf = true; if (live.current.active) calls.current.onBuffering?.(true) })
        on('VIDEO_TIMECHANGE', (s) => {
          if (!mine(s)) return
          const Lv = live.current
          if (!Lv.active) return
          const t = Number(s?.videoTime) || 0
          calls.current.onProgress?.(t, Number(s?.videoDuration) || 0)
          if (Lv.end == null) return
          const S = st.current
          if (t < Lv.end - 2) S.clipDone = false
          else if (t >= Lv.end - 0.3 && !S.clipDone) {
            S.clipDone = true
            if (!calls.current.onClipEnd?.()) { safe(() => p.seek(Lv.start)); calls.current.onLoop?.() }
          }
        })
        on('VIDEO_END', (s) => {
          if (!mine(s) || !live.current.active) return
          if (calls.current.onClipEnd?.()) return
          safe(() => { p.seek(live.current.start); p.play() })
          calls.current.onLoop?.()
        })
        on('PLAYER_ERROR', (s) => {
          if (live.current.want && mine(s)) bad(`dm:${s?.playerError?.code || 'error'}`)
        })
        setReady(true)
      })
    }).catch(() => { if (!dead) calls.current.onLibFail?.() })
    return () => {
      dead = true
      safe(() => (player.current || made)?.destroy?.())
      player.current = null
      if (host.current) host.current.innerHTML = ''
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boot])

  // A different video landed in this slot: swap it inside the live player.
  useEffect(() => {
    const p = player.current
    if (!ready || !p) return
    if (!want) { safe(() => { p.pause(); p.setMute(true) }); return }
    if (want === vid.current) return
    vid.current = want
    st.current = { playing: false, ever: false, ad: false, clipDone: false, q: false, buf: false }
    was.current = false
    safe(() => { p.setMute(true); p.loadContent({ video: want, startTime: start }) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [want, ready])

  useEffect(() => {
    const p = player.current
    if (!ready || !p || !want) return undefined
    if (!active) { was.current = false; if (st.current.playing) safe(() => p.pause()); safe(() => p.setMute(true)); return undefined }
    if (paused) { safe(() => p.pause()); return undefined }
    safe(() => p.setMute(Boolean(live.current.muted)))
    if (!was.current && st.current.ever) safe(() => p.seek(start))
    was.current = true
    safe(() => p.play())
    // Sound refused by the browser? Retry muted rather than show a play button.
    const t1 = setTimeout(() => {
      if (!st.current.playing && !st.current.ad && !st.current.buf && !live.current.muted) { safe(() => { p.setMute(true); p.play() }); calls.current.onAutoMuted?.() }
    }, 2500)
    const t2 = setTimeout(() => { if (!st.current.playing && !st.current.ad) safe(() => p.play()) }, 3500)
    const t3 = setTimeout(() => { if (!st.current.ever && !st.current.ad) bad('dm:stall') }, 15000)
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, ready, paused, want])

  useEffect(() => {
    const p = player.current
    if (ready && active && want && p) safe(() => p.setMute(Boolean(muted)))
  }, [muted, ready, active, want])

  useEffect(() => {
    if (ready && active && want) control.current = { seek: (sec) => safe(() => player.current?.seek(sec)) }
  }, [ready, active, want, control])

  return <div ref={host} className="dm-box" style={{ visibility: want ? 'visible' : 'hidden' }} />
}

// ---------------------------------------------------------------- native <video> (Archive MP4, X, Instagram)
function Native({ item, active, warm, ahead, muted, paused, cb, control, q, clip }) {
  const v = useRef(null)
  const calls = useLatest(cb)
  const last = useRef(0)
  const was = useRef(false)
  // The small hosted clip (GitHub Pages) when FeedCard picked one: 144p in Data saver, 240p in
  // Auto. If it ever fails, the original plays instead (nobody sees an error).
  const [hostedBad, setHostedBad] = useState(null)
  const hosted = clip?.hosted && clip.url && hostedBad !== item.id ? clip.url : null
  // A hosted clip starts at 0; the original plays [start, end) of the whole video.
  const start = hosted ? 0 : clip ? (clip.hosted ? item.clip.from : clip.from) : item.start || 0
  const clipLen = clip?.to != null ? clip.to - clip.from : null
  const end = clipLen ? start + clipLen : null
  const clipDone = useRef(false)
  const list = useMemo(
    () => (item.renditions?.length ? item.renditions : [{ url: item.media_url, fallback: null }]),
    [item.renditions, item.media_url],
  )

  // Which file, and whether we're on the archive.org/download/ fallback. Picked for the target
  // quality for each new video; never switched under a video that's already playing well.
  const fresh = pickRendition(list, q.h, q.min)
  const [sel, setSel] = useState(() => ({ id: item.id, r: fresh, fb: false, locked: false }))
  let cur = sel
  if (sel.id !== item.id || (!active && !sel.locked && sel.r !== fresh && !was.current)) {
    cur = { id: item.id, r: fresh, fb: false, locked: false }
    setSel(cur)
  }
  const rend = list[Math.min(cur.r, list.length - 1)] || list[0]
  const file = cur.fb && rend.fallback ? rend.fallback : viaEdge(rend.url)
  const src = hosted || file + (start ? `#t=${start}` : '')
  const floorR = lowestRendition(list, q.min)

  const resumeAt = useRef(null)
  const gotFrame = useRef(false)
  const waits = useRef([])
  useEffect(() => { gotFrame.current = false; waits.current = []; clipDone.current = false }, [src])

  const switchTo = (patch) => {
    const el = v.current
    resumeAt.current = el && el.currentTime > 0.5 ? el.currentTime : null
    setSel((s) => ({ ...s, ...patch, locked: true }))
  }
  // Too slow: a smaller file of the same clip, never below the mode's floor (Auto 240p, HD 480p).
  const downgrade = () => { if (cur.r > floorR) { switchTo({ r: cur.r - 1, fb: false }); return true } return false }

  useEffect(() => { if (v.current) v.current.muted = muted }, [muted])

  useEffect(() => {
    const el = v.current
    if (!el) return undefined
    if (!active) { was.current = false; el.pause(); return undefined }
    if (paused) { el.pause(); return undefined }
    if (!was.current && resumeAt.current == null) { try { el.currentTime = start } catch { /* not seekable yet */ } }
    was.current = true
    el.muted = muted
    const p = el.play()
    p?.catch((err) => {
      if (err?.name === 'NotAllowedError' && !el.muted) {
        el.muted = true
        calls.current.onAutoMuted?.()
        el.play().catch(() => {})
      }
    })
    // No first frame yet after a few seconds: drop to a smaller file of the same clip.
    // (A hosted clip is already tiny; it only falls back to the original if it shows nothing for 8 s.)
    const t = setTimeout(() => {
      if (gotFrame.current) return
      if (hosted) setHostedBad(item.id); else downgrade()
    }, hosted ? 8000 : q.tier === 'low' ? 3500 : 5000)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, paused, src])

  useEffect(() => {
    if (active) control.current = { seek: (s) => { if (v.current) v.current.currentTime = s } }
  }, [active, control])

  // Warm the connection to the storage server of the next videos.
  useEffect(() => {
    if (!(warm || ahead)) return
    if (hosted) preconnect(hosted); else if (file) preconnect(file)
  }, [warm, ahead, file, hosted])

  // The next video: a hosted clip is tiny, so buffer it fully even in Data saver.
  const preload = active ? 'auto' : warm ? (PLAN[q.tier].warmFull || hosted ? 'auto' : 'metadata') : 'metadata'

  return (
    <video ref={v} className="native" src={src}
      muted playsInline loop={end == null} preload={preload}
      disablePictureInPicture controlsList="nodownload noplaybackrate"
      onLoadedMetadata={(e) => {
        if (resumeAt.current != null) {
          try { e.currentTarget.currentTime = resumeAt.current } catch { /* ignore */ }
          resumeAt.current = null
        }
      }}
      onPlaying={() => { gotFrame.current = true; if (active) calls.current.onPlaying?.(true) }}
      onWaiting={() => {
        if (!active) return
        calls.current.onBuffering?.(true)
        if (!gotFrame.current || hosted) return
        // Two stalls in 20s: this file is too big for the connection, step down.
        const now = Date.now()
        waits.current = [...waits.current.filter((x) => now - x < 20000), now]
        if (waits.current.length >= 2) downgrade()
      }}
      onEnded={(e) => {
        // A clip that reaches the end of its file: next video, or loop it while the controls are up.
        if (!active || end == null) return
        if (!calls.current.onClipEnd?.()) { try { e.currentTarget.currentTime = start; e.currentTarget.play() } catch { /* ignore */ } }
      }}
      onCanPlay={() => active && calls.current.onBuffering?.(false)}
      onPause={() => calls.current.onPlaying?.(false)}
      onTimeUpdate={(e) => {
        const el = e.currentTarget
        const t = el.currentTime
        if (t + 1 < last.current) calls.current.onLoop?.()
        last.current = t
        if (!active) return
        calls.current.onProgress?.(t, el.duration)
        if (end == null) return
        if (t < end - 2) clipDone.current = false
        else if (t >= end - 0.25 && !clipDone.current) {
          clipDone.current = true
          if (!calls.current.onClipEnd?.()) { try { el.currentTime = start } catch { /* ignore */ } }
        }
      }}
      onError={(e) => {
        if (hosted) { setHostedBad(item.id); return }                       // hosted copy unreachable: the original
        // Direct storage-server link gone (item moved)? Use the always-valid /download/ link.
        if (!cur.fb && rend.fallback && rend.fallback !== rend.url) { switchTo({ fb: true }); return }
        if (downgrade()) return
        calls.current.onFail?.(`media:${e.currentTarget.error?.code || 0}`)
      }} />
  )
}

// ---------------------------------------------------------------- TikTok embed player v1 (postMessage)
function TikTok({ item, active, warm, muted, paused, cb }) {
  const f = useRef(null)
  const [ready, setReady] = useState(false)
  const [fallback, setFallback] = useState(false)
  const calls = useLatest(cb)
  const live = useLatest({ active, paused })
  const playing = useRef(false)

  const send = (type, value) => f.current?.contentWindow?.postMessage(
    { 'x-tiktok-player': true, type, ...(value !== undefined ? { value } : {}) }, '*')

  useEffect(() => {
    const onMsg = (e) => {
      if (!f.current || e.source !== f.current.contentWindow) return
      const d = e.data
      if (!d || typeof d !== 'object' || !d['x-tiktok-player']) return
      setReady(true)
      if (d.type === 'onStateChange') {
        if (d.value === 1) { playing.current = true; if (live.current.active) calls.current.onPlaying?.(true); else send('pause') }
        else if (d.value === 2) { playing.current = false; if (live.current.active && !live.current.paused) send('play') }
        else if (d.value === 0) calls.current.onLoop?.()
      } else if (d.type === 'onCurrentTime' && live.current.active) {
        calls.current.onProgress?.(d.value?.currentTime, d.value?.duration)
      } else if (d.type === 'onError') calls.current.onFail?.('tt:error')
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!ready || fallback) return undefined
    if (!active) { send('pause'); send('mute'); return undefined }
    if (paused) { send('pause'); return undefined }
    send(muted ? 'mute' : 'unMute'); send('seekTo', 0); send('play')
    const t = setInterval(() => { if (!playing.current) { send('mute'); send('play') } }, 700)
    const s = setTimeout(() => clearInterval(t), 6000)
    return () => { clearInterval(t); clearTimeout(s) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, ready, paused, fallback])

  useEffect(() => { if (ready && active) send(muted ? 'mute' : 'unMute') }, [muted]) // eslint-disable-line

  // Player never answered: plain autoplay URL.
  useEffect(() => {
    if (!active || ready || fallback) return undefined
    const t = setTimeout(() => setFallback(true), 4000)
    return () => clearTimeout(t)
  }, [active, ready, fallback])

  if (!active && !warm) return null
  return (
    <iframe ref={f} key={(fallback ? 'fb' : 'api') + item.external_id} className="frame" title={item.title}
      src={tiktokUrl(item, { autoplay: fallback })} tabIndex={-1}
      onLoad={() => { if (fallback) setTimeout(() => calls.current.onPlaying?.(true), 600) }}
      allow="autoplay; encrypted-media; picture-in-picture; fullscreen" referrerPolicy="strict-origin-when-cross-origin" />
  )
}

// ---------------------------------------------------------------- plain autoplay iframe (Facebook, Dailymotion fallback...)
function Frame({ item, active, muted, cb }) {
  const calls = useLatest(cb)
  const spec = frameFor(item, { muted })
  const frozen = useRef(null)
  if (!active) { frozen.current = null; return null }
  // Only rebuild the URL on mute changes for players that read mute from the URL.
  if (!frozen.current || frozen.current.id !== item.id || spec?.remountOnMute) frozen.current = spec && { ...spec, id: item.id }
  const s = frozen.current
  if (!s) return null
  return (
    <iframe key={s.src} className={`frame ${s.interactive ? 'interactive' : ''}`} title={item.title} src={s.src}
      tabIndex={-1} onLoad={() => setTimeout(() => calls.current.onPlaying?.(true), 700)}
      allow="autoplay; encrypted-media; picture-in-picture; fullscreen; clipboard-write"
      referrerPolicy="strict-origin-when-cross-origin" />
  )
}

// ---------------------------------------------------------------- still images (Archive photo sets)
function Still({ item, active, cb }) {
  const calls = useLatest(cb)
  useEffect(() => { if (active) calls.current.onPlaying?.(true) }, [active, item.id]) // eslint-disable-line
  return <img className={`still ${active ? 'kenburns' : ''}`} src={item.media_url || item.thumbnail} alt="" />
}

// v13: if any player crashes, only that video is skipped. The site keeps running.
class Guard extends Component {
  constructor(p) { super(p); this.state = { err: null } }
  static getDerivedStateFromError() { return { err: true } }
  componentDidCatch() { try { this.props.onFail?.('crash') } catch { /* ignore */ } }
  componentDidUpdate(prev) { if (prev.id !== this.props.id && this.state.err) this.setState({ err: null }) }
  render() { return this.state.err ? null : this.props.children }
}

export default function Player(props) {
  return <Guard id={props.item?.id} onFail={props.cb?.onFail}><Engines {...props} /></Guard>
}

function Engines(props) {
  const { item } = props
  const q = useQuality()
  const [nativeFailed, setNativeFailed] = useState(null)
  const [dmBlocked, setDmBlocked] = useState(false)
  let kind = nativeFailed === item.id ? 'frame' : playerKind(item)
  if (kind === 'dailymotion' && dmBlocked) kind = 'frame'
  // Once this slot has a YouTube / Dailymotion player, keep it alive (hidden) while the slot
  // shows other sources, so the next video of that kind here doesn't pay for a new player.
  const hasYT = useRef(false)
  const hasDM = useRef(false)
  if (kind === 'youtube') hasYT.current = true
  if (kind === 'dailymotion') hasDM.current = true
  const cb = {
    ...props.cb,
    // A dead CDN link (expired Instagram URL) falls back to the official embed.
    onFail: (code) => {
      if (kind === 'native' && frameFor(item) && item.source !== 'archive') setNativeFailed(item.id)
      else props.cb.onFail?.(code)
    },
    // Dailymotion's player library blocked (ad blocker, firewall): its plain embed instead.
    onLibFail: () => { hasDM.current = false; setDmBlocked(true) },
  }
  const mount = props.active || props.warm || props.near || (props.ahead && PLAN[q.tier].ahead >= 2)
  let other = null
  if (kind !== 'youtube' && kind !== 'dailymotion' && mount) {
    switch (kind) {
      case 'native': other = <Native {...props} q={q} cb={cb} />; break
      case 'tiktok': other = <TikTok {...props} cb={cb} />; break
      case 'image': other = <Still {...props} cb={cb} />; break
      default: other = <Frame {...props} cb={cb} />
    }
  }
  return (
    <>
      {hasYT.current && <YouTube {...props} q={q} item={kind === 'youtube' ? item : null} cb={cb} />}
      {hasDM.current && <Dailymotion {...props} q={q} item={kind === 'dailymotion' ? item : null} cb={cb} />}
      {other}
    </>
  )
}

export { playerKind }