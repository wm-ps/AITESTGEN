// The public site's address and per-page head copy, in one place. The build's
// prerender step (src/prerender.tsx) builds canonical links, the sitemap,
// robots.txt and llms.txt from SITE_URL; App.tsx sets the tab title from
// PAGE_META on client navigation. Titles and descriptions reuse each page's
// own h1 and hero sentence, so nothing here is copy the page doesn't show.

import type { PublicPage } from './components/marketing/MarketingChrome'

export const SITE_URL = 'https://vantage.omnewave.com'
export const SITE_NAME = 'Vantage'
// The footer's "An initiative of Omnewave."
export const PUBLISHER = 'Omnewave'

export const PAGE_META: Record<PublicPage, { path: string; title: string; description: string }> = {
  landing: {
    path: '/',
    title: 'Vantage | Test smarter. Release with confidence.',
    description: 'Vantage explores your web application, writes its tests with AI, runs them and keeps every suite in one place.',
  },
  product: {
    path: '/product',
    title: 'Vantage | Rethink Software Testing. Redefine Quality.',
    description:
      'Vantage transforms the way organizations approach software testing, bringing intelligent test generation, automated execution and centralized test management together in one platform.',
  },
}
