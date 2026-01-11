import clsx from 'clsx'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export function LoadingSpinner({ size = 'md', className }: LoadingSpinnerProps) {
  const sizeClass = size === 'sm' ? 'h-4 w-4' : size === 'lg' ? 'h-12 w-12' : 'h-8 w-8'

  return (
    <div className={clsx('flex items-center justify-center h-64', className)}>
      <div className={clsx('spinner', sizeClass)} />
    </div>
  )
}
