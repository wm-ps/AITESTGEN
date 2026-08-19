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
  totalItems,
  pageSize,
  onPrev,
  onNext,
  onPage,
}: {
  page: number
  totalPages: number
  totalItems?: number
  pageSize?: number
  onPrev: () => void
  onNext: () => void
  // Omitted → plain "Page X of Y" + Prev/Next (DiscoverJourneys/ReviewScenarios
  // narrow sidebars, no room for numbered chips). Passed → "Showing X-Y of Z"
  // plus clickable page numbers (workspace tables).
  onPage?: (page: number) => void
}) {
  if (totalPages <= 1) return null

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
        <button type="button" className="button-secondary" disabled={page <= 0} onClick={onPrev}>
          Prev
        </button>
        <span className="caption" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
          Page {page + 1} of {totalPages}
        </span>
        <button type="button" className="button-secondary" disabled={page >= totalPages - 1} onClick={onNext}>
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
        {pageWindow(page, totalPages).map((p) => (
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
        <button type="button" className="button-secondary" disabled={page >= totalPages - 1} onClick={onNext}>
          Next
        </button>
      </div>
    </div>
  )
}
