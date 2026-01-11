import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { IconDocument, IconPerson } from '@/components/icons'
import { LoadingSpinner, PageHeader, EmptyState, Pagination } from '@/components/ui'
import { auditApi } from '@/services/api'

export default function AuditLog() {
  const [page, setPage] = useState(1)
  const [entityId, setEntityId] = useState('')
  const [userId, setUserId] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['audit', page, entityId, userId],
    queryFn: () =>
      auditApi
        .getLog({
          page,
          limit: 50,
          entity_id: entityId || undefined,
          user_id: userId || undefined,
        })
        .then((r) => r.data),
  })

  return (
    <div>
      <PageHeader title="Audit Log" />

      <div className="flex gap-3 mb-4">
        <input
          type="text"
          placeholder="Filter by entity ID..."
          value={entityId}
          onChange={(e) => setEntityId(e.target.value)}
          className="input py-2 flex-1"
        />
        <input
          type="text"
          placeholder="Filter by user ID..."
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          className="input py-2 flex-1"
        />
      </div>

      <div className="card overflow-hidden">
        {isLoading ? (
          <LoadingSpinner />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-4 text-left">Timestamp</th>
                  <th className="px-6 py-4 text-left">User</th>
                  <th className="px-6 py-4 text-left">Action</th>
                  <th className="px-6 py-4 text-left">Entity</th>
                  <th className="px-6 py-4 text-left">Details</th>
                </tr>
              </thead>
              <tbody>
                {data?.items?.map((entry: any) => (
                  <tr key={entry.id} className="table-row">
                    <td className="table-cell font-mono text-xs text-archeron-400">
                      {new Date(entry.timestamp).toLocaleString()}
                    </td>
                    <td className="table-cell">
                      <div className="flex items-center gap-2">
                        <IconPerson className="h-4 w-4 text-archeron-500" />
                        <span className="text-sm text-archeron-200">{entry.user_id}</span>
                      </div>
                    </td>
                    <td className="table-cell">
                      <span className="badge badge-neutral">{entry.action}</span>
                    </td>
                    <td className="table-cell">
                      <div className="flex items-center gap-2">
                        <IconDocument className="h-4 w-4 text-archeron-500" />
                        <span className="text-sm text-archeron-400 font-mono">{entry.entity_id || '-'}</span>
                      </div>
                    </td>
                    <td className="table-cell text-archeron-400 text-sm max-w-md truncate">
                      {entry.details ? JSON.stringify(entry.details) : '-'}
                    </td>
                  </tr>
                ))}
                {data?.items?.length === 0 && (
                  <tr>
                    <td colSpan={5}>
                      <EmptyState message="No audit log entries found" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        <Pagination
          page={page}
          totalItems={data?.total ?? 0}
          onPageChange={setPage}
          itemLabel="entries"
        />
      </div>
    </div>
  )
}
