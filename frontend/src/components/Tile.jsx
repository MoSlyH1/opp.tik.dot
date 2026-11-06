import { Link } from 'react-router-dom'

export default function Tile({ item }) {
  return (
    <Link to={`/v/${item.id}`} className="tile">
      {item.thumbnail ? <img src={item.thumbnail} alt="" loading="lazy" /> : <div className="tile-blank" />}
      <span className="badge solid mono tile-year">{item.year || item.era_label}</span>
      <div className="tile-meta">
        <p className="tile-title">{item.title}</p>
        <p className="mono muted tile-src">{item.category_label} · {item.source_label}</p>
      </div>
    </Link>
  )
}
