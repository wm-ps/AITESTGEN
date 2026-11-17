import { useEffect, useRef, type CSSProperties } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import {
  faArrowTrendUp,
  faCompass,
  faDiagramProject,
  faLayerGroup,
  faScrewdriverWrench,
  faWandMagicSparkles,
  type IconDefinition,
} from '@fortawesome/free-solid-svg-icons'
import { faCirclePlay, faEyeSlash, faHourglassHalf } from '@fortawesome/free-regular-svg-icons'
import {
  ConnectTeamButton,
  ContactDialog,
  DemoDialog,
  MAX_WIDTH,
  MarketingFooter,
  MarketingHeader,
  TEAL,
  useMarketingDialogs,
  WatchDemoButton,
  type PublicPage,
} from './marketing/MarketingChrome'
import { AUDIENCES, CAPABILITIES } from './marketing/productContent'
import { Dial, HeroSchematic } from './marketing/productArt'

// Signed-out product page at /product (claude.ai/design "Vantage Product").

const GUTTER = 'clamp(20px,4vw,40px)'
const SECTION_PAD = `clamp(56px,6vw,88px) ${GUTTER}`
const INNER: CSSProperties = { maxWidth: MAX_WIDTH.product, margin: '0 auto' }

const CHALLENGES: { icon: IconDefinition; title: string; desc: string }[] = [
  { icon: faHourglassHalf, title: 'Time-consuming Testing', desc: 'Manual effort and repetitive test creation slow down software delivery.' },
  { icon: faDiagramProject, title: 'Fragmented Testing Workflows', desc: 'Disconnected tools make testing difficult to coordinate and manage.' },
  { icon: faScrewdriverWrench, title: 'Test Maintenance Overhead', desc: 'Application changes introduce additional test maintenance effort.' },
  { icon: faEyeSlash, title: 'Limited Quality Visibility', desc: 'Teams struggle to get a consolidated view of test coverage and execution outcomes.' },
]

const STAGES: { icon: IconDefinition; name: string }[] = [
  { icon: faCompass, name: 'Explore' },
  { icon: faWandMagicSparkles, name: 'Generate' },
  { icon: faCirclePlay, name: 'Execute' },
  { icon: faLayerGroup, name: 'Manage' },
]

// The art plays once, at normal speed, and rests on its finished frame — no
// pause button. The CSS loops in each `[data-play-once]` block wait, paused,
// until the block scrolls into view, then:
// - a story keyframe (FINISH) plays its first cycle and stops at the point it
//   is finished: journey drawn, node lit, test passed. The hero map ends
//   about 6-7 s in, past WCAG 2.2.2's 5 s; accepted for one normal-speed play.
// - an ambient loop (spin, dash, float, pulse) has no end, so it stops after
//   AMBIENT_MS, on its REST frame when it has one.
const FINISH: Record<string, number> = {
  'product-draw': 0.46,
  'product-on': 0.06,
  'product-grow': 0.31,
  'product-fill': 0.71,
  'product-pass': 0.73,
  'product-heal': 0.85,
}
const REST: Record<string, number> = { 'product-twinkle': 0.5, 'product-travel': 0.5, 'product-ping': 0.3 }
const AMBIENT_MS = 5000

const frameAt = (a: Animation, f: number) => {
  const { delay, duration } = a.effect!.getTiming()
  return (Number(delay) || 0) + (Number(duration) || 0) * f
}

// Plays `a` from its start, then freezes it as above.
function playOnce(a: Animation, timers: number[]) {
  const name = a instanceof CSSAnimation ? a.animationName : ''
  const finish = FINISH[name]
  const rest = REST[name]
  a.currentTime = 0
  a.play()
  const stopAt = finish === undefined ? AMBIENT_MS : frameAt(a, finish)
  timers.push(
    window.setTimeout(() => {
      a.pause()
      if (finish !== undefined) a.currentTime = frameAt(a, finish)
      else if (rest !== undefined) a.currentTime = frameAt(a, rest)
    }, stopAt),
  )
}

function usePlayOnceInView(rootRef: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const root = rootRef.current
    // No Web Animations API or observer (jsdom, old browsers): the loops just
    // run, as before. Reduced motion already sets them to none in index.css.
    if (!root || typeof root.getAnimations !== 'function' || !('IntersectionObserver' in window)) return
    const loops = (el: Element) => el.getAnimations({ subtree: true }).filter((a) => a.effect?.getComputedTiming().iterations === Infinity)
    const blocks = root.querySelectorAll('[data-play-once]')
    blocks.forEach((b) => loops(b).forEach((a) => a.pause()))
    const timers: number[] = []
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((en) => {
          if (!en.isIntersecting) return
          io.unobserve(en.target)
          loops(en.target).forEach((a) => playOnce(a, timers))
        }),
      { threshold: 0.3 },
    )
    blocks.forEach((b) => io.observe(b))
    return () => {
      io.disconnect()
      timers.forEach(clearTimeout)
    }
  }, [rootRef])
}

function Eyebrow({ children, color = '#5C5C66' }: { children: string; color?: string }) {
  return (
    <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', color }}>{children}</p>
  )
}

const H2: CSSProperties = {
  margin: 0,
  fontSize: 'clamp(32px,3.8vw,52px)',
  lineHeight: 1.04,
  fontWeight: 600,
  letterSpacing: '-0.045em',
  color: '#16161A',
  textWrap: 'balance',
}

export function Product({ onNavigate, onSignIn }: { onNavigate: (page: PublicPage) => void; onSignIn: () => void }) {
  const { demoOpen, contactOpen, openDemo, openContact, closeAll } = useMarketingDialogs()
  const rootRef = useRef<HTMLDivElement>(null)
  usePlayOnceInView(rootRef)

  return (
    <div
      ref={rootRef}
      className="product-page"
      style={{ background: '#FAFAFB', minHeight: '100svh', overflowX: 'clip', color: '#3E3E46' }}
    >
      <a href="#product-main" className="product-skip">
        Skip to content
      </a>
      <MarketingHeader current="product" onNavigate={onNavigate} onSignIn={onSignIn} />

      <main id="product-main">
        {/* Fills the first screen under the 64px header, so nothing of the
            next section shows on load. */}
        <section
          aria-labelledby="product-hero-title"
          style={{
            minHeight: 'calc(100svh - 64px)',
            display: 'flex',
            alignItems: 'center',
            padding: `clamp(48px,6vw,80px) ${GUTTER} clamp(48px,6vw,72px)`,
          }}
        >
          <div
            style={{
              ...INNER,
              width: '100%',
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit,minmax(min(100%,480px),1fr))',
              gap: '40px clamp(32px,5vw,80px)',
              alignItems: 'center',
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <h1
                id="product-hero-title"
                style={{
                  margin: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  fontSize: 'clamp(42px,5.4vw,82px)',
                  lineHeight: 0.98,
                  fontWeight: 600,
                  letterSpacing: '-0.05em',
                  color: '#16161A',
                }}
              >
                <span className="landing-up" style={{ animationDuration: '.9s', animationDelay: '.08s' }}>
                  Rethink Software Testing.
                </span>
                <span className="landing-up" style={{ color: TEAL, animationDuration: '.9s', animationDelay: '.18s' }}>
                  Redefine Quality.
                </span>
              </h1>
              <p
                className="landing-up"
                style={{
                  margin: '28px 0 0',
                  maxWidth: 560,
                  fontSize: 'clamp(16.5px,1.3vw,19px)',
                  lineHeight: 1.65,
                  color: '#484851',
                  textWrap: 'pretty',
                  animationDuration: '.9s',
                  animationDelay: '.28s',
                }}
              >
                Vantage transforms the way organizations approach software testing, bringing intelligent test generation, automated execution
                and centralized test management together in one platform.
              </p>
              <div className="landing-up" style={{ marginTop: 36, display: 'flex', flexWrap: 'wrap', gap: 14, animationDuration: '.9s', animationDelay: '.36s' }}>
                <WatchDemoButton onClick={openDemo} />
                <ConnectTeamButton onClick={openContact} />
              </div>
            </div>
            <figure
              data-play-once=""
              className="landing-up"
              style={{
                margin: 0,
                position: 'relative',
                justifySelf: 'center',
                width: 'min(100%,600px)',
                aspectRatio: '1/1',
                borderRadius: 28,
                background:
                  'linear-gradient(rgba(15,118,110,0.06) 1px,transparent 1px) 0 0/28px 28px,linear-gradient(90deg,rgba(15,118,110,0.06) 1px,transparent 1px) 0 0/28px 28px,#F5F8F8',
                border: '1px solid #E1E8E6',
                animationDuration: '1.1s',
                animationDelay: '.2s',
              }}
            >
              <div aria-hidden="true" style={{ position: 'absolute', inset: 0 }}>
                <HeroSchematic />
              </div>
            </figure>
          </div>
        </section>

        <section
          aria-labelledby="product-challenges-title"
          style={{ padding: SECTION_PAD, background: '#fff', borderTop: '1px solid #E5E6E9', borderBottom: '1px solid #E5E6E9' }}
        >
          <div style={INNER}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 40 }}>
              <Eyebrow>The challenges we solve</Eyebrow>
              <h2 id="product-challenges-title" style={H2}>
                Traditional Testing Shouldn't Slow Down Innovation.
              </h2>
            </div>
            <div
              className="product-grid4"
              style={{
                display: 'grid',
                border: '1px solid #E5E6E9',
                borderRadius: 20,
                overflow: 'hidden',
                // 1px gaps over this background are the dividers between
                // cells, however many columns the cards wrap into.
                background: '#E5E6E9',
                gap: 1,
              }}
            >
              {CHALLENGES.map((c) => (
                <article key={c.title} className="product-challenge">
                  <span
                    style={{
                      width: 48,
                      height: 48,
                      borderRadius: 13,
                      background: '#fff',
                      border: '1px solid #E5E6E9',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: TEAL,
                      fontSize: 18,
                    }}
                  >
                    <FontAwesomeIcon icon={c.icon} />
                  </span>
                  <h3 style={{ margin: '14px 0 0', fontSize: 20, fontWeight: 600, letterSpacing: '-0.02em', color: '#16161A' }}>{c.title}</h3>
                  <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: '#484851' }}>{c.desc}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section
          aria-labelledby="product-platform-title"
          className="product-on-dark"
          data-play-once=""
          style={{ background: '#0E2624', color: '#C9D8D5', padding: SECTION_PAD }}
        >
          <div style={INNER}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 56 }}>
              <Eyebrow color="#7FCFC4">Meet the Vantage platform</Eyebrow>
              <h2 id="product-platform-title" style={{ ...H2, color: '#FFFFFF' }}>
                One Platform. Every Stage of Testing.
              </h2>
            </div>
            <div style={{ position: 'relative' }}>
              {/* The connecting line only makes sense with all four stages on one row. */}
              <div className="product-lifeline" aria-hidden="true">
                <div style={{ position: 'absolute', inset: '4px 0 auto', height: 1, background: 'rgba(127,207,196,0.22)' }} />
                <div className="product-lifeline-fill" />
                <span className="product-lifeline-pulse" />
              </div>
              <ol
                className="product-stages"
                style={{
                  position: 'relative',
                  listStyle: 'none',
                  margin: 0,
                  padding: 0,
                  display: 'grid',
                  gap: '32px 16px',
                }}
              >
                {STAGES.map((s) => (
                  <li
                    key={s.name}
                    style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: 14 }}
                  >
                    <span
                      style={{
                        width: 88,
                        height: 88,
                        borderRadius: 100,
                        background: '#0E2624',
                        border: '1px solid rgba(127,207,196,0.45)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <span
                        style={{
                          width: 64,
                          height: 64,
                          borderRadius: 100,
                          background: TEAL,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: '#fff',
                          fontSize: 22,
                        }}
                      >
                        <FontAwesomeIcon icon={s.icon} />
                      </span>
                    </span>
                    <h3 style={{ margin: 0, fontSize: 24, fontWeight: 600, letterSpacing: '-0.025em', color: '#fff' }}>{s.name}</h3>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </section>

        <section aria-label="Platform capabilities" style={{ padding: SECTION_PAD }}>
          {/* At most two columns, so the four cards sit 2×2 rather than 3 + 1. */}
          <div
            style={{
              ...INNER,
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit,minmax(min(100%,max(420px,calc((100% - 24px) / 2))),1fr))',
              gap: 24,
            }}
          >
            {CAPABILITIES.map((c, i) => (
              <article key={c.name} data-play-once="" className="product-cap">
                <div
                  style={{
                    position: 'relative',
                    width: '100%',
                    aspectRatio: '16/10',
                    borderBottom: '1px solid #E1E8E6',
                    background: `radial-gradient(rgba(15,118,110,0.12) 1px,transparent 1px) 0 0/18px 18px,${i % 2 ? '#F6F7F8' : '#F1F5F4'}`,
                  }}
                >
                  <div style={{ position: 'absolute', inset: '8%' }}>
                    <c.Art />
                  </div>
                </div>
                <div style={{ padding: '24px 24px 26px', display: 'flex', flexDirection: 'column', gap: 14, flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span
                      style={{
                        width: 44,
                        height: 44,
                        flex: 'none',
                        borderRadius: 12,
                        background: '#E6F4F2',
                        border: '1px solid #CFE7E3',
                        color: TEAL,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 17,
                      }}
                    >
                      <FontAwesomeIcon icon={c.icon} />
                    </span>
                    <h3 style={{ margin: 0, fontSize: 26, lineHeight: 1, fontWeight: 600, letterSpacing: '-0.035em', color: '#16161A' }}>{c.name}</h3>
                  </div>
                  <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: '#3E3E46', textWrap: 'pretty' }}>{c.desc}</p>
                  <div style={{ marginTop: 'auto', paddingTop: 14, borderTop: '1px solid #EBECEE', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                    <FontAwesomeIcon icon={faArrowTrendUp} style={{ marginTop: 3, color: TEAL, fontSize: 13 }} />
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: '#16161A' }}>{c.value}</span>
                      <span style={{ fontSize: 13, lineHeight: 1.5, color: '#5C5C66' }}>{c.valueDesc}</span>
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section
          aria-labelledby="product-who-title"
          style={{ background: '#F1F5F4', borderTop: '1px solid #E1E8E6', borderBottom: '1px solid #E1E8E6', padding: SECTION_PAD }}
        >
          <div style={INNER}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 40 }}>
              <Eyebrow>Who benefits from Vantage?</Eyebrow>
              <h2 id="product-who-title" style={H2}>
                Designed for Teams That Care About Quality.
              </h2>
            </div>
            <div className="product-grid4" style={{ display: 'grid', gap: 16 }}>
              {AUDIENCES.map((a) => (
                <div key={a.title} className="product-audience">
                  <span
                    style={{
                      width: 52,
                      height: 52,
                      borderRadius: 14,
                      background: '#E6F4F2',
                      color: TEAL,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 19,
                    }}
                  >
                    <FontAwesomeIcon icon={a.icon} />
                  </span>
                  <h3 style={{ margin: 'auto 0 0', fontSize: 22, fontWeight: 600, letterSpacing: '-0.02em', color: '#16161A' }}>{a.title}</h3>
                  <p style={{ margin: 0, fontSize: 15.5, lineHeight: 1.6, color: '#484851' }}>{a.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section
          aria-labelledby="product-cta-title"
          className="product-on-dark"
          data-play-once=""
          style={{ position: 'relative', overflow: 'hidden', background: TEAL, padding: `clamp(72px,8vw,112px) ${GUTTER}` }}
        >
          <div
            aria-hidden="true"
            style={{
              position: 'absolute',
              right: '-8%',
              top: '50%',
              width: 'min(760px,90vw)',
              aspectRatio: '1/1',
              transform: 'translateY(-50%)',
              opacity: 0.55,
              pointerEvents: 'none',
            }}
          >
            <Dial />
          </div>
          <div style={{ ...INNER, position: 'relative', display: 'flex', flexDirection: 'column', gap: 22 }}>
            <h2 id="product-cta-title" style={{ ...H2, maxWidth: 760, color: '#fff' }}>
              Ready to Rethink Testing?
            </h2>
            <p style={{ margin: 0, maxWidth: 560, fontSize: 18, lineHeight: 1.6, color: '#FFFFFF', textWrap: 'pretty' }}>
              See how Vantage can help your team simplify testing, accelerate quality and deliver with confidence.
            </p>
            <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 12 }}>
              <WatchDemoButton onClick={openDemo} onTeal />
              <ConnectTeamButton onClick={openContact} />
            </div>
          </div>
        </section>
      </main>

      <MarketingFooter current="product" />

      {demoOpen && <DemoDialog onClose={closeAll} />}
      {contactOpen && <ContactDialog onClose={closeAll} />}
    </div>
  )
}
