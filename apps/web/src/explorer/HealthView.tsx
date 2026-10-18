import { useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'
import { faBan, faBug, faChevronDown, faLinkSlash, faServer } from '@fortawesome/free-solid-svg-icons'
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
  const [openId, setOpenId] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const askFor = (issue: ExplorerHealthIssue) =>
    issue.shot_id ? questions.find((q) => q.kind === 'rule' && q.status === 'open' && q.shot_id === issue.shot_id) : undefined

  const send = async (q: ExplorerQuestion, answer: string) => {
    setBusy(q.id + answer)
    try {
      await explorerApi.answer(q.id, answer)
      await onAnswered()
    } finally {
      setBusy(null)
    }
  }

  return (
    <div style={{ ...glassCard, padding: 0, overflow: 'hidden' }}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '14px 20px', border: 'none', background: 'transparent', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}
      >
        <FontAwesomeIcon icon={faBug} style={{ fontSize: 12.5, color: 'var(--fg-4)' }} />
        <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: 'var(--fg-2)' }}>Things that look wrong</span>
        <span style={{ fontSize: 12.5, color: 'var(--fg-4)' }}>{bugs.length}</span>
        <FontAwesomeIcon icon={faChevronDown} style={{ fontSize: 11, color: 'var(--fg-5)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 200ms ease' }} />
      </button>
      {open && bugs.length === 0 && <div style={{ padding: '0 20px 16px', fontSize: 13.5, color: 'var(--fg-3)' }}>Nothing so far.</div>}
      {open &&
        bugs.map((issue) => {
          const kind = KIND[issue.kind]
          const expanded = openId === issue.id
          const q = askFor(issue)
          return (
            <div key={issue.id} style={{ borderTop: '1px solid var(--line)' }}>
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => setOpenId(expanded ? null : issue.id)}
                style={{ width: '100%', display: 'flex', gap: 12, alignItems: 'center', padding: '10px 20px', border: 'none', background: 'transparent', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}
              >
                <IconTile icon={kind.icon} tone={issue.severity === 'high' ? 'bad' : 'warn'} size={26} />
                <span style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{issue.title}</span>
                {q && <span style={{ width: 8, height: 8, flex: 'none', borderRadius: 1000, background: 'var(--warn-2)', animation: 'explorer-attention 1.6s ease-out infinite' }} title="Needs your answer" />}
                <FontAwesomeIcon icon={faChevronDown} style={{ fontSize: 10, color: 'var(--fg-5)', transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 200ms ease' }} />
              </button>
              {expanded && (
                <div style={{ padding: '0 20px 14px 58px', display: 'flex', gap: 14, flexWrap: 'wrap', animation: 'aitg-fade-up 200ms ease' }}>
                  {issue.shot_id && (
                    <img
                      src={shotUrl(issue.shot_id)}
                      alt=""
                      onClick={() => onOpenShot(issue.shot_id!, issue.title)}
                      style={{ width: 200, aspectRatio: '16 / 10', objectFit: 'cover', objectPosition: 'top', borderRadius: 8, border: '1px solid var(--line)', cursor: 'zoom-in' }}
                    />
                  )}
                  <div style={{ flex: '1 1 260px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <Pill tone={issue.severity === 'high' ? 'bad' : 'warn'}>{issue.severity === 'high' ? 'Bug' : kind.label}</Pill>
                    {issue.detail && <div style={{ fontSize: 12.5, color: 'var(--fg-3)', lineHeight: '18px', wordBreak: 'break-word' }}>{issue.detail}</div>}
                    {q && (
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <button type="button" className="button-primary" disabled={busy !== null} onClick={() => void send(q, "It's a bug")} style={{ padding: '6px 12px', fontSize: 12.5 }}>
                          {busy === q.id + "It's a bug" ? <LoadingDots label="Saving" /> : "It's a bug"}
                        </button>
                        <button type="button" className="button-secondary" disabled={busy !== null} onClick={() => void send(q, "It's correct — that's how it should work")} style={{ padding: '6px 12px', fontSize: 12.5 }}>
                          {busy === q.id + "It's correct — that's how it should work" ? <LoadingDots label="Saving" /> : "It's correct"}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
    </div>
  )
}
