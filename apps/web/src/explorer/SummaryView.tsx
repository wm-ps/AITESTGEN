import { useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faBullseye, faCircleCheck, faCircleQuestion, faListOl, faPen, faPlus, faTrashCan } from '@fortawesome/free-solid-svg-icons'
import { LoadingDots } from '../components/LoadingDots'
import { shotUrl, type AppBrief, type ExplorerRun, type ExplorerScreen } from './explorerApi'
import { glassCard, Pill, SectionTitle } from './ui'

// Only what Explorer can stand behind: what the app is, the tasks it will
// test, and the questions it needs answered. Its guesses about the business
// (who uses it, business objects and their statuses, expected rules, parts
// that may appear sometimes) are left out of view — they were too often wrong.

const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '7px 10px',
  border: '1px solid var(--border-2)',
  borderRadius: 8,
  fontSize: 13,
  fontFamily: 'inherit',
  color: 'var(--fg)',
  background: 'white',
}

export function SummaryView({
  run,
  screens,
  onSave,
  onConfirm,
}: {
  run: ExplorerRun
  screens: ExplorerScreen[]
  onSave: (brief: AppBrief) => Promise<void>
  onConfirm: () => Promise<void>
}) {
  const [draft, setDraft] = useState<AppBrief>(run.brief ?? {})
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState<'save' | 'confirm' | null>(null)
  // Confirm pressed with a question still open: say why nothing happened.
  const [confirmBlocked, setConfirmBlocked] = useState(false)
  const questionsRef = useRef<HTMLDivElement>(null)
  const editable = run.status === 'awaiting_confirmation'

  useEffect(() => {
    if (!editing) setDraft(run.brief ?? {})
  }, [run.brief, editing])

  const set = <K extends keyof AppBrief>(key: K, value: AppBrief[K]) => setDraft((d) => ({ ...d, [key]: value }))
  const updateTask = (index: number, patch: object) => {
    const list = [...(draft.key_tasks ?? [])]
    list[index] = { ...list[index], ...patch }
    set('key_tasks', list)
  }

  const save = async (next: AppBrief = draft) => {
    setBusy('save')
    try {
      await onSave(next)
      setEditing(false)
    } finally {
      setBusy(null)
    }
  }

  const answer = async (index: number, option: string) => {
    const questions = [...(draft.questions_for_you ?? [])]
    questions[index] = { ...questions[index], answer: option }
    const next = { ...draft, questions_for_you: questions }
    setDraft(next)
    if (!editing && editable) await onSave(next)
  }

  if (!run.brief) {
    return (
      <div style={{ ...glassCard, padding: 28, fontSize: 13.5, color: 'var(--fg-3)' }}>
        The App Summary appears here once Explorer has finished looking around.
      </div>
    )
  }

  const b = draft
  // Questions can only be answered before the summary is confirmed; after
  // that only the answered ones are worth showing.
  const questions = (b.questions_for_you ?? []).map((q, i) => ({ ...q, i })).filter((q) => editable || q.answer)
  const unanswered = questions.filter((q) => !q.answer).length
  // One tile per screen name; screens behind a choice show under their own name too.
  const tiles = [...new Map(screens.map((s) => [s.name, s])).values()]
  const skipped = new Set(b.skip_screens ?? [])
  const toggleScreen = (name: string) => {
    const next = { ...draft, skip_screens: skipped.has(name) ? [...skipped].filter((n) => n !== name) : [...skipped, name] }
    setDraft(next)
    if (!editing) void onSave(next)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ ...glassCard, padding: '22px 24px', display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap', background: 'linear-gradient(135deg, rgba(255,255,255,0.95), color-mix(in srgb, var(--accent-wash) 70%, white))' }}>
        <div style={{ flex: '1 1 360px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div>
            {run.brief_confirmed_at ? <Pill tone="ok" icon={faCircleCheck}>Confirmed by you</Pill> : run.status === 'expired' ? <Pill tone="neutral">Expired: not confirmed in time</Pill> : <Pill tone="warn">Waiting for your review</Pill>}
          </div>
          {editing ? (
            <>
              <input aria-label="Application name" placeholder="Enter the application name" value={b.app_name ?? ''} onChange={(e) => set('app_name', e.target.value)} style={{ ...inputStyle, fontSize: 18, fontWeight: 600 }} />
              <textarea aria-label="One-line description" placeholder="Describe in one sentence what this app is and who it is for" value={b.one_liner ?? ''} onChange={(e) => set('one_liner', e.target.value)} rows={2} style={{ ...inputStyle, resize: 'vertical' }} />
            </>
          ) : (
            <>
              <h2 style={{ margin: 0, fontSize: 22, fontWeight: 650, letterSpacing: '-0.02em', color: 'var(--fg)' }}>{b.app_name}</h2>
              <p style={{ margin: 0, fontSize: 15, lineHeight: '23px', color: 'var(--fg-2)', maxWidth: 820 }}>{b.one_liner}</p>
            </>
          )}
        </div>
        {editable && (
          <div style={{ display: 'flex', gap: 8, flex: 'none' }}>
            {editing ? (
              <>
                <button type="button" className="button-secondary" onClick={() => { setDraft(run.brief ?? {}); setEditing(false) }}>Cancel</button>
                <button type="button" className="button-primary" disabled={busy !== null} onClick={() => save()}>
                  {busy === 'save' ? <LoadingDots label="Saving" /> : 'Save changes'}
                </button>
              </>
            ) : (
              <>
                <button type="button" className="button-secondary" onClick={() => setEditing(true)} style={{ display: 'inline-flex', gap: 7, alignItems: 'center' }}>
                  <FontAwesomeIcon icon={faPen} style={{ fontSize: 11 }} /> Edit
                </button>
                <button
                  type="button"
                  className="button-primary"
                  disabled={busy !== null}
                  onClick={async () => {
                    if (unanswered > 0) {
                      setConfirmBlocked(true)
                      questionsRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
                      return
                    }
                    setBusy('confirm')
                    try {
                      await onConfirm()
                    } finally {
                      setBusy(null)
                    }
                  }}
                  style={{ display: 'inline-flex', gap: 7, alignItems: 'center', animation: 'explorer-attention 1.8s ease-out infinite' }}
                >
                  {busy === 'confirm' ? <LoadingDots label="Confirming" /> : (<><FontAwesomeIcon icon={faCircleCheck} /> Looks right — confirm</>)}
                </button>
                {confirmBlocked && unanswered > 0 && (
                  <span role="alert" style={{ alignSelf: 'center', fontSize: 12.5, fontWeight: 600, color: 'var(--warn-2)' }}>
                    Answer the questions first — they change what Explorer tests.
                  </span>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {questions.length > 0 && (
        <div
          ref={questionsRef}
          style={{
            ...glassCard,
            padding: '18px 20px',
            ...(editable && unanswered
              ? { borderColor: 'color-mix(in srgb, var(--warn-2) 40%, transparent)', animation: 'explorer-attention 1.8s ease-out infinite' }
              : {}),
          }}
        >
          <SectionTitle
            icon={faCircleQuestion}
            aside={
              <span style={{ fontSize: 12, color: editable && unanswered ? 'var(--warn-2)' : 'var(--fg-5)', fontWeight: editable && unanswered ? 600 : 400 }}>
                {editable ? (unanswered ? `Pick an answer for ${unanswered} before you confirm` : 'All answered') : 'Your answers'}
              </span>
            }
          >
            Questions for you
          </SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {questions.map((q, n) => (
              <SummaryQuestion key={q.i} number={n + 1} question={q.question} options={q.options} answer={q.answer} editable={editable} onAnswer={(a) => answer(q.i, a)} />
            ))}
          </div>
        </div>
      )}

      <div style={{ ...glassCard, padding: '18px 20px' }}>
        <SectionTitle
          icon={faListOl}
          aside={editing ? (
            <button type="button" className="button-secondary" style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => set('key_tasks', [...(b.key_tasks ?? []), { name: '', why_it_matters: '' }])}>
              <FontAwesomeIcon icon={faPlus} style={{ fontSize: 10, marginRight: 5 }} /> Add task
            </button>
          ) : undefined}
        >
          What Explorer will test
        </SectionTitle>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {(b.key_tasks ?? []).map((task, i) => (
            <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '10px 0', borderTop: i ? '1px solid var(--line)' : 'none' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-2)', fontWeight: 700 }}>{String(i + 1).padStart(2, '0')}</span>
              {editing ? (
                <>
                  <input aria-label="Task name" placeholder="Enter the task" value={task.name} onChange={(e) => updateTask(i, { name: e.target.value })} style={inputStyle} />
                  <button type="button" aria-label="Remove" onClick={() => set('key_tasks', (b.key_tasks ?? []).filter((_, k) => k !== i))} style={{ flex: 'none', width: 28, height: 28, border: '1px solid var(--line)', borderRadius: 8, background: 'white', color: 'var(--fg-4)', cursor: 'pointer' }}>
                    <FontAwesomeIcon icon={faTrashCan} style={{ fontSize: 11 }} />
                  </button>
                </>
              ) : (
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--fg)' }}>{task.name}</span>
              )}
            </div>
          ))}
        </div>
      </div>

      <div style={{ ...glassCard, padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <SectionTitle
          icon={faBullseye}
          aside={tiles.length > 0 ? <span style={{ fontSize: 12, color: 'var(--fg-5)' }}>{tiles.length - tiles.filter((t) => skipped.has(t.name)).length} of {tiles.length} screens included</span> : undefined}
        >
          Goal
        </SectionTitle>
        {editable ? (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <label htmlFor="explorer-focus" style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-2)' }}>
                Goal for this run <span style={{ fontWeight: 400, color: 'var(--fg-5)' }}>(optional)</span>
              </label>
              <textarea
                id="explorer-focus"
                rows={2}
                value={b.focus ?? ''}
                onChange={(e) => set('focus', e.target.value)}
                onBlur={() => { if (!editing && (b.focus ?? '') !== (run.brief?.focus ?? '')) void onSave(draft) }}
                placeholder="Describe what Explorer should focus on, or leave empty to cover the whole app"
                style={{ ...inputStyle, resize: 'vertical' }}
              />
            </div>
            {tiles.length > 0 && (
              <div style={{ fontSize: 12.5, color: 'var(--fg-4)' }}>
                Untick screens Explorer should leave alone. It won't plan missions or scenarios for them.
              </div>
            )}
          </>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13.5, color: 'var(--fg-2)' }}>
            <div><span style={{ fontWeight: 600 }}>Goal:</span> {b.focus?.trim() || 'The whole app'}</div>
            <div><span style={{ fontWeight: 600 }}>Left out:</span> {skipped.size ? [...skipped].join(', ') : 'Nothing'}</div>
          </div>
        )}
        {editable && tiles.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 10 }}>
            {tiles.map((t) => {
              const on = !skipped.has(t.name)
              return (
                <label key={t.name} style={{ display: 'flex', flexDirection: 'column', borderRadius: 10, overflow: 'hidden', cursor: 'pointer', border: `1px solid ${on ? 'color-mix(in srgb, var(--accent-2) 35%, transparent)' : 'var(--line)'}`, background: 'white', opacity: on ? 1 : 0.55, transition: 'all 150ms ease' }}>
                  <span style={{ aspectRatio: '16 / 10', background: 'var(--bg-2)', overflow: 'hidden' }}>
                    {t.shot_id && <img src={shotUrl(t.shot_id)} alt="" loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top', filter: on ? 'none' : 'grayscale(1)' }} />}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px' }}>
                    <input type="checkbox" checked={on} onChange={() => toggleScreen(t.name)} style={{ accentColor: 'var(--accent-2)', flex: 'none' }} />
                    <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={t.name}>{t.name}</span>
                  </span>
                </label>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// One summary question, easy to scan: numbered, the question on its own
// line, then the choices. "Other" is always there for an answer the choices
// don't cover.
function SummaryQuestion({
  number,
  question,
  options,
  answer,
  editable,
  onAnswer,
}: {
  number: number
  question: string
  options: string[]
  answer?: string
  editable: boolean
  onAnswer: (answer: string) => void
}) {
  const custom = !!answer && !options.includes(answer)
  const [typing, setTyping] = useState(false)
  const [text, setText] = useState(custom ? answer : '')
  const pill = (label: string, chosen: boolean, onClick: () => void) => (
    <button
      key={label}
      type="button"
      disabled={!editable}
      onClick={onClick}
      style={{
        padding: '7px 13px',
        borderRadius: 1000,
        fontSize: 12.5,
        fontFamily: 'inherit',
        fontWeight: chosen ? 600 : 500,
        cursor: editable ? 'pointer' : 'default',
        color: chosen ? 'white' : 'var(--fg-2)',
        background: chosen ? 'var(--accent-2)' : 'white',
        border: `1px solid ${chosen ? 'var(--accent-2)' : 'var(--border-2)'}`,
        transition: 'all 150ms ease',
      }}
    >
      {chosen && <FontAwesomeIcon icon={faCircleCheck} style={{ marginRight: 6, fontSize: 11 }} />}
      {label}
    </button>
  )
  const send = () => text.trim() && onAnswer(text.trim())
  return (
    <div style={{ display: 'flex', gap: 12, padding: '12px 0', borderTop: number > 1 ? '1px solid var(--line)' : 'none' }}>
      <span style={{ flex: 'none', width: 22, height: 22, borderRadius: 1000, background: 'var(--accent-wash)', color: 'var(--accent-2)', fontSize: 12, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>{number}</span>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--fg)', lineHeight: '20px' }}>{question}</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {editable ? (
            <>
              {options.map((option) => pill(option, answer === option, () => { setTyping(false); onAnswer(option) }))}
              {pill(custom ? `Other: ${answer}` : 'Other', custom || typing, () => setTyping(true))}
            </>
          ) : (
            answer && pill(answer, true, () => {})
          )}
        </div>
        {editable && typing && (
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              className="field"
              aria-label={`Your answer to: ${question}`}
              placeholder="Type your answer, then press Enter"
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  send()
                  setTyping(false)
                }
              }}
              style={{ flex: 1, fontFamily: 'inherit', fontSize: 13, padding: '8px 10px' }}
            />
            <button type="button" className="button-primary" disabled={!text.trim()} onClick={() => { send(); setTyping(false) }}>
              Save
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
