// Build-time server entry for scripts/prerender.mjs: renders the two public
// pages to HTML and builds their head tags and the crawler files, so search
// and AI crawlers get the full page without running JavaScript. Every fact
// here comes from site.ts or the pages themselves; nothing is new copy.
//
// ponytail: hand-rolled prerender of two fixed routes (renderToString into
// the built index.html), not an SSR/SSG framework. Enough while `/` and
// `/product` are the only public pages; if more public pages arrive, move to
// a real static-generation setup instead of growing this file.

import { renderToString } from 'react-dom/server'
import { dom } from '@fortawesome/fontawesome-svg-core'
import { Landing } from './components/Landing'
import { Product } from './components/Product'
import { AUDIENCES, CAPABILITIES } from './components/marketing/productContent'
import type { PublicPage } from './components/marketing/MarketingChrome'
import { PAGE_META, PUBLISHER, SITE_NAME, SITE_URL } from './site'

const noop = () => {}
const PAGES: PublicPage[] = ['landing', 'product']
const urlOf = (page: PublicPage) => SITE_URL + PAGE_META[page].path

const attr = (s: string) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')
const text = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
// JSON inside <script> must not be able to close the tag.
const jsonLd = (data: unknown) => JSON.stringify(data).replace(/</g, '\\u003c')

function renderBody(page: PublicPage) {
  return renderToString(page === 'landing' ? <Landing onNavigate={noop} onSignIn={noop} /> : <Product onNavigate={noop} onSignIn={noop} />)
}

function structuredData(page: PublicPage) {
  const meta = PAGE_META[page]
  const home = urlOf('landing')
  const graph: Record<string, unknown>[] = [
    { '@type': 'Organization', '@id': `${home}#publisher`, name: PUBLISHER },
    { '@type': 'WebSite', '@id': `${home}#website`, url: home, name: SITE_NAME, publisher: { '@id': `${home}#publisher` } },
    {
      '@type': 'SoftwareApplication',
      '@id': `${home}#software`,
      name: SITE_NAME,
      url: home,
      applicationCategory: 'DeveloperApplication',
      operatingSystem: 'Web',
      description: PAGE_META.landing.description,
      featureList: CAPABILITIES.map((c) => `${c.name}: ${c.desc}`),
      audience: AUDIENCES.map((a) => ({ '@type': 'Audience', audienceType: a.title })),
      publisher: { '@id': `${home}#publisher` },
    },
    {
      '@type': 'WebPage',
      '@id': `${urlOf(page)}#webpage`,
      url: urlOf(page),
      name: meta.title,
      description: meta.description,
      isPartOf: { '@id': `${home}#website` },
      about: { '@id': `${home}#software` },
    },
  ]
  if (page === 'product') {
    graph.push({
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: home },
        { '@type': 'ListItem', position: 2, name: 'Product', item: urlOf('product') },
      ],
    })
  }
  return { '@context': 'https://schema.org', '@graph': graph }
}

function headTags(page: PublicPage) {
  const { title, description } = PAGE_META[page]
  const url = urlOf(page)
  const image = `${SITE_URL}/og.png`
  return [
    `<link rel="canonical" href="${attr(url)}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:site_name" content="${attr(SITE_NAME)}" />`,
    `<meta property="og:title" content="${attr(title)}" />`,
    `<meta property="og:description" content="${attr(description)}" />`,
    `<meta property="og:url" content="${attr(url)}" />`,
    `<meta property="og:image" content="${attr(image)}" />`,
    `<meta property="og:image:width" content="1200" />`,
    `<meta property="og:image:height" content="630" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${attr(title)}" />`,
    `<meta name="twitter:description" content="${attr(description)}" />`,
    `<meta name="twitter:image" content="${attr(image)}" />`,
    // FontAwesome adds this at runtime; inline it so prerendered icons are
    // sized from the first paint, before the bundle runs.
    `<style>${dom.css()}</style>`,
    `<script type="application/ld+json">${jsonLd(structuredData(page))}</script>`,
  ].join('\n    ')
}

const ROOT = '<div id="root"></div>'
const TITLE = /<title>[^<]*<\/title>/
const DESCRIPTION = /<meta name="description" content="[^"]*" \/>/

function check(shell: string) {
  if (!shell.includes(ROOT) || !TITLE.test(shell) || !DESCRIPTION.test(shell) || !shell.includes('</head>')) {
    throw new Error('prerender: dist/index.html no longer has the expected root, title, description or </head>')
  }
}

/** The built index.html with `page` rendered into #root and its own head. */
export function renderPage(shell: string, page: PublicPage) {
  check(shell)
  const { title, description } = PAGE_META[page]
  return shell
    .replace(TITLE, `<title>${text(title)}</title>`)
    .replace(DESCRIPTION, `<meta name="description" content="${attr(description)}" />`)
    .replace('</head>', `  ${headTags(page)}\n  </head>`)
    .replace(ROOT, `<div id="root">${renderBody(page)}</div>`)
}

/** The empty app shell nginx falls back to for every other route. */
export function appShell(shell: string) {
  check(shell)
  return shell.replace('</head>', `  <meta name="robots" content="noindex" />\n  </head>`)
}

export function robotsTxt() {
  return `# Public pages are open to every crawler, AI crawlers included.
User-agent: *
User-agent: Googlebot
User-agent: Bingbot
User-agent: GPTBot
User-agent: OAI-SearchBot
User-agent: ChatGPT-User
User-agent: ClaudeBot
User-agent: Claude-SearchBot
User-agent: PerplexityBot
User-agent: Google-Extended
Allow: /
Disallow: /signin
Disallow: /accept-invite
Disallow: /reset-password
Disallow: /recording-session
Disallow: /applications/

Sitemap: ${SITE_URL}/sitemap.xml
`
}

export function sitemapXml(lastmod: string) {
  const urls = PAGES.map((p) => `  <url>\n    <loc>${text(urlOf(p))}</loc>\n    <lastmod>${lastmod}</lastmod>\n  </url>`).join('\n')
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`
}

// llms.txt (llmstxt.org): a plain summary AI engines can read in one fetch,
// built only from sentences the two pages already show.
export function llmsTxt() {
  return `# ${SITE_NAME}

> ${PAGE_META.landing.description}

${PAGE_META.product.description}

${SITE_NAME} is an initiative of ${PUBLISHER}.

## Pages

- [Home](${urlOf('landing')}): ${PAGE_META.landing.description}
- [Product](${urlOf('product')}): ${PAGE_META.product.description}

## Capabilities

${CAPABILITIES.map((c) => `- ${c.name}: ${c.desc} ${c.value}: ${c.valueDesc}`).join('\n')}

## Who it is for

${AUDIENCES.map((a) => `- ${a.title}: ${a.desc}`).join('\n')}
`
}
