import { StrictMode } from 'react'
import { createRoot, hydrateRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/ServiceError.tsx'
import { hasSignedInHint } from './signedInHint'

const container = document.getElementById('root')!
const tree = (
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
)

// `/` and `/product` arrive prerendered (scripts/prerender.mjs). A visitor
// without the signed-in hint gets that same page from App's first render, so
// React adopts the HTML in place. A hinted visitor gets the boot loader
// instead, so the prerendered page is cleared rather than mismatched; the
// inline script in index.html kept it hidden until now.
if (container.firstElementChild && !hasSignedInHint()) {
  hydrateRoot(container, tree)
} else {
  container.replaceChildren()
  document.documentElement.removeAttribute('data-signed-in-hint')
  createRoot(container).render(tree)
}
