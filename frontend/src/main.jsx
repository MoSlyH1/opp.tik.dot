import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { GoogleOAuthProvider } from '@react-oauth/google'
import App from './App.jsx'
import { api } from './api.js'
import './styles.css'

const root = ReactDOM.createRoot(document.getElementById('root'))

// The Google client id comes from the backend so one env var configures both sides.
api.meta()
  .catch(() => ({ offline: true }))
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
