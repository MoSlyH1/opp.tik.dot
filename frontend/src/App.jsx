import { useEffect, useMemo, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api } from './api.js'
import { AuthContext, MetaContext } from './context.js'
import Logo from './components/Logo.jsx'
import Shell from './components/Shell.jsx'
import Feed from './pages/Feed.jsx'
import Login from './pages/Login.jsx'
import Search from './pages/Search.jsx'
import Profile from './pages/Profile.jsx'
import ItemPage from './pages/ItemPage.jsx'

export default function App({ meta }) {
  const [user, setUser] = useState(undefined)

  useEffect(() => {
    api.me().then((r) => setUser(r.user)).catch(() => setUser(null))
  }, [])

  const auth = useMemo(() => ({
    user,
    setUser,
    logout: async () => {
      await api.logout().catch(() => {})
      setUser(null)
    },
  }), [user])

  if (user === undefined) {
    return (
      <div className="splash">
        <Logo size={72} />
      </div>
    )
  }

  return (
    <MetaContext.Provider value={meta}>
      <AuthContext.Provider value={auth}>
        {!user ? (
          <Login />
        ) : (
          <Routes>
            <Route element={<Shell />}>
              <Route index element={<Feed />} />
              <Route path="search" element={<Search />} />
              <Route path="me" element={<Profile />} />
              <Route path="v/:id" element={<ItemPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        )}
      </AuthContext.Provider>
    </MetaContext.Provider>
  )
}
