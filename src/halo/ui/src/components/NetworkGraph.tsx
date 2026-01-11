/**
 * NetworkGraph - Interactive graph visualization component.
 *
 * Displays entity networks using a force-directed layout.
 * Supports node/edge filtering, zooming, and click interactions.
 */

import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import clsx from 'clsx'
import {
  IconZoomIn,
  IconZoomOut,
  IconMaximize,
  IconRefresh,
} from '@/components/icons'

// Types
interface GraphNode {
  id: string
  type: 'Company' | 'Person' | 'Address' | 'Property' | 'BankAccount' | 'Document'
  label: string
  riskScore?: number
  shellScore?: number
  x?: number
  y?: number
}

interface GraphEdge {
  source: string
  target: string
  type: string
  label?: string
}

interface NetworkGraphProps {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedNodeId?: string
  onNodeClick?: (node: GraphNode) => void
  onNodeDoubleClick?: (node: GraphNode) => void
  width?: number
  height?: number
  className?: string
}

// Constants
const NODE_RADIUS = 12
const SMALL_NODE_RADIUS = 8

// Node colors by type
const NODE_COLORS: Record<string, string> = {
  Company: '#3b82f6',  // blue
  Person: '#10b981',   // green
  Address: '#f59e0b',  // amber
  Property: '#8b5cf6', // purple
  BankAccount: '#ec4899', // pink
  Document: '#6b7280', // gray
}

// Risk colors
function getRiskColor(score: number): string {
  if (score >= 0.8) return '#ef4444' // red
  if (score >= 0.6) return '#f97316' // orange
  if (score >= 0.4) return '#eab308' // yellow
  return '#22c55e' // green
}

/**
 * Force-directed layout using iterative simulation.
 * Runs to completion synchronously for stable positioning.
 */
function computeLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  width: number,
  height: number
): GraphNode[] {
  if (nodes.length === 0) return []

  // Build adjacency and node map
  const adjacency = new Map<string, Set<string>>()
  nodes.forEach(n => adjacency.set(n.id, new Set()))

  edges.forEach(edge => {
    adjacency.get(edge.source)?.add(edge.target)
    adjacency.get(edge.target)?.add(edge.source)
  })

  // Find connected components
  const visited = new Set<string>()
  const components: string[][] = []
  const nodeToComponent = new Map<string, number>()

  nodes.forEach(node => {
    if (visited.has(node.id)) return

    const component: string[] = []
    const queue = [node.id]

    while (queue.length > 0) {
      const current = queue.shift()!
      if (visited.has(current)) continue

      visited.add(current)
      component.push(current)
      nodeToComponent.set(current, components.length)

      adjacency.get(current)?.forEach(neighbor => {
        if (!visited.has(neighbor)) {
          queue.push(neighbor)
        }
      })
    }

    components.push(component)
  })

  // Initialize positions - spread components across the canvas
  type SimNode = { id: string; x: number; y: number; vx: number; vy: number; component: number }
  const simNodes: SimNode[] = []
  const nodeIndex = new Map<string, number>()

  // Calculate component centers spread across canvas
  const connectedComponents = components.filter(c => c.length > 1)
  const isolatedNodes = components.filter(c => c.length === 1).flat()

  // Place connected components in a rough grid
  const numConnected = connectedComponents.length
  const cols = Math.ceil(Math.sqrt(numConnected))
  const cellWidth = width / (cols + 1)
  const cellHeight = height / (Math.ceil(numConnected / cols) + 1)

  connectedComponents.forEach((component, compIdx) => {
    const col = compIdx % cols
    const row = Math.floor(compIdx / cols)
    const centerX = cellWidth * (col + 1)
    const centerY = cellHeight * (row + 1)

    // Spread nodes in component around center
    component.forEach((nodeId, i) => {
      const angle = (i / component.length) * 2 * Math.PI
      const spread = Math.min(100, component.length * 8)
      nodeIndex.set(nodeId, simNodes.length)
      simNodes.push({
        id: nodeId,
        x: centerX + Math.cos(angle) * spread + (Math.random() - 0.5) * 20,
        y: centerY + Math.sin(angle) * spread + (Math.random() - 0.5) * 20,
        vx: 0,
        vy: 0,
        component: compIdx,
      })
    })
  })

  // Place isolated nodes at the bottom/edges
  const isolatedStartY = height * 0.85
  isolatedNodes.forEach((nodeId, i) => {
    const x = 50 + (i % 20) * 40
    const y = isolatedStartY + Math.floor(i / 20) * 30
    nodeIndex.set(nodeId, simNodes.length)
    simNodes.push({
      id: nodeId,
      x,
      y,
      vx: 0,
      vy: 0,
      component: -1,
    })
  })

  // Force simulation parameters
  const iterations = 100
  const repulsion = 800
  const attraction = 0.05
  const damping = 0.85
  const minDistance = 35

  // Run simulation
  for (let iter = 0; iter < iterations; iter++) {
    const alpha = 1 - iter / iterations // Cooling

    // Repulsion between all nodes (within same component only for efficiency)
    for (let i = 0; i < simNodes.length; i++) {
      const nodeA = simNodes[i]
      if (nodeA.component === -1) continue // Skip isolated nodes

      for (let j = i + 1; j < simNodes.length; j++) {
        const nodeB = simNodes[j]
        if (nodeB.component !== nodeA.component) continue // Only within component

        const dx = nodeA.x - nodeB.x
        const dy = nodeA.y - nodeB.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1

        // Repulsion force
        const force = (repulsion * alpha) / (dist * dist)
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force

        nodeA.vx += fx
        nodeA.vy += fy
        nodeB.vx -= fx
        nodeB.vy -= fy

        // Collision avoidance
        if (dist < minDistance) {
          const overlap = (minDistance - dist) / 2
          const pushX = (dx / dist) * overlap
          const pushY = (dy / dist) * overlap
          nodeA.x += pushX
          nodeA.y += pushY
          nodeB.x -= pushX
          nodeB.y -= pushY
        }
      }
    }

    // Attraction along edges
    edges.forEach(edge => {
      const srcIdx = nodeIndex.get(edge.source)
      const tgtIdx = nodeIndex.get(edge.target)
      if (srcIdx === undefined || tgtIdx === undefined) return

      const src = simNodes[srcIdx]
      const tgt = simNodes[tgtIdx]

      const dx = tgt.x - src.x
      const dy = tgt.y - src.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1

      // Spring force - pull connected nodes together
      const targetDist = 60
      const force = (dist - targetDist) * attraction * alpha
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force

      src.vx += fx
      src.vy += fy
      tgt.vx -= fx
      tgt.vy -= fy
    })

    // Apply velocities and damping
    simNodes.forEach(node => {
      if (node.component === -1) return // Don't move isolated nodes

      node.vx *= damping
      node.vy *= damping
      node.x += node.vx
      node.y += node.vy

      // Keep in bounds with padding
      node.x = Math.max(30, Math.min(width - 30, node.x))
      node.y = Math.max(30, Math.min(height * 0.8, node.y))
    })
  }

  // Return nodes with computed positions
  return nodes.map(node => {
    const idx = nodeIndex.get(node.id)
    if (idx === undefined) return { ...node, x: width / 2, y: height / 2 }
    return {
      ...node,
      x: simNodes[idx].x,
      y: simNodes[idx].y,
    }
  })
}

export default function NetworkGraph({
  nodes,
  edges,
  selectedNodeId,
  onNodeClick,
  onNodeDoubleClick,
  width = 800,
  height = 600,
  className,
}: NetworkGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })
  const [showLabels, setShowLabels] = useState(true)

  // Compute layout once when nodes/edges change
  const layoutNodes = useMemo(() => {
    // Use larger canvas for layout, we'll zoom to fit
    return computeLayout(nodes, edges, width * 2, height * 2)
  }, [nodes, edges, width, height])

  // Auto-fit to content
  useEffect(() => {
    if (layoutNodes.length === 0) return

    const xs = layoutNodes.map(n => n.x!)
    const ys = layoutNodes.map(n => n.y!)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)

    const contentWidth = maxX - minX + 100
    const contentHeight = maxY - minY + 100

    const scaleX = width / contentWidth
    const scaleY = height / contentHeight
    const scale = Math.min(scaleX, scaleY, 1.5) * 0.9

    const centerX = (minX + maxX) / 2
    const centerY = (minY + maxY) / 2

    setZoom(scale)
    setPan({
      x: width / 2 - centerX * scale,
      y: height / 2 - centerY * scale,
    })
  }, [layoutNodes, width, height])

  // Decide whether to show labels based on node count
  useEffect(() => {
    setShowLabels(nodes.length <= 100)
  }, [nodes.length])

  // Pan handlers
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    setIsDragging(true)
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y })
  }, [pan])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isDragging) {
      setPan({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      })
    }
  }, [isDragging, dragStart])

  const handleMouseUp = useCallback(() => {
    setIsDragging(false)
  }, [])

  // Zoom handlers
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return

    const mouseX = e.clientX - rect.left
    const mouseY = e.clientY - rect.top

    const delta = e.deltaY > 0 ? 0.9 : 1.1
    const newZoom = Math.max(0.1, Math.min(5, zoom * delta))

    // Zoom towards mouse position
    const scale = newZoom / zoom
    setPan({
      x: mouseX - (mouseX - pan.x) * scale,
      y: mouseY - (mouseY - pan.y) * scale,
    })
    setZoom(newZoom)
  }, [zoom, pan])

  const zoomIn = () => setZoom(z => Math.min(5, z * 1.3))
  const zoomOut = () => setZoom(z => Math.max(0.1, z / 1.3))
  const resetView = useCallback(() => {
    if (layoutNodes.length === 0) return

    const xs = layoutNodes.map(n => n.x!)
    const ys = layoutNodes.map(n => n.y!)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)

    const contentWidth = maxX - minX + 100
    const contentHeight = maxY - minY + 100

    const scaleX = width / contentWidth
    const scaleY = height / contentHeight
    const scale = Math.min(scaleX, scaleY, 1.5) * 0.9

    const centerX = (minX + maxX) / 2
    const centerY = (minY + maxY) / 2

    setZoom(scale)
    setPan({
      x: width / 2 - centerX * scale,
      y: height / 2 - centerY * scale,
    })
  }, [layoutNodes, width, height])

  // Build edge map for rendering
  const nodeMap = useMemo(() => new Map(layoutNodes.map(n => [n.id, n])), [layoutNodes])

  // Determine node radius based on count
  const nodeRadius = nodes.length > 150 ? SMALL_NODE_RADIUS : NODE_RADIUS

  return (
    <div className={clsx('relative rounded-lg border border-archeron-700 overflow-hidden', className)}>
      {/* Controls */}
      <div className="absolute top-3 right-3 z-10 flex flex-col gap-1">
        <button
          onClick={zoomIn}
          className="p-2 bg-archeron-800 rounded-md text-archeron-400 hover:text-archeron-100 transition-colors"
          title="Zoom in"
        >
          <IconZoomIn className="h-4 w-4" />
        </button>
        <button
          onClick={zoomOut}
          className="p-2 bg-archeron-800 rounded-md text-archeron-400 hover:text-archeron-100 transition-colors"
          title="Zoom out"
        >
          <IconZoomOut className="h-4 w-4" />
        </button>
        <button
          onClick={resetView}
          className="p-2 bg-archeron-800 rounded-md text-archeron-400 hover:text-archeron-100 transition-colors"
          title="Reset view"
        >
          <IconMaximize className="h-4 w-4" />
        </button>
      </div>

      {/* Node count indicator */}
      <div className="absolute top-3 left-3 z-10 bg-archeron-900/90 rounded-md px-2 py-1 text-xs text-archeron-400">
        {nodes.length} nodes, {edges.length} edges
      </div>

      {/* Legend */}
      <div className="absolute bottom-3 left-3 z-10 bg-archeron-900/90 rounded-md p-2 text-xs">
        <div className="flex flex-wrap gap-3">
          {Object.entries(NODE_COLORS).slice(0, 3).map(([type, color]) => (
            <div key={type} className="flex items-center gap-1">
              <div
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: color }}
              />
              <span className="text-archeron-400">{type}</span>
            </div>
          ))}
        </div>
      </div>

      {/* SVG Canvas */}
      <svg
        ref={svgRef}
        width={width}
        height={height}
        className="bg-archeron-950 cursor-grab active:cursor-grabbing"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
      >
        <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
          {/* Edges */}
          {edges.map((edge, i) => {
            const source = nodeMap.get(edge.source)
            const target = nodeMap.get(edge.target)
            if (!source || !target) return null

            return (
              <line
                key={`edge-${i}`}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke="#4b5563"
                strokeWidth={1}
                strokeOpacity={0.6}
              />
            )
          })}

          {/* Nodes */}
          {layoutNodes.map((node) => {
            const color = NODE_COLORS[node.type] || '#6b7280'
            const isSelected = node.id === selectedNodeId
            const shellScore = node.shellScore ?? 0
            const hasRisk = shellScore > 0.3

            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onClick={(e) => {
                  e.stopPropagation()
                  onNodeClick?.(node)
                }}
                onDoubleClick={(e) => {
                  e.stopPropagation()
                  onNodeDoubleClick?.(node)
                }}
                className="cursor-pointer"
              >
                {/* Risk indicator ring */}
                {hasRisk && (
                  <circle
                    r={nodeRadius + 3}
                    fill="none"
                    stroke={getRiskColor(shellScore)}
                    strokeWidth={2}
                    strokeDasharray="3 2"
                  />
                )}

                {/* Selection ring */}
                {isSelected && (
                  <circle
                    r={nodeRadius + 5}
                    fill="none"
                    stroke="#f59e0b"
                    strokeWidth={2}
                  />
                )}

                {/* Node circle */}
                <circle
                  r={nodeRadius}
                  fill={color}
                  className="transition-opacity hover:opacity-80"
                />

                {/* Label (only for small graphs) */}
                {showLabels && (
                  <text
                    y={nodeRadius + 12}
                    textAnchor="middle"
                    className="fill-archeron-400 text-[9px] pointer-events-none"
                  >
                    {node.label.length > 12 ? node.label.slice(0, 12) + '...' : node.label}
                  </text>
                )}
              </g>
            )
          })}
        </g>
      </svg>

      {/* Empty state */}
      {nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <IconRefresh className="h-8 w-8 text-archeron-600 mx-auto mb-2" />
            <p className="text-archeron-500">No nodes to display</p>
          </div>
        </div>
      )}
    </div>
  )
}
