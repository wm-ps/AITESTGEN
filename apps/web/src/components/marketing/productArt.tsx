import type { CSSProperties } from 'react'
import { TEAL } from './MarketingChrome'

// Decorative SVG art for the Product page (claude.ai/design "Vantage
// Product"). All motion is CSS keyframes (`product-*` in index.css), so none
// of these re-render; prefers-reduced-motion stops them there.

const GREEN = '#0D8A64'
const LINE = '#D3DCDA'
const BAR = '#E5E6E9'
// Lets transformOrigin: center/left mean the shape's own box, not the SVG's.
const FILL_BOX: CSSProperties = { transformBox: 'fill-box' }

function Svg({ viewBox, children }: { viewBox: string; children: React.ReactNode }) {
  return (
    <svg viewBox={viewBox} width="100%" height="100%" aria-hidden="true" style={{ display: 'block', overflow: 'visible' }}>
      {children}
    </svg>
  )
}

// --- Hero: an application map with two user journeys tracing through it ----

const MAP_X = [62, 131, 200, 269, 338]
const MAP_Y = [78, 154, 230, 306]
const MAP_OFF = new Set(['4,0', '0,1', '0,3', '4,1'])
const MAP_DUR = 9
const JOURNEYS = [
  { pts: [[0, 0], [1, 0], [1, 1], [2, 1], [3, 1], [3, 2], [4, 2]], start: 0 },
  { pts: [[0, 2], [1, 2], [2, 2], [2, 3], [3, 3], [4, 3]], start: 1.6 },
]
const MAP_LABELS: [number, number, string][] = [
  [0, 0, '/login'],
  [4, 2, '/checkout'],
  [0, 2, '/claims'],
  [4, 3, '/reports'],
  [2, 0, '/dashboard'],
]

export function HeroSchematic() {
  const has = (c: number, r: number) => !MAP_OFF.has(`${c},${r}`) && c >= 0 && c < 5 && r >= 0 && r < 4
  const nodes: [number, number][] = []
  for (let r = 0; r < 4; r++) for (let c = 0; c < 5; c++) if (has(c, r)) nodes.push([c, r])
  // When (seconds into the loop) each journey reaches a node, to light it up.
  const onPath = new Map<string, number>()
  JOURNEYS.forEach((j) => j.pts.forEach(([c, r], i) => onPath.set(`${c},${r}`, j.start + (i / (j.pts.length - 1)) * MAP_DUR * 0.45)))
  const mono = 'IBM Plex Mono, monospace'

  return (
    <svg viewBox="0 0 400 400" width="100%" height="100%" aria-hidden="true" style={{ display: 'block' }}>
      {nodes.map(([c, r]) => (
        <g key={`l${c}${r}`}>
          {has(c + 1, r) && (c + r) % 3 !== 2 && <line x1={MAP_X[c] + 17} y1={MAP_Y[r]} x2={MAP_X[c + 1] - 17} y2={MAP_Y[r]} stroke="#D5DEDC" strokeWidth={1} />}
          {has(c, r + 1) && (c * 2 + r) % 3 !== 1 && <line x1={MAP_X[c]} y1={MAP_Y[r] + 12} x2={MAP_X[c]} y2={MAP_Y[r + 1] - 12} stroke="#D5DEDC" strokeWidth={1} />}
        </g>
      ))}
      {JOURNEYS.map((j, ji) => {
        const d = j.pts.map(([c, r], i) => `${i ? 'L' : 'M'}${MAP_X[c]} ${MAP_Y[r]}`).join(' ')
        const [ec, er] = j.pts[j.pts.length - 1]
        const ex = MAP_X[ec]
        const ey = MAP_Y[er]
        return (
          <g key={`j${ji}`}>
            <path d={d} fill="none" stroke={TEAL} strokeOpacity={0.12} strokeWidth={6} strokeLinejoin="round" strokeLinecap="round" />
            <path
              d={d}
              fill="none"
              stroke={TEAL}
              strokeWidth={1.8}
              strokeLinejoin="round"
              strokeLinecap="round"
              pathLength={1}
              strokeDasharray={1}
              style={{ animation: `product-draw ${MAP_DUR}s ${j.start}s cubic-bezier(.45,0,.25,1) infinite both` }}
            />
            <g style={{ opacity: 0, animation: `product-on ${MAP_DUR}s ${(j.start + MAP_DUR * 0.47).toFixed(2)}s ease infinite both` }}>
              <circle cx={ex + 24} cy={ey - 16} r={7} fill={GREEN} />
              <polyline
                points={`${ex + 20.8},${ey - 16} ${ex + 23.2},${ey - 13.4} ${ex + 27.4},${ey - 18.6}`}
                fill="none"
                stroke="#fff"
                strokeWidth={1.6}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </g>
          </g>
        )
      })}
      {nodes.map(([c, r]) => {
        const x = MAP_X[c] - 17
        const y = MAP_Y[r] - 12
        const on = onPath.get(`${c},${r}`)
        return (
          <g key={`n${c}${r}`}>
            <rect x={x} y={y} width={34} height={24} rx={4} fill="#FFFFFF" stroke="#C9D4D2" strokeWidth={1} />
            <rect x={x + 6} y={y + 7} width={14} height={2.6} rx={1.3} fill="#C9D4D2" />
            <rect x={x + 6} y={y + 13} width={20} height={2.6} rx={1.3} fill="#E3E9E8" />
            {on !== undefined && (
              <g style={{ opacity: 0, animation: `product-on ${MAP_DUR}s ${on.toFixed(2)}s ease infinite both` }}>
                <rect x={x} y={y} width={34} height={24} rx={4} fill="#E6F4F2" stroke={TEAL} strokeWidth={1.3} />
                <rect x={x + 6} y={y + 7} width={14} height={2.6} rx={1.3} fill={TEAL} />
                <rect x={x + 6} y={y + 13} width={20} height={2.6} rx={1.3} fill="#9FD0C8" />
              </g>
            )}
          </g>
        )
      })}
      {MAP_LABELS.map(([c, r, t]) => (
        <text key={t} x={MAP_X[c]} y={MAP_Y[r] + 27} textAnchor="middle" fontFamily={mono} fontSize={8.5} fill="#6F7F7C">
          {t}
        </text>
      ))}
      <text x={30} y={34} fontFamily={mono} fontSize={9} letterSpacing={1.2} fill="#5C6B68">
        APPLICATION MAP
      </text>
      <g fontFamily={mono} fontSize={8.5} fill="#5C6B68">
        <line x1={30} y1={366} x2={46} y2={366} stroke={TEAL} strokeWidth={1.8} />
        <text x={52} y={369}>
          User journey
        </text>
        <circle cx={142} cy={366} r={4.5} fill={GREEN} />
        <text x={152} y={369}>
          Test passed
        </text>
      </g>
    </svg>
  )
}

// --- CTA band: slowly rotating concentric dial ------------------------------

export function Dial() {
  const C = 200
  const line = 'rgba(255,255,255,0.22)'
  const accent = '#BFE6E0'
  const rings = [56, 96, 136, 176]
  const speeds = [38, 56, 80, 120]
  const arcs = [0.22, 0.16, 0.12, 0.08]
  const ticks = []
  for (let a = 0; a < 360; a += 6) {
    const th = (a * Math.PI) / 180
    const long = a % 30 === 0
    ticks.push(
      <line
        key={a}
        x1={C + Math.cos(th) * 182}
        y1={C + Math.sin(th) * 182}
        x2={C + Math.cos(th) * (long ? 192 : 187)}
        y2={C + Math.sin(th) * (long ? 192 : 187)}
        stroke={long ? 'rgba(255,255,255,0.4)' : line}
        strokeWidth={0.9}
      />,
    )
  }
  return (
    <svg viewBox="0 0 400 400" width="100%" height="100%" aria-hidden="true" style={{ display: 'block', overflow: 'visible' }}>
      <line x1={0} y1={C} x2={400} y2={C} stroke={line} strokeWidth={0.6} />
      <line x1={C} y1={0} x2={C} y2={400} stroke={line} strokeWidth={0.6} />
      {rings.map((r) => (
        <circle key={r} cx={C} cy={C} r={r} fill="none" stroke={line} strokeWidth={0.9} />
      ))}
      <g style={{ transformOrigin: '200px 200px', animation: 'product-spin 240s linear infinite' }}>{ticks}</g>
      {rings.map((r, i) => {
        const circ = 2 * Math.PI * r
        const len = circ * arcs[i]
        const lead = i === 1
        return (
          <g
            key={`o${r}`}
            style={{ transformOrigin: '200px 200px', animation: `${i % 2 ? 'product-spin-rev' : 'product-spin'} ${speeds[i]}s linear infinite` }}
          >
            <circle
              cx={C}
              cy={C}
              r={r}
              fill="none"
              stroke={accent}
              strokeWidth={lead ? 1.8 : 1.1}
              strokeOpacity={lead ? 0.95 : 0.5}
              strokeDasharray={`${len} ${circ - len}`}
              strokeLinecap="round"
            />
            <circle cx={C + r} cy={C} r={lead ? 4.6 : 2.8} fill={lead ? accent : '#FFFFFF'} fillOpacity={lead ? 1 : 0.6} />
            {lead && <circle cx={C + r} cy={C} r={10} fill="none" stroke={accent} strokeOpacity={0.35} strokeWidth={0.9} />}
          </g>
        )
      })}
    </svg>
  )
}

// --- Capability card art -----------------------------------------------------

function PageCard({ x, y, w, h, accent }: { x: number; y: number; w: number; h: number; accent: boolean }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={8} fill="#FFFFFF" stroke={accent ? TEAL : '#DADCE0'} strokeWidth={accent ? 1.4 : 1} />
      <line x1={x} y1={y + 14} x2={x + w} y2={y + 14} stroke="#EBECEE" />
      {[0, 1, 2].map((i) => (
        <circle key={i} cx={x + 9 + i * 7} cy={y + 7} r={2.2} fill={i === 0 && accent ? TEAL : '#DADCE0'} />
      ))}
      <rect x={x + 10} y={y + 22} width={w * 0.45} height={6} rx={2} fill="#3E3E46" opacity={0.8} />
      <rect x={x + 10} y={y + 34} width={w - 20} height={4} rx={2} fill={BAR} />
      <rect x={x + 10} y={y + 42} width={w * 0.6} height={4} rx={2} fill={BAR} />
      <rect x={x + 10} y={y + h - 16} width={28} height={9} rx={4.5} fill={TEAL} />
    </g>
  )
}

export function ArtExplore() {
  const P = [[40, 40], [200, 20], [340, 60], [90, 190], [250, 170], [370, 220], [180, 290]]
  const E = [[0, 1], [1, 2], [0, 3], [1, 4], [2, 5], [3, 4], [4, 5], [3, 6], [4, 6]]
  const W = 92
  const H = 66
  const c = (i: number) => [P[i][0] + W / 2, P[i][1] + H / 2]
  const [px, py] = c(4)
  return (
    <Svg viewBox="0 0 480 380">
      {E.map(([a, b], k) => {
        const [x1, y1] = c(a)
        const [x2, y2] = c(b)
        return (
          <g key={k}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={LINE} strokeWidth={1.2} />
            <line
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={TEAL}
              strokeWidth={1.4}
              strokeDasharray="4 16"
              style={{ animation: `product-dash ${2 + (k % 3) * 0.6}s linear infinite` }}
            />
          </g>
        )
      })}
      {P.map((p, i) => (
        <PageCard key={i} x={p[0]} y={p[1]} w={W} h={H} accent={i === 4} />
      ))}
      <circle cx={px} cy={py} r={60} fill="none" stroke={TEAL} strokeWidth={1.2} style={{ ...FILL_BOX, transformOrigin: 'center', animation: 'product-ping 2.6s ease-out infinite' }} />
    </Svg>
  )
}

function Sparkle({ x, y, s, delay }: { x: number; y: number; s: number; delay: number }) {
  const q = s * 0.25
  const d = `M${x} ${y - s} L${x + q} ${y - q} L${x + s} ${y} L${x + q} ${y + q} L${x} ${y + s} L${x - q} ${y + q} L${x - s} ${y} L${x - q} ${y - q} Z`
  return <path d={d} fill={TEAL} style={{ ...FILL_BOX, transformOrigin: 'center', animation: `product-twinkle 2.8s ${delay}s ease-in-out infinite` }} />
}

// [line index, width, colour]; width 0 is a blank line in the code panel.
const CODE_LINES: [number, number, string][] = [
  [0, 70, '#7FCFC4'],
  [1, 120, '#C9D8D5'],
  [2, 96, '#C9D8D5'],
  [4, 110, '#F2C46B'],
  [5, 140, '#C9D8D5'],
  [6, 88, '#7FCFC4'],
  [7, 124, '#C9D8D5'],
  [8, 60, '#C9D8D5'],
  [10, 104, '#7FCFC4'],
]

export function ArtGenerate() {
  return (
    <Svg viewBox="0 0 480 380">
      <rect x={20} y={60} width={170} height={250} rx={14} fill="#FFFFFF" stroke="#DADCE0" />
      <rect x={38} y={80} width={80} height={8} rx={3} fill="#3E3E46" opacity={0.8} />
      {[0, 1, 2, 3, 4].map((i) => {
        const y = 110 + i * 38
        return (
          <g key={i}>
            <rect x={36} y={y} width={138} height={28} rx={7} fill={i === 1 ? '#E6F4F2' : '#F5F6F7'} stroke={i === 1 ? TEAL : 'none'} />
            <circle cx={50} cy={y + 14} r={4} fill={i < 2 ? TEAL : '#C8CACF'} />
            <rect x={62} y={y + 11} width={70 + (i % 3) * 18} height={6} rx={3} fill="#D3D5DA" />
          </g>
        )
      })}
      <path d="M200 185 C 230 185, 230 185, 262 185" fill="none" stroke={TEAL} strokeWidth={1.6} strokeDasharray="4 6" style={{ animation: 'product-dash 1.6s linear infinite' }} />
      <path d="M256 179 L264 185 L256 191" fill="none" stroke={TEAL} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
      <rect x={272} y={40} width={190} height={290} rx={14} fill="#11201F" />
      {[0, 1, 2].map((i) => (
        <circle key={i} cx={290 + i * 10} cy={58} r={3} fill="#2E4A47" />
      ))}
      {CODE_LINES.map(([i, w, col]) => (
        <rect
          key={i}
          x={290 + (i % 4 === 1 ? 12 : 0)}
          y={80 + i * 22}
          width={w}
          height={7}
          rx={3.5}
          fill={col}
          opacity={0.85}
          style={{ ...FILL_BOX, transformOrigin: 'left', animation: `product-grow 6s ${(i * 0.18).toFixed(2)}s ease-out infinite` }}
        />
      ))}
      <Sparkle x={248} y={120} s={9} delay={0} />
      <Sparkle x={230} y={250} s={6} delay={0.9} />
      <Sparkle x={452} y={30} s={7} delay={1.6} />
    </Svg>
  )
}

export function ArtExecute() {
  const lanes = [3.4, 4.6, 3.9, 5.2, 4.2]
  return (
    <Svg viewBox="0 0 480 380">
      <rect x={20} y={30} width={440} height={320} rx={16} fill="#FFFFFF" stroke="#DADCE0" />
      <rect x={44} y={54} width={120} height={9} rx={3} fill="#3E3E46" opacity={0.8} />
      <rect x={372} y={50} width={64} height={18} rx={9} fill="#E6F4F2" />
      <circle cx={386} cy={59} r={3.5} fill={TEAL} style={{ ...FILL_BOX, transformOrigin: 'center', animation: 'product-twinkle 1.6s ease-in-out infinite' }} />
      {lanes.map((d, i) => {
        const y = 96 + i * 48
        // One lane goes amber (self-healing) before it passes.
        const heal = i === 3
        return (
          <g key={i}>
            <circle cx={56} cy={y + 12} r={9} fill="#C8CACF" style={{ animation: `${heal ? 'product-heal' : 'product-pass'} ${d}s linear infinite` }} />
            <polyline points={`51,${y + 12} 55,${y + 16} 61,${y + 8}`} fill="none" stroke="#fff" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
            <rect x={80} y={y + 2} width={90 + (i % 3) * 22} height={7} rx={3.5} fill="#3E3E46" opacity={0.7} />
            <rect x={80} y={y + 16} width={340} height={6} rx={3} fill={BAR} />
            <rect
              x={80}
              y={y + 16}
              width={340}
              height={6}
              rx={3}
              fill={heal ? '#D4911E' : GREEN}
              opacity={0.85}
              style={{ ...FILL_BOX, transformOrigin: 'left', animation: `product-fill ${d}s linear infinite` }}
            />
          </g>
        )
      })}
    </Svg>
  )
}

// Isometric slab: polygon point strings for its top, right and left faces.
function iso(cx: number, cy: number, w: number, d: number, z: number, th: number) {
  const p = (x: number, y: number, zz: number) => [cx + (x - y) * 0.87, cy + (x + y) * 0.5 - zz]
  const hw = w / 2
  const hd = d / 2
  const s = (a: number[][]) => a.map((q) => `${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(' ')
  return {
    top: s([p(-hw, -hd, z + th), p(hw, -hd, z + th), p(hw, hd, z + th), p(-hw, hd, z + th)]),
    right: s([p(hw, -hd, z), p(hw, hd, z), p(hw, hd, z + th), p(hw, -hd, z + th)]),
    left: s([p(-hw, hd, z), p(hw, hd, z), p(hw, hd, z + th), p(-hw, hd, z + th)]),
  }
}

const SLABS = [
  { z: 0, c: ['#FFFFFF', '#E5E9E8', '#D6DCDB'], st: '#C8D2D0', d: 0 },
  { z: 46, c: ['#E6F4F2', '#C7E5E0', '#B3D9D3'], st: '#9FD0C8', d: 0.5 },
  { z: 92, c: [TEAL, '#0B5E57', '#0A524C'], st: '#0A524C', d: 1 },
]

export function ArtManage() {
  return (
    <Svg viewBox="0 0 480 380">
      {SLABS.map((s, i) => {
        const g = iso(240, 210, 200, 200, s.z, 16)
        const chip = iso(240, 210, 34, 34, s.z + 16, 8)
        return (
          <g key={i} style={{ animation: `product-float 5s ${s.d}s ease-in-out infinite` }}>
            <polygon points={g.right} fill={s.c[2]} stroke={s.st} strokeWidth={0.8} />
            <polygon points={g.left} fill={s.c[1]} stroke={s.st} strokeWidth={0.8} />
            <polygon points={g.top} fill={s.c[0]} stroke={s.st} strokeWidth={0.8} />
            {i === 2 &&
              [[-60, -40], [-10, -40], [40, -40], [-60, 10], [-10, 10]].map(([x, y], k) => (
                <g key={k} transform={`translate(${(x - y) * 0.87 + 30} ${(x + y) * 0.5 + 14})`}>
                  <polygon points={chip.right} fill="#D6EFEA" />
                  <polygon points={chip.left} fill="#BFE6E0" />
                  <polygon points={chip.top} fill="#FFFFFF" />
                </g>
              ))}
          </g>
        )
      })}
    </Svg>
  )
}
