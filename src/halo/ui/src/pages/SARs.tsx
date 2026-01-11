import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { IconPlus, IconDocument } from '@/components/icons'
import { LoadingSpinner, RiskBadge, PageHeader, EmptyState, Pagination } from '@/components/ui'
import { sarsApi } from '@/services/api'
import { SAR } from '@/types'

type SARStatusFilter = 'all' | 'draft' | 'pending_review' | 'approved' | 'submitted'

export default function SARs() {
  const [statusFilter, setStatusFilter] = useState<SARStatusFilter>('all')
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['sars', statusFilter, page],
    queryFn: () =>
      sarsApi
        .list({
          status: statusFilter === 'all' ? undefined : statusFilter,
          page,
          limit: 20,
        })
        .then((r) => r.data),
  })

  return (
    <div>
      <PageHeader
        title="Suspicious Activity Reports"
        actions={
          <Link to="/sars/new" className="btn btn-primary">
            <IconPlus className="h-4 w-4 mr-2" />
            New SAR
          </Link>
        }
      />

      <div className="flex gap-3 mb-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as SARStatusFilter)}
          className="input py-2"
        >
          <option value="all">All Status</option>
          <option value="draft">Draft</option>
          <option value="pending_review">Pending Review</option>
          <option value="approved">Approved</option>
          <option value="submitted">Submitted</option>
        </select>
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : (
        <div className="border border-archeron-800 divide-y divide-archeron-800">
          {data?.items.map((sar: SAR) => (
            <Link key={sar.id} to={`/sars/${sar.id}`} className="block p-4 hover:bg-archeron-900/50">
              <div className="flex items-start justify-between">
                <div className="flex gap-3 flex-1">
                  <IconDocument className="h-5 w-5 text-archeron-500 mt-0.5" />
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-1">
                      <span className="font-mono text-xs text-archeron-500">{sar.id}</span>
                      <span className="badge badge-neutral">{sar.sar_type}</span>
                      <span className="badge badge-neutral">{sar.status}</span>
                    </div>
                    <div className="text-sm text-archeron-200">{sar.summary || 'No summary'}</div>
                    <div className="text-xs text-archeron-500 mt-1">
                      {sar.total_amount && `Amount: ${sar.total_amount} ${sar.currency || 'SEK'}`}
                    </div>
                  </div>
                </div>
                <RiskBadge level={sar.priority} />
              </div>
            </Link>
          ))}
          {data?.items.length === 0 && (
            <EmptyState message="No SARs found" />
          )}
        </div>
      )}

      <Pagination
        page={page}
        totalItems={data?.total ?? 0}
        onPageChange={setPage}
        itemLabel="SARs"
      />
    </div>
  )
}
