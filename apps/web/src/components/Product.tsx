import { useEffect, useRef, type ComponentType, type CSSProperties } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import {
  faArrowTrendUp,
  faChartLine,
  faClipboardCheck,
  faCode,
  faCompass,
  faDiagramProject,
  faLayerGroup,
  faScrewdriverWrench,
  faSitemap,
  faWandMagicSparkles,
  type IconDefinition,
} from '@fortawesome/free-solid-svg-icons'
import { faCirclePlay, faEyeSlash, faHourglassHalf } from '@fortawesome/free-regular-svg-icons'
import {
  ContactDialog,
  DemoDialog,
  MAX_WIDTH,
  MarketingFooter,
  MarketingHeader,
  TEAL,
  useMarketingDialogs,
  type PublicPage,
} from './marketing/MarketingChrome'
import { ArtExecute, ArtExplore, ArtGenerate, ArtManage, Dial, HeroSchematic } from './marketing/productArt'

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

const CAPABILITIES: { name: string; icon: IconDefinition; desc: string; value: string; valueDesc: string; Art: ComponentType }[] = [
  {
    name: 'Explore',
    icon: faCompass,
    desc: 'Understand your application, explore its pages and map user journeys to establish a foundation for comprehensive testing.',
    value: 'Faster Test Preparation',
    valueDesc: 'Accelerate the journey from application understanding to automated testing.',
    Art: ArtExplore,
  },
  {
    name: 'Generate',
    icon: faWandMagicSparkles,
    desc: 'Transform application insights into intelligent test scenarios and automated Playwright test cases.',
    value: 'Reduced Manual Effort',
    valueDesc: 'Minimize repetitive test creation and execution activities.',
    Art: ArtGenerate,
  },
  {
    name: 'Execute',
    icon: faCirclePlay,
    desc: 'Execute automated tests, monitor outcomes and gain visibility into test performance.',
    value: 'Better Visibility',
    valueDesc: 'Gain centralized insights into test execution and outcomes.',
    Art: ArtExecute,
  },
  {
    name: 'Manage',
    icon: faLayerGroup,
    desc: 'Centralize test suites, test cases, test data, reports and execution schedules.',
    value: 'Operational Efficiency',
    valueDesc: 'Manage testing activities through one platform.',
    Art: ArtManage,
  },
]

const AUDIENCES: { icon: IconDefinition; title: string; desc: string }[] = [
  { icon: faClipboardCheck, title: 'QA Managers', desc: 'Better control over test coverage, execution and reporting.' },
  { icon: faCode, title: 'QA Engineers', desc: 'Less repetitive work and easier test maintenance.' },
  { icon: faSitemap, title: 'Engineering Leaders', desc: 'Improved visibility into automation and quality workflows.' },
  { icon: faChartLine, title: 'Business Leaders', desc: 'A more efficient and structured approach to software quality.' },
]

// Fades `[data-reveal]` blocks up as they scroll into view (after their
// optional data-delay ms) and sweeps the `[data-fill]` lifecycle line across.
// Elements are only hidden once an IntersectionObserver is there to show
// them again, so without one (or with reduced motion) everything is visible.
function useScrollReveal(rootRef: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const root = rootRef.current
    if (!root || !('IntersectionObserver' in window)) return
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((en) => {
          if (!en.isIntersecting) return
          const el = en.target as HTMLElement
          el.classList.add('is-revealed')
          // The stagger delay is for the entrance only, not later hovers.
          el.addEventListener('transitionend', () => (el.style.transitionDelay = ''), { once: true })
          io.unobserve(el)
        }),
      { threshold: 0.12, rootMargin: '0px 0px -6% 0px' },
    )
    root.querySelectorAll<HTMLElement>('[data-reveal], [data-fill]').forEach((el) => {
      el.style.transitionDelay = `${Number(el.dataset.delay || 0)}ms`
      el.classList.add('product-reveal-pending')
      io.observe(el)
    })
    return () => io.disconnect()
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
  useScrollReveal(rootRef)

  return (
    <div ref={rootRef} className="product-page" style={{ background: '#FAFAFB', minHeight: '100svh', overflowX: 'clip', color: '#3E3E46' }}>
      <a href="#product-main" className="product-skip">
        Skip to content
      </a>
      <MarketingHeader current="product" onNavigate={onNavigate} onSignIn={onSignIn} />

      <main id="product-main">
        <section aria-labelledby="product-hero-title" style={{ padding: `clamp(48px,6vw,80px) ${GUTTER} clamp(48px,6vw,72px)` }}>
          <div
            style={{
              ...INNER,
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
            </div>
            <figure
              aria-hidden="true"
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
              <div style={{ position: 'absolute', inset: 0 }}>
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
            <div data-reveal="" style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 40 }}>
              <Eyebrow>The challenges we solve</Eyebrow>
              <h2 id="product-challenges-title" style={H2}>
                Traditional Testing Shouldn't Slow Down Innovation.
              </h2>
            </div>
            <div
              data-reveal=""
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit,minmax(min(100%,260px),1fr))',
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

        <section aria-labelledby="product-platform-title" style={{ background: '#0E2624', color: '#C9D8D5', padding: SECTION_PAD }}>
          <div style={INNER}>
            <div data-reveal="" style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 56 }}>
              <Eyebrow color="#7FCFC4">Meet the Vantage platform</Eyebrow>
              <h2 id="product-platform-title" style={{ ...H2, color: '#FFFFFF' }}>
                One Platform. Every Stage of Testing.
              </h2>
            </div>
            <div style={{ position: 'relative' }}>
              {/* The connecting line only makes sense with all four stages on one row. */}
              <div className="product-lifeline" aria-hidden="true">
                <div style={{ position: 'absolute', inset: '4px 0 auto', height: 1, background: 'rgba(127,207,196,0.22)' }} />
                <div data-fill="" className="product-lifeline-fill" />
                <span className="product-lifeline-pulse" />
              </div>
              <ol
                style={{
                  position: 'relative',
                  listStyle: 'none',
                  margin: 0,
                  padding: 0,
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit,minmax(min(100%,170px),1fr))',
                  gap: '32px 16px',
                }}
              >
                {STAGES.map((s, i) => (
                  <li
                    key={s.name}
                    data-reveal=""
                    data-delay={150 + i * 400}
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
              <article key={c.name} data-reveal="" data-delay={i * 90} className="product-cap">
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
                    <h2 style={{ margin: 0, fontSize: 26, lineHeight: 1, fontWeight: 600, letterSpacing: '-0.035em', color: '#16161A' }}>{c.name}</h2>
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
            <div data-reveal="" style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 40 }}>
              <Eyebrow>Who benefits from Vantage?</Eyebrow>
              <h2 id="product-who-title" style={H2}>
                Designed for Teams That Care About Quality.
              </h2>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(min(100%,280px),1fr))', gap: 16 }}>
              {AUDIENCES.map((a, i) => (
                <div key={a.title} data-reveal="" data-delay={i * 80} className="product-audience">
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
          <div data-reveal="" style={{ ...INNER, position: 'relative', display: 'flex', flexDirection: 'column', gap: 22 }}>
            <h2
              id="product-cta-title"
              style={{
                margin: 0,
                maxWidth: 760,
                fontSize: 'clamp(40px,5.2vw,76px)',
                lineHeight: 1,
                fontWeight: 600,
                letterSpacing: '-0.05em',
                color: '#fff',
                textWrap: 'balance',
              }}
            >
              Ready to Rethink Testing?
            </h2>
            <p style={{ margin: 0, maxWidth: 560, fontSize: 18, lineHeight: 1.6, color: '#E3F2EF', textWrap: 'pretty' }}>
              See how Vantage can help your team simplify testing, accelerate quality and deliver with confidence.
            </p>
            <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 12 }}>
              <button
                type="button"
                className="landing-btn landing-btn-lift product-btn-white"
                onClick={openDemo}
                style={{ height: 54, gap: 10, padding: '0 26px', borderRadius: 12, fontSize: 15.5 }}
              >
                <FontAwesomeIcon icon={faCirclePlay} style={{ fontSize: 14 }} />
                Watch a Demo
              </button>
              <button
                type="button"
                className="landing-btn landing-btn-lift product-btn-outline"
                onClick={openContact}
                style={{ height: 54, padding: '0 26px', borderRadius: 12, fontSize: 15.5 }}
              >
                Connect with Our Team
              </button>
            </div>
          </div>
        </section>
      </main>

      <MarketingFooter current="product" />

      {demoOpen && <DemoDialog onClose={closeAll} />}
      {contactOpen && (
<ContactDialog onClose={closeAll} />
      )}
    </div>
  )
}
