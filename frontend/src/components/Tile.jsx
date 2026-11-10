import { Link } from 'react-router-dom'
import { fmtTime } from '../embed.js'

export default function Tile({ item, onOpen }) {
  return (
    <Link to={`/v/${item.id}`} className="tile" onClick={onOpen}>
      {item.thumbnail ? <img src={item.thumbnail} alt="" loading="lazy" /> : <div className="tile-blank" />}
      <span className="badge solid mono tile-year">{item.year || item.era_label}</span>
      {item.duration ? <span className="badge mono tile-dur">{fmtTime(item.duration)}</span> : null}
      <div className="tile-meta">
        <p className="tile-title">{item.title}</p>
        <p className="mono muted tile-src">{item.category_label}{item.regions?.[0] ? ` · ${item.regions[0].label}` : ''} · {item.source_label}</p>
      </div>
    </Link>
  )
}
