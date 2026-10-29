import { useEffect, useRef, useState, type DragEvent } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'
import {
  faBook,
  faBug,
  faChevronDown,
  faCircleCheck,
  faCircleQuestion,
  faFileArrowUp,
  faHandPointer,
  faKey,
  faPause,
  faPlus,
  faTrashCan,
  faXmark,
} from '@fortawesome/free-solid-svg-icons'
import { AllAnsweredIllustration, EmptyState, QuestionsIllustration } from '../components/EmptyState'
import { LoadingDots } from '../components/LoadingDots'
import { useEscapeToClose } from '../hooks/useEscapeToClose'
import { explorerApi, shotUrl, type ExplorerKnowledge, type ExplorerQuestion } from './explorerApi'
import { useCanEdit } from '../PermissionsContext'
import { glassCard, Pill, timeAgo, type Tone } from './ui'

// Every question says what it is, what your answer changes, and what to do.
const KIND: Record<string, { label: string; icon: IconDefinition; tone: Tone; effect: string }> = {
  data: { label: 'Needs test data', icon: faKey, tone: 'info', effect: 'A mission is paused until you answer. Type the value Explorer should use.' },
  risk: { label: 'Needs your OK', icon: faHandPointer, tone: 'warn', effect: 'Explorer will not press this until you say yes. It changes something for real.' },
  rule: { label: 'Bug or correct?', icon: faBug, tone: 'bad', effect: 'Your answer decides whether this goes in the bug list. Explorer is not waiting on it.' },
  clarify: { label: 'Question', icon: faCircleQuestion, tone: 'neutral', effect: 'Your answer is used from the next step and remembered for this app.' },
}

const sectionLabel = { fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--fg-5)', textTransform: 'uppercase' } as const

export function QuestionsView({
  questions,
  onAnswered,
  onOpenShot,
}: {
  questions: ExplorerQuestion[] | null
  onAnswered: () => Promise<void>
  onOpenShot: (shotId: string, caption: string) => void
}) {
  const open = (questions ?? []).filter((q) => q.status === 'open')
  const blocking = open.filter((q) => q.kind !== 'rule')
  const bugChecks = open.filter((q) => q.kind === 'rule')
  const done = (questions ?? []).filter((q) => q.status !== 'open')
  const [showDone, setShowDone] = useState(false)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      {open.length > 0 && (
        <div style={{ fontSize: 13.5, color: 'var(--fg-3)' }}>
          Explorer asks when it is stuck or unsure. Each answer is used straight away and remembered for this app, so it never asks twice.
        </div>
      )}

      {open.length === 0 &&
        (done.length === 0 ? (
          <EmptyState
            variant="scene"
            illustration={<QuestionsIllustration />}
            title="No questions yet"
            subtitle="When Explorer is stuck or unsure, it asks you here. Anything it is waiting on will pulse so you don't miss it."
          />
        ) : (
          <EmptyState
            variant="scene"
            illustration={<AllAnsweredIllustration />}
            title="You're all caught up"
            subtitle={`Explorer has everything it needs. Your ${done.length} answer${done.length === 1 ? ' is' : 's are'} remembered for this app.`}
          />
        ))}

      {blocking.length > 0 && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ ...sectionLabel, color: 'var(--warn-2)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <FontAwesomeIcon icon={faPause} style={{ fontSize: 10 }} /> Explorer is waiting on {blocking.length === 1 ? 'this' : `these ${blocking.length}`}
          </div>
          {blocking.map((q) => (
            <QuestionCard key={q.id} question={q} onAnswered={onAnswered} onOpenShot={onOpenShot} />
          ))}
        </section>
      )}

      {bugChecks.length > 0 && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={sectionLabel}>Bug or correct? · {bugChecks.length}</div>
          {bugChecks.map((q) => (
            <QuestionCard key={q.id} question={q} onAnswered={onAnswered} onOpenShot={onOpenShot} />
          ))}
        </section>
      )}

      {done.length > 0 && (
        <section style={{ ...glassCard, padding: 0, overflow: 'hidden' }}>
          <button
            type="button"
            aria-expanded={showDone}
            onClick={() => setShowDone((v) => !v)}
            style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '13px 18px', border: 'none', background: 'transparent', cursor: 'pointer', fontFamily: 'inherit' }}
          >
            <FontAwesomeIcon icon={faCircleCheck} style={{ fontSize: 12, color: 'var(--ok)' }} />
            <span style={{ flex: 1, textAlign: 'left', fontSize: 13, fontWeight: 600, color: 'var(--fg-2)' }}>Answered · {done.length}</span>
            <FontAwesomeIcon icon={faChevronDown} style={{ fontSize: 10, color: 'var(--fg-5)', transform: showDone ? 'rotate(180deg)' : 'none', transition: 'transform 200ms ease' }} />
          </button>
          {showDone &&
            done.map((q) => (
              <div key={q.id} style={{ padding: '10px 18px', borderTop: '1px solid var(--line)', fontSize: 12.5, lineHeight: '18px' }}>
                <div style={{ color: 'var(--fg-3)' }}>{q.question}</div>
                <div style={{ color: q.status === 'answered' ? 'var(--accent-2)' : 'var(--fg-5)', fontWeight: 600 }}>{q.status === 'answered' ? q.answer : 'Skipped'}</div>
              </div>
            ))}
        </section>
      )}
    </div>
  )
}

// Questions open in a dialog from the header button, over whatever tab you're on.
export function QuestionsDialog({
  questions,
  onAnswered,
  onOpenShot,
  onClose,
}: {
  questions: ExplorerQuestion[] | null
  onAnswered: () => Promise<void>
  onOpenShot: (shotId: string, caption: string) => void
  onClose: () => void
}) {
  useEscapeToClose(onClose)
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 90, background: 'rgba(15,23,42,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div
        role="dialog"
        aria-label="Questions for you"
        onClick={(e) => e.stopPropagation()}
        style={{ background: 'var(--panel)', border: '1px solid var(--border-2)', borderRadius: 16, boxShadow: '0 30px 80px rgba(8,12,20,0.34), var(--panel-shadow)', width: '100%', maxWidth: 820, maxHeight: '86vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', animation: 'aitg-fade-up 220ms ease' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 20px', borderBottom: '1px solid var(--line)' }}>
          <FontAwesomeIcon icon={faCircleQuestion} style={{ fontSize: 14, color: 'var(--accent-2)' }} />
          <h3 style={{ margin: 0, flex: 1, fontSize: 16, fontWeight: 650, color: 'var(--fg)' }}>Questions for you</h3>
          <button type="button" aria-label="Close" onClick={onClose} style={{ width: 32, height: 32, border: '1px solid var(--line)', borderRadius: 8, background: 'white', cursor: 'pointer', color: 'var(--fg-3)' }}>
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </div>
        <div style={{ padding: 20, overflowY: 'auto' }}>
          <QuestionsView questions={questions} onAnswered={onAnswered} onOpenShot={onOpenShot} />
        </div>
      </div>
    </div>
  )
}

export function QuestionCard({ question: q, onAnswered, onOpenShot }: { question: ExplorerQuestion; onAnswered: () => Promise<void>; onOpenShot: (shotId: string, caption: string) => void }) {
  const kind = KIND[q.kind] ?? KIND.clarify
  const canEdit = useCanEdit()
  const waiting = canEdit && q.kind !== 'rule'
  const [text, setText] = useState('')
  // With choices offered, the text box opens from "Other"; without, it's the answer.
  const [typing, setTyping] = useState(q.options.length === 0)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const send = async (answer: string) => {
    setBusy(answer)
    setError(null)
    try {
      await explorerApi.answer(q.id, answer)
      await onAnswered()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send the answer')
    } finally {
      setBusy(null)
    }
  }
  return (
    <div
      style={{
        ...glassCard,
        padding: 0,
        overflow: 'hidden',
        display: 'flex',
        flexWrap: 'wrap',
        animation: waiting ? 'aitg-fade-up 280ms ease, explorer-attention 1.8s ease-out 300ms infinite' : 'aitg-fade-up 280ms ease',
        borderColor: waiting ? 'color-mix(in srgb, var(--warn-2) 40%, transparent)' : undefined,
      }}
    >
      {q.shot_id && (
        <img
          src={shotUrl(q.shot_id)}
          alt=""
          onClick={() => onOpenShot(q.shot_id!, q.question)}
          style={{ width: 240, maxWidth: '100%', aspectRatio: '16 / 10', objectFit: 'cover', objectPosition: 'top', cursor: 'zoom-in', borderRight: '1px solid var(--line)', flex: 'none' }}
        />
      )}
      <div style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 10, flex: '1 1 320px', minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <Pill tone={kind.tone} icon={kind.icon}>{kind.label}</Pill>
          {q.mission_title && <span style={{ fontSize: 11.5, color: 'var(--fg-5)' }}>{q.mission_title}</span>}
          <span style={{ fontSize: 11.5, color: 'var(--fg-5)', marginLeft: 'auto' }}>{timeAgo(q.created_at, Date.now())}</span>
        </div>
        <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)', lineHeight: '21px' }}>{q.question.replace(/^I need this to continue: /, '').replace(/ — is that correct, or a bug\?$/, ' Is that how it should work?')}</div>
        {/* One short muted line under the question: why it asks, else what your answer does. */}
        <div style={{ fontSize: 12.5, color: 'var(--fg-4)', lineHeight: '18px', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }} title={q.why ? `${q.why} ${kind.effect}` : kind.effect}>{q.why || kind.effect}</div>
        {canEdit && q.options.length > 0 && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {q.options.map((option, i) => (
              <button
                key={option}
                type="button"
                className={i === 0 ? 'button-primary' : 'button-secondary'}
                disabled={busy !== null}
                onClick={() => void send(option)}
                style={{ padding: '7px 14px', fontSize: 13 }}
              >
                {busy === option ? <LoadingDots label="Sending" /> : option}
              </button>
            ))}
            <button type="button" className="button-secondary" disabled={busy !== null} aria-expanded={typing} onClick={() => setTyping(true)} style={{ padding: '7px 14px', fontSize: 13 }}>
              Other
            </button>
          </div>
        )}
        {canEdit && (<div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {typing && (<>
          <input
            className="field"
            aria-label="Your answer"
            autoFocus={q.options.length > 0}
            placeholder="Type your answer"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && text.trim() && void send(text.trim())}
            style={{ flex: '1 1 220px', fontFamily: 'inherit', fontSize: 13, padding: '8px 10px' }}
          />
          <button type="button" className={q.options.length ? 'button-secondary' : 'button-primary'} disabled={!text.trim() || busy !== null} onClick={() => void send(text.trim())}>
            {busy === text.trim() && busy ? <LoadingDots label="Sending" /> : 'Send'}
          </button>
          </>)}
          <button
            type="button"
            className="button-secondary"
            disabled={busy !== null}
            title={waiting ? 'Explorer carries on without it' : 'Leave it as a possible bug'}
            onClick={async () => {
              await explorerApi.dismiss(q.id)
              await onAnswered()
            }}
          >
            Skip
          </button>
        </div>)}
        {error && <div style={{ fontSize: 12, color: 'var(--danger)' }}>{error}</div>}
      </div>
    </div>
  )
}

// Knowledge rows are stored as plain sentences; show them the way a person
// would say them back.
function readAnswer(text: string): { tag?: string; tone?: Tone; question?: string; answer: string } {
  const bug = text.match(/^Confirmed bug \(by the user\): (.*)$/s)
  if (bug) return { tag: 'Bug', tone: 'bad', answer: bug[1] }
  const fine = text.match(/^Correct behaviour \(confirmed by the user\): (.*)$/s)
  if (fine) return { tag: 'Not a bug', tone: 'ok', answer: fine[1] }
  const cut = text.lastIndexOf(' — ')
  return cut > 0 ? { question: text.slice(0, cut).replace(/^I need this to continue: /, ''), answer: text.slice(cut + 3) } : { answer: text }
}

function readFact(text: string): { tag?: string; text: string } {
  const data = text.match(/^Test data(?: Explorer created itself| the app showed)?:\s*(.*)$/s)
  return data ? { tag: 'Test data', text: data[1] } : { text }
}

export function KnowledgePanel({ applicationId }: { applicationId: string }) {
  const [items, setItems] = useState<ExplorerKnowledge[] | null>(null)
  const [fact, setFact] = useState('')
  const [busy, setBusy] = useState<'fact' | 'doc' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [allAnswers, setAllAnswers] = useState(false)
  const canEdit = useCanEdit()
  const fileRef = useRef<HTMLInputElement>(null)
  const load = () => explorerApi.knowledge(applicationId).then(setItems).catch(() => setItems([]))
  useEffect(() => {
    void load()
  }, [applicationId]) // eslint-disable-line react-hooks/exhaustive-deps

  const docs = new Map<string, number>()
  for (const k of items ?? []) if (k.kind === 'doc') docs.set(k.source ?? 'document', (docs.get(k.source ?? 'document') ?? 0) + 1)
  const answers = (items ?? []).filter((k) => k.kind === 'answer')
  const facts = (items ?? []).filter((k) => k.kind !== 'answer' && k.kind !== 'doc')
  const forget = async (id: string) => {
    await explorerApi.deleteKnowledge(id)
    await load()
  }
  const upload = async (file: File | undefined) => {
    if (!file) return
    setBusy('doc')
    setError(null)
    try {
      await explorerApi.uploadDocument(applicationId, file)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setBusy(null)
    }
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    void upload(e.dataTransfer.files?.[0])
  }

  const forgetButton = (id: string) => canEdit && (
    <button type="button" aria-label="Forget this" title="Forget this" onClick={() => void forget(id)} style={{ flex: 'none', border: 'none', background: 'transparent', color: 'var(--fg-5)', cursor: 'pointer', padding: 4 }}>
      <FontAwesomeIcon icon={faTrashCan} style={{ fontSize: 11 }} />
    </button>
  )

  return (
    // Side by side, same width and same height, whatever each one holds.
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'stretch' }}>
      {/* What you have told Explorer */}
      <section style={{ ...glassCard, padding: '18px 20px', flex: '1 1 380px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 650, color: 'var(--fg)' }}>What you told Explorer</div>
          <div style={{ fontSize: 12.5, color: 'var(--fg-4)', marginTop: 2 }}>Your answers to its questions. It trusts these over anything the app shows.</div>
        </div>
        {items !== null && answers.length === 0 && <div style={{ fontSize: 13, color: 'var(--fg-5)', padding: '6px 0' }}>No answers yet.</div>}
        {(allAnswers ? answers : answers.slice(0, 5)).map((k) => {
          const a = readAnswer(k.text)
          return (
            <div key={k.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', paddingTop: 10, borderTop: '1px solid var(--line)' }}>
              <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
                {a.question && <div style={{ fontSize: 12.5, color: 'var(--fg-4)', lineHeight: '18px' }}>{a.question}</div>}
                <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                  {a.tag && <Pill tone={a.tone}>{a.tag}</Pill>}
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg)', lineHeight: '19px' }}>{a.answer}</span>
                </div>
              </div>
              {forgetButton(k.id)}
            </div>
          )
        })}
        {answers.length > 5 && (
          <button type="button" onClick={() => setAllAnswers((v) => !v)} style={{ border: 'none', background: 'none', padding: 0, cursor: 'pointer', fontFamily: 'inherit', fontSize: 12.5, color: 'var(--accent-2)', alignSelf: 'flex-start' }}>
            {allAnswers ? 'Show fewer' : `Show all ${answers.length}`}
          </button>
        )}
      </section>

      {/* Teach it more */}
      <section style={{ ...glassCard, padding: '18px 20px', flex: '1 1 380px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 650, color: 'var(--fg)' }}>Teach Explorer</div>
          <div style={{ fontSize: 12.5, color: 'var(--fg-4)', marginTop: 2 }}>Requirements and test data it should use in every run.</div>
        </div>
        {canEdit && (<>
        <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.md" style={{ display: 'none' }} onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = '' }} />
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 6,
            padding: '20px 16px',
            borderRadius: 12,
            border: `1.5px dashed ${dragging ? 'var(--accent-2)' : 'var(--border-2)'}`,
            background: dragging ? 'var(--accent-wash)' : 'color-mix(in srgb, var(--accent-wash) 35%, white)',
            cursor: 'pointer',
            fontFamily: 'inherit',
            transition: 'all 150ms ease',
          }}
        >
          {busy === 'doc' ? (
            <LoadingDots label="Reading the document" />
          ) : (
            <>
              <FontAwesomeIcon icon={faFileArrowUp} style={{ fontSize: 18, color: 'var(--accent-2)' }} />
              <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg)' }}>Upload a requirements document</span>
              <span style={{ fontSize: 12, color: 'var(--fg-4)' }}>Drop a PDF, Word or text file here, or click to choose</span>
            </>
          )}
        </button>
        </>)}
        {error && <div style={{ fontSize: 12, color: 'var(--danger)' }}>{error}</div>}
        {docs.size > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {[...docs.entries()].map(([name, count]) => (
              <Pill key={name} icon={faBook} title={`${count} passages read`}>{name}</Pill>
            ))}
          </div>
        )}

        <div style={{ ...sectionLabel, marginTop: 4 }}>Facts and test data</div>
        {canEdit && (<div style={{ display: 'flex', gap: 8 }}>
          <input
            className="field"
            aria-label="New fact or test data"
            placeholder="Add a fact or test data, then press Enter"
            value={fact}
            onChange={(e) => setFact(e.target.value)}
            onKeyDown={async (e) => {
              if (e.key !== 'Enter' || !fact.trim()) return
              setBusy('fact')
              try {
                await explorerApi.addFact(applicationId, fact.trim())
                setFact('')
                await load()
              } finally {
                setBusy(null)
              }
            }}
            style={{ flex: 1, fontFamily: 'inherit', fontSize: 13, padding: '8px 10px' }}
          />
          <button
            type="button"
            aria-label="Add"
            className="button-secondary"
            disabled={!fact.trim() || busy !== null}
            onClick={async () => {
              setBusy('fact')
              try {
                await explorerApi.addFact(applicationId, fact.trim())
                setFact('')
                await load()
              } finally {
                setBusy(null)
              }
            }}
          >
            {busy === 'fact' ? <LoadingDots label="Adding" /> : <FontAwesomeIcon icon={faPlus} />}
          </button>
        </div>)}
        {items !== null && facts.length === 0 && <div style={{ fontSize: 13, color: 'var(--fg-5)', padding: '6px 0' }}>No facts yet.</div>}
        {facts.map((k) => {
          const f = readFact(k.text)
          return (
            <div key={k.id} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              {f.tag && <Pill tone="info">{f.tag}</Pill>}
              <span style={{ flex: 1, fontSize: 12.5, color: 'var(--fg-2)', lineHeight: '18px' }}>{f.text}</span>
              {forgetButton(k.id)}
            </div>
          )
        })}
      </section>
    </div>
  )
}
