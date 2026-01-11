import { useState } from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import {
  IconDashboard,
  IconPeople,
  IconAlertTriangle,
  IconFolder,
  IconSearch,
  IconSettings,
  IconMenu,
  IconX,
  IconHalo,
  IconBell,
  IconPerson,
  IconNetwork,
} from '@/components/icons'
import clsx from 'clsx'

const navigation = [
  { name: 'Dashboard', href: '/', icon: IconDashboard },
  { name: 'Network', href: '/network', icon: IconNetwork },
  { name: 'Entities', href: '/entities', icon: IconPeople },
  { name: 'Alerts', href: '/alerts', icon: IconAlertTriangle },
  { name: 'Cases', href: '/cases', icon: IconFolder },
  { name: 'Search', href: '/search', icon: IconSearch },
  { name: 'Settings', href: '/settings', icon: IconSettings },
]

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="min-h-screen bg-archeron-950">
      {/* Mobile sidebar */}
      <div
        className={clsx(
          'fixed inset-0 z-50 lg:hidden',
          sidebarOpen ? 'block' : 'hidden'
        )}
      >
        <div
          className="fixed inset-0 bg-archeron-950/80 backdrop-blur-sm"
          onClick={() => setSidebarOpen(false)}
        />
        <div className="fixed inset-y-0 left-0 flex w-64 flex-col bg-archeron-900 border-r border-archeron-800">
          <div className="flex h-16 items-center justify-between px-4 border-b border-archeron-800">
            <div className="flex items-center gap-3">
              <div className="p-1.5 bg-accent-600/20 rounded-lg">
                <IconHalo className="h-6 w-6 text-accent-400" />
              </div>
              <span className="text-lg font-semibold text-archeron-50 tracking-tight">Halo</span>
            </div>
            <button
              type="button"
              className="text-archeron-400 hover:text-archeron-100 transition-colors"
              onClick={() => setSidebarOpen(false)}
            >
              <IconX className="h-5 w-5" />
            </button>
          </div>
          <nav className="flex-1 px-3 py-4 space-y-1">
            {navigation.map((item) => (
              <NavLink
                key={item.name}
                to={item.href}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-all duration-200',
                    isActive
                      ? 'bg-archeron-800 text-archeron-50 border-l-2 border-accent-500 ml-[-2px]'
                      : 'text-archeron-400 hover:bg-archeron-800/50 hover:text-archeron-200'
                  )
                }
                onClick={() => setSidebarOpen(false)}
              >
                <item.icon className="h-5 w-5" />
                {item.name}
              </NavLink>
            ))}
          </nav>
          <div className="p-4 border-t border-archeron-800">
            <div className="text-xs text-archeron-500">
              Archeron Technologies
            </div>
          </div>
        </div>
      </div>

      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:w-64 lg:flex-col">
        <div className="flex grow flex-col gap-y-5 overflow-y-auto bg-archeron-900 border-r border-archeron-800 px-6 pb-4">
          <div className="flex h-16 shrink-0 items-center gap-3">
            <div className="p-1.5 bg-accent-600/20 rounded-lg">
              <IconHalo className="h-6 w-6 text-accent-400" />
            </div>
            <span className="text-lg font-semibold text-archeron-50 tracking-tight">Halo</span>
          </div>
          <nav className="flex flex-1 flex-col">
            <ul role="list" className="flex flex-1 flex-col gap-y-1">
              {navigation.map((item) => (
                <li key={item.name}>
                  <NavLink
                    to={item.href}
                    className={({ isActive }) =>
                      clsx(
                        'flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-all duration-200',
                        isActive
                          ? 'bg-archeron-800 text-archeron-50 border-l-2 border-accent-500 ml-[-2px]'
                          : 'text-archeron-400 hover:bg-archeron-800/50 hover:text-archeron-200'
                      )
                    }
                  >
                    <item.icon className="h-5 w-5" />
                    {item.name}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <div className="border-t border-archeron-800 pt-4">
            <div className="text-xs text-archeron-500">
              Archeron Technologies
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="lg:pl-64">
        {/* Top bar */}
        <div className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-x-4 border-b border-archeron-800 bg-archeron-900/80 backdrop-blur-md px-4 sm:gap-x-6 sm:px-6 lg:px-8">
          <button
            type="button"
            className="text-archeron-400 hover:text-archeron-100 lg:hidden transition-colors"
            onClick={() => setSidebarOpen(true)}
          >
            <IconMenu className="h-6 w-6" />
          </button>

          {/* Separator */}
          <div className="h-6 w-px bg-archeron-700 lg:hidden" />

          <div className="flex flex-1 gap-x-4 self-stretch lg:gap-x-6">
            <div className="flex flex-1 items-center">
              {/* Global search could go here */}
            </div>
            <div className="flex items-center gap-x-4 lg:gap-x-6">
              {/* Notifications */}
              <button
                type="button"
                className="relative p-2 text-archeron-400 hover:text-archeron-100 transition-colors"
              >
                <IconBell className="h-5 w-5" />
                <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-accent-500" />
              </button>

              {/* Separator */}
              <div className="hidden lg:block h-6 w-px bg-archeron-700" />

              {/* User menu */}
              <div className="flex items-center gap-3">
                <div className="hidden lg:block text-right">
                  <p className="text-sm font-medium text-archeron-200">Analyst</p>
                  <p className="text-xs text-archeron-500">v0.1.0</p>
                </div>
                <button
                  type="button"
                  className="p-2 rounded-full bg-archeron-800 text-archeron-400 hover:text-archeron-100 transition-colors"
                >
                  <IconPerson className="h-5 w-5" />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Page content */}
        <main className="py-8">
          <div className="px-4 sm:px-6 lg:px-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
