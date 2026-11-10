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

export function tiktokUrl(item, { autoplay = false } = {}) {
  const id = encodeURIComponent(item.external_id)
  return `https://www.tiktok.com/player/v1/${id}?autoplay=${autoplay ? 1 : 0}&loop=1&music_info=1&description=0` +
    '&rel=0&controls=0&progress_bar=0&volume_control=0&play_button=0&timestamp=0&fullscreen_button=0' +
    '&native_context_menu=0&closed_caption=0'
}

// Sources played in a plain iframe. `interactive`: the embed can't autoplay and needs a tap inside it.
export function frameFor(item, { muted = true } = {}) {
  const id = encodeURIComponent(item.external_id)
  const m = muted ? 1 : 0
  switch (item.source) {
    case 'dailymotion':
      return { src: `https://www.dailymotion.com/embed/video/${id}?autoplay=1&mute=${m}&controls=0` +
        `&queue-enable=false&queue-autoplay-next=false&sharing-enable=false&ui-start-screen-info=false&ui-logo=false` +
        (item.start ? `&start=${item.start}` : ''), remountOnMute: true }
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
