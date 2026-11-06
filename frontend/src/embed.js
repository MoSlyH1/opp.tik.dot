// Official embed players only. Nothing is downloaded or re-hosted.
// YouTube/TikTok players are preloaded paused and started via postMessage (see FeedCard),
// so the next video is ready the moment you scroll to it. `autoplay` is the fallback path.
export function embedUrl(item, { autoplay = false } = {}) {
  const id = encodeURIComponent(item.external_id)
  const ap = autoplay ? 1 : 0
  switch (item.source) {
    case 'youtube':
      return `https://www.youtube-nocookie.com/embed/${id}?autoplay=${ap}&mute=1&enablejsapi=1` +
        `&origin=${encodeURIComponent(window.location.origin)}` +
        `&playsinline=1&loop=1&playlist=${id}&rel=0&modestbranding=1&controls=0&disablekb=1&fs=0&iv_load_policy=3`
    case 'tiktok':
      return `https://www.tiktok.com/player/v1/${id}?autoplay=${ap}&loop=1&music_info=1&description=0` +
        `&rel=0&controls=1&progress_bar=1&volume_control=1&play_button=0&timestamp=0&fullscreen_button=0`
    case 'archive':
      return `https://archive.org/embed/${id}?autoplay=1`
    default:
      return null
  }
}

export const shareUrl = (item) => `${window.location.origin}/v/${item.id}`