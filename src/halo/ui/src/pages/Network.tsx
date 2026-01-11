/**
 * Network - Full graph visualization of all entities.
 *
 * Displays the entire constellation of companies, persons, and their relationships.
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  IconBuilding,
  IconPerson,
  IconFilter,
  IconRefresh,
  IconAlertTriangle,
  IconPeople,
  IconLink,
  IconTarget,
} from '@/components/icons'
import { PageHeader, EmptyState } from '@/components/ui'
import NetworkGraph from '../components/NetworkGraph'
import { graphApi } from '@/services/api'

interface GraphNode {
  id: string
  type: 'Company' | 'Person' | 'Address' | 'Property' | 'BankAccount' | 'Document'
  label: string
  riskScore?: number
  shellScore?: number
  degree?: number
  clusterId?: string
}

interface GraphEdge {
  source: string
  target: string
  type: string
  label?: string
}

interface Cluster {
  id: string
  nodes: string[]
  size: number
  avgShellScore: number
  maxShellScore: number
  companyCount: number
  personCount: number
}

interface GraphStats {
  total_nodes: number
  total_edges: number
  displayed_nodes: number
  displayed_edges: number
  connected_nodes: number
  cluster_count: number
  total_companies: number
  total_persons: number
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  clusters: Cluster[]
  stats: GraphStats
}

export default function Network() {
  const navigate = useNavigate()
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [selectedCluster, setSelectedCluster] = useState<Cluster | null>(null)

  // Filters
  const [maxNodes, setMaxNodes] = useState(200)
  const [minShellScore, setMinShellScore] = useState(0)
  const [mode, setMode] = useState<'connected' | 'all' | 'high_risk'>('connected')
  const [showFilters, setShowFilters] = useState(false)

  const fetchGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await graphApi.getFull({
        max_nodes: maxNodes,
        min_shell_score: minShellScore,
        mode: mode,
      })
      setGraphData(response.data)
      setSelectedNode(null)
      setSelectedCluster(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch graph')
    } finally {
      setLoading(false)
    }
  }, [maxNodes, minShellScore, mode])

  useEffect(() => {
    fetchGraph()
  }, [fetchGraph])

  const handleNodeClick = (node: GraphNode) => {
    setSelectedNode(node)
    // Find cluster for this node
    if (node.clusterId && graphData?.clusters) {
      const cluster = graphData.clusters.find(c => c.id === node.clusterId)
      setSelectedCluster(cluster || null)
    } else {
      setSelectedCluster(null)
    }
  }

  const handleNodeDoubleClick = (node: GraphNode) => {
    navigate(`/entities/${encodeURIComponent(node.id)}`)
  }

  const handleClusterClick = (cluster: Cluster) => {
    setSelectedCluster(cluster)
    // Find first node in cluster
    const node = graphData?.nodes.find(n => n.id === cluster.nodes[0])
    if (node) setSelectedNode(node)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <PageHeader title="Entity Network" />

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              showFilters
                ? 'bg-accent-600 text-white'
                : 'bg-archeron-800 text-archeron-300 hover:bg-archeron-700'
            }`}
          >
            <IconFilter className="h-4 w-4" />
            Filters
          </button>
          <button
            onClick={fetchGraph}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-archeron-800 text-archeron-300 rounded-lg text-sm font-medium hover:bg-archeron-700 transition-colors disabled:opacity-50"
          >
            <IconRefresh className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-archeron-900 border border-archeron-700 rounded-lg p-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-archeron-300 mb-2">
                View Mode
              </label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as typeof mode)}
                className="w-full px-3 py-2 bg-archeron-800 border border-archeron-700 rounded-lg text-archeron-200 focus:outline-none focus:ring-2 focus:ring-accent-500"
              >
                <option value="connected">Connected entities (prioritize relationships)</option>
                <option value="high_risk">High risk (prioritize shell scores)</option>
                <option value="all">All entities (no priority)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-archeron-300 mb-2">
                Max Nodes
              </label>
              <select
                value={maxNodes}
                onChange={(e) => setMaxNodes(Number(e.target.value))}
                className="w-full px-3 py-2 bg-archeron-800 border border-archeron-700 rounded-lg text-archeron-200 focus:outline-none focus:ring-2 focus:ring-accent-500"
              >
                <option value={100}>100 nodes</option>
                <option value={200}>200 nodes</option>
                <option value={300}>300 nodes</option>
                <option value={500}>500 nodes</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-archeron-300 mb-2">
                Min Shell Score
              </label>
              <select
                value={minShellScore}
                onChange={(e) => setMinShellScore(Number(e.target.value))}
                className="w-full px-3 py-2 bg-archeron-800 border border-archeron-700 rounded-lg text-archeron-200 focus:outline-none focus:ring-2 focus:ring-accent-500"
              >
                <option value={0}>All companies</option>
                <option value={0.3}>Low risk+ (0.3+)</option>
                <option value={0.4}>Medium risk+ (0.4+)</option>
                <option value={0.6}>High risk only (0.6+)</option>
              </select>
            </div>
            <div className="flex items-end">
              <button
                onClick={fetchGraph}
                className="w-full px-4 py-2 bg-accent-600 text-white rounded-lg text-sm font-medium hover:bg-accent-700 transition-colors"
              >
                Apply Filters
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Stats Bar */}
      {graphData?.stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="bg-archeron-900 border border-archeron-700 rounded-lg p-3">
            <div className="flex items-center gap-2">
              <IconBuilding className="h-4 w-4 text-blue-400" />
              <div>
                <p className="text-lg font-semibold text-archeron-50">
                  {graphData.stats.total_companies.toLocaleString()}
                </p>
                <p className="text-xs text-archeron-400">Companies</p>
              </div>
            </div>
          </div>
          <div className="bg-archeron-900 border border-archeron-700 rounded-lg p-3">
            <div className="flex items-center gap-2">
              <IconPerson className="h-4 w-4 text-green-400" />
              <div>
                <p className="text-lg font-semibold text-archeron-50">
                  {graphData.stats.total_persons.toLocaleString()}
                </p>
                <p className="text-xs text-archeron-400">Persons</p>
              </div>
            </div>
          </div>
          <div className="bg-archeron-900 border border-archeron-700 rounded-lg p-3">
            <div className="flex items-center gap-2">
              <IconLink className="h-4 w-4 text-purple-400" />
              <div>
                <p className="text-lg font-semibold text-archeron-50">
                  {graphData.stats.connected_nodes}
                </p>
                <p className="text-xs text-archeron-400">Connected</p>
              </div>
            </div>
          </div>
          <div className="bg-archeron-900 border border-archeron-700 rounded-lg p-3">
            <div className="flex items-center gap-2">
              <IconPeople className="h-4 w-4 text-amber-400" />
              <div>
                <p className="text-lg font-semibold text-archeron-50">
                  {graphData.stats.cluster_count}
                </p>
                <p className="text-xs text-archeron-400">Clusters</p>
              </div>
            </div>
          </div>
          <div className="bg-archeron-900 border border-archeron-700 rounded-lg p-3">
            <div className="flex items-center gap-2">
              <IconTarget className="h-4 w-4 text-red-400" />
              <div>
                <p className="text-lg font-semibold text-archeron-50">
                  {graphData.stats.displayed_edges}
                </p>
                <p className="text-xs text-archeron-400">Relationships</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Graph */}
        <div className="lg:col-span-3">
          {loading ? (
            <div className="bg-archeron-900 border border-archeron-700 rounded-lg h-[600px] flex items-center justify-center">
              <div className="text-center">
                <IconRefresh className="h-8 w-8 text-archeron-600 mx-auto mb-2 animate-spin" />
                <p className="text-archeron-500">Loading graph...</p>
              </div>
            </div>
          ) : error ? (
            <div className="bg-archeron-900 border border-archeron-700 rounded-lg h-[600px] flex items-center justify-center">
              <EmptyState
                message={error}
                icon={<IconAlertTriangle className="h-8 w-8 text-red-500" />}
                action={
                  <button
                    onClick={fetchGraph}
                    className="mt-4 px-4 py-2 bg-archeron-800 text-archeron-300 rounded-lg text-sm hover:bg-archeron-700 transition-colors"
                  >
                    Retry
                  </button>
                }
              />
            </div>
          ) : graphData ? (
            <NetworkGraph
              nodes={graphData.nodes}
              edges={graphData.edges}
              selectedNodeId={selectedNode?.id}
              onNodeClick={handleNodeClick}
              onNodeDoubleClick={handleNodeDoubleClick}
              width={850}
              height={600}
              className="bg-archeron-900"
            />
          ) : null}
        </div>

        {/* Sidebar */}
        <div className="lg:col-span-1 space-y-4">
          {/* Selected Node Details */}
          <div className="bg-archeron-900 border border-archeron-700 rounded-lg p-4">
            <h3 className="text-sm font-medium text-archeron-300 mb-3">
              {selectedNode ? 'Selected Entity' : 'Select an Entity'}
            </h3>

            {selectedNode ? (
              <div className="space-y-3">
                <div>
                  <p className="text-archeron-200 font-medium text-sm">{selectedNode.label}</p>
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium mt-1 ${
                      selectedNode.type === 'Company'
                        ? 'bg-blue-500/20 text-blue-400'
                        : 'bg-green-500/20 text-green-400'
                    }`}
                  >
                    {selectedNode.type === 'Company' ? (
                      <IconBuilding className="h-3 w-3" />
                    ) : (
                      <IconPerson className="h-3 w-3" />
                    )}
                    {selectedNode.type}
                  </span>
                </div>

                {(selectedNode.shellScore ?? 0) > 0 && (
                  <div>
                    <p className="text-xs text-archeron-500 mb-1">Shell Score</p>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-archeron-800 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            (selectedNode.shellScore ?? 0) >= 0.6
                              ? 'bg-red-500'
                              : (selectedNode.shellScore ?? 0) >= 0.4
                              ? 'bg-amber-500'
                              : 'bg-green-500'
                          }`}
                          style={{ width: `${(selectedNode.shellScore ?? 0) * 100}%` }}
                        />
                      </div>
                      <span className="text-xs text-archeron-300">
                        {((selectedNode.shellScore ?? 0) * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                )}

                <div className="flex gap-4 text-xs text-archeron-400">
                  <span>{selectedNode.degree ?? 0} connections</span>
                </div>

                <button
                  onClick={() => handleNodeDoubleClick(selectedNode)}
                  className="w-full px-3 py-1.5 bg-accent-600 text-white rounded text-xs font-medium hover:bg-accent-700 transition-colors"
                >
                  View Full Details
                </button>
              </div>
            ) : (
              <p className="text-archeron-500 text-xs">
                Click a node to see details. Double-click to open entity page.
              </p>
            )}
          </div>

          {/* Clusters */}
          {graphData?.clusters && graphData.clusters.length > 0 && (
            <div className="bg-archeron-900 border border-archeron-700 rounded-lg p-4">
              <h3 className="text-sm font-medium text-archeron-300 mb-3">
                Top Clusters ({graphData.clusters.length})
              </h3>
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {graphData.clusters.slice(0, 10).map((cluster, i) => (
                  <button
                    key={cluster.id}
                    onClick={() => handleClusterClick(cluster)}
                    className={`w-full text-left p-2 rounded border transition-colors ${
                      selectedCluster?.id === cluster.id
                        ? 'bg-accent-600/20 border-accent-500'
                        : 'bg-archeron-800/50 border-archeron-700 hover:border-archeron-600'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-archeron-200">
                        Cluster {i + 1}
                      </span>
                      {cluster.maxShellScore >= 0.4 && (
                        <span
                          className={`text-xs px-1.5 py-0.5 rounded ${
                            cluster.maxShellScore >= 0.6
                              ? 'bg-red-500/20 text-red-400'
                              : 'bg-amber-500/20 text-amber-400'
                          }`}
                        >
                          {cluster.maxShellScore >= 0.6 ? 'High' : 'Medium'}
                        </span>
                      )}
                    </div>
                    <div className="flex gap-3 mt-1 text-xs text-archeron-400">
                      <span className="flex items-center gap-1">
                        <IconBuilding className="h-3 w-3" />
                        {cluster.companyCount}
                      </span>
                      <span className="flex items-center gap-1">
                        <IconPerson className="h-3 w-3" />
                        {cluster.personCount}
                      </span>
                      <span>{cluster.size} nodes</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Legend */}
          <div className="bg-archeron-900 border border-archeron-700 rounded-lg p-4">
            <h3 className="text-sm font-medium text-archeron-300 mb-3">Legend</h3>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-blue-500" />
                <span className="text-xs text-archeron-400">Company</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-green-500" />
                <span className="text-xs text-archeron-400">Person</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-amber-500" />
                <span className="text-xs text-archeron-400">Address</span>
              </div>
            </div>
            <div className="mt-3 pt-3 border-t border-archeron-800">
              <p className="text-xs text-archeron-500 mb-2">Risk Ring:</p>
              <div className="grid grid-cols-2 gap-1">
                <div className="flex items-center gap-1">
                  <div className="w-3 h-3 rounded-full border border-dashed border-green-500" />
                  <span className="text-xs text-archeron-500">Low</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-3 h-3 rounded-full border border-dashed border-yellow-500" />
                  <span className="text-xs text-archeron-500">Med</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-3 h-3 rounded-full border border-dashed border-orange-500" />
                  <span className="text-xs text-archeron-500">High</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-3 h-3 rounded-full border border-dashed border-red-500" />
                  <span className="text-xs text-archeron-500">Crit</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
