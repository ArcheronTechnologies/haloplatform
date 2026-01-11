/**
 * RiskIndicator - Visual component for displaying risk levels.
 *
 * Shows risk scores with color-coded badges and progress bars.
 */

import clsx from 'clsx'
import {
  IconShieldCheck,
  IconShieldAlert,
  IconAlertTriangle,
  IconAlertCircle,
} from '@/components/icons'
import { SVGProps, ComponentType } from 'react'

type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

interface RiskIndicatorProps {
  level: RiskLevel
  score?: number
  label?: string
  showScore?: boolean
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const RISK_CONFIG: Record<RiskLevel, {
  color: string
  bg: string
  border: string
  icon: ComponentType<SVGProps<SVGSVGElement>>
  label: string
}> = {
  low: {
    color: 'text-green-400',
    bg: 'bg-green-500/10',
    border: 'border-green-500/30',
    icon: IconShieldCheck,
    label: 'Low Risk',
  },
  medium: {
    color: 'text-yellow-400',
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
    icon: IconAlertCircle,
    label: 'Medium Risk',
  },
  high: {
    color: 'text-orange-400',
    bg: 'bg-orange-500/10',
    border: 'border-orange-500/30',
    icon: IconAlertTriangle,
    label: 'High Risk',
  },
  critical: {
    color: 'text-red-400',
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    icon: IconShieldAlert,
    label: 'Critical Risk',
  },
}

const SIZE_CLASSES = {
  sm: 'text-xs px-2 py-0.5',
  md: 'text-sm px-2.5 py-1',
  lg: 'text-base px-3 py-1.5',
}

const ICON_SIZES = {
  sm: 'h-3 w-3',
  md: 'h-4 w-4',
  lg: 'h-5 w-5',
}

export default function RiskIndicator({
  level,
  score,
  label,
  showScore = true,
  size = 'md',
  className,
}: RiskIndicatorProps) {
  const config = RISK_CONFIG[level]
  const Icon = config.icon

  return (
    <div
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border font-medium',
        config.bg,
        config.border,
        config.color,
        SIZE_CLASSES[size],
        className
      )}
    >
      <Icon className={ICON_SIZES[size]} />
      <span>{label || config.label}</span>
      {showScore && score !== undefined && (
        <span className="opacity-70">({(score * 100).toFixed(0)}%)</span>
      )}
    </div>
  )
}

// Progress bar variant
interface RiskProgressProps {
  score: number
  label?: string
  showPercentage?: boolean
  className?: string
}

export function RiskProgress({
  score,
  label,
  showPercentage = true,
  className,
}: RiskProgressProps) {
  const level = scoreToLevel(score)
  const config = RISK_CONFIG[level]

  const bgColors: Record<RiskLevel, string> = {
    low: 'bg-green-500',
    medium: 'bg-yellow-500',
    high: 'bg-orange-500',
    critical: 'bg-red-500',
  }

  return (
    <div className={clsx('space-y-1', className)}>
      {(label || showPercentage) && (
        <div className="flex justify-between text-sm">
          {label && <span className="text-archeron-400">{label}</span>}
          {showPercentage && (
            <span className={config.color}>{(score * 100).toFixed(0)}%</span>
          )}
        </div>
      )}
      <div className="h-2 bg-archeron-800 rounded-full overflow-hidden">
        <div
          className={clsx('h-full rounded-full transition-all duration-500', bgColors[level])}
          style={{ width: `${Math.min(100, score * 100)}%` }}
        />
      </div>
    </div>
  )
}

// Score to level conversion
export function scoreToLevel(score: number): RiskLevel {
  if (score >= 0.8) return 'critical'
  if (score >= 0.6) return 'high'
  if (score >= 0.3) return 'medium'
  return 'low'
}

// Score badge for tables
interface RiskScoreBadgeProps {
  score: number
  className?: string
}

export function RiskScoreBadge({ score, className }: RiskScoreBadgeProps) {
  const level = scoreToLevel(score)
  const config = RISK_CONFIG[level]

  return (
    <span
      className={clsx(
        'inline-flex items-center justify-center w-12 h-6 rounded text-xs font-medium',
        config.bg,
        config.color,
        className
      )}
    >
      {(score * 100).toFixed(0)}%
    </span>
  )
}

// Shell company indicator
interface ShellIndicatorProps {
  score: number
  signals?: string[]
  className?: string
}

export function ShellIndicator({ score, signals = [], className }: ShellIndicatorProps) {
  const isLikelyShell = score >= 0.5

  return (
    <div className={clsx('space-y-2', className)}>
      <div className="flex items-center justify-between">
        <span className="text-sm text-archeron-400">Shell Score</span>
        <RiskScoreBadge score={score} />
      </div>

      {isLikelyShell && signals.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-archeron-500">Detected signals:</p>
          <ul className="space-y-0.5">
            {signals.slice(0, 5).map((signal, i) => (
              <li
                key={i}
                className="text-xs text-orange-400 flex items-center gap-1"
              >
                <span className="w-1 h-1 bg-orange-400 rounded-full" />
                {signal}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
