import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  IconChevronLeft,
  IconFolder,
  IconClock,
  IconPerson,
  IconDocument,
  IconMessage,
  IconPlus,
  IconCheckCircle,
  IconAlertTriangle,
} from '@/components/icons'
import { casesApi } from '@/services/api'
import clsx from 'clsx'

export default function CaseDetail() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const [newNote, setNewNote] = useState('')
  const [activeTab, setActiveTab] = useState<'overview' | 'evidence' | 'timeline' | 'notes'>('overview')

  const { data: caseData, isLoading } = useQuery({
    queryKey: ['case', id],
    queryFn: () => casesApi.get(id!).then((r) => r.data),
    enabled: !!id,
  })

  const { data: evidence } = useQuery({
    queryKey: ['case', id, 'evidence'],
    queryFn: () => casesApi.getEvidence(id!).then((r) => r.data),
    enabled: !!id && activeTab === 'evidence',
  })

  const { data: timeline } = useQuery({
    queryKey: ['case', id, 'timeline'],
    queryFn: () => casesApi.getTimeline(id!).then((r) => r.data),
    enabled: !!id && activeTab === 'timeline',
  })

  const addNoteMutation = useMutation({
    mutationFn: (note: string) => casesApi.addNote(id!, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['case', id] })
      setNewNote('')
    },
  })

  const updateStatusMutation = useMutation({
    mutationFn: (status: string) => casesApi.updateStatus(id!, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['case', id] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-halo-600" />
      </div>
    )
  }

  if (!caseData) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">Case not found</p>
      </div>
    )
  }

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      open: 'bg-blue-100 text-blue-800',
      in_progress: 'bg-yellow-100 text-yellow-800',
      pending_review: 'bg-purple-100 text-purple-800',
      closed: 'bg-gray-100 text-gray-800',
    }
    return colors[status] || 'bg-gray-100 text-gray-800'
  }

  const tabs = [
    { id: 'overview', label: 'Overview', icon: IconDocument },
    { id: 'evidence', label: 'Evidence', icon: IconFolder },
    { id: 'timeline', label: 'Timeline', icon: IconClock },
    { id: 'notes', label: 'Notes', icon: IconMessage },
  ] as const

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link to="/cases" className="text-gray-400 hover:text-gray-600">
          <IconChevronLeft className="h-6 w-6" />
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <IconFolder className="h-8 w-8 text-halo-600" />
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold text-gray-900">
                  {caseData.title}
                </h1>
                <span
                  className={clsx(
                    'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
                    getStatusColor(caseData.status)
                  )}
                >
                  {caseData.status.replace(/_/g, ' ')}
                </span>
              </div>
              <p className="text-sm text-gray-500 font-mono">
                {caseData.case_number}
              </p>
            </div>
          </div>
        </div>

        {/* Status Actions */}
        <div className="flex gap-2">
          {caseData.status !== 'closed' && (
            <select
              value={caseData.status}
              onChange={(e) => updateStatusMutation.mutate(e.target.value)}
              className="input py-1.5"
            >
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="pending_review">Pending Review</option>
              <option value="closed">Closed</option>
            </select>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium',
                activeTab === tab.id
                  ? 'border-halo-600 text-halo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              )}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Case Details */}
          <div className="card">
            <div className="p-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Details</h2>
            </div>
            <dl className="divide-y divide-gray-200">
              <div className="px-4 py-3 sm:grid sm:grid-cols-3 sm:gap-4">
                <dt className="text-sm font-medium text-gray-500">Type</dt>
                <dd className="mt-1 text-sm text-gray-900 sm:col-span-2 sm:mt-0 capitalize">
                  {caseData.case_type}
                </dd>
              </div>
              <div className="px-4 py-3 sm:grid sm:grid-cols-3 sm:gap-4">
                <dt className="text-sm font-medium text-gray-500">Priority</dt>
                <dd className="mt-1 text-sm sm:col-span-2 sm:mt-0">
                  <span
                    className={clsx(
                      'badge',
                      caseData.priority === 'critical' && 'badge-critical',
                      caseData.priority === 'high' && 'badge-high',
                      caseData.priority === 'medium' && 'badge-medium',
                      caseData.priority === 'low' && 'badge-low'
                    )}
                  >
                    {caseData.priority}
                  </span>
                </dd>
              </div>
              <div className="px-4 py-3 sm:grid sm:grid-cols-3 sm:gap-4">
                <dt className="text-sm font-medium text-gray-500">
                  Assigned To
                </dt>
                <dd className="mt-1 text-sm text-gray-900 sm:col-span-2 sm:mt-0">
                  {caseData.assigned_to || 'Unassigned'}
                </dd>
              </div>
              <div className="px-4 py-3 sm:grid sm:grid-cols-3 sm:gap-4">
                <dt className="text-sm font-medium text-gray-500">Created</dt>
                <dd className="mt-1 text-sm text-gray-900 sm:col-span-2 sm:mt-0">
                  {new Date(caseData.created_at).toLocaleString()}
                </dd>
              </div>
              <div className="px-4 py-3 sm:grid sm:grid-cols-3 sm:gap-4">
                <dt className="text-sm font-medium text-gray-500">Updated</dt>
                <dd className="mt-1 text-sm text-gray-900 sm:col-span-2 sm:mt-0">
                  {new Date(caseData.updated_at || caseData.created_at).toLocaleString()}
                </dd>
              </div>
            </dl>
          </div>

          {/* Description */}
          <div className="card">
            <div className="p-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">
                Description
              </h2>
            </div>
            <div className="p-4">
              <p className="text-sm text-gray-700 whitespace-pre-wrap">
                {caseData.description || 'No description provided'}
              </p>
            </div>
          </div>

          {/* Related Entities */}
          <div className="card">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">
                Related Entities
              </h2>
              <button className="btn btn-secondary text-xs py-1 px-2">
                <IconPlus className="h-3 w-3 mr-1" />
                Add
              </button>
            </div>
            <ul className="divide-y divide-gray-200">
              {caseData.entities?.map((entity: any) => (
                <li key={entity.id} className="px-4 py-3">
                  <Link
                    to={`/entities/${entity.id}`}
                    className="flex items-center justify-between hover:text-halo-600"
                  >
                    <span className="text-sm font-medium">{entity.name}</span>
                    <span className="text-xs text-gray-500">
                      {entity.entity_type}
                    </span>
                  </Link>
                </li>
              )) ?? (
                <li className="px-4 py-3 text-sm text-gray-500">
                  No related entities
                </li>
              )}
            </ul>
          </div>

          {/* Related Alerts */}
          <div className="card">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">
                Related Alerts
              </h2>
              <button className="btn btn-secondary text-xs py-1 px-2">
                <IconPlus className="h-3 w-3 mr-1" />
                Link
              </button>
            </div>
            <ul className="divide-y divide-gray-200">
              {caseData.alerts?.map((alert: any) => (
                <li key={alert.id} className="px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <IconAlertTriangle className="h-4 w-4 text-orange-500" />
                      <span className="text-sm">
                        {alert.alert_type.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <span
                      className={clsx(
                        'badge',
                        alert.risk_level === 'critical' && 'badge-critical',
                        alert.risk_level === 'high' && 'badge-high',
                        alert.risk_level === 'medium' && 'badge-medium',
                        alert.risk_level === 'low' && 'badge-low'
                      )}
                    >
                      {alert.risk_level}
                    </span>
                  </div>
                </li>
              )) ?? (
                <li className="px-4 py-3 text-sm text-gray-500">
                  No related alerts
                </li>
              )}
            </ul>
          </div>
        </div>
      )}

      {activeTab === 'evidence' && (
        <div className="card">
          <div className="p-4 border-b border-gray-200 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Evidence</h2>
            <button className="btn btn-primary text-sm">
              <IconPlus className="h-4 w-4 mr-2" />
              Add Evidence
            </button>
          </div>
          <ul className="divide-y divide-gray-200">
            {evidence?.items?.map((item: any) => (
              <li key={item.id} className="px-4 py-4">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {item.title}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      {item.evidence_type} - Added{' '}
                      {new Date(item.collected_at).toLocaleString()}
                    </p>
                    <p className="text-xs text-gray-400 font-mono mt-1">
                      Hash: {item.hash?.substring(0, 16)}...
                    </p>
                  </div>
                  <IconCheckCircle className="h-5 w-5 text-green-500" />
                </div>
              </li>
            )) ?? (
              <li className="px-4 py-8 text-center text-gray-500">
                No evidence collected yet
              </li>
            )}
          </ul>
        </div>
      )}

      {activeTab === 'timeline' && (
        <div className="card p-4">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Timeline</h2>
          <div className="relative">
            <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-200" />
            <ul className="space-y-4">
              {timeline?.events?.map((event: any, index: number) => (
                <li key={index} className="relative pl-10">
                  <div className="absolute left-2.5 w-3 h-3 rounded-full bg-halo-600" />
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-sm font-medium text-gray-900">
                      {event.description}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      {new Date(event.timestamp).toLocaleString()}
                    </p>
                  </div>
                </li>
              )) ?? (
                <li className="text-center text-gray-500 py-8">
                  No timeline events
                </li>
              )}
            </ul>
          </div>
        </div>
      )}

      {activeTab === 'notes' && (
        <div className="card">
          <div className="p-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">Notes</h2>
          </div>

          {/* Add Note Form */}
          <div className="p-4 border-b border-gray-200">
            <textarea
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
              placeholder="Add a note..."
              rows={3}
              className="input w-full"
            />
            <div className="mt-2 flex justify-end">
              <button
                onClick={() => addNoteMutation.mutate(newNote)}
                disabled={!newNote.trim() || addNoteMutation.isPending}
                className="btn btn-primary"
              >
                Add Note
              </button>
            </div>
          </div>

          {/* Notes List */}
          <ul className="divide-y divide-gray-200">
            {caseData.notes?.map((note: any) => (
              <li key={note.id} className="p-4">
                <div className="flex items-start gap-3">
                  <div className="h-8 w-8 rounded-full bg-gray-100 flex items-center justify-center">
                    <IconPerson className="h-4 w-4 text-gray-500" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-900">
                        {note.author}
                      </span>
                      <span className="text-xs text-gray-500">
                        {new Date(note.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 mt-1 whitespace-pre-wrap">
                      {note.content}
                    </p>
                  </div>
                </div>
              </li>
            )) ?? (
              <li className="p-4 text-center text-gray-500">No notes yet</li>
            )}
          </ul>
        </div>
      )}
    </div>
  )
}
