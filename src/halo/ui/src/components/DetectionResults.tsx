/**
 * DetectionResults - Component for displaying fraud detection results.
 *
 * Shows pattern matches, anomaly scores, and risk predictions.
 */

import { useState } from 'react'
import clsx from 'clsx'
import { format } from 'date-fns'
import {
  AlertTriangle,
  Shield,
  Eye,
  TrendingUp,
  GitBranch,
  Clock,
  ChevronDown,
  ChevronRight,
  FileText,
} from 'lucide-react'
import RiskIndicator, { RiskProgress, scoreToLevel, ShellIndicator } from './RiskIndicator'

// Types matching API responses
interface PatternMatch {
  pattern_id: string
  pattern_name: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  typology: string
  entity_ids: string[]
  match_data: Record<string, unknown>
  detected_at: string
}

interface AnomalyScore {
  entity_id: string
  entity_type: string
  composite_score: number
  is_anomalous: boolean
  severity: string
  z_scores: Record<string, number>
  flags: Array<{ type: string; severity: string; description?: string }>
}

interface FraudPrediction {
  entity_id: string
  entity_type: string
  risk_level: 'low' | 'medium' | 'high' | 'critical'
  probability: number
  confidence: number
  rationale: string
  construction_signals: string[]
  recommended_action?: string
}

interface PlaybookMatch {
  playbook_id: string
  playbook_name: string
  severity: string
  confidence: number
  current_stage: number
  total_stages: number
  next_expected?: string
  matched_events: Array<Record<string, unknown>>
  entity_id: string
  alert: string
}

// Pattern Match Card
interface PatternMatchCardProps {
  match: PatternMatch
  onViewDetails?: () => void
  className?: string
}

export function PatternMatchCard({ match, onViewDetails, className }: PatternMatchCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const severityColors: Record<string, string> = {
    low: 'border-l-green-500',
    medium: 'border-l-yellow-500',
    high: 'border-l-orange-500',
    critical: 'border-l-red-500',
  }

  return (
    <div
      className={clsx(
        'bg-archeron-800/50 rounded-lg border border-archeron-700 border-l-4',
        severityColors[match.severity],
        className
      )}
    >
      <div
        className="p-4 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3">
            <div className="p-2 bg-archeron-700 rounded-lg">
              <GitBranch className="h-5 w-5 text-archeron-300" />
            </div>
            <div>
              <h4 className="font-medium text-archeron-100">{match.pattern_name}</h4>
              <p className="text-sm text-archeron-400 mt-0.5">
                {match.typology.replace(/_/g, ' ')}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <RiskIndicator level={match.severity as any} size="sm" showScore={false} />
            {isExpanded ? (
              <ChevronDown className="h-4 w-4 text-archeron-400" />
            ) : (
              <ChevronRight className="h-4 w-4 text-archeron-400" />
            )}
          </div>
        </div>

        <div className="flex items-center gap-4 mt-3 text-xs text-archeron-500">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {format(new Date(match.detected_at), 'MMM d, HH:mm')}
          </span>
          <span>
            {match.entity_ids.length} entities involved
          </span>
        </div>
      </div>

      {isExpanded && (
        <div className="px-4 pb-4 border-t border-archeron-700">
          <div className="pt-3 space-y-3">
            <div>
              <h5 className="text-xs font-medium text-archeron-400 uppercase tracking-wider mb-2">
                Involved Entities
              </h5>
              <div className="flex flex-wrap gap-1">
                {match.entity_ids.map((id) => (
                  <span
                    key={id}
                    className="px-2 py-0.5 bg-archeron-700 rounded text-xs text-archeron-300"
                  >
                    {id}
                  </span>
                ))}
              </div>
            </div>

            {onViewDetails && (
              <button
                onClick={onViewDetails}
                className="flex items-center gap-1 text-sm text-accent-400 hover:text-accent-300 transition-colors"
              >
                <Eye className="h-4 w-4" />
                View full details
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Anomaly Score Card
interface AnomalyScoreCardProps {
  score: AnomalyScore
  className?: string
}

export function AnomalyScoreCard({ score, className }: AnomalyScoreCardProps) {
  return (
    <div
      className={clsx(
        'bg-archeron-800/50 rounded-lg border border-archeron-700 p-4',
        className
      )}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-archeron-400" />
          <span className="font-medium text-archeron-200">Anomaly Analysis</span>
        </div>
        <RiskIndicator
          level={score.severity as any || scoreToLevel(score.composite_score)}
          score={score.composite_score}
          size="sm"
        />
      </div>

      <RiskProgress
        score={score.composite_score}
        label="Composite Score"
        className="mb-4"
      />

      {score.flags.length > 0 && (
        <div>
          <h5 className="text-xs font-medium text-archeron-400 uppercase tracking-wider mb-2">
            Detected Flags
          </h5>
          <ul className="space-y-1">
            {score.flags.map((flag, i) => (
              <li
                key={i}
                className="flex items-center gap-2 text-sm"
              >
                <AlertTriangle className={clsx(
                  'h-3.5 w-3.5',
                  flag.severity === 'high' ? 'text-orange-400' :
                  flag.severity === 'critical' ? 'text-red-400' :
                  'text-yellow-400'
                )} />
                <span className="text-archeron-300">
                  {flag.type.replace(/_/g, ' ')}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {Object.keys(score.z_scores).length > 0 && (
        <div className="mt-4 pt-4 border-t border-archeron-700">
          <h5 className="text-xs font-medium text-archeron-400 uppercase tracking-wider mb-2">
            Z-Scores
          </h5>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(score.z_scores).map(([key, value]) => (
              <div key={key} className="text-sm">
                <span className="text-archeron-500">{key}:</span>
                <span className={clsx(
                  'ml-1 font-mono',
                  value > 2 ? 'text-red-400' :
                  value > 1.5 ? 'text-orange-400' :
                  'text-archeron-300'
                )}>
                  {value.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// Fraud Prediction Card
interface FraudPredictionCardProps {
  prediction: FraudPrediction
  onGenerateSAR?: () => void
  className?: string
}

export function FraudPredictionCard({
  prediction,
  onGenerateSAR,
  className,
}: FraudPredictionCardProps) {
  return (
    <div
      className={clsx(
        'bg-archeron-800/50 rounded-lg border border-archeron-700 p-4',
        className
      )}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-archeron-400" />
          <span className="font-medium text-archeron-200">Risk Prediction</span>
        </div>
        <RiskIndicator
          level={prediction.risk_level}
          score={prediction.probability}
          size="sm"
        />
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <RiskProgress
          score={prediction.probability}
          label="Probability"
        />
        <RiskProgress
          score={prediction.confidence}
          label="Confidence"
        />
      </div>

      <div className="mb-4">
        <h5 className="text-xs font-medium text-archeron-400 uppercase tracking-wider mb-1">
          Rationale
        </h5>
        <p className="text-sm text-archeron-300">{prediction.rationale}</p>
      </div>

      {prediction.construction_signals.length > 0 && (
        <ShellIndicator
          score={prediction.probability}
          signals={prediction.construction_signals}
          className="mb-4"
        />
      )}

      {prediction.recommended_action && (
        <div className="p-3 bg-archeron-900 rounded-lg">
          <h5 className="text-xs font-medium text-archeron-400 mb-1">
            Recommended Action
          </h5>
          <p className="text-sm text-accent-400 font-medium">
            {prediction.recommended_action.replace(/_/g, ' ')}
          </p>
        </div>
      )}

      {onGenerateSAR && prediction.risk_level !== 'low' && (
        <button
          onClick={onGenerateSAR}
          className="mt-4 w-full flex items-center justify-center gap-2 px-4 py-2 bg-accent-600 hover:bg-accent-500 rounded-lg text-sm font-medium text-white transition-colors"
        >
          <FileText className="h-4 w-4" />
          Generate SAR
        </button>
      )}
    </div>
  )
}

// Playbook Match Card
interface PlaybookMatchCardProps {
  match: PlaybookMatch
  className?: string
}

export function PlaybookMatchCard({ match, className }: PlaybookMatchCardProps) {
  const progressPercent = (match.current_stage / match.total_stages) * 100

  return (
    <div
      className={clsx(
        'bg-archeron-800/50 rounded-lg border border-archeron-700 p-4',
        className
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <h4 className="font-medium text-archeron-100">{match.playbook_name}</h4>
          <p className="text-sm text-archeron-400">{match.alert}</p>
        </div>
        <span className={clsx(
          'px-2 py-0.5 rounded text-xs font-medium',
          match.confidence >= 0.8 ? 'bg-red-500/20 text-red-400' :
          match.confidence >= 0.5 ? 'bg-orange-500/20 text-orange-400' :
          'bg-yellow-500/20 text-yellow-400'
        )}>
          {(match.confidence * 100).toFixed(0)}% confident
        </span>
      </div>

      {/* Progress bar */}
      <div className="mb-3">
        <div className="flex justify-between text-xs text-archeron-400 mb-1">
          <span>Stage {match.current_stage} of {match.total_stages}</span>
          <span>{progressPercent.toFixed(0)}% complete</span>
        </div>
        <div className="h-2 bg-archeron-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-orange-500 rounded-full transition-all"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {match.next_expected && (
        <div className="p-2 bg-archeron-900 rounded-lg">
          <p className="text-xs text-archeron-500">Next expected:</p>
          <p className="text-sm text-orange-400 font-medium">
            {match.next_expected.replace(/_/g, ' ')}
          </p>
        </div>
      )}
    </div>
  )
}

// Combined Detection Results Panel
interface DetectionResultsProps {
  patterns?: PatternMatch[]
  anomaly?: AnomalyScore
  prediction?: FraudPrediction
  playbooks?: PlaybookMatch[]
  onGenerateSAR?: () => void
  className?: string
}

export default function DetectionResults({
  patterns = [],
  anomaly,
  prediction,
  playbooks = [],
  onGenerateSAR,
  className,
}: DetectionResultsProps) {
  const hasResults = patterns.length > 0 || anomaly || prediction || playbooks.length > 0

  if (!hasResults) {
    return (
      <div className={clsx('text-center py-8', className)}>
        <Shield className="h-12 w-12 text-archeron-600 mx-auto mb-3" />
        <p className="text-archeron-400">No detection results available</p>
        <p className="text-sm text-archeron-500 mt-1">
          Run analysis to see fraud detection results
        </p>
      </div>
    )
  }

  return (
    <div className={clsx('space-y-4', className)}>
      {/* Risk Prediction */}
      {prediction && (
        <FraudPredictionCard
          prediction={prediction}
          onGenerateSAR={onGenerateSAR}
        />
      )}

      {/* Anomaly Score */}
      {anomaly && <AnomalyScoreCard score={anomaly} />}

      {/* Playbook Matches */}
      {playbooks.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-archeron-300 mb-2">
            Playbook Matches ({playbooks.length})
          </h3>
          <div className="space-y-2">
            {playbooks.map((match, i) => (
              <PlaybookMatchCard key={i} match={match} />
            ))}
          </div>
        </div>
      )}

      {/* Pattern Matches */}
      {patterns.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-archeron-300 mb-2">
            Pattern Matches ({patterns.length})
          </h3>
          <div className="space-y-2">
            {patterns.map((match, i) => (
              <PatternMatchCard key={i} match={match} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
