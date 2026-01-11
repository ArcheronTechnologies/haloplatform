import { ReactNode } from 'react'
import clsx from 'clsx'

interface EmptyStateProps {
  message: string
  icon?: ReactNode
  action?: ReactNode
  className?: string
  colSpan?: number
}

export function EmptyState({ message, icon, action, className, colSpan }: EmptyStateProps) {
  const content = (
    <div className={clsx('empty-state', className)}>
      {icon && <div className="mb-3">{icon}</div>}
      <p>{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )

  if (colSpan) {
    return <tr><td colSpan={colSpan}>{content}</td></tr>
  }

  return content
}
