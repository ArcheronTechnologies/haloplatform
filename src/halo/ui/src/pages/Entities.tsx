import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { IconPeople, IconBuilding, IconProperty, IconVehicle, IconChevronRight } from '@/components/icons'
import { LoadingSpinner, RiskBadge, PageHeader, Pagination } from '@/components/ui'
import { entitiesApi } from '@/services/api'

const entityTypeIcons = {
  person: IconPeople,
  company: IconBuilding,
  property: IconProperty,
  vehicle: IconVehicle,
}

export default function Entities() {
  const [filters, setFilters] = useState({
    type: '',
    risk_level: '',
    page: 1,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['entities', filters],
    queryFn: () => entitiesApi.list(filters).then((r) => r.data),
  })

  return (
    <div>
      <PageHeader title="Entities" />

      <div className="flex gap-3 mb-4">
        <select
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value, page: 1 })}
          className="input py-2"
        >
          <option value="">All Types</option>
          <option value="person">Persons</option>
          <option value="company">Companies</option>
          <option value="property">Properties</option>
          <option value="vehicle">Vehicles</option>
        </select>
        <select
          value={filters.risk_level}
          onChange={(e) => setFilters({ ...filters, risk_level: e.target.value, page: 1 })}
          className="input py-2"
        >
          <option value="">All Risk Levels</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="very_high">Very High</option>
        </select>
      </div>

      {/* Entity List */}
      <div className="card overflow-hidden">
        {isLoading ? (
          <LoadingSpinner />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-4 text-left">Entity</th>
                  <th className="px-6 py-4 text-left">Type</th>
                  <th className="px-6 py-4 text-left">Identifier</th>
                  <th className="px-6 py-4 text-left">Risk Level</th>
                  <th className="px-6 py-4 text-left">Status</th>
                  <th className="relative px-6 py-4">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((entity) => {
                  const Icon = entityTypeIcons[entity.entity_type] || IconPeople
                  return (
                    <tr key={entity.id} className="table-row">
                      <td className="table-cell">
                        <div className="flex items-center">
                          <div className="h-10 w-10 flex-shrink-0 rounded-lg bg-archeron-800 flex items-center justify-center">
                            <Icon className="h-5 w-5 text-archeron-400" />
                          </div>
                          <div className="ml-4">
                            <div className="text-sm font-medium text-archeron-100">
                              {entity.name}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="table-cell text-archeron-400 capitalize">
                        {entity.entity_type}
                      </td>
                      <td className="table-cell font-mono text-archeron-400">
                        {entity.identifier}
                      </td>
                      <td className="table-cell">
                        <RiskBadge level={entity.risk_level} />
                      </td>
                      <td className="table-cell text-archeron-400 capitalize">
                        {entity.status}
                      </td>
                      <td className="table-cell text-right">
                        <Link
                          to={`/entities/${entity.id}`}
                          className="text-accent-400 hover:text-accent-300 transition-colors"
                        >
                          <IconChevronRight className="h-5 w-5" />
                        </Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        <Pagination
          page={filters.page}
          totalItems={data?.total ?? 0}
          onPageChange={(newPage) => setFilters({ ...filters, page: newPage })}
        />
      </div>
    </div>
  )
}
