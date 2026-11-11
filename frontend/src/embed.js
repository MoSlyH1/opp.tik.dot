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
let dmPlayerId = ''
let dmPromise = null
let dmBroken = false   // blocked once (ad blocker, firewall): don't make every card wait for it again
export function setDmPlayer(id) { dmPlayerId = typeof id === 'string' && /^[a-z0-9]+$/i.test(id) ? id : '' }
export function loadDailymotion() {
  if (window.dailymotion?.createPlayer) return Promise.resolve(window.dailymotion)
  if (dmBroken) return Promise.reject(new Error('Dailymotion player blocked'))
  if (!dmPromise) {
    dmPromise = new Promise((resolve, reject) => {
      const done = () => { if (window.dailymotion?.createPlayer) { clearTimeout(t); resolve(window.dailymotion) } }
      // The library calls onScriptLoaded once it is ready (official way to wait for it).
      window.dailymotion = { ...(window.dailymotion || {}), onScriptLoaded: done }
      const s = document.createElement('script')
      s.src = dmPlayerId ? `https://geo.dailymotion.com/libs/player/${dmPlayerId}.js` : 'https://geo.dailymotion.com/libs/player.js'
      s.async = true
      s.onload = () => setTimeout(done, 0)
      const fail = () => { dmPromise = null; dmBroken = true; reject(new Error('Dailymotion player blocked')) }
      s.onerror = fail
      const t = setTimeout(fail, 8000)
      document.head.appendChild(s)
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
export function frameFor(item, { muted = true } = {}) {
  const id = encodeURIComponent(item.external_id)
  switch (item.source) {
    case 'dailymotion':
      // v12.1: Dailymotion's own embed page, the address its retired embed link redirects to. The
      // feed reveals it when it loads (no events needed). `interactive`: if the browser blocks
      // autoplay, the viewer can tap Dailymotion's play button.
      return { src: `https://geo.dailymotion.com/player${dmPlayerId ? `/${dmPlayerId}` : ''}.html?video=${id}` +
        `&mute=${muted ? 'true' : 'false'}${item.start ? `&startTime=${item.start}` : ''}`, remountOnMute: true, interactive: true }
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