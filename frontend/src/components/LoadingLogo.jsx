import { LOGO } from '../brand.js'

// Your logo as the loading sign: the logo with a ring turning around it. Inlined (no download),
// so it shows the moment anything starts loading.
export default function LoadingLogo({ size = 64, label = 'Loading' }) {
  return (
    <span className="load-logo" style={{ '--s': `${size}px` }} role="img" aria-label={label}>
      <img src={LOGO} alt="" width={size} height={size} decoding="sync" draggable="false" />
    </span>
  )
}
