import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export type Person = { name: string; email: string }

export function initialsOf(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

export function Avatar({ name, size = 26 }: { name: string; size?: number }) {
  return (
    <span
      aria-hidden="true"
      style={{ width: size, height: size, flex: 'none', borderRadius: 1000, background: 'var(--chip)', color: 'var(--accent-2)', fontSize: size > 28 ? 12.5 : 10.5, fontWeight: 600, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
    >
      {initialsOf(name)}
    </span>
  )
}

// Bolds the part of a suggestion that matches what was typed.
function highlight(text: string, query: string): React.ReactNode {
  const at = query ? text.toLowerCase().indexOf(query.toLowerCase()) : -1
  if (at < 0) return text
  return (
    <>
      {text.slice(0, at)}
      <b style={{ color: 'var(--fg)', fontWeight: 700 }}>{text.slice(at, at + query.length)}</b>
      {text.slice(at + query.length)}
    </>
  )
}

// A type-ahead for picking one person from a list the caller supplies. The
// list opens while there is text, closes after a pick, and says so when nothing
// matches. `options` is already filtered (locally or by the server).
export function PersonPicker({
  query,
  onQuery,
  options,
  onPick,
  loading = false,
  placeholder = 'Type name or email address',
  label,
  height = 38,
}: {
  query: string
  onQuery: (value: string) => void
  options: Person[]
  onPick: (person: Person) => void
  loading?: boolean
  placeholder?: string
  label: string
  height?: number
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState<{ left: number; top: number; width: number } | null>(null)

  useEffect(() => {
    function onDown(event: MouseEvent) {
      const target = event.target as Node
      if (ref.current?.contains(target) || listRef.current?.contains(target)) return
      setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  const show = open && query.trim() !== ''

  // The list renders in a portal so a dialog's scroll area can't clip it; it
  // follows the field while the page scrolls or resizes.
  useLayoutEffect(() => {
    if (!show) return
    function place() {
      const rect = ref.current?.getBoundingClientRect()
      if (rect) setBox({ left: rect.left, top: rect.top + height + 6, width: rect.width })
    }
    place()
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [show, height])
  return (
    <div ref={ref} className="person-picker" style={{ position: 'relative', flex: 1, minWidth: 0 }}>
      <div className="field-shell" style={{ height, borderRadius: 8 }}>
        <input
          data-bare
          aria-label={label}
          value={query}
          placeholder={placeholder}
          autoComplete="off"
          onChange={(event) => {
            onQuery(event.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          style={{ fontSize: 14 }}
        />
      </div>
      {show && box && createPortal(
        <div
          ref={listRef}
          role="listbox"
          aria-label={`${label} suggestions`}
          style={{ position: 'fixed', zIndex: 100, left: box.left, top: box.top, width: box.width, borderRadius: 8, background: 'var(--panel)', border: '1px solid var(--border)', boxShadow: '0 12px 30px rgba(10,12,16,0.16)', overflow: 'hidden' }}
        >
          <div style={{ maxHeight: 220, overflowY: 'auto' }}>
            {options.map((person) => (
              <button
                key={person.email}
                type="button"
                role="option"
                aria-selected={false}
                className="menu-row-hover"
                onClick={() => {
                  onPick(person)
                  setOpen(false)
                }}
                style={{ display: 'block', width: '100%', padding: '10px 12px', border: 'none', background: 'transparent', cursor: 'pointer', textAlign: 'left', font: 'inherit', fontSize: 14, color: 'var(--fg-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              >
                {highlight(person.name, query.trim())}
                <span style={{ color: 'var(--fg-4)', fontSize: 12.5 }}> · {highlight(person.email, query.trim())}</span>
              </button>
            ))}
          </div>
          <div style={{ padding: '9px 12px', textAlign: 'center', fontSize: 12.5, color: 'var(--fg-3)', borderTop: '1px solid var(--row-line)' }}>
            {loading ? 'Searching' : options.length === 0 ? 'No matching people' : 'No more data to load'}
          </div>
        </div>,
        document.body,
      )}
    </div>
  )
}
