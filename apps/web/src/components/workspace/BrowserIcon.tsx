import type { Browser } from '../../runTarget'
import chromeLogo from '../../assets/browsers/chrome.svg'
import firefoxLogo from '../../assets/browsers/firefox.svg'
import safariLogo from '../../assets/browsers/safari.svg'

const LOGOS = { chromium: chromeLogo, firefox: firefoxLogo, webkit: safariLogo }

// The browser's own full-colour logo, so a result reads as "validated in Chrome /
// Firefox / Safari" at a glance. Decorative: the name always sits next to it, or
// in the chip's own label.
export function BrowserIcon({ browser, size = 14 }: { browser: Browser; size?: number }) {
  return <img src={LOGOS[browser]} alt="" aria-hidden="true" width={size} height={size} style={{ flex: 'none' }} />
}
