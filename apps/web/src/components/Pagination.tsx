function pageWindow(current: number, totalPages: number, size = 5): number[] {
  const half = Math.floor(size / 2)
  let start = Math.max(0, current - half)
  const end = Math.min(totalPages, start + size)
  start = Math.max(0, end - size)
  return Array.from({ length: end - start }, (_, i) => start + i)
}

export function Pagination({
  page,
  totalPages,
  hasPrev,
  hasNext,
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
  totalItems?: number
  pageSize?: number
  onPrev: () => void
  onNext: () => void
  // Omitted → plain "Page X" + Prev/Next (DiscoverJourneys/ReviewScenarios
  // narrow sidebars, cursor-paginated tables — no room for numbered chips
  // or no total to build them from). Passed → "Showing X-Y of Z" plus
  // clickable page numbers (offset-paginated workspace tables).
  onPage?: (page: number) => void
}) {
  const canPrev = hasPrev ?? page > 0
  const canNext = hasNext ?? (totalPages !== undefined && page < totalPages - 1)
  if (totalPages !== undefined && totalPages <= 1) return null
  if (totalPages === undefined && !canPrev && !canNext) return null

  if (!onPage) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 'var(--space-3)',
          padding: 'var(--space-4) var(--space-5)',
        }}
      >
        <button type="button" className="button-secondary" disabled={!canPrev} onClick={onPrev}>
          Prev
        </button>
        <span className="caption" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
          {totalPages !== undefined ? `Page ${page + 1} of ${totalPages}` : `Page ${page + 1}`}
        </span>
        <button type="button" className="button-secondary" disabled={!canNext} onClick={onNext}>
          Next
        </button>
      </div>
    )
  }

  // Numbered chips need a real total — this branch is only reached by
  // callers that pass `onPage` alongside `totalPages` (offset pagination).
  const numberedTotalPages = totalPages ?? 1
  const showCount = totalItems !== undefined && pageSize !== undefined
  const rangeStart = page * (pageSize ?? 0) + 1
  const rangeEnd = Math.min(totalItems ?? 0, rangeStart + (pageSize ?? 0) - 1)
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 'var(--space-3)',
        padding: 'var(--space-4) var(--space-5)',
      }}
    >
      {showCount ? (
        <span className="caption" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
          Showing {rangeStart.toLocaleString()}-{rangeEnd.toLocaleString()} of {(totalItems ?? 0).toLocaleString()}
        </span>
      ) : (
        <span />
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
        <button type="button" className="button-secondary" disabled={page <= 0} onClick={onPrev}>
          Previous
        </button>
        {pageWindow(page, numberedTotalPages).map((p) => (
          <button
            key={p}
            type="button"
            className={`pagination-page-btn${p === page ? ' pagination-page-btn--active' : ''}`}
            disabled={p === page}
            onClick={() => onPage(p)}
          >
            {p + 1}
          </button>
        ))}
        <button type="button" className="button-secondary" disabled={page >= numberedTotalPages - 1} onClick={onNext}>
          Next
        </button>
      </div>
    </div>
  )
}
