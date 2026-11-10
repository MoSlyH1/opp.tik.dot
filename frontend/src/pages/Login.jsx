import { useEffect, useState } from 'react'
import { GoogleLogin } from '@react-oauth/google'
import { api } from '../api.js'
import { useAuth, useMeta } from '../context.js'
import Logo from '../components/Logo.jsx'

const YEARS = [1984, 1991, 1999, 2003, 1987, 1996, 2001, 2007, 1993, 1989, 2005, 1998, 2000, 1995, 2008, 1986, 2002, 1997]

export default function Login() {
  const meta = useMeta()
  const { setUser } = useAuth()
  const [wall, setWall] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.preview().then((r) => setWall(r.items)).catch(() => {})
  }, [])

  const signIn = async (fn) => {
    setError('')
    try { setUser((await fn()).user) } catch (e) { setError(e.message) }
  }

  return (
    <div className="login">
      <div className="login-wall" aria-hidden="true">
        {YEARS.map((y, i) => {
          const it = wall[i]
          return (
            <div className="wall-frame" key={i} style={{ animationDelay: `${(i % 6) * -1.3}s` }}>
              {it?.thumbnail ? <img src={it.thumbnail} alt="" loading="lazy" /> : null}
              <span className="mono">{it ? it.era_label : y}</span>
            </div>
          )
        })}
      </div>

      <main className="login-panel">
        <Logo size={96} />
        <h1 className="wordmark big">opp.tik.dot</h1>
        <p className="lede">The feed, rewound.</p>
        <p className="sub">
          Cartoons, football, music videos, films, ads and TV from the '50s to the 2000s,
          from Beirut to Tokyo to Mexico City. One swipe at a time, or rewind.
        </p>

        <div className="login-actions">
          {meta.offline ? (
            <p className="error">Can't reach the server. Is the backend running?</p>
          ) : meta.google_client_id ? (
            <GoogleLogin
              onSuccess={({ credential }) => signIn(() => api.loginGoogle(credential))}
              onError={() => setError('Google sign-in did not complete')}
              theme="filled_black" shape="pill" size="large" text="continue_with" />
          ) : (
            <p className="error">Google sign-in isn't configured. Set GOOGLE_CLIENT_ID on the server.</p>
          )}
          {meta.dev_login && (
            <button type="button" className="btn ghost" onClick={() => signIn(api.loginDev)}>
              Dev sign-in (local only)
            </button>
          )}
          {error && <p className="error">{error}</p>}
        </div>

        <p className="fine mono">Plays through official YouTube, Internet Archive, Dailymotion and TikTok players.</p>
      </main>
    </div>
  )
}
