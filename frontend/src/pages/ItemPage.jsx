import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import FeedScroller from '../components/FeedScroller.jsx'
import Icon from '../components/Icon.jsx'

export default function ItemPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [item, setItem] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setItem(null)
    api.item(id).then((r) => setItem(r.item)).catch((e) => setError(e.message))
  }, [id])

  return (
    <div className="feed-page">
      <div className="item-top">
        <button type="button" className="pill" onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/'))}>
          <Icon name="back" size={16} /> Back
        </button>
        <Link to="/" className="pill">Open the feed</Link>
      </div>
      <FeedScroller items={item ? [item] : []} loading={!item && !error} error={error} done
        onItemChange={setItem} />
    </div>
  )
}
