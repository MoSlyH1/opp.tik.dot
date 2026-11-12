// Official embed players only. Nothing is downloaded or re-hosted.

let ytPromise = null
// The official YouTube IFrame Player API: reliable play / mute / seek / error events,
// instead of hand-rolled postMessage handshakes.
export function loadYouTube() {
  if (window.YT?.Player) return Promise.resolve(window.YT)
  if (!ytPromise) {
    ytPromise = new Promise((resolve, reject) => {
      const prev = window.onYouTubeIframeAPIReady
      window.onYouTubeIframeAPIReady = () => { prev?.(); resolve(window.YT) }
      const s = document.createElement('script')
      s.src = 'https://www.youtube.com/iframe_api'
      s.async = true
      s.onerror = () => { ytPromise = null; reject(new Error('YouTube API blocked')) }
      document.head.appendChild(s)
    })
  }
  return ytPromise
}

/*
 * v12 Dailymotion. The old embed address (www.dailymotion.com/embed/video/<id>) has been retired:
 * since September 2025 it only redirects to the new player and ignores the old settings, which
 * is why Dailymotion videos stopped loading. The new player is loaded through Dailymotion's
 * official Player Library (geo.dailymotion.com), which also gives real play / pause / time /
 * error events, so the feed knows when a Dailymotion video actually starts.
 * DM_PLAYER_ID (optional, Vercel env) picks your own player from Dailymotion Studio.
 */
// v13: Dailymotion only plays on other sites through a player ID (the no-ID address returns 403).
// Backups, in order: your own DM_PLAYER_ID(s) (comma-separated), then two public player IDs from
// Dailymotion's own docs. A player that fails 3 videos in a row without playing any is benched
// on this browser for 2 days, then tried again. If every player is benched, all are tried again,
// so the list is never empty. Nothing here can throw: storage errors are ignored.
const DM_PUBLIC = ['xfh28', 'xc394']
const DM_BENCH_MS = 2 * 24 * 3600 * 1000
let dmOwn = []
const dmFails = {}
const dmStore = {
  get() { try { return JSON.parse(localStorage.getItem('dm_bench') || '{}') || {} } catch { return {} } },
  set(v) { try { localStorage.setItem('dm_bench', JSON.stringify(v)) } catch { /* private mode */ } },
}
export function setDmPlayer(id) {
  dmOwn = String(id || '').split(',').map((x) => x.trim()).filter((x) => /^[a-z0-9]+$/i.test(x))
}
export function dmIds() {
  const all = [...new Set([...dmOwn, ...DM_PUBLIC])]
  const bench = dmStore.get()
  const now = Date.now()
  const ok = all.filter((x) => !(bench[x] && now - bench[x] < DM_BENCH_MS))
  if (ok.length) return ok
  dmStore.set({})
  return all
}
// Report how a Dailymotion player did. Success clears its strikes; 3 strikes benches it.
export function dmReport(pid, good) {
  if (!pid) return
  if (good) { dmFails[pid] = 0; return }
  dmFails[pid] = (dmFails[pid] || 0) + 1
  if (dmFails[pid] >= 3) {
    dmFails[pid] = 0
    const b = dmStore.get(); b[pid] = Date.now(); dmStore.set(b)
  }
}

let dmLib = null        // the player ID the library was loaded with
let dmPromise = null
let dmBroken = false    // blocked once (ad blocker, firewall): plain embeds from then on
export const dmLibId = () => dmLib
export function loadDailymotion() {
  if (window.dailymotion?.createPlayer && dmLib) return Promise.resolve(window.dailymotion)
  if (dmBroken) return Promise.reject(new Error('Dailymotion player blocked'))
  if (!dmPromise) {
    dmLib = dmIds()[0]
    dmPromise = new Promise((resolve, reject) => {
      let t = null
      const done = () => { if (window.dailymotion?.createPlayer) { clearTimeout(t); resolve(window.dailymotion) } }
      const fail = () => { clearTimeout(t); dmPromise = null; dmBroken = true; reject(new Error('Dailymotion player blocked')) }
      try {
        // The library calls onScriptLoaded once it is ready (official way to wait for it).
        window.dailymotion = { ...(window.dailymotion || {}), onScriptLoaded: done }
        const s = document.createElement('script')
        s.src = `https://geo.dailymotion.com/libs/player/${dmLib}.js`
        s.async = true
        s.onload = () => setTimeout(done, 0)
        s.onerror = fail
        t = setTimeout(fail, 8000)
        document.head.appendChild(s)
      } catch { fail() }
    })
  }
  return dmPromise
}

export function tiktokUrl(item, { autoplay = false } = {}) {
  const id = encodeURIComponent(item.external_id)
  return `https://www.tiktok.com/player/v1/${id}?autoplay=${autoplay ? 1 : 0}&loop=1&music_info=1&description=0` +
    '&rel=0&controls=0&progress_bar=0&volume_control=0&play_button=0&timestamp=0&fullscreen_button=0' +
    '&native_context_menu=0&closed_caption=0'
}

// Sources played in a plain iframe. `interactive`: the embed can't autoplay and needs a tap inside it.
export function frameFor(item, { muted = true, alt = 0 } = {}) {
  const id = encodeURIComponent(item.external_id)
  switch (item.source) {
    case 'dailymotion': {
      // Plain embed (library blocked). Always with a player ID: without one Dailymotion answers 403.
      // `alt` picks the next backup player when the previous plain embed showed nothing.
      const ids = dmIds()
      const pid = ids[(alt || 0) % ids.length]
      return { src: `https://geo.dailymotion.com/player/${pid}.html?video=${id}` +
        `&autoplay=true&mute=${muted ? 'true' : 'false'}${item.start ? `&startTime=${Math.floor(item.start)}` : ''}`,
      remountOnMute: true, interactive: true, pid, tries: ids.length }
    }
    case 'facebook':
      return { src: `https://www.facebook.com/plugins/video.php?href=${encodeURIComponent(item.url)}` +
        `&show_text=false&autoplay=true&mute=${muted ? 'true' : 'false'}&allowfullscreen=false`, remountOnMute: true }
    case 'instagram':
      return { src: `https://www.instagram.com/reel/${id}/embed/`, interactive: true }
    case 'x':
      return { src: `https://platform.twitter.com/embed/Tweet.html?id=${id}&theme=dark&hideThread=true`, interactive: true }
    case 'archive':
      // Last resort when no MP4 could be found: archive.org's own player.
      return { src: `https://archive.org/embed/${id}?autoplay=1&muted=1`, interactive: true }
    default:
      return null
  }
}

// Which player a card uses.
export function playerKind(item) {
  if (item.kind === 'image') return 'image'
  if (item.source === 'youtube') return 'youtube'
  if (item.source === 'tiktok') return 'tiktok'
  if (item.source === 'dailymotion') return 'dailymotion'
  if (item.media_url) return 'native'
  return 'frame'
}

export const isTall = (item) => ['tiktok', 'instagram'].includes(item.source)

export const shareUrl = (item) => `${window.location.origin}/v/${item.id}`

export const fmtTime = (s) => {
  if (!Number.isFinite(s) || s < 0) return '0:00'
  const m = Math.floor(s / 60)
  const r = Math.floor(s % 60)
  return m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}:${String(r).padStart(2, '0')}`
    : `${m}:${String(r).padStart(2, '0')}`
}