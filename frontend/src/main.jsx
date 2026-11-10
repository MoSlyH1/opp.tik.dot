import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { GoogleOAuthProvider } from '@react-oauth/google'
import App from './App.jsx'
import { boot } from './lib/boot.js'
import './styles.css'

// Free caching on the viewer's device: app files, thumbnails and video chunks (public/sw.js).
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => {}) })
}

const root = ReactDOM.createRoot(document.getElementById('root'))

// The Google client id comes from the backend so one env var configures both sides.
boot.meta
  .then((meta) => {
    const tree = (
      <BrowserRouter>
        <App meta={meta} />
      </BrowserRouter>
    )
    root.render(
      meta.google_client_id
        ? <GoogleOAuthProvider clientId={meta.google_client_id}>{tree}</GoogleOAuthProvider>
        : tree,
    )
  })
