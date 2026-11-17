// Runs after `vite build` and the SSR build of src/prerender.tsx (see the
// `build` script). Writes the prerendered public pages and crawler files into
// dist; all content and the site address come from src/prerender.tsx and
// src/site.ts. nginx.conf serves product.html for /product and app.html for
// every app route.

import { readFile, writeFile } from 'node:fs/promises'

const dist = new URL('../dist/', import.meta.url)
const ssr = await import(new URL('../dist-ssr/prerender.js', import.meta.url).href)
const shell = await readFile(new URL('index.html', dist), 'utf8')

const out = {
  'app.html': ssr.appShell(shell),
  'index.html': ssr.renderPage(shell, 'landing'),
  'product.html': ssr.renderPage(shell, 'product'),
  'robots.txt': ssr.robotsTxt(),
  'sitemap.xml': ssr.sitemapXml(new Date().toISOString().slice(0, 10)),
  'llms.txt': ssr.llmsTxt(),
}
for (const [name, body] of Object.entries(out)) {
  await writeFile(new URL(name, dist), body)
  console.log(`prerender: dist/${name}`)
}
