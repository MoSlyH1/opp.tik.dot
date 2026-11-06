import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context.js'
import Icon from './Icon.jsx'
import Logo from './Logo.jsx'

const NAV = [
  { to: '/', label: 'Feed', icon: 'home', end: true },
  { to: '/search', label: 'Search', icon: 'search' },
  { to: '/me', label: 'Profile', icon: 'user' },
]

export default function Shell() {
  const { user } = useAuth()
  return (
    <div className="shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand">
          <Logo size={40} />
          <span className="wordmark">opp.tik.dot</span>
        </NavLink>
        <nav className="side-nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className="side-link">
              <Icon name={n.icon} /> <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          {user.avatar ? <img src={user.avatar} alt="" className="avatar sm" referrerPolicy="no-referrer" /> : null}
          <div className="side-user">
            <strong>{user.name || 'You'}</strong>
            <span className="mono muted">{user.email}</span>
          </div>
        </div>
      </aside>

      <main className="main"><Outlet /></main>

      <nav className="bottom-nav">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className="bottom-link" aria-label={n.label}>
            <Icon name={n.icon} size={24} />
            <span>{n.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
