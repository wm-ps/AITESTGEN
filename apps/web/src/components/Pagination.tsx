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
  // Omitted → plain "Page X" + </> (DiscoverJourneys/ReviewScenarios narrow
  // sidebars — no total/knownPages to build chips from). Passed → clickable
  // page numbers, plus "Showing X-Y of Z" when totalItems/pageSize are given.
  onPage?: (page: number) => void
}) {
  const canPrev = hasPrev ?? page > 0
  const canNext = hasNext ?? (totalPages !== undefined && page < totalPages - 1)
  if (totalPages !== undefined && totalPages <= 1) return null
  if (totalPages === undefined && !canPrev && !canNext) return null

  const chipCount = totalPages ?? knownPages

  if (!onPage || chipCount === undefined) {
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

  const showCount = totalItems !== undefined && pageSize !== undefined
  const rangeStart = page * (pageSize ?? 0) + 1
  const rangeEnd = Math.min(totalItems ?? 0, rangeStart + (pageSize ?? 0) - 1)
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: 'var(--space-3)',
        padding: 'var(--space-4) var(--space-5)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
        {showCount && (
          <span className="caption" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
            Showing {rangeStart.toLocaleString()}-{rangeEnd.toLocaleString()} of {(totalItems ?? 0).toLocaleString()}
          </span>
        )}
        <button type="button" className="pagination-arrow-btn" disabled={!canPrev} onClick={onPrev} aria-label="Previous page">
          &lt;
        </button>
        {pageWindow(page, chipCount).map((p) => (
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
        <button type="button" className="pagination-arrow-btn" disabled={!canNext} onClick={onNext} aria-label="Next page">
          &gt;
        </button>
      </div>
    </div>
  )
}
