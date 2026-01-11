import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { IconPlus } from '@/components/icons'
import { LoadingSpinner, RiskBadge, PageHeader, EmptyState, Pagination } from '@/components/ui'
import { casesApi } from '@/services/api'
import { Case } from '@/types'
import clsx from 'clsx'

type CaseStatus = 'all' | 'open' | 'in_progress' | 'pending_review' | 'closed'
type CaseType = 'all' | 'aml' | 'sanctions' | 'fraud' | 'pep' | 'other'

export default function Cases() {
  const [statusFilter, setStatusFilter] = useState<CaseStatus>('all')
  const [typeFilter, setTypeFilter] = useState<CaseType>('all')
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['cases', statusFilter, typeFilter, page],
    queryFn: () =>
      casesApi
        .list({
          status: statusFilter === 'all' ? undefined : statusFilter,
          case_type: typeFilter === 'all' ? undefined : typeFilter,
          page,
          limit: 20,
        })
        .then((r) => r.data),
  })

  return (
    <div>
      <PageHeader
        title="Cases"
        actions={
          <Link to="/cases/new" className="btn btn-primary">
            <IconPlus className="h-4 w-4 mr-2" />
            New Case
          </Link>
        }
      />

      <div className="flex gap-3 mb-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as CaseStatus)}
          className="input py-2"
        >
          <option value="all">All Status</option>
          <option value="open">Open</option>
          <option value="in_progress">In Progress</option>
          <option value="pending_review">Pending Review</option>
          <option value="closed">Closed</option>
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as CaseType)}
          className="input py-2"
        >
          <option value="all">All Types</option>
          <option value="aml">AML</option>
          <option value="sanctions">Sanctions</option>
          <option value="fraud">Fraud</option>
          <option value="pep">PEP</option>
          <option value="other">Other</option>
        </select>
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : (
        <div className="border border-archeron-800 divide-y divide-archeron-800">
          {data?.items.map((c: Case) => (
            <Link key={c.id} to={`/cases/${c.id}`} className="block p-4 hover:bg-archeron-900/50">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-1">
                    <span className="font-mono text-xs text-archeron-500">{c.case_number}</span>
                    <span className={clsx('badge', `badge-${c.status}`)}>{c.status.replace(/_/g, ' ')}</span>
                  </div>
                  <div className="text-sm text-archeron-200">{c.title}</div>
                  <div className="text-xs text-archeron-500 mt-1">{c.assigned_to || 'Unassigned'}</div>
                </div>
                <RiskBadge level={c.priority} />
              </div>
            </Link>
          ))}
          {data?.items.length === 0 && (
            <EmptyState message="No cases found" />
          )}
        </div>
      )}

      <Pagination
        page={page}
        totalItems={data?.total ?? 0}
        onPageChange={setPage}
        itemLabel="cases"
      />
    </div>
  )
}
