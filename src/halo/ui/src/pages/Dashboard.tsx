import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { LoadingSpinner, RiskBadge, PageHeader } from '@/components/ui'
import { dashboardApi } from '@/services/api'

export default function Dashboard() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: () => dashboardApi.getStats().then((r) => r.data),
  })

  const { data: recentAlerts } = useQuery({
    queryKey: ['dashboard', 'recent-alerts'],
    queryFn: () => dashboardApi.getRecentAlerts(5).then((r) => r.data),
  })

  const { data: recentCases } = useQuery({
    queryKey: ['dashboard', 'recent-cases'],
    queryFn: () => dashboardApi.getRecentCases(5).then((r) => r.data),
  })

  if (isLoading) return <LoadingSpinner />

  return (
    <div>
      <PageHeader title="Dashboard" />

      <div className="grid grid-cols-4 gap-3 mb-6">
        <Link to="/alerts" className="border border-archeron-800 p-4 hover:border-archeron-700">
          <div className="text-2xl font-mono text-archeron-100">{stats?.alerts.total ?? 0}</div>
          <div className="text-xs text-archeron-500 mt-1">Open Alerts</div>
        </Link>
        <Link to="/cases" className="border border-archeron-800 p-4 hover:border-archeron-700">
          <div className="text-2xl font-mono text-archeron-100">{stats?.cases.open ?? 0}</div>
          <div className="text-xs text-archeron-500 mt-1">Active Cases</div>
        </Link>
        <Link to="/entities?risk=high" className="border border-archeron-800 p-4 hover:border-archeron-700">
          <div className="text-2xl font-mono text-archeron-100">{stats?.entities.high_risk ?? 0}</div>
          <div className="text-xs text-archeron-500 mt-1">High Risk</div>
        </Link>
        <Link to="/sars" className="border border-archeron-800 p-4 hover:border-archeron-700">
          <div className="text-2xl font-mono text-archeron-100">
            {(stats?.sars.draft ?? 0) + (stats?.sars.pending ?? 0)}
          </div>
          <div className="text-xs text-archeron-500 mt-1">Pending SARs</div>
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-archeron-300">Recent Alerts</h2>
            <Link to="/alerts" className="text-xs text-accent-400 hover:text-accent-300">
              View all →
            </Link>
          </div>
          <div className="border border-archeron-800 divide-y divide-archeron-800">
            {recentAlerts?.length === 0 ? (
              <div className="px-4 py-6 text-center text-sm text-archeron-700">No alerts</div>
            ) : (
              recentAlerts?.map((alert) => (
                <Link
                  key={alert.id}
                  to={`/alerts/${alert.id}`}
                  className="block px-4 py-3 hover:bg-archeron-900/50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-archeron-200 truncate">{alert.title}</div>
                      <div className="text-xs text-archeron-600 truncate mt-0.5">
                        {alert.description}
                      </div>
                    </div>
                    <RiskBadge level={alert.severity} />
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-archeron-300">Recent Cases</h2>
            <Link to="/cases" className="text-xs text-accent-400 hover:text-accent-300">
              View all →
            </Link>
          </div>
          <div className="border border-archeron-800 divide-y divide-archeron-800">
            {recentCases?.length === 0 ? (
              <div className="px-4 py-6 text-center text-sm text-archeron-700">No cases</div>
            ) : (
              recentCases?.map((case_) => (
                <Link
                  key={case_.id}
                  to={`/cases/${case_.id}`}
                  className="block px-4 py-3 hover:bg-archeron-900/50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-mono text-archeron-500">{case_.case_number}</div>
                      <div className="text-sm text-archeron-200 truncate mt-0.5">{case_.title}</div>
                    </div>
                    <RiskBadge level={case_.priority} />
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
