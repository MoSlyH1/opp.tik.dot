// Connection awareness: decide how aggressive pre-buffering can be.
// On a slow link, the video you're watching must get ALL the bandwidth first;
// the next one only starts buffering once the current one is actually playing.
const conn = () => (typeof navigator !== 'undefined' ? navigator.connection || navigator.mozConnection || navigator.webkitConnection : null)

export function isSlow() {
  const c = conn()
  if (!c) return false
  if (c.saveData) return true
  if (/^(slow-2g|2g|3g)$/.test(c.effectiveType || '')) return true
  return Boolean(c.downlink && c.downlink < 1.5)
}

export function onNetworkChange(fn) {
  const c = conn()
  c?.addEventListener?.('change', fn)
  return () => c?.removeEventListener?.('change', fn)
}
