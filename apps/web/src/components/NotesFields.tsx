import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faBuildingColumns, faBullseye, faCircleInfo, faScaleBalanced } from '@fortawesome/free-solid-svg-icons'
import type { ApplicationContext } from '../api'

// Shared by NotesTab.tsx (view/edit an existing Application's Notes) and
// ConnectAppForm.tsx (optionally provide Notes during onboarding, so the
// very first InferenceActivity run — chained automatically right after the
// initial crawl — already sees them, not just later PATCHes).

export const NOTES_FIELD_MAX_LENGTH = 2000

// `business_rules` is edited as one item per line in a plain textarea — no
// JSON, just prose — and split/joined at the form boundary only; the API
// itself still deals in a real `string[]`.
const LIST_FIELDS = ['business_rules'] as const

export type NotesFormState = Record<keyof ApplicationContext, string>

export const EMPTY_NOTES_FORM: NotesFormState = {
  business_goal: '',
  business_domain: '',
  business_rules: '',
  additional_context: '',
}

export function toNotesFormState(context: ApplicationContext | null): NotesFormState {
  if (!context) return EMPTY_NOTES_FORM
  const form = { ...EMPTY_NOTES_FORM }
  for (const key of Object.keys(EMPTY_NOTES_FORM) as (keyof ApplicationContext)[]) {
    const value = context[key]
    form[key] = Array.isArray(value) ? value.join('\n') : value ?? ''
  }
  return form
}

export function toNotesPayload(form: NotesFormState): ApplicationContext {
  const payload = {} as ApplicationContext
  for (const key of Object.keys(EMPTY_NOTES_FORM) as (keyof ApplicationContext)[]) {
    if ((LIST_FIELDS as readonly string[]).includes(key)) {
      const items = form[key]
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
      // @ts-expect-error — list-shaped key, matching ApplicationContext's own union.
      payload[key] = items.length ? items : null
    } else {
      // @ts-expect-error — text-shaped key.
      payload[key] = form[key].trim() || null
    }
  }
  return payload
}

const SECTIONS: {
  key: keyof ApplicationContext
  label: string
  icon: typeof faBullseye
  placeholder: string
  hint: string
}[] = [
  {
    key: 'business_goal',
    label: 'Business goal',
    icon: faBullseye,
    placeholder: 'Describe the primary purpose of the application and the outcomes it should deliver',
    hint: 'What the application exists to achieve and which outcomes matter most.',
  },
  {
    key: 'business_domain',
    label: 'Business domain',
    icon: faBuildingColumns,
    placeholder: 'Describe the industry, user roles, key entities and terminology',
    hint: 'Industry, users, key entities and the terms your team uses.',
  },
  {
    key: 'business_rules',
    label: 'Business rules',
    icon: faScaleBalanced,
    placeholder: 'List validations, limits, permissions and conditions the application enforces',
    hint: 'Validations, limits, permissions and conditions tests must respect. One rule per line works best.',
  },
  {
    key: 'additional_context',
    label: 'Additional context',
    icon: faCircleInfo,
    placeholder: 'Add any other information that helps generate accurate scenarios and test cases',
    hint: 'Anything else: test accounts, environments, known issues, areas to avoid.',
  },
]

const textareaStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '11px 13px',
  border: '1px solid var(--border-2)',
  borderRadius: 9,
  fontSize: 13.5,
  color: 'var(--fg-1)',
  // `--panel` (white), not `--panel-2` (light gray fill used for
  // read-only/inert surfaces elsewhere) — every other genuinely-editable
  // field in this codebase (e.g. ConnectAppForm's own inputs, even nested
  // inside a --panel-2 box) uses white so it reads as writable.
  background: 'var(--panel)',
  fontFamily: 'inherit',
  resize: 'vertical',
  outline: 'none',
}

// Pure presentational grid — no load/save/api concerns, so both call sites
// own their own data flow (NotesTab: fetch + PATCH; ConnectAppForm: local
// state submitted together with the rest of the create-application form).
export function NotesFields({
  form,
  onChange,
}: {
  form: NotesFormState
  onChange: (form: NotesFormState) => void
}) {
  return (
    <div
      style={{
        display: 'grid',
        // minmax(500px,...) rather than a bare `repeat(2, 1fr)` — 2 columns
        // at typical desktop widths, collapsing to 1 on a narrow viewport
        // instead of squeezing.
        gridTemplateColumns: 'repeat(auto-fit,minmax(500px,1fr))',
        gap: '24px 32px',
      }}
    >
      {SECTIONS.map((section) => (
        <div key={section.key} style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <FontAwesomeIcon icon={section.icon} style={{ fontSize: 13, color: 'var(--fg-2)' }} />
            <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg)' }}>{section.label}</span>
          </div>
          <textarea
            value={form[section.key]}
            onChange={(e) => onChange({ ...form, [section.key]: e.target.value })}
            placeholder={section.placeholder}
            maxLength={NOTES_FIELD_MAX_LENGTH}
            rows={4}
            style={textareaStyle}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <span style={{ fontSize: 11.5, color: 'var(--fg-4)', lineHeight: 1.4 }}>{section.hint}</span>
            <span
              style={{
                fontSize: 11,
                color: 'var(--fg-5)',
                fontFamily: 'var(--font-mono)',
                flex: 'none',
                whiteSpace: 'nowrap',
              }}
            >
              {`${form[section.key].length} / ${NOTES_FIELD_MAX_LENGTH.toLocaleString()}`}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
