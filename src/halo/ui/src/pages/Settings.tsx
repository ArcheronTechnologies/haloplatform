import { useState } from 'react'
import {
  IconSettings,
  IconShieldCheck,
  IconBell,
  IconDatabase,
  IconPeople,
  IconLock,
  IconGlobe,
  IconCheckCircle,
  IconAlertTriangle,
} from '@/components/icons'
import clsx from 'clsx'

type SettingsTab = 'general' | 'security' | 'notifications' | 'integrations' | 'team'

export default function Settings() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('general')

  const tabs = [
    { id: 'general', label: 'General', icon: IconSettings },
    { id: 'security', label: 'Security', icon: IconShieldCheck },
    { id: 'notifications', label: 'Notifications', icon: IconBell },
    { id: 'integrations', label: 'Integrations', icon: IconDatabase },
    { id: 'team', label: 'Team', icon: IconPeople },
  ] as const

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="page-title">Settings</h1>
        <p className="page-subtitle">
          Manage your Halo configuration and preferences
        </p>
      </div>

      <div className="flex gap-6">
        {/* Sidebar */}
        <nav className="w-48 flex-shrink-0">
          <ul className="space-y-1">
            {tabs.map((tab) => (
              <li key={tab.id}>
                <button
                  onClick={() => setActiveTab(tab.id)}
                  className={clsx(
                    'w-full flex items-center gap-3 px-3 py-2.5 text-sm font-medium rounded-lg transition-colors',
                    activeTab === tab.id
                      ? 'bg-archeron-800 text-archeron-50 border-l-2 border-accent-500 ml-[-2px]'
                      : 'text-archeron-400 hover:bg-archeron-800/50 hover:text-archeron-200'
                  )}
                >
                  <tab.icon className="h-5 w-5" />
                  {tab.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        {/* Content */}
        <div className="flex-1">
          {activeTab === 'general' && <GeneralSettings />}
          {activeTab === 'security' && <SecuritySettings />}
          {activeTab === 'notifications' && <NotificationSettings />}
          {activeTab === 'integrations' && <IntegrationSettings />}
          {activeTab === 'team' && <TeamSettings />}
        </div>
      </div>
    </div>
  )
}

function GeneralSettings() {
  const [language, setLanguage] = useState('sv')
  const [timezone, setTimezone] = useState('Europe/Stockholm')
  const [dateFormat, setDateFormat] = useState('YYYY-MM-DD')

  return (
    <div className="space-y-6">
      <div className="card">
        <div className="p-5 border-b border-archeron-800">
          <h2 className="section-title">Regional Settings</h2>
        </div>
        <div className="p-5 space-y-5">
          <div>
            <label className="block text-sm font-medium text-archeron-300 mb-2">
              Language
            </label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="input w-full max-w-xs"
            >
              <option value="sv">Svenska</option>
              <option value="en">English</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-archeron-300 mb-2">
              Timezone
            </label>
            <select
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              className="input w-full max-w-xs"
            >
              <option value="Europe/Stockholm">Europe/Stockholm (CET)</option>
              <option value="UTC">UTC</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-archeron-300 mb-2">
              Date Format
            </label>
            <select
              value={dateFormat}
              onChange={(e) => setDateFormat(e.target.value)}
              className="input w-full max-w-xs"
            >
              <option value="YYYY-MM-DD">2025-01-15 (ISO)</option>
              <option value="DD/MM/YYYY">15/01/2025</option>
              <option value="MM/DD/YYYY">01/15/2025</option>
            </select>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="p-5 border-b border-archeron-800">
          <h2 className="section-title">Risk Thresholds</h2>
        </div>
        <div className="p-5 space-y-5">
          <div>
            <label className="block text-sm font-medium text-archeron-300 mb-2">
              Tier 3 Threshold (Approval Required)
            </label>
            <input
              type="number"
              defaultValue={0.85}
              step={0.05}
              min={0}
              max={1}
              className="input w-32"
            />
            <p className="text-xs text-archeron-500 mt-1.5">
              Alerts above this confidence require manual approval
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-archeron-300 mb-2">
              Tier 2 Threshold (Acknowledgment Required)
            </label>
            <input
              type="number"
              defaultValue={0.5}
              step={0.05}
              min={0}
              max={1}
              className="input w-32"
            />
            <p className="text-xs text-archeron-500 mt-1.5">
              Alerts above this confidence require acknowledgment
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-archeron-300 mb-2">
              Minimum Review Time (seconds)
            </label>
            <input
              type="number"
              defaultValue={2}
              step={0.5}
              min={0}
              className="input w-32"
            />
            <p className="text-xs text-archeron-500 mt-1.5">
              Flag reviews faster than this as potential rubber-stamps
            </p>
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <button className="btn btn-primary">Save Changes</button>
      </div>
    </div>
  )
}

function SecuritySettings() {
  return (
    <div className="space-y-6">
      <div className="card">
        <div className="p-5 border-b border-archeron-800">
          <h2 className="section-title">Authentication</h2>
        </div>
        <div className="p-5 space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-archeron-200">
                Two-Factor Authentication
              </p>
              <p className="text-xs text-archeron-500 mt-0.5">
                Require 2FA for all user logins
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" className="sr-only peer" defaultChecked />
              <div className="w-11 h-6 bg-archeron-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-archeron-400 after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-600 peer-checked:after:bg-white"></div>
            </label>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-archeron-200">
                Session Timeout
              </p>
              <p className="text-xs text-archeron-500 mt-0.5">
                Automatically log out inactive users
              </p>
            </div>
            <select className="input py-2 w-36">
              <option value="15">15 minutes</option>
              <option value="30">30 minutes</option>
              <option value="60">1 hour</option>
              <option value="120">2 hours</option>
            </select>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="p-5 border-b border-archeron-800">
          <h2 className="section-title">API Keys</h2>
        </div>
        <div className="p-5">
          <div className="flex items-center justify-between mb-5">
            <p className="text-sm text-archeron-400">
              Manage API keys for external integrations
            </p>
            <button className="btn btn-secondary text-sm">
              <IconLock className="h-4 w-4 mr-2" />
              Generate New Key
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="table-header">
                <tr>
                  <th className="px-4 py-3 text-left">Name</th>
                  <th className="px-4 py-3 text-left">Created</th>
                  <th className="px-4 py-3 text-left">Last Used</th>
                  <th className="px-4 py-3 text-right"></th>
                </tr>
              </thead>
              <tbody>
                <tr className="table-row">
                  <td className="table-cell text-archeron-200">Production API</td>
                  <td className="table-cell">2025-01-10</td>
                  <td className="table-cell">2 hours ago</td>
                  <td className="table-cell text-right">
                    <button className="text-red-400 hover:text-red-300 text-xs transition-colors">
                      Revoke
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="p-5 border-b border-archeron-800">
          <h2 className="section-title">Audit Log</h2>
        </div>
        <div className="p-5">
          <p className="text-sm text-archeron-400 mb-4">
            All actions are logged for compliance and security auditing.
          </p>
          <button className="btn btn-secondary text-sm">
            Download Audit Log
          </button>
        </div>
      </div>
    </div>
  )
}

function NotificationSettings() {
  return (
    <div className="space-y-6">
      <div className="card">
        <div className="p-5 border-b border-archeron-800">
          <h2 className="section-title">Alert Notifications</h2>
        </div>
        <div className="p-5 space-y-4">
          {['Critical', 'High', 'Medium', 'Low'].map((level) => (
            <div key={level} className="flex items-center justify-between py-2">
              <div className="flex items-center gap-3">
                <span
                  className={clsx(
                    'badge',
                    level === 'Critical' && 'badge-critical',
                    level === 'High' && 'badge-high',
                    level === 'Medium' && 'badge-medium',
                    level === 'Low' && 'badge-low'
                  )}
                >
                  {level}
                </span>
                <span className="text-sm text-archeron-300">
                  {level} risk alerts
                </span>
              </div>
              <div className="flex items-center gap-6">
                <label className="flex items-center gap-2 text-sm text-archeron-400">
                  <input
                    type="checkbox"
                    className="rounded bg-archeron-800 border-archeron-600 text-accent-600 focus:ring-accent-500"
                    defaultChecked={level === 'Critical' || level === 'High'}
                  />
                  Email
                </label>
                <label className="flex items-center gap-2 text-sm text-archeron-400">
                  <input
                    type="checkbox"
                    className="rounded bg-archeron-800 border-archeron-600 text-accent-600 focus:ring-accent-500"
                    defaultChecked={level === 'Critical'}
                  />
                  SMS
                </label>
                <label className="flex items-center gap-2 text-sm text-archeron-400">
                  <input
                    type="checkbox"
                    className="rounded bg-archeron-800 border-archeron-600 text-accent-600 focus:ring-accent-500"
                    defaultChecked
                  />
                  In-app
                </label>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="p-5 border-b border-archeron-800">
          <h2 className="section-title">Report Schedule</h2>
        </div>
        <div className="p-5 space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-archeron-200">Daily Summary</p>
              <p className="text-xs text-archeron-500 mt-0.5">
                Receive a daily summary of alerts and cases
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" className="sr-only peer" defaultChecked />
              <div className="w-11 h-6 bg-archeron-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-archeron-400 after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-600 peer-checked:after:bg-white"></div>
            </label>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-archeron-200">
                Weekly Compliance Report
              </p>
              <p className="text-xs text-archeron-500 mt-0.5">
                Detailed compliance metrics every Monday
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" className="sr-only peer" defaultChecked />
              <div className="w-11 h-6 bg-archeron-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-archeron-400 after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-600 peer-checked:after:bg-white"></div>
            </label>
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <button className="btn btn-primary">Save Changes</button>
      </div>
    </div>
  )
}

function IntegrationSettings() {
  const integrations = [
    {
      name: 'Bolagsverket',
      description: 'Swedish Companies Registration Office API',
      status: 'pending',
      icon: IconDatabase,
    },
    {
      name: 'SCB Företagsregistret',
      description: 'Statistics Sweden company register',
      status: 'connected',
      icon: IconDatabase,
    },
    {
      name: 'Lantmäteriet',
      description: 'Swedish mapping and cadastral authority',
      status: 'disconnected',
      icon: IconGlobe,
    },
    {
      name: 'Finanspolisen',
      description: 'Swedish Financial Intelligence Unit (SAR submission)',
      status: 'connected',
      icon: IconShieldCheck,
    },
  ]

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'connected':
        return (
          <span className="flex items-center gap-1 text-xs text-green-400 bg-green-500/20 px-2 py-0.5 rounded-full ring-1 ring-green-500/30">
            <IconCheckCircle className="h-3 w-3" />
            Connected
          </span>
        )
      case 'pending':
        return (
          <span className="flex items-center gap-1 text-xs text-yellow-400 bg-yellow-500/20 px-2 py-0.5 rounded-full ring-1 ring-yellow-500/30">
            <IconAlertTriangle className="h-3 w-3" />
            Pending
          </span>
        )
      default:
        return (
          <span className="text-xs text-archeron-500 bg-archeron-800 px-2 py-0.5 rounded-full ring-1 ring-archeron-700">
            Disconnected
          </span>
        )
    }
  }

  return (
    <div className="space-y-6">
      <div className="card">
        <div className="p-5 border-b border-archeron-800">
          <h2 className="section-title">Data Source Integrations</h2>
        </div>
        <ul className="divide-y divide-archeron-800">
          {integrations.map((integration) => (
            <li
              key={integration.name}
              className="p-5 flex items-center justify-between"
            >
              <div className="flex items-center gap-4">
                <div className="h-10 w-10 rounded-lg bg-archeron-800 flex items-center justify-center">
                  <integration.icon className="h-5 w-5 text-archeron-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-archeron-200">
                    {integration.name}
                  </p>
                  <p className="text-xs text-archeron-500 mt-0.5">
                    {integration.description}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {getStatusBadge(integration.status)}
                <button className="btn btn-ghost text-xs py-1.5 px-3">
                  Configure
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <div className="p-5 border-b border-archeron-800">
          <h2 className="section-title">Webhooks</h2>
        </div>
        <div className="p-5">
          <p className="text-sm text-archeron-400 mb-4">
            Configure webhooks to receive real-time notifications in external
            systems.
          </p>
          <button className="btn btn-secondary text-sm">Add Webhook</button>
        </div>
      </div>
    </div>
  )
}

function TeamSettings() {
  const teamMembers = [
    {
      name: 'Anna Andersson',
      email: 'anna@example.com',
      role: 'Admin',
      status: 'active',
    },
    {
      name: 'Erik Eriksson',
      email: 'erik@example.com',
      role: 'Analyst',
      status: 'active',
    },
    {
      name: 'Maria Larsson',
      email: 'maria@example.com',
      role: 'Reviewer',
      status: 'active',
    },
  ]

  return (
    <div className="space-y-6">
      <div className="card">
        <div className="p-5 border-b border-archeron-800 flex items-center justify-between">
          <h2 className="section-title">Team Members</h2>
          <button className="btn btn-primary text-sm">
            <IconPeople className="h-4 w-4 mr-2" />
            Invite Member
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="table-header">
              <tr>
                <th className="px-5 py-4 text-left">Name</th>
                <th className="px-5 py-4 text-left">Role</th>
                <th className="px-5 py-4 text-left">Status</th>
                <th className="px-5 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {teamMembers.map((member) => (
                <tr key={member.email} className="table-row">
                  <td className="table-cell">
                    <div>
                      <p className="text-sm font-medium text-archeron-200">
                        {member.name}
                      </p>
                      <p className="text-xs text-archeron-500">{member.email}</p>
                    </div>
                  </td>
                  <td className="table-cell">
                    <select
                      defaultValue={member.role}
                      className="input py-1.5 text-sm w-28"
                    >
                      <option value="Admin">Admin</option>
                      <option value="Analyst">Analyst</option>
                      <option value="Reviewer">Reviewer</option>
                      <option value="Viewer">Viewer</option>
                    </select>
                  </td>
                  <td className="table-cell">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/20 text-green-400 ring-1 ring-green-500/30">
                      Active
                    </span>
                  </td>
                  <td className="table-cell text-right">
                    <button className="text-red-400 hover:text-red-300 text-sm transition-colors">
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="p-5 border-b border-archeron-800">
          <h2 className="section-title">Roles</h2>
        </div>
        <div className="p-5">
          <ul className="space-y-3 text-sm">
            <li>
              <span className="font-medium text-archeron-200">Admin</span>
              <span className="text-archeron-500">
                {' '}
                - Full system access, user management, settings
              </span>
            </li>
            <li>
              <span className="font-medium text-archeron-200">Analyst</span>
              <span className="text-archeron-500">
                {' '}
                - Create/manage cases, review alerts, generate SARs
              </span>
            </li>
            <li>
              <span className="font-medium text-archeron-200">Reviewer</span>
              <span className="text-archeron-500">
                {' '}
                - Review and approve cases, read-only analytics
              </span>
            </li>
            <li>
              <span className="font-medium text-archeron-200">Viewer</span>
              <span className="text-archeron-500">
                {' '}
                - Read-only access to dashboards and reports
              </span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  )
}
