import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { IconSearch, IconPeople, IconBuilding, IconAlertTriangle, IconFolder } from '@/components/icons'
import { LoadingSpinner, RiskBadge, PageHeader, EmptyState } from '@/components/ui'
import { searchApi } from '@/services/api'

type SearchType = 'all' | 'entities' | 'alerts' | 'cases' | 'transactions'

interface SearchResult {
  id: string
  type: 'entity' | 'alert' | 'case' | 'transaction'
  title: string
  subtitle?: string
  score: number
  metadata?: Record<string, unknown>
}

const RESULT_ICONS = {
  entity: IconPeople,
  alert: IconAlertTriangle,
  case: IconFolder,
  transaction: IconBuilding,
}

const RESULT_LINKS = {
  entity: (id: string) => `/entities/${id}`,
  alert: (id: string) => `/alerts/${id}`,
  case: (id: string) => `/cases/${id}`,
  transaction: () => '#',
}

export default function Search() {
  const [query, setQuery] = useState('')
  const [searchType, setSearchType] = useState<SearchType>('all')
  const [debouncedQuery, setDebouncedQuery] = useState('')

  // Debounce search
  const handleSearch = (value: string) => {
    setQuery(value)
    const timer = setTimeout(() => {
      if (value.length >= 2) {
        setDebouncedQuery(value)
      }
    }, 300)
    return () => clearTimeout(timer)
  }

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['search', debouncedQuery, searchType],
    queryFn: () =>
      searchApi
        .search({
          query: debouncedQuery,
          type: searchType === 'all' ? undefined : searchType,
          limit: 50,
        })
        .then((r) => r.data),
    enabled: debouncedQuery.length >= 2,
  })


  return (
    <div>
      <PageHeader title="Search" />

      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-archeron-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search by name, identifier, case number..."
            className="input pl-10 w-full"
            autoFocus
          />
          {isFetching && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="spinner h-4 w-4" />
            </div>
          )}
        </div>
        <select
          value={searchType}
          onChange={(e) => setSearchType(e.target.value as SearchType)}
          className="input py-2"
        >
          <option value="all">All Types</option>
          <option value="entities">Entities</option>
          <option value="alerts">Alerts</option>
          <option value="cases">Cases</option>
          <option value="transactions">Transactions</option>
        </select>
      </div>

      {debouncedQuery && (
        <div className="card">
          <div className="p-5 border-b border-archeron-800">
            <div className="flex items-center justify-between">
              <h2 className="section-title">Results</h2>
              {data && (
                <span className="text-sm text-archeron-500">
                  {data.total} result{data.total !== 1 ? 's' : ''} found
                </span>
              )}
            </div>
          </div>

          {isLoading ? (
            <LoadingSpinner size="sm" className="h-32" />
          ) : data?.results?.length === 0 ? (
            <EmptyState
              message={`No results found for "${debouncedQuery}"`}
              icon={<IconSearch className="h-12 w-12 mx-auto text-archeron-700" />}
            />
          ) : (
            <ul className="divide-y divide-archeron-800">
              {data?.results?.map((r: SearchResult) => {
                const Icon = RESULT_ICONS[r.type] || IconSearch
                return (
                  <li key={`${r.type}-${r.id}`}>
                    <Link
                      to={RESULT_LINKS[r.type]?.(r.id) || '#'}
                      className="flex items-start gap-4 p-4 hover:bg-archeron-800/50"
                    >
                      <Icon className="h-5 w-5 text-archeron-500 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-archeron-100">{r.title}</div>
                        <div className="text-xs text-archeron-500 mt-0.5">{r.subtitle}</div>
                        {typeof r.metadata?.risk_level === 'string' && (
                          <RiskBadge level={r.metadata.risk_level} className="mt-1" />
                        )}
                      </div>
                      <span className="badge badge-neutral">{r.type}</span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
