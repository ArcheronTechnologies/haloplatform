import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { IconChevronLeft, IconAlertTriangle, IconFolder, IconPeople, IconBuilding } from '@/components/icons'
import { entitiesApi } from '@/services/api'
import clsx from 'clsx'

export default function EntityDetail() {
  const { id } = useParams<{ id: string }>()

  const { data: entity, isLoading } = useQuery({
    queryKey: ['entity', id],
    queryFn: () => entitiesApi.get(id!).then((r) => r.data),
    enabled: !!id,
  })

  const { data: transactions } = useQuery({
    queryKey: ['entity', id, 'transactions'],
    queryFn: () => entitiesApi.getTransactions(id!).then((r) => r.data),
    enabled: !!id,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-halo-600" />
      </div>
    )
  }

  if (!entity) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">Entity not found</p>
      </div>
    )
  }

  const Icon = entity.entity_type === 'company' ? IconBuilding : IconPeople

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link to="/entities" className="text-gray-400 hover:text-gray-600">
          <IconChevronLeft className="h-6 w-6" />
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <div className="h-12 w-12 rounded-full bg-gray-100 flex items-center justify-center">
              <Icon className="h-6 w-6 text-gray-500" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{entity.name}</h1>
              <p className="text-sm text-gray-500 font-mono">{entity.identifier}</p>
            </div>
          </div>
        </div>
        <span
          className={clsx(
            'badge text-base px-4 py-1',
            entity.risk_level === 'very_high' && 'badge-critical',
            entity.risk_level === 'high' && 'badge-high',
            entity.risk_level === 'medium' && 'badge-medium',
            entity.risk_level === 'low' && 'badge-low'
          )}
        >
          {entity.risk_level?.replace('_', ' ')} risk
        </span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="card p-4">
          <div className="flex items-center gap-3">
            <IconAlertTriangle className="h-5 w-5 text-orange-500" />
            <div>
              <p className="text-sm text-gray-500">Open Alerts</p>
              <p className="text-xl font-bold text-gray-900">0</p>
            </div>
          </div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-3">
            <IconFolder className="h-5 w-5 text-blue-500" />
            <div>
              <p className="text-sm text-gray-500">Active Cases</p>
              <p className="text-xl font-bold text-gray-900">0</p>
            </div>
          </div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-3">
            <div className="h-5 w-5 flex items-center justify-center text-green-500 font-bold">
              %
            </div>
            <div>
              <p className="text-sm text-gray-500">Risk Score</p>
              <p className="text-xl font-bold text-gray-900">
                {(entity.risk_score * 100).toFixed(0)}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Content Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Entity Details */}
        <div className="card">
          <div className="p-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">Details</h2>
          </div>
          <dl className="divide-y divide-gray-200">
            <div className="px-4 py-3 sm:grid sm:grid-cols-3 sm:gap-4">
              <dt className="text-sm font-medium text-gray-500">Type</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:col-span-2 sm:mt-0 capitalize">
                {entity.entity_type}
              </dd>
            </div>
            <div className="px-4 py-3 sm:grid sm:grid-cols-3 sm:gap-4">
              <dt className="text-sm font-medium text-gray-500">Identifier</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:col-span-2 sm:mt-0 font-mono">
                {entity.identifier}
              </dd>
            </div>
            <div className="px-4 py-3 sm:grid sm:grid-cols-3 sm:gap-4">
              <dt className="text-sm font-medium text-gray-500">Status</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:col-span-2 sm:mt-0 capitalize">
                {entity.status}
              </dd>
            </div>
            <div className="px-4 py-3 sm:grid sm:grid-cols-3 sm:gap-4">
              <dt className="text-sm font-medium text-gray-500">Created</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:col-span-2 sm:mt-0">
                {new Date(entity.created_at).toLocaleString()}
              </dd>
            </div>
          </dl>
        </div>

        {/* Recent Transactions */}
        <div className="card">
          <div className="p-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">Recent Transactions</h2>
          </div>
          <ul className="divide-y divide-gray-200 max-h-80 overflow-y-auto">
            {transactions?.items.slice(0, 10).map((txn) => (
              <li key={txn.id} className="px-4 py-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {txn.amount.toLocaleString()} {txn.currency}
                    </p>
                    <p className="text-xs text-gray-500">{txn.transaction_type}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-gray-500">
                      {new Date(txn.timestamp).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              </li>
            )) ?? (
              <li className="px-4 py-3 text-sm text-gray-500">No transactions</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  )
}
