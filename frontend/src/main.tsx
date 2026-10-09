import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@fontsource-variable/inter'
import '@fontsource/playfair-display/500.css'
import '@fontsource/playfair-display/600.css'
import './styles.css'
import App from './App'
import { AppProvider } from './state/AppState'

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter><AppProvider><App /></AppProvider></BrowserRouter>
  </React.StrictMode>,
)
