import { ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  actions?: ReactNode
}

export function PageHeader({ title, actions }: PageHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h1 className="text-xl font-semibold text-archeron-100">{title}</h1>
      {actions}
    </div>
  )
}
