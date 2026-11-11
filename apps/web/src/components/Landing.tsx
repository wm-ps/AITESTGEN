import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faPlay } from '@fortawesome/free-solid-svg-icons'
import { faComments } from '@fortawesome/free-regular-svg-icons'
import {
  ContactDialog,
  DemoDialog,
  MarketingFooter,
  MarketingHeader,
  TEAL,
  useMarketingDialogs,
  type PublicPage,
} from './marketing/MarketingChrome'

// Signed-out home page (claude.ai/design "Vantage Landing modified"). Sign in
// opens the existing SignIn screen; the hero animation is LandingVisual below.

// The background art lives in public/ (not src/assets) so a missing file only
// drops back to the #EEF5F5 base colour instead of breaking the build.
const LANDING_BG = '/landing-bg-teal-waves.png'

export function Landing({ onNavigate, onSignIn }: { onNavigate: (page: PublicPage) => void; onSignIn: () => void }) {
  const { demoOpen, contactOpen, openDemo, openContact, closeAll } = useMarketingDialogs()

  return (
    <div
      className="landing"
      style={{
        minHeight: '100svh',
        background: `linear-gradient(90deg,rgba(250,250,251,0.9) 0%,rgba(250,250,251,0.55) 45%,rgba(250,250,251,0) 75%),url(${LANDING_BG}) center bottom/cover no-repeat,#EEF5F5`,
        display: 'flex',
        flexDirection: 'column',
        overflowX: 'hidden',
        color: '#3E3E46',
      }}
    >
      <MarketingHeader current="landing" onNavigate={onNavigate} onSignIn={onSignIn} />

      <main
        style={{
          flex: 1,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: 'clamp(24px,4.5vh,56px) clamp(20px,4vw,32px)',
        }}
      >
        <div
          style={{
            maxWidth: 1240,
            width: '100%',
            margin: '0 auto',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit,minmax(min(100%,460px),1fr))',
            gap: 'clamp(32px,5vh,56px) clamp(40px,6vw,96px)',
            alignItems: 'center',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            <h1
              style={{
                margin: 0,
                display: 'flex',
                flexDirection: 'column',
                fontSize: 'clamp(32px,min(4.4vw,8vh),68px)',
                lineHeight: 1.04,
                fontWeight: 650,
                letterSpacing: '-0.05em',
                color: '#16161A',
              }}
            >
              <span className="landing-up" style={{ whiteSpace: 'nowrap', animationDelay: '.08s' }}>
                Test smarter.
              </span>
              <span className="landing-up" style={{ whiteSpace: 'nowrap', color: TEAL, animationDelay: '.16s' }}>
                Release with confidence.
              </span>
            </h1>
            <div className="landing-up" style={{ marginTop: 'clamp(22px,3.6vh,32px)', width: 56, height: 2, background: TEAL, animationDelay: '.3s' }} />
            <p
              className="landing-up"
              style={{
                margin: 'clamp(16px,2.6vh,22px) 0 0',
                maxWidth: 480,
                fontSize: 'clamp(16px,1.25vw,18px)',
                lineHeight: 1.65,
                color: '#484851',
                textWrap: 'pretty',
                animationDelay: '.38s',
              }}
            >
              Experience a smarter approach to software testing with AI-driven test generation, seamless execution and centralized test
              management.
            </p>
            <div className="landing-up" style={{ marginTop: 'clamp(28px,5vh,48px)', display: 'flex', flexWrap: 'wrap', gap: 14, animationDelay: '.42s' }}>
              <button
                type="button"
                className="landing-btn landing-btn-teal landing-btn-lift"
                onClick={openDemo}
                style={{ height: 54, gap: 12, padding: '0 24px 0 9px', borderRadius: 12, fontSize: 15.5 }}
              >
                <span
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 9,
                    background: 'rgba(255,255,255,0.16)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <FontAwesomeIcon icon={faPlay} style={{ fontSize: 12, marginLeft: 2 }} />
                </span>
                Watch a demo
              </button>
              <button
                type="button"
                className="landing-btn landing-btn-ink landing-btn-lift"
                onClick={openContact}
                style={{ height: 54, gap: 10, padding: '0 24px', borderRadius: 12, fontSize: 15.5 }}
              >
                <FontAwesomeIcon icon={faComments} style={{ fontSize: 14 }} />
                Connect with team
              </button>
            </div>
          </div>
          <figure
            role="img"
            aria-label="Abstract animation: an application being discovered, its journeys traced and its tests passing"
            className="landing-up"
            style={{ margin: 0, justifySelf: 'center', width: 'min(100%,56vh,540px)', aspectRatio: '1/1', animationDuration: '1s', animationDelay: '.25s' }}
          >
            <div className="landing-float" style={{ width: '100%', height: '100%' }}>
              <LandingVisual />
            </div>
          </figure>
        </div>
      </main>

      <MarketingFooter current="landing" />

      {demoOpen && <DemoDialog onClose={closeAll} />}
      {contactOpen && (
<ContactDialog onClose={closeAll} />
      )}
    </div>
  )
}

// --- Hero animation ---------------------------------------------------------
// A looping SVG story in a 100x100 viewBox: a cursor walks five app screens
// (scan), test chips spring out of each (draw), the chips run and pass — one
// briefly "heals" amber (run) — then fly into three suite trays (hold), fade.
// Ticks every 40ms in its own component so the page around it never re-renders.

type Card = { x: number; y: number; w: number; h: number; kind: 0 | 1 | 2; chips: number }
const CARDS: Card[] = [
  { x: 6, y: 10, w: 26, h: 18, kind: 0, chips: 2 },
  { x: 38, y: 4, w: 26, h: 18, kind: 1, chips: 3 },
  { x: 70, y: 13, w: 25, h: 17, kind: 2, chips: 2 },
  { x: 44, y: 41, w: 25, h: 18, kind: 1, chips: 3 },
  { x: 12, y: 47, w: 25, h: 17, kind: 2, chips: 2 },
]
type Chip = { card: number; i: number; o: number; tray: number; slot: number }
const CHIPS: Chip[] = CARDS.flatMap((c, k) => Array.from({ length: c.chips }, (_, i) => ({ card: k, i }))).map((ch, o) => ({
  ...ch,
  o,
  tray: o % 3,
  slot: Math.floor(o / 3),
}))
const HEAL_CHIP = 7
const TRAYS = [0, 1, 2].map((s) => ({ x: 62, y: 70 + s * 9.6, w: 34, h: 7.6 }))
const T_SCAN = 120
const T_DRAW = 80
const T_RUN = 70
const T_HOLD = 70
const T_FADE = 20
const CYCLE = T_SCAN + T_DRAW + T_RUN + T_HOLD + T_FADE
// Frame shown when motion is reduced: every test run and passed.
const STILL_TICK = T_SCAN + T_DRAW + T_RUN + 10

const ease = (t: number) => (t < 0 ? 0 : t > 1 ? 1 : 1 - Math.pow(1 - t, 3))
const cl = (t: number) => (t < 0 ? 0 : t > 1 ? 1 : t)
const lerp = (a: number, b: number, t: number) => a + (b - a) * t

function LandingVisual() {
  const [reduced] = useState(() => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (reduced) return
    const iv = setInterval(() => setTick((t) => (t + 1) % CYCLE), 40)
    return () => clearInterval(iv)
  }, [reduced])

  return <VisualFrame tick={reduced ? STILL_TICK : tick} />
}

function VisualFrame({ tick }: { tick: number }) {
  const scanT = tick / T_SCAN
  const drawT = (tick - T_SCAN) / T_DRAW
  const runT = (tick - T_SCAN - T_DRAW) / T_RUN
  const holdT = (tick - T_SCAN - T_DRAW - T_RUN) / T_HOLD
  const fade = 1 - cl((tick - (CYCLE - T_FADE)) / T_FADE)
  const u = cl(scanT * 1.12) * (CARDS.length - 1)
  const bob = (k: number) => Math.sin(tick / 22 + k * 1.7) * 0.55
  const center = (k: number): [number, number] => {
    const c = CARDS[k]
    return [c.x + c.w / 2, c.y + c.h / 2 + bob(k)]
  }
  const edgeFade = 1 - cl(holdT * 1.5) * 0.65

  const edges = CARDS.slice(0, -1).map((_, k) => {
    const p = cl(u - k)
    if (p <= 0) return null
    const [x1, y1] = center(k)
    const [x2, y2] = center(k + 1)
    const my = (y1 + y2) / 2
    const d = `M${x1} ${y1} C${x1} ${my} ${x2} ${my} ${x2} ${y2}`
    return (
      <g key={`e${k}`} opacity={edgeFade}>
        <path d={d} fill="none" stroke="#CFEDE8" strokeWidth={1.6} strokeLinecap="round" />
        <path d={d} fill="none" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - ease(p)} stroke={TEAL} strokeWidth={0.45} strokeLinecap="round" />
      </g>
    )
  })

  const cards = CARDS.map((c, k) => {
    const vis = ease(cl((u - k + 0.35) * 2.2))
    if (vis <= 0) return null
    const y = c.y + bob(k)
    const { x, w, h: hh } = c
    const active = u >= k - 0.05 && u < k + 0.9 && scanT < 1.05
    const cx = x + w / 2
    const cy = y + hh / 2
    const ripple = u >= k && u < k + 0.4 && scanT < 1 ? (u - k) / 0.4 : null
    return (
      <g key={`c${k}`}>
        <g
          style={{ opacity: vis * (1 - cl(holdT * 1.5) * 0.25) }}
          transform={`translate(${cx} ${cy}) scale(${0.92 + vis * 0.08}) translate(${-cx} ${-cy})`}
        >
          <rect x={x} y={y} width={w} height={hh} rx={1.8} fill="#FFFFFF" stroke={active ? TEAL : '#DADCE0'} strokeWidth={active ? 0.45 : 0.3} filter="url(#vSh)" />
          <line x1={x} y1={y + 3.4} x2={x + w} y2={y + 3.4} stroke="#EBECEE" strokeWidth={0.25} />
          {[0, 1, 2].map((i) => (
            <circle key={i} cx={x + 2 + i * 1.5} cy={y + 1.75} r={0.5} fill={i === 0 && active ? TEAL : '#DADCE0'} />
          ))}
          <rect x={x + 6.8} y={y + 0.95} width={w - 9.5} height={1.6} rx={0.8} fill="#F2F3F5" />
          <rect x={x + 2.4} y={y + 5.6} width={w * 0.42} height={1.7} rx={0.5} fill="#3E3E46" opacity={0.85} />
          {c.kind === 0 &&
            [0, 1].map((i) => (
              <rect key={i} x={x + 2.4} y={y + 8.6 + i * 2.9} width={w - 4.8} height={2.1} rx={0.6} fill="#fff" stroke="#DADCE0" strokeWidth={0.22} />
            ))}
          {c.kind === 1 &&
            [0, 1, 2].map((i) => (
              <rect key={i} x={x + 2.4 + i * ((w - 4.8) / 3)} y={y + 8.6} width={(w - 4.8) / 3 - 0.9} height={4.6} rx={0.6} fill={i === 1 ? '#E6F4F2' : '#F2F3F5'} />
            ))}
          {c.kind === 2 &&
            [0, 1, 2].map((i) => (
              <rect key={i} x={x + 2.4} y={y + 8.6 + i * 1.9} width={(w - 4.8) * (1 - i * 0.18)} height={0.9} rx={0.45} fill="#E5E6E9" />
            ))}
          <rect x={x + 2.4} y={y + hh - 4.2} width={7.2} height={2.4} rx={1.2} fill={TEAL} />
          {active && <rect x={x + 0.3} y={y + 3.6 + (hh - 4.2) * cl((u - k) / 0.85)} width={w - 0.6} height={1.1} fill={TEAL} opacity={0.16} />}
        </g>
        {ripple !== null && <circle cx={x + 5.9} cy={y + hh - 3} r={1 + ripple * 4} fill="none" stroke={TEAL} strokeWidth={0.3} opacity={1 - ripple} />}
      </g>
    )
  })

  const trays =
    holdT > -0.2
      ? TRAYS.map((t, s) => {
          const g = ease(cl((holdT + 0.05) * 2.4 - s * 0.2))
          if (g <= 0) return null
          const filled = CHIPS.filter((ch) => ch.tray === s).every((ch) => ease(holdT * 1.5 - ch.o * 0.03) >= 1)
          const y = t.y + (1 - g) * 3
          return (
            <g key={`tray${s}`} style={{ opacity: g }}>
              <rect x={t.x} y={y} width={t.w} height={t.h} rx={1.8} fill="#FFFFFF" stroke={filled ? TEAL : '#DADCE0'} strokeWidth={filled ? 0.45 : 0.3} filter="url(#vSh)" />
              <rect x={t.x + 1.3} y={y + 1.3} width={5} height={5} rx={1.2} fill={filled ? TEAL : '#E6F4F2'} />
              {[0, 1, 2].map((i) => (
                <line key={i} x1={t.x + 2.5} y1={y + 2.6 + i * 1.2} x2={t.x + 5.1} y2={y + 2.6 + i * 1.2} stroke={filled ? '#fff' : TEAL} strokeWidth={0.35} strokeLinecap="round" />
              ))}
              <rect x={t.x + 7.6} y={y + 1.5} width={9} height={1.2} rx={0.6} fill="#3E3E46" opacity={0.8} />
            </g>
          )
        })
      : null

  const chips = CHIPS.map((ch) => {
    const c = CARDS[ch.card]
    const app = ease(drawT * 1.45 - ch.o * 0.035)
    if (app <= 0) return null
    const sx = c.x + 2 + (1 - app) * 3
    const sy = c.y + c.h + 1.6 + ch.i * 5.2 + bob(ch.card)
    const m = ease(holdT * 1.5 - ch.o * 0.03)
    const t = TRAYS[ch.tray]
    const tx = t.x + 8 + ch.slot * 5.7
    const ty = t.y + 4.1
    const x = lerp(sx, tx, m)
    const y = lerp(sy, ty, m) - Math.sin(m * Math.PI) * 6
    const sc = lerp(1, 0.34, m)
    const rt = runT * 1.3 - ch.o * 0.025
    const prog = cl(rt * 4)
    const heal = ch.o === HEAL_CHIP && rt >= 0.25 && rt < 0.55
    const passed = runT > 0 && rt >= 0.25 && !heal
    const W = 15
    const H = 4.4
    const px = W + 1.6
    const py = -0.6
    return (
      <g key={`ch${ch.o}`} transform={`translate(${x.toFixed(2)} ${y.toFixed(2)}) scale(${sc.toFixed(3)})`} style={{ opacity: app }}>
        <rect x={0} y={0} width={W} height={H} rx={H / 2} fill="#FFFFFF" stroke={passed ? '#9FD8BF' : heal ? '#F0CF8E' : '#DADCE0'} strokeWidth={0.28 / sc} filter="url(#vSh)" />
        <rect x={4.2} y={H / 2 - 0.6} width={W - 6.4} height={1.2} rx={0.6} fill="#E5E6E9" opacity={1 - m} />
        <rect x={4.2} y={H / 2 - 0.6} width={(W - 6.4) * prog} height={1.2} rx={0.6} fill={heal ? '#F2C46B' : '#7FCBA9'} opacity={1 - m} />
        <circle cx={2.2} cy={H / 2} r={1.15} fill={passed ? '#0D8A64' : heal ? '#D4911E' : '#C8CACF'} style={{ transition: 'fill .3s' }} />
        {passed && <polyline points="1.65,2.25 2.1,2.7 2.85,1.75" fill="none" stroke="#fff" strokeWidth={0.35} strokeLinecap="round" strokeLinejoin="round" />}
        {app < 1 && app > 0.05 && (
          <path
            d={`M${px} ${py - 1.4} L${px + 0.35} ${py - 0.35} L${px + 1.4} ${py} L${px + 0.35} ${py + 0.35} L${px} ${py + 1.4} L${px - 0.35} ${py + 0.35} L${px - 1.4} ${py} L${px - 0.35} ${py - 0.35} Z`}
            fill={TEAL}
            opacity={1 - app}
          />
        )}
      </g>
    )
  })

  let cursor = null
  if (scanT < 1.15) {
    const seg = Math.min(CARDS.length - 2, Math.floor(u))
    const lt = ease(cl(u - seg))
    const tgt = (k: number): [number, number] => {
      const c = CARDS[k]
      return [c.x + 5.9, c.y + c.h - 3 + bob(k)]
    }
    const [p1x, p1y] = tgt(seg)
    const [p2x, p2y] = tgt(seg + 1)
    const cx = lerp(p1x, p2x, lt)
    const cy = lerp(p1y, p2y, lt) - Math.sin(lt * Math.PI) * 5
    cursor = (
      <path
        d="M0 0 L0 5.2 L1.45 3.9 L2.5 6.1 L3.35 5.7 L2.3 3.55 L4.1 3.4 Z"
        transform={`translate(${cx.toFixed(2)} ${cy.toFixed(2)})`}
        fill="#16161A"
        stroke="#fff"
        strokeWidth={0.4}
        strokeLinejoin="round"
        style={{ opacity: 1 - cl((scanT - 1) / 0.15) }}
      />
    )
  }

  return (
    <svg viewBox="0 0 100 100" width="100%" height="100%" aria-hidden="true" style={{ display: 'block', overflow: 'visible', opacity: fade, transition: 'opacity .3s' }}>
      <defs>
        <pattern id="vDots" width={4} height={4} patternUnits="userSpaceOnUse">
          <circle cx={0.5} cy={0.5} r={0.28} fill="#D3D5DA" />
        </pattern>
        <filter id="vSh" x="-20%" y="-20%" width="140%" height="160%">
          <feDropShadow dx={0} dy={0.8} stdDeviation={0.9} floodColor="#16161A" floodOpacity={0.08} />
        </filter>
      </defs>
      <rect x={-2} y={-2} width={104} height={104} fill="url(#vDots)" opacity={0.7} />
      {edges}
      {cards}
      {trays}
      {chips}
      {cursor}
    </svg>
  )
}
