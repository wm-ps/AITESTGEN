function pageWindow(current: number, totalPages: number, size = 5): number[] {
  const half = Math.floor(size / 2)
  let start = Math.max(0, current - half)
  const end = Math.min(totalPages, start + size)
  start = Math.max(0, end - size)
  return Array.from({ length: end - start }, (_, i) => start + i)
}

// Shared with the arrow buttons — matches the prototype's reusable
// pagination helper (paginate(): prevStyle/nextStyle/pageButtons' style).
const navButtonStyle = (disabled: boolean): React.CSSProperties => ({
  display: 'inline-flex',
  alignItems: 'center',
  height: 26,
  padding: '0 10px',
  borderRadius: 6,
  border: '1px solid var(--border-2)',
  background: 'var(--panel)',
  fontSize: 11.5,
  color: disabled ? 'var(--fg-5)' : 'var(--fg-3)',
  cursor: disabled ? 'default' : 'pointer',
})

export function Pagination({
  page,
  totalPages,
  hasPrev,
  hasNext,
  knownPages,
  totalItems,
  pageSize,
  onPrev,
  onNext,
  onPage,
}: {
  page: number
  // Omitted (cursor pagination) → hasPrev/hasNext drive the button state
  // and no "of Y"/total is shown, since a cursor doesn't know the total.
  totalPages?: number
  hasPrev?: boolean
  hasNext?: boolean
  // Cursor pagination only: how many pages have been visited/fetched so far
  // (e.g. `cursors.length`). Lets number chips render for the pages we
  // actually know about, even though the real total is unknown until the
  // cursor runs out.
  knownPages?: number
  totalItems?: number
  pageSize?: number
  onPrev: () => void
  onNext: () => void
  // Omitted → plain "Page X" + Previous/Next (DiscoverJourneys/ReviewScenarios
  // narrow sidebars — no total/knownPages to build chips from). Passed →
  // clickable page numbers, plus "Showing X-Y of Z" when totalItems/pageSize
  // are given.
  onPage?: (page: number) => void
}) {
  const canPrev = hasPrev ?? page > 0
  const canNext = hasNext ?? (totalPages !== undefined && page < totalPages - 1)
  if (totalPages !== undefined && totalPages <= 1) return null
  if (totalPages === undefined && !canPrev && !canNext) return null

  const chipCount = totalPages ?? knownPages

  if (!onPage || chipCount === undefined) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 20px', background: 'var(--panel-2)' }}>
        <span style={{ fontSize: 11.5, color: 'var(--fg-4)' }}>{totalPages !== undefined ? `Page ${page + 1} of ${totalPages}` : `Page ${page + 1}`}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button type="button" style={navButtonStyle(!canPrev)} disabled={!canPrev} onClick={onPrev}>
            Previous
          </button>
          <button type="button" style={navButtonStyle(!canNext)} disabled={!canNext} onClick={onNext}>
            Next
          </button>
        </div>
      </div>
    )
  }

  const showCount = totalItems !== undefined && pageSize !== undefined
  const rangeStart = page * (pageSize ?? 0) + 1
  const rangeEnd = Math.min(totalItems ?? 0, rangeStart + (pageSize ?? 0) - 1)
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 20px', background: 'var(--panel-2)' }}>
      <span style={{ fontSize: 11.5, color: 'var(--fg-4)' }}>
        {showCount ? `Showing ${rangeStart.toLocaleString()}–${rangeEnd.toLocaleString()} of ${(totalItems ?? 0).toLocaleString()}` : ''}
      </span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <button type="button" style={navButtonStyle(!canPrev)} disabled={!canPrev} onClick={onPrev}>
          Previous
        </button>
        {pageWindow(page, chipCount).map((p) => (
          <button
            key={p}
            type="button"
            disabled={p === page}
            onClick={() => onPage(p)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              minWidth: 26,
              height: 26,
              padding: '0 8px',
              borderRadius: 6,
              fontSize: 11.5,
              cursor: p === page ? 'default' : 'pointer',
              background: p === page ? 'var(--accent)' : 'var(--panel)',
              color: p === page ? '#fff' : 'var(--fg-3)',
              fontWeight: p === page ? 600 : 400,
              border: p === page ? '1px solid var(--accent)' : '1px solid var(--border-2)',
            }}
          >
            {p + 1}
          </button>
        ))}
        <button type="button" style={navButtonStyle(!canNext)} disabled={!canNext} onClick={onNext}>
          Next
        </button>
      </div>
    </div>
  )
}
