import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  IconChevronLeft,
  IconAlertTriangle,
  IconShieldCheck,
  IconCheckCircle,
  IconXCircle,
  IconArrowUpRight,
  IconPeople,
  IconBuilding,
  IconDocument,
} from '@/components/icons'
import { LoadingSpinner, RiskBadge, EmptyState } from '@/components/ui'
import { alertsApi, entitiesApi } from '@/services/api'
import clsx from 'clsx'

// Tier descriptions for Brottsdatalagen compliance
const TIER_INFO = {
  1: {
    name: 'Informational',
    description: 'Low confidence pattern. Logged for reference only.',
    action: 'No action required',
    color: 'text-archeron-400',
    bgColor: 'bg-archeron-800',
  },
  2: {
    name: 'Acknowledgment Required',
    description: 'Medium confidence pattern. Must be reviewed before export.',
    action: 'Review and acknowledge',
    color: 'text-yellow-400',
    bgColor: 'bg-yellow-500/10',
  },
  3: {
    name: 'Approval Required',
    description: 'High confidence pattern affecting individuals. Requires explicit approval with justification per Brottsdatalagen 2 kap. 19 §.',
    action: 'Review, justify, and approve',
    color: 'text-orange-400',
    bgColor: 'bg-orange-500/10',
  },
}

// Minimum justification length for Tier 3
const MIN_JUSTIFICATION_LENGTH = 10

// Garbage justifications that will be rejected
const GARBAGE_JUSTIFICATIONS = ['ok', 'yes', 'approved', 'fine', 'good', 'ja', 'godkänd']

export default function AlertDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [justification, setJustification] = useState('')
  const [displayedAt] = useState(new Date().toISOString())
  const [reviewStartTime] = useState(Date.now())
  const [justificationError, setJustificationError] = useState<string | null>(null)

  const { data: alertData, isLoading } = useQuery({
    queryKey: ['alert', id],
    queryFn: () => alertsApi.get(id!).then((r) => r.data),
    enabled: !!id,
  })

  // Fetch related entities
  const { data: entities } = useQuery({
    queryKey: ['alert', id, 'entities'],
    queryFn: async () => {
      if (!alertData?.entity_ids?.length) return []
      const results = await Promise.all(
        alertData.entity_ids.slice(0, 5).map((eid) =>
          entitiesApi.get(eid).then((r) => r.data).catch(() => null)
        )
      )
      return results.filter(Boolean)
    },
    enabled: !!alertData?.entity_ids?.length,
  })

  // Acknowledge mutation (Tier 2)
  const acknowledgeMutation = useMutation({
    mutationFn: () =>
      alertsApi.acknowledge(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert', id] })
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })

  // Approve mutation (Tier 3)
  const approveMutation = useMutation({
    mutationFn: (data: { decision: string; justification: string }) =>
      alertsApi.resolve(id!, { outcome: data.decision, notes: data.justification }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert', id] })
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      navigate('/alerts')
    },
  })

  // Dismiss mutation
  const dismissMutation = useMutation({
    mutationFn: (reason: string) => alertsApi.dismiss(id!, { reason }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert', id] })
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      navigate('/alerts')
    },
  })

  // Create case mutation
  const createCaseMutation = useMutation({
    mutationFn: () => alertsApi.createCase(id!),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      navigate(`/cases/${data.data.id}`)
    },
  })

  // Validate justification
  const validateJustification = (text: string): string | null => {
    const trimmed = text.trim().toLowerCase()

    if (trimmed.length < MIN_JUSTIFICATION_LENGTH) {
      return `Justification must be at least ${MIN_JUSTIFICATION_LENGTH} characters`
    }

    if (GARBAGE_JUSTIFICATIONS.includes(trimmed)) {
      return 'Please provide a meaningful justification explaining your decision'
    }

    return null
  }

  const handleApprove = () => {
    const error = validateJustification(justification)
    if (error) {
      setJustificationError(error)
      return
    }

    // Check for rubber-stamp (review time < 2 seconds)
    const reviewDuration = (Date.now() - reviewStartTime) / 1000
    if (reviewDuration < 2) {
      setJustificationError('Please take time to review the alert before approving')
      return
    }

    setJustificationError(null)
    approveMutation.mutate({ decision: 'approved', justification })
  }

  const handleReject = () => {
    const error = validateJustification(justification)
    if (error) {
      setJustificationError(error)
      return
    }
    setJustificationError(null)
    approveMutation.mutate({ decision: 'rejected', justification })
  }

  if (isLoading) {
    return <LoadingSpinner />
  }

  if (!alertData) {
    return <EmptyState message="Alert not found" />
  }

  const tier = alertData.tier || (alertData.confidence >= 0.85 ? 3 : alertData.confidence >= 0.5 ? 2 : 1)
  const tierInfo = TIER_INFO[tier as keyof typeof TIER_INFO]
  const isReviewed = alertData.status === 'acknowledged' || alertData.status === 'resolved'
  const canAcknowledge = tier === 2 && alertData.status === 'new'
  const canApprove = tier === 3 && alertData.status !== 'resolved'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link to="/alerts" className="text-archeron-400 hover:text-archeron-200 transition-colors">
          <IconChevronLeft className="h-6 w-6" />
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-orange-500/10">
              <IconAlertTriangle className="h-6 w-6 text-orange-400" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-archeron-100">
                {alertData.title || alertData.alert_type?.replace(/_/g, ' ')}
              </h1>
              <p className="text-sm text-archeron-500 font-mono">
                {alertData.id.substring(0, 8)}...
              </p>
            </div>
          </div>
        </div>

        {/* Status Badge */}
        <span
          className={clsx(
            'badge text-sm px-3 py-1',
            alertData.status === 'resolved' && 'bg-green-500/20 text-green-400',
            alertData.status === 'acknowledged' && 'bg-blue-500/20 text-blue-400',
            alertData.status === 'new' && 'bg-orange-500/20 text-orange-400',
            alertData.status === 'dismissed' && 'bg-archeron-700 text-archeron-400'
          )}
        >
          {alertData.status}
        </span>
      </div>

      {/* Tier Compliance Banner */}
      <div className={clsx('card p-4 border-l-4', tierInfo.bgColor,
        tier === 1 && 'border-archeron-600',
        tier === 2 && 'border-yellow-500',
        tier === 3 && 'border-orange-500'
      )}>
        <div className="flex items-start gap-4">
          <IconShieldCheck className={clsx('h-6 w-6 mt-0.5', tierInfo.color)} />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h3 className={clsx('font-semibold', tierInfo.color)}>
                Tier {tier}: {tierInfo.name}
              </h3>
              {tier === 3 && (
                <span className="text-xs bg-orange-500/20 text-orange-400 px-2 py-0.5 rounded">
                  Brottsdatalagen
                </span>
              )}
            </div>
            <p className="text-sm text-archeron-400 mt-1">{tierInfo.description}</p>
            <p className="text-sm text-archeron-300 mt-2">
              <strong>Required action:</strong> {tierInfo.action}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Alert Details */}
          <div className="card">
            <div className="p-4 border-b border-archeron-800">
              <h2 className="section-title">Alert Details</h2>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="text-xs font-medium text-archeron-500 uppercase tracking-wider">
                  Pattern Type
                </label>
                <p className="text-archeron-200 mt-1 capitalize">
                  {alertData.pattern_type?.replace(/_/g, ' ') || alertData.alert_type?.replace(/_/g, ' ')}
                </p>
              </div>

              <div>
                <label className="text-xs font-medium text-archeron-500 uppercase tracking-wider">
                  Description
                </label>
                <p className="text-archeron-300 mt-1">
                  {alertData.description || 'No description available'}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-medium text-archeron-500 uppercase tracking-wider">
                    Confidence Score
                  </label>
                  <div className="flex items-center gap-2 mt-1">
                    <div className="flex-1 h-2 bg-archeron-800 rounded-full overflow-hidden">
                      <div
                        className={clsx(
                          'h-full rounded-full',
                          alertData.confidence >= 0.85 && 'bg-orange-500',
                          alertData.confidence >= 0.5 && alertData.confidence < 0.85 && 'bg-yellow-500',
                          alertData.confidence < 0.5 && 'bg-archeron-600'
                        )}
                        style={{ width: `${(alertData.confidence || 0) * 100}%` }}
                      />
                    </div>
                    <span className="text-sm font-mono text-archeron-300">
                      {((alertData.confidence || 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-archeron-500 uppercase tracking-wider">
                    Severity
                  </label>
                  <p className="mt-1">
                    <RiskBadge level={alertData.severity} />
                  </p>
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-archeron-500 uppercase tracking-wider">
                  Created
                </label>
                <p className="text-archeron-300 mt-1">
                  {new Date(alertData.created_at).toLocaleString('sv-SE')}
                </p>
              </div>

              {alertData.reviewed_at && (
                <div>
                  <label className="text-xs font-medium text-archeron-500 uppercase tracking-wider">
                    Reviewed
                  </label>
                  <p className="text-archeron-300 mt-1">
                    {new Date(alertData.reviewed_at).toLocaleString('sv-SE')}
                    {alertData.reviewed_by && ` by ${alertData.reviewed_by}`}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Related Entities */}
          <div className="card">
            <div className="p-4 border-b border-archeron-800">
              <h2 className="section-title">Affected Entities</h2>
            </div>
            {entities && entities.length > 0 ? (
              <ul className="divide-y divide-archeron-800">
                {entities.map((entity: any) => (
                  <li key={entity.id} className="p-4">
                    <Link
                      to={`/entities/${entity.id}`}
                      className="flex items-center justify-between group"
                    >
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-archeron-800">
                          {entity.entity_type === 'company' ? (
                            <IconBuilding className="h-4 w-4 text-archeron-400" />
                          ) : (
                            <IconPeople className="h-4 w-4 text-archeron-400" />
                          )}
                        </div>
                        <div>
                          <p className="text-sm font-medium text-archeron-200 group-hover:text-accent-400 transition-colors">
                            {entity.name}
                          </p>
                          <p className="text-xs text-archeron-500 font-mono">
                            {entity.identifier}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <RiskBadge level={entity.risk_level} className="text-xs" />
                        <IconArrowUpRight className="h-4 w-4 text-archeron-600 group-hover:text-accent-400 transition-colors" />
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="p-4 text-center text-archeron-500">
                No entities linked to this alert
              </div>
            )}
          </div>

          {/* Transactions (if any) */}
          {alertData.transaction_ids && alertData.transaction_ids.length > 0 && (
            <div className="card">
              <div className="p-4 border-b border-archeron-800">
                <h2 className="section-title">Related Transactions</h2>
              </div>
              <div className="p-4 text-sm text-archeron-400">
                {alertData.transaction_ids.length} transaction(s) flagged
              </div>
            </div>
          )}
        </div>

        {/* Sidebar - Review Actions */}
        <div className="space-y-6">
          {/* Quick Actions */}
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-archeron-200 mb-4">Actions</h3>
            <div className="space-y-3">
              {!isReviewed && (
                <button
                  onClick={() => createCaseMutation.mutate()}
                  disabled={createCaseMutation.isPending}
                  className="btn btn-secondary w-full justify-center"
                >
                  <IconDocument className="h-4 w-4 mr-2" />
                  Create Investigation Case
                </button>
              )}
            </div>
          </div>

          {/* Tier 2: Acknowledgment */}
          {canAcknowledge && (
            <div className="card p-4 border border-yellow-500/30">
              <h3 className="text-sm font-semibold text-yellow-400 mb-3 flex items-center gap-2">
                <IconShieldCheck className="h-4 w-4" />
                Acknowledge Alert
              </h3>
              <p className="text-xs text-archeron-400 mb-4">
                By acknowledging, you confirm you have reviewed this alertData.
                This action will be logged in the audit trail.
              </p>
              <button
                onClick={() => acknowledgeMutation.mutate()}
                disabled={acknowledgeMutation.isPending}
                className="btn btn-primary w-full justify-center bg-yellow-600 hover:bg-yellow-500"
              >
                {acknowledgeMutation.isPending ? (
                  <span className="spinner h-4 w-4" />
                ) : (
                  <>
                    <IconCheckCircle className="h-4 w-4 mr-2" />
                    Acknowledge
                  </>
                )}
              </button>
            </div>
          )}

          {/* Tier 3: Approval with Justification */}
          {canApprove && (
            <div className="card p-4 border border-orange-500/30">
              <h3 className="text-sm font-semibold text-orange-400 mb-3 flex items-center gap-2">
                <IconShieldCheck className="h-4 w-4" />
                Review Decision
              </h3>
              <p className="text-xs text-archeron-400 mb-4">
                This alert affects individuals and requires explicit approval with
                justification per Brottsdatalagen 2 kap. 19 §.
              </p>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-archeron-400 mb-2">
                    Justification (required)
                  </label>
                  <textarea
                    value={justification}
                    onChange={(e) => {
                      setJustification(e.target.value)
                      setJustificationError(null)
                    }}
                    placeholder="Explain your decision... (minimum 10 characters)"
                    rows={4}
                    className={clsx(
                      'input w-full text-sm',
                      justificationError && 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
                    )}
                  />
                  {justificationError && (
                    <p className="text-xs text-red-400 mt-1">{justificationError}</p>
                  )}
                  <p className="text-xs text-archeron-600 mt-1">
                    {justification.length} / {MIN_JUSTIFICATION_LENGTH} min characters
                  </p>
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={handleApprove}
                    disabled={approveMutation.isPending}
                    className="btn btn-primary flex-1 justify-center bg-green-600 hover:bg-green-500"
                  >
                    {approveMutation.isPending ? (
                      <span className="spinner h-4 w-4" />
                    ) : (
                      <>
                        <IconCheckCircle className="h-4 w-4 mr-1" />
                        Approve
                      </>
                    )}
                  </button>
                  <button
                    onClick={handleReject}
                    disabled={approveMutation.isPending}
                    className="btn btn-secondary flex-1 justify-center text-red-400 hover:text-red-300"
                  >
                    <IconXCircle className="h-4 w-4 mr-1" />
                    Reject
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Dismiss Option */}
          {!isReviewed && (
            <div className="card p-4">
              <h3 className="text-sm font-semibold text-archeron-400 mb-3">
                Dismiss Alert
              </h3>
              <p className="text-xs text-archeron-500 mb-3">
                Mark as false positive or not requiring action.
              </p>
              <button
                onClick={() => {
                  const reason = prompt('Reason for dismissing:')
                  if (reason && reason.length >= 10) {
                    dismissMutation.mutate(reason)
                  } else if (reason) {
                    alert('Please provide a reason of at least 10 characters')
                  }
                }}
                disabled={dismissMutation.isPending}
                className="btn btn-ghost w-full justify-center text-archeron-400 hover:text-archeron-200"
              >
                <IconXCircle className="h-4 w-4 mr-2" />
                Dismiss
              </button>
            </div>
          )}

          {/* Already Reviewed */}
          {isReviewed && (
            <div className="card p-4 bg-archeron-800/50">
              <div className="flex items-center gap-2 text-green-400">
                <IconCheckCircle className="h-5 w-5" />
                <span className="font-medium">Reviewed</span>
              </div>
              <p className="text-xs text-archeron-400 mt-2">
                This alert has been reviewed and {alertData.status}.
              </p>
              {alertData.reviewed_at && (
                <p className="text-xs text-archeron-500 mt-1">
                  {new Date(alertData.reviewed_at).toLocaleString('sv-SE')}
                </p>
              )}
            </div>
          )}

          {/* Audit Info */}
          <div className="card p-4 bg-archeron-800/30">
            <h3 className="text-xs font-medium text-archeron-500 uppercase tracking-wider mb-2">
              Audit Information
            </h3>
            <dl className="space-y-2 text-xs">
              <div className="flex justify-between">
                <dt className="text-archeron-500">Displayed at</dt>
                <dd className="text-archeron-400 font-mono">
                  {new Date(displayedAt).toLocaleTimeString('sv-SE')}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-archeron-500">Alert ID</dt>
                <dd className="text-archeron-400 font-mono truncate max-w-[120px]">
                  {alertData.id}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </div>
  )
}
