/**
 * Demo page showing shell company detection results from real Bolagsverket data.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  IconBuilding,
  IconPeople,
  IconAlertTriangle,
  IconNetwork,
  IconChevronRight,
  IconExternalLink,
  IconTriangle,
  IconReceipt,
  IconBriefcase,
  IconFileX,
} from '@/components/icons'
import NetworkGraph from '@/components/NetworkGraph'
import clsx from 'clsx'

interface DemoSummary {
  companies: number
  persons: number
  edges: number
  alerts: number
  serial_directors: number
  shell_networks: number
  role_concentrations: number
  circular_directors: number
  new_companies_many_directors: number
  dormant_reactivations: number
  top_serial_directors: Array<{
    person_name: string
    company_count: number
    company_ids: string[]
    severity: string
  }>
  top_shell_networks: Array<{
    company_count: number
    company_ids: string[]
    severity: string
  }>
  top_role_concentrations: Array<{
    person_name: string
    role: string
    company_count: number
    company_ids: string[]
    severity: string
  }>
  top_circular_directors: Array<{
    company_ids: string[]
    company_names: string[]
    severity: string
  }>
  top_new_companies_many_directors: Array<{
    company_id: string
    company_name: string
    director_count: number
    signature_date: string
    severity: string
  }>
  // SCB enrichment data
  scb_enriched: boolean
  scb_stats: {
    f_skatt_registered: number
    moms_registered: number
    zero_employees: number
  }
  scb_patterns: {
    no_fskatt: number
    zero_employees_many_directors: number
    shell_sni_codes: number
  }
  top_zero_emp_many_dirs: Array<{
    company_id: string
    company_name: string
    director_count: number
    employee_count: number
    severity: string
  }>
  top_shell_sni: Array<{
    company_id: string
    company_name: string
    shell_sni_codes: Array<{ code: string; description: string }>
    employee_count: number
    severity: string
  }>
}

interface NetworkData {
  nodes: Array<{
    id: string
    type: 'Company' | 'Person' | 'Address' | 'Property' | 'BankAccount' | 'Document'
    label: string
    riskScore?: number
    shellScore?: number
  }>
  edges: Array<{
    source: string
    target: string
    type: string
    label?: string
  }>
}

type PatternTab = 'serial' | 'network' | 'role' | 'circular' | 'new_company' | 'scb_employees' | 'scb_sni'

export default function Demo() {
  const [selectedDirector, setSelectedDirector] = useState<string | null>(null)
  const [selectedNetwork, setSelectedNetwork] = useState<string[] | null>(null)
  const [patternTab, setPatternTab] = useState<PatternTab>('serial')

  const { data: summary, isLoading } = useQuery<DemoSummary>({
    queryKey: ['demo', 'summary'],
    queryFn: () => fetch('/api/demo/summary').then(r => r.json()),
  })

  const { data: networkData } = useQuery<NetworkData>({
    queryKey: ['demo', 'network', selectedDirector || selectedNetwork?.[0]],
    queryFn: () => {
      const entityId = selectedDirector || selectedNetwork?.[0]
      if (!entityId) return { nodes: [], edges: [] }
      return fetch(`/api/graph/entities/${entityId}/network?hops=2&max_nodes=20`).then(r => r.json())
    },
    enabled: !!(selectedDirector || selectedNetwork),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner h-8 w-8" />
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="page-title">Shell Company Detection Demo</h1>
        <p className="page-subtitle">
          Real intelligence from {summary?.companies.toLocaleString()} Swedish companies extracted from Bolagsverket
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-8">
        <StatCard
          icon={IconBuilding}
          iconColor="text-blue-400"
          label="Companies"
          value={summary?.companies ?? 0}
          detail="Extracted"
        />
        <StatCard
          icon={IconPeople}
          iconColor="text-green-400"
          label="Directors"
          value={summary?.persons ?? 0}
          detail="Unique"
        />
        <StatCard
          icon={IconAlertTriangle}
          iconColor="text-orange-400"
          label="Alerts"
          value={summary?.alerts ?? 0}
          detail="Generated"
        />
        <StatCard
          icon={IconNetwork}
          iconColor="text-purple-400"
          label="Networks"
          value={summary?.shell_networks ?? 0}
          detail="Shell companies"
        />
        <StatCard
          icon={IconTriangle}
          iconColor="text-red-400"
          label="Circular"
          value={summary?.circular_directors ?? 0}
          detail="Relationships"
        />
        <StatCard
          icon={IconReceipt}
          iconColor="text-emerald-400"
          label="F-skatt"
          value={summary?.scb_stats?.f_skatt_registered ?? 0}
          detail="Registered"
        />
        <StatCard
          icon={IconBriefcase}
          iconColor="text-amber-400"
          label="No Employees"
          value={summary?.scb_stats?.zero_employees ?? 0}
          detail="Zero staff"
        />
        <StatCard
          icon={IconFileX}
          iconColor="text-rose-400"
          label="SCB Flags"
          value={summary?.scb_patterns?.zero_employees_many_directors ?? 0}
          detail="0 emp + dirs"
        />
      </div>

      {/* SCB Enrichment Banner */}
      {summary?.scb_enriched && (
        <div className="card p-4 bg-gradient-to-r from-emerald-500/10 to-blue-500/10 border-emerald-500/30">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/20">
              <IconReceipt className="h-5 w-5 text-emerald-400" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-emerald-100">SCB Företagsregistret Data Enriched</p>
              <p className="text-xs text-emerald-300/70">
                F-skatt, VAT, and employee data added • {summary.scb_stats.f_skatt_registered} with F-skatt • {summary.scb_stats.zero_employees} with 0 employees
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Panel - Findings with Tabs */}
        <div className="lg:col-span-1">
          <div className="card">
            {/* Pattern Tabs */}
            <div className="flex border-b border-archeron-800 overflow-x-auto">
              <button
                onClick={() => setPatternTab('serial')}
                className={clsx(
                  'px-3 py-2 text-xs font-medium border-b-2 whitespace-nowrap',
                  patternTab === 'serial'
                    ? 'border-orange-400 text-orange-400'
                    : 'border-transparent text-archeron-400 hover:text-white'
                )}
              >
                Serial ({summary?.serial_directors ?? 0})
              </button>
              <button
                onClick={() => setPatternTab('network')}
                className={clsx(
                  'px-3 py-2 text-xs font-medium border-b-2 whitespace-nowrap',
                  patternTab === 'network'
                    ? 'border-purple-400 text-purple-400'
                    : 'border-transparent text-archeron-400 hover:text-white'
                )}
              >
                Networks ({summary?.shell_networks ?? 0})
              </button>
              <button
                onClick={() => setPatternTab('role')}
                className={clsx(
                  'px-3 py-2 text-xs font-medium border-b-2 whitespace-nowrap',
                  patternTab === 'role'
                    ? 'border-cyan-400 text-cyan-400'
                    : 'border-transparent text-archeron-400 hover:text-white'
                )}
              >
                Roles ({summary?.role_concentrations ?? 0})
              </button>
              <button
                onClick={() => setPatternTab('circular')}
                className={clsx(
                  'px-3 py-2 text-xs font-medium border-b-2 whitespace-nowrap',
                  patternTab === 'circular'
                    ? 'border-red-400 text-red-400'
                    : 'border-transparent text-archeron-400 hover:text-white'
                )}
              >
                Circular ({summary?.circular_directors ?? 0})
              </button>
              <button
                onClick={() => setPatternTab('new_company')}
                className={clsx(
                  'px-3 py-2 text-xs font-medium border-b-2 whitespace-nowrap',
                  patternTab === 'new_company'
                    ? 'border-yellow-400 text-yellow-400'
                    : 'border-transparent text-archeron-400 hover:text-white'
                )}
              >
                New ({summary?.new_companies_many_directors ?? 0})
              </button>
              <button
                onClick={() => setPatternTab('scb_employees')}
                className={clsx(
                  'px-3 py-2 text-xs font-medium border-b-2 whitespace-nowrap',
                  patternTab === 'scb_employees'
                    ? 'border-emerald-400 text-emerald-400'
                    : 'border-transparent text-archeron-400 hover:text-white'
                )}
              >
                0 Emp ({summary?.scb_patterns?.zero_employees_many_directors ?? 0})
              </button>
              <button
                onClick={() => setPatternTab('scb_sni')}
                className={clsx(
                  'px-3 py-2 text-xs font-medium border-b-2 whitespace-nowrap',
                  patternTab === 'scb_sni'
                    ? 'border-rose-400 text-rose-400'
                    : 'border-transparent text-archeron-400 hover:text-white'
                )}
              >
                Shell SNI ({summary?.scb_patterns?.shell_sni_codes ?? 0})
              </button>
            </div>

            {/* Pattern Content */}
            <div className="max-h-[500px] overflow-y-auto">
              {/* Serial Directors */}
              {patternTab === 'serial' && (
                <ul className="divide-y divide-archeron-800">
                  {summary?.top_serial_directors.map((director, i) => (
                    <li
                      key={i}
                      className={clsx(
                        'p-4 cursor-pointer transition-colors',
                        selectedDirector === director.company_ids[0]
                          ? 'bg-accent-500/10'
                          : 'hover:bg-archeron-800/50'
                      )}
                      onClick={() => {
                        setSelectedDirector(director.company_ids[0])
                        setSelectedNetwork(null)
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-archeron-100">
                            {director.person_name}
                          </p>
                          <p className="text-xs text-archeron-500">
                            {director.company_count} companies
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={clsx(
                            'badge',
                            director.severity === 'high' ? 'badge-high' : 'badge-medium'
                          )}>
                            {director.severity}
                          </span>
                          <IconChevronRight className="h-4 w-4 text-archeron-500" />
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              {/* Shell Networks */}
              {patternTab === 'network' && (
                <ul className="divide-y divide-archeron-800">
                  {summary?.top_shell_networks.map((network, i) => (
                    <li
                      key={i}
                      className={clsx(
                        'p-4 cursor-pointer transition-colors',
                        selectedNetwork === network.company_ids
                          ? 'bg-accent-500/10'
                          : 'hover:bg-archeron-800/50'
                      )}
                      onClick={() => {
                        setSelectedNetwork(network.company_ids)
                        setSelectedDirector(null)
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-archeron-100">
                            Network of {network.company_count} companies
                          </p>
                          <p className="text-xs text-archeron-500">
                            Connected through shared directors
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={clsx(
                            'badge',
                            network.severity === 'high' ? 'badge-high' : 'badge-medium'
                          )}>
                            {network.severity}
                          </span>
                          <IconChevronRight className="h-4 w-4 text-archeron-500" />
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              {/* Role Concentrations */}
              {patternTab === 'role' && (
                <ul className="divide-y divide-archeron-800">
                  {summary?.top_role_concentrations?.map((item, i) => (
                    <li
                      key={i}
                      className={clsx(
                        'p-4 cursor-pointer transition-colors',
                        selectedDirector === item.company_ids?.[0]
                          ? 'bg-accent-500/10'
                          : 'hover:bg-archeron-800/50'
                      )}
                      onClick={() => {
                        setSelectedDirector(item.company_ids?.[0] || null)
                        setSelectedNetwork(null)
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-archeron-100">
                            {item.person_name}
                          </p>
                          <p className="text-xs text-archeron-500">
                            {item.role} at {item.company_count} companies
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={clsx(
                            'badge',
                            item.severity === 'high' ? 'badge-high' : 'badge-medium'
                          )}>
                            {item.severity}
                          </span>
                          <IconChevronRight className="h-4 w-4 text-archeron-500" />
                        </div>
                      </div>
                    </li>
                  )) ?? <li className="p-4 text-archeron-500 text-sm">No role concentrations found</li>}
                </ul>
              )}

              {/* Circular Directors */}
              {patternTab === 'circular' && (
                <ul className="divide-y divide-archeron-800">
                  {summary?.top_circular_directors?.map((item, i) => (
                    <li
                      key={i}
                      className={clsx(
                        'p-4 cursor-pointer transition-colors',
                        selectedNetwork === item.company_ids
                          ? 'bg-accent-500/10'
                          : 'hover:bg-archeron-800/50'
                      )}
                      onClick={() => {
                        setSelectedNetwork(item.company_ids)
                        setSelectedDirector(null)
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-archeron-100">
                            Circular relationship
                          </p>
                          <p className="text-xs text-archeron-500">
                            {item.company_names?.slice(0, 2).join(', ')}...
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="badge badge-high">
                            {item.severity}
                          </span>
                          <IconChevronRight className="h-4 w-4 text-archeron-500" />
                        </div>
                      </div>
                    </li>
                  )) ?? <li className="p-4 text-archeron-500 text-sm">No circular relationships found</li>}
                </ul>
              )}

              {/* New Companies with Many Directors */}
              {patternTab === 'new_company' && (
                <ul className="divide-y divide-archeron-800">
                  {summary?.top_new_companies_many_directors?.map((item, i) => (
                    <li
                      key={i}
                      className={clsx(
                        'p-4 cursor-pointer transition-colors',
                        selectedDirector === item.company_id
                          ? 'bg-accent-500/10'
                          : 'hover:bg-archeron-800/50'
                      )}
                      onClick={() => {
                        setSelectedDirector(item.company_id)
                        setSelectedNetwork(null)
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-archeron-100">
                            {item.company_name}
                          </p>
                          <p className="text-xs text-archeron-500">
                            {item.director_count} directors • {item.signature_date}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={clsx(
                            'badge',
                            item.severity === 'high' ? 'badge-high' : 'badge-medium'
                          )}>
                            {item.severity}
                          </span>
                          <IconChevronRight className="h-4 w-4 text-archeron-500" />
                        </div>
                      </div>
                    </li>
                  )) ?? <li className="p-4 text-archeron-500 text-sm">No new companies with many directors found</li>}
                </ul>
              )}

              {/* SCB: Zero Employees + Many Directors */}
              {patternTab === 'scb_employees' && (
                <ul className="divide-y divide-archeron-800">
                  {summary?.top_zero_emp_many_dirs?.map((item, i) => (
                    <li
                      key={i}
                      className={clsx(
                        'p-4 cursor-pointer transition-colors',
                        selectedDirector === item.company_id
                          ? 'bg-accent-500/10'
                          : 'hover:bg-archeron-800/50'
                      )}
                      onClick={() => {
                        setSelectedDirector(item.company_id)
                        setSelectedNetwork(null)
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-archeron-100">
                            {item.company_name}
                          </p>
                          <p className="text-xs text-archeron-500">
                            {item.director_count} directors • 0 employees
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={clsx(
                            'badge',
                            item.severity === 'high' ? 'badge-high' : 'badge-medium'
                          )}>
                            {item.severity}
                          </span>
                          <IconChevronRight className="h-4 w-4 text-archeron-500" />
                        </div>
                      </div>
                    </li>
                  )) ?? <li className="p-4 text-archeron-500 text-sm">No zero-employee companies found</li>}
                </ul>
              )}

              {/* SCB: Shell SNI Codes */}
              {patternTab === 'scb_sni' && (
                <ul className="divide-y divide-archeron-800">
                  {summary?.top_shell_sni?.map((item, i) => (
                    <li
                      key={i}
                      className={clsx(
                        'p-4 cursor-pointer transition-colors',
                        selectedDirector === item.company_id
                          ? 'bg-accent-500/10'
                          : 'hover:bg-archeron-800/50'
                      )}
                      onClick={() => {
                        setSelectedDirector(item.company_id)
                        setSelectedNetwork(null)
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-archeron-100">
                            {item.company_name}
                          </p>
                          <p className="text-xs text-archeron-500">
                            SNI: {item.shell_sni_codes?.map(c => c.code).join(', ')} • {item.employee_count} emp
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={clsx(
                            'badge',
                            item.severity === 'high' ? 'badge-high' : 'badge-medium'
                          )}>
                            {item.severity}
                          </span>
                          <IconChevronRight className="h-4 w-4 text-archeron-500" />
                        </div>
                      </div>
                    </li>
                  )) ?? <li className="p-4 text-archeron-500 text-sm">No shell SNI code companies found</li>}
                </ul>
              )}
            </div>
          </div>
        </div>

        {/* Right Panel - Network Visualization */}
        <div className="lg:col-span-2">
          <div className="card">
            <div className="p-4 border-b border-archeron-800">
              <h2 className="section-title">Network Visualization</h2>
              <p className="text-xs text-archeron-500 mt-1">
                {selectedDirector || selectedNetwork
                  ? 'Click a node to see details. Blue = Company, Green = Person.'
                  : 'Select a finding from the left panel to visualize.'}
              </p>
            </div>
            <div className="p-4">
              {networkData && (networkData.nodes?.length ?? 0) > 0 ? (
                <NetworkGraph
                  nodes={networkData.nodes}
                  edges={networkData.edges}
                  width={800}
                  height={600}
                  onNodeClick={(node) => {
                    console.log('Clicked node:', node)
                  }}
                />
              ) : (
                <div className="h-[600px] flex items-center justify-center bg-archeron-900/50 rounded-lg border border-archeron-800">
                  <div className="text-center">
                    <IconNetwork className="h-12 w-12 text-archeron-700 mx-auto mb-3" />
                    <p className="text-archeron-500">
                      Select a serial director or shell network to visualize
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Data Sources */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-green-500/10">
              <IconBuilding className="h-5 w-5 text-green-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-archeron-100">Bolagsverket HVD</p>
              <p className="text-xs text-archeron-500">
                Company registry data • Directors • Annual reports
              </p>
            </div>
          </div>
          <a
            href="https://www.bolagsverket.se"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-sm text-accent-400 hover:text-accent-300"
          >
            <IconExternalLink className="h-4 w-4" />
          </a>
        </div>
        <div className="card p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/10">
              <IconReceipt className="h-5 w-5 text-emerald-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-archeron-100">SCB Företagsregistret</p>
              <p className="text-xs text-archeron-500">
                F-skatt • VAT • Employees • SNI codes
              </p>
            </div>
          </div>
          <a
            href="https://www.scb.se"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-sm text-accent-400 hover:text-accent-300"
          >
            <IconExternalLink className="h-4 w-4" />
          </a>
        </div>
      </div>
    </div>
  )
}

function StatCard({
  icon: Icon,
  iconColor,
  label,
  value,
  detail,
}: {
  icon: typeof IconBuilding
  iconColor: string
  label: string
  value: number
  detail: string
}) {
  return (
    <div className="card p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="stat-label">{label}</p>
          <p className="stat-value mt-1">{value.toLocaleString()}</p>
        </div>
        <div className="stat-icon">
          <Icon className={clsx('h-5 w-5', iconColor)} />
        </div>
      </div>
      <p className="mt-2 text-xs text-archeron-500">{detail}</p>
    </div>
  )
}
