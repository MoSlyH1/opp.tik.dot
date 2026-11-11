import { LOGO } from '../brand.js'
import { useMeta } from '../context.js'

/*
 * The "Sponsored" box on the loading card. Fill it from Vercel -> Environment Variables
 * (no rebuild needed, it comes from /api/meta):
 *   SPONSOR_TITLE  "Abela Delices"            SPONSOR_TEXT   "Fresh pastries, delivered"
 *   SPONSOR_URL    https://... (tap target)   SPONSOR_IMAGE  https://... (square image)
 * Empty = a house ad with your logo. To plug in an ad network later, render its unit here.
 */
const HOUSE = { title: 'opp.tik.dot', text: 'The feed, rewound. Advertise here.', url: '', image: '' }

export default function Sponsor() {
  const meta = useMeta()
  const s = meta?.sponsor || HOUSE
  const body = (
    <>
      <img className="sp-img" src={s.image || LOGO} alt="" width="40" height="40" />
      <span className="sp-text">
        <strong>{s.title || HOUSE.title}</strong>
        {s.text && <span>{s.text}</span>}
      </span>
    </>
  )
  return (
    <div className="sponsor" onPointerDown={(e) => e.stopPropagation()}>
      <span className="sp-tag mono">Sponsored</span>
      {s.url
        ? <a className="sp-body" href={s.url} target="_blank" rel="noopener noreferrer sponsored" onClick={(e) => e.stopPropagation()}>{body}</a>
        : <div className="sp-body">{body}</div>}
    </div>
  )
}
