import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { IconAlertTriangle, IconCheckCircle, IconClock, IconEye } from '@/components/icons'
import { LoadingSpinner, RiskBadge, PageHeader, EmptyState, Pagination } from '@/components/ui'
import { alertsApi } from '@/services/api'
import { Alert } from '@/types'

type AlertStatus = 'all' | 'open' | 'acknowledged' | 'resolved'
type RiskLevel = 'all' | 'critical' | 'high' | 'medium' | 'low'

const STATUS_ICONS = {
  resolved: <IconCheckCircle className="h-4 w-4 text-green-400" />,
  acknowledged: <IconEye className="h-4 w-4 text-blue-400" />,
  open: <IconClock className="h-4 w-4 text-orange-400" />,
}

export default function Alerts() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<AlertStatus>('open')
  const [risk, setRisk] = useState<RiskLevel>('all')
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['alerts', status, risk, page],
    queryFn: () =>
      alertsApi
        .list({
          status: status === 'all' ? undefined : status,
          risk_level: risk === 'all' ? undefined : risk,
          page,
          limit: 20,
        })
        .then((r) => r.data),
  })

  const acknowledgeMutation = useMutation({
    mutationFn: (id: string) => alertsApi.acknowledge(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })

  return (
    <div>
      <PageHeader title="Alerts" />

      <div className="flex gap-3 mb-4">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as AlertStatus)}
          className="input py-2"
        >
          <option value="all">All Status</option>
          <option value="open">Open</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
        </select>
        <select
          value={risk}
          onChange={(e) => setRisk(e.target.value as RiskLevel)}
          className="input py-2"
        >
          <option value="all">All Risk Levels</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      <div className="card overflow-hidden">
        {isLoading ? (
          <LoadingSpinner />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-4 text-left">Alert</th>
                  <th className="px-6 py-4 text-left">Entity</th>
                  <th className="px-6 py-4 text-left">Risk</th>
                  <th className="px-6 py-4 text-left">Status</th>
                  <th className="px-6 py-4 text-left">Created</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((alert: Alert) => (
                  <tr key={alert.id} className="table-row">
                    <td className="table-cell">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-orange-500/10">
                          <IconAlertTriangle className="h-4 w-4 text-orange-400" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-archeron-100">
                            {alert.alert_type.replace(/_/g, ' ')}
                          </p>
                          <p className="text-xs text-archeron-500 max-w-md truncate">
                            {alert.description}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="table-cell">
                      {alert.entity_id ? (
                        <Link
                          to={`/entities/${alert.entity_id}`}
                          className="text-sm text-accent-400 hover:text-accent-300 transition-colors"
                        >
                          View Entity
                        </Link>
                      ) : (
                        <span className="text-sm text-archeron-600">-</span>
                      )}
                    </td>
                    <td className="table-cell">
                      <RiskBadge level={alert.risk_level} />
                    </td>
                    <td className="table-cell">
                      <div className="flex items-center gap-2">
                        {STATUS_ICONS[alert.status as keyof typeof STATUS_ICONS] || STATUS_ICONS.open}
                        <span className="text-sm text-archeron-300 capitalize">
                          {alert.status}
                        </span>
                      </div>
                    </td>
                    <td className="table-cell text-archeron-400">
                      {new Date(alert.created_at).toLocaleString()}
                    </td>
                    <td className="table-cell text-right">
                      <div className="flex items-center justify-end gap-2">
                        {alert.status === 'open' && (
                          <button
                            onClick={() => acknowledgeMutation.mutate(alert.id)}
                            disabled={acknowledgeMutation.isPending}
                            className="btn btn-ghost text-xs py-1.5 px-3"
                          >
                            Acknowledge
                          </button>
                        )}
                        <Link
                          to={`/alerts/${alert.id}`}
                          className="btn btn-primary text-xs py-1.5 px-3"
                        >
                          Review
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
                {data?.items.length === 0 && (
                  <EmptyState message="No alerts found" colSpan={6} />
                )}
              </tbody>
            </table>
          </div>
        )}

        <Pagination
          page={page}
          totalItems={data?.total ?? 0}
          onPageChange={setPage}
          itemLabel="alerts"
        />
      </div>
    </div>
  )
}
