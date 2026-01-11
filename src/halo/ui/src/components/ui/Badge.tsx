import clsx from 'clsx'
import { ReactNode } from 'react'

type BadgeVariant = 'critical' | 'high' | 'medium' | 'low' | 'neutral'

interface BadgeProps {
  variant?: BadgeVariant
  children: ReactNode
  className?: string
}

export function Badge({ variant = 'neutral', children, className }: BadgeProps) {
  return (
    <span className={clsx('badge', `badge-${variant}`, className)}>
      {children}
    </span>
  )
}

interface RiskBadgeProps {
  level?: string | null
  className?: string
}

export function RiskBadge({ level, className }: RiskBadgeProps) {
  if (!level) return <Badge className={className}>-</Badge>

  const normalized = level.toLowerCase().replace('_', '')
  const variant =
    normalized === 'critical' || normalized === 'veryhigh' ? 'critical' :
    normalized === 'high' ? 'high' :
    normalized === 'medium' ? 'medium' :
    normalized === 'low' ? 'low' : 'neutral'

  return (
    <Badge variant={variant} className={className}>
      {level.replace('_', ' ')}
    </Badge>
  )
}
