import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { detectBrowserLanguage, loadTranslations } from './i18n'

const rootEl = document.getElementById('root')
if (!rootEl) {
  throw new Error('Root element "#root" not found')
}
const root = rootEl

function renderApp() {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void loadTranslations(detectBrowserLanguage()).then(renderApp, renderApp)
