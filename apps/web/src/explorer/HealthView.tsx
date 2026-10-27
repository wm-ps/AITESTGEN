import { useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'
import { faBan, faBug, faChevronDown, faFileArrowDown, faLinkSlash, faServer } from '@fortawesome/free-solid-svg-icons'
import { LoadingDots } from '../components/LoadingDots'
import { explorerApi, shotUrl, type ExplorerHealthIssue, type ExplorerQuestion } from './explorerApi'
import { glassCard, IconTile, Pill } from './ui'

// Only what a person would call a bug. Slow pages, wording nits and errors
// hidden in the browser console are left out — they buried the real ones.
const KIND: Record<string, { icon: IconDefinition; label: string }> = {
  looks_wrong: { icon: faBug, label: 'Looks wrong' },
  crash: { icon: faBan, label: 'Broken screen' },
  server_error: { icon: faServer, label: 'Server error' },
  broken_link: { icon: faLinkSlash, label: 'Broken link' },
}

export function possibleBugs(issues: ExplorerHealthIssue[]): ExplorerHealthIssue[] {
  return issues.filter((i) => i.kind in KIND)
}

// One CSV cell. Text comes from the app under test, so a leading = + - @ is
// defused (Excel would run it as a formula); quotes are doubled.
function cell(value: string | number): string {
  const text = String(value ?? '')
  const safe = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text
  return `"${safe.replace(/"/g, '""')}"`
}

// Every finding as a CSV Excel opens directly (UTF-8 with BOM).
export function bugsCsv(bugs: ExplorerHealthIssue[], questions: ExplorerQuestion[]): string {
  const waiting = (issue: ExplorerHealthIssue) =>
    !!issue.shot_id && questions.some((q) => q.kind === 'rule' && q.status === 'open' && q.shot_id === issue.shot_id)
  const header = ['Type', 'Severity', 'Needs your answer', 'Title', 'Details', 'Page', 'Times seen']
  const rows = bugs.map((issue) => [
    KIND[issue.kind]?.label ?? issue.kind,
    issue.severity === 'high' ? 'Bug' : issue.severity,
    waiting(issue) ? 'Yes' : 'No',
    issue.title,
    issue.detail ?? '',
    issue.url,
    issue.occurrences,
  ])
  return '\ufeff' + [header, ...rows].map((r) => r.map(cell).join(',')).join('\r\n')
}

function downloadCsv(name: string, csv: string) {
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

// Folded by default: worth a look, never the headline. A mission's "is this
// a bug?" question is answered right on the finding it is about.
export function HealthView({
  issues,
  questions,
  onAnswered,
  onOpenShot,
}: {
  issues: ExplorerHealthIssue[]
  questions: ExplorerQuestion[]
  onAnswered: () => Promise<void>
  onOpenShot: (shotId: string, caption: string) => void
}) {
  const bugs = possibleBugs(issues)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const askFor = (issue: ExplorerHealthIssue) =>
    issue.shot_id ? questions.find((q) => q.kind === 'rule' && q.status === 'open' && q.shot_id === issue.shot_id) : undefined

  const act = async (key: string, run: () => Promise<void>) => {
    setBusy(key)
    try {
      await run()
      await onAnswered()
    } finally {
      setBusy(null)
    }
  }

  return (
    <div style={{ ...glassCard, padding: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 10, padding: '14px 20px', border: 'none', background: 'transparent', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}
        >
          <FontAwesomeIcon icon={faBug} style={{ fontSize: 12.5, color: 'var(--fg-4)' }} />
          <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: 'var(--fg-2)' }}>Things that look wrong</span>
          <span style={{ fontSize: 12.5, color: 'var(--fg-4)' }}>{bugs.length}</span>
          <FontAwesomeIcon icon={faChevronDown} style={{ fontSize: 11, color: 'var(--fg-5)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 200ms ease' }} />
        </button>
        {bugs.length > 0 && (
          <button
            type="button"
            className="button-secondary"
            onClick={() => downloadCsv('things-that-look-wrong.csv', bugsCsv(bugs, questions))}
            title="Download every finding as a CSV file (opens in Excel)"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, margin: '0 16px 0 0', padding: '5px 11px', fontSize: 12.5, flex: 'none' }}
          >
            <FontAwesomeIcon icon={faFileArrowDown} style={{ fontSize: 11 }} /> Download CSV
          </button>
        )}
      </div>
      {open && bugs.length === 0 && <div style={{ padding: '0 20px 16px', fontSize: 13.5, color: 'var(--fg-3)' }}>Nothing so far.</div>}
      {/* A compact grid: every finding, its proof and its answers at a glance, no expanding. */}
      {open && bugs.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 10, padding: '0 16px 16px' }}>
          {bugs.map((issue) => {
            const kind = KIND[issue.kind]
            const q = askFor(issue)
            const action = (label: string, run: () => Promise<void>, primary = false) => (
              <button type="button" className={primary ? 'button-primary' : 'button-secondary'} disabled={busy !== null} onClick={() => void act(issue.id + label, run)} style={{ padding: '4px 10px', fontSize: 12 }}>
                {busy === issue.id + label ? <LoadingDots label="Saving" /> : label}
              </button>
            )
            return (
              <div key={issue.id} style={{ display: 'flex', gap: 10, padding: 10, border: '1px solid var(--line)', borderRadius: 10, background: 'white', minWidth: 0 }}>
                {issue.shot_id ? (
                  <img
                    src={shotUrl(issue.shot_id)}
                    alt=""
                    onClick={() => onOpenShot(issue.shot_id!, issue.title)}
                    style={{ width: 88, height: 56, flex: 'none', objectFit: 'cover', objectPosition: 'top', borderRadius: 6, border: '1px solid var(--line)', cursor: 'zoom-in' }}
                  />
                ) : (
                  <IconTile icon={kind.icon} tone={issue.severity === 'high' ? 'bad' : 'warn'} size={26} />
                )}
                <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', minWidth: 0 }}>
                    <Pill tone={issue.severity === 'high' ? 'bad' : 'warn'}>{issue.severity === 'high' ? 'Bug' : kind.label}</Pill>
                    {q && <span style={{ width: 7, height: 7, flex: 'none', borderRadius: 1000, background: 'var(--warn-2)', animation: 'explorer-attention 1.6s ease-out infinite' }} title="Needs your answer" />}
                  </div>
                  <div title={issue.title} style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--fg)', lineHeight: '17px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{issue.title}</div>
                  {issue.detail && <div title={issue.detail} style={{ fontSize: 12, color: 'var(--fg-3)', lineHeight: '16px', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', wordBreak: 'break-word' }}>{issue.detail}</div>}
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
                    {q && action("It's a bug", () => explorerApi.answer(q.id, "It's a bug").then(() => undefined), true)}
                    {q && action("It's correct", () => explorerApi.answer(q.id, "It's correct — that's how it should work").then(() => undefined))}
                    {action('False alarm', () => explorerApi.falseAlarm(issue.id))}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
