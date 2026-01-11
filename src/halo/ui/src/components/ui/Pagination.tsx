interface PaginationProps {
  page: number
  totalItems: number
  pageSize?: number
  onPageChange: (page: number) => void
  itemLabel?: string
}

export function Pagination({
  page,
  totalItems,
  pageSize = 20,
  onPageChange,
  itemLabel = 'items',
}: PaginationProps) {
  const totalPages = Math.ceil(totalItems / pageSize)
  const start = (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, totalItems)

  if (totalItems <= pageSize) return null

  return (
    <div className="px-6 py-4 border-t border-archeron-800 flex items-center justify-between">
      <p className="text-sm text-archeron-500">
        Showing {start} to {end} of {totalItems} {itemLabel}
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page === 1}
          className="btn btn-secondary py-1.5"
        >
          Previous
        </button>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="btn btn-secondary py-1.5"
        >
          Next
        </button>
      </div>
    </div>
  )
}
