import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { Companion, Connection } from './Connection'
import './connection.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {location.pathname === '/host' ? <Companion /> : <Connection><App /></Connection>}
  </StrictMode>,
)
