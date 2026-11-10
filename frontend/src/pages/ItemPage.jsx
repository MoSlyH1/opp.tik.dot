import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import Pager from '../components/Pager.jsx'
import Icon from '../components/Icon.jsx'

// A shared link, or a tile opened from Search / Profile: when we came from a list, you can
// keep swiping through that list like a feed.
export default function ItemPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { state } = useLocation()
  const [items, setItems] = useState(() => state?.items || [])
  const [start] = useState(() => state?.index || 0)
  const [error, setError] = useState('')

  useEffect(() => {
    if (state?.items?.length) return
    setItems([])
    api.item(id).then((r) => setItems([r.item])).catch((e) => setError(e.message))
  }, [id, state])

  const update = useCallback((it) => setItems((prev) => prev.map((p) => (p.id === it.id ? { ...p, ...it } : p))), [])
  const hide = useCallback((hid) => setItems((prev) => prev.filter((p) => p.id !== hid)), [])

  return (
    <div className="feed-page">
      <div className="item-top">
        <button type="button" className="pill" onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/'))}>
          <Icon name="back" size={16} /> Back
        </button>
        <Link to="/" className="pill">Open the feed</Link>
      </div>
      <Pager items={items} startIndex={start} resetKey={state?.items ? 'list' : id}
        loading={!items.length && !error} error={error} done={false}
        onItemChange={update} onHide={state?.items ? hide : undefined} />
    </div>
  )
}
