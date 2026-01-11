import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { IconPerson, IconPlus } from '@/components/icons'
import { LoadingSpinner, PageHeader, EmptyState, Pagination } from '@/components/ui'
import { usersApi } from '@/services/api'

export default function Users() {
  const [page, setPage] = useState(1)
  const [showCreateModal, setShowCreateModal] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['users', page],
    queryFn: () =>
      usersApi
        .list({ page, limit: 20 })
        .then((r) => r.data),
  })

  return (
    <div>
      <PageHeader
        title="User Management"
        actions={
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn btn-primary"
          >
            <IconPlus className="h-4 w-4 mr-2" />
            Create User
          </button>
        }
      />

      <div className="card overflow-hidden">
        {isLoading ? (
          <LoadingSpinner />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-4 text-left">User</th>
                  <th className="px-6 py-4 text-left">Email</th>
                  <th className="px-6 py-4 text-left">Role</th>
                  <th className="px-6 py-4 text-left">Status</th>
                  <th className="px-6 py-4 text-left">Last Login</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.items?.map((user: any) => (
                  <tr key={user.id} className="table-row">
                    <td className="table-cell">
                      <div className="flex items-center gap-3">
                        <IconPerson className="h-5 w-5 text-archeron-500" />
                        <div>
                          <div className="text-sm font-medium text-archeron-100">
                            {user.full_name}
                          </div>
                          <div className="text-xs text-archeron-500">
                            {user.username}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="table-cell text-archeron-400">
                      {user.email}
                    </td>
                    <td className="table-cell">
                      <span className="badge badge-neutral capitalize">
                        {user.role}
                      </span>
                    </td>
                    <td className="table-cell">
                      <span
                        className={`badge ${
                          user.is_active ? 'badge-low' : 'badge-medium'
                        }`}
                      >
                        {user.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="table-cell text-archeron-400 text-sm">
                      {user.last_login
                        ? new Date(user.last_login).toLocaleDateString()
                        : 'Never'}
                    </td>
                    <td className="table-cell text-right">
                      <button className="btn btn-ghost text-xs py-1.5 px-3">
                        Edit
                      </button>
                    </td>
                  </tr>
                ))}
                {data?.items?.length === 0 && (
                  <tr>
                    <td colSpan={6}>
                      <EmptyState message="No users found" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        <Pagination
          page={page}
          totalItems={data?.total ?? 0}
          onPageChange={setPage}
          itemLabel="users"
        />
      </div>

      {showCreateModal && (
        <CreateUserModal onClose={() => setShowCreateModal(false)} />
      )}
    </div>
  )
}

function CreateUserModal({ onClose }: { onClose: () => void }) {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('viewer')
  const queryClient = useQueryClient()

  const createMutation = useMutation({
    mutationFn: () =>
      usersApi.create({
        username,
        email,
        full_name: fullName,
        password,
        role,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-archeron-900 border border-archeron-700 rounded-lg p-6 max-w-md w-full">
        <h2 className="text-lg font-semibold text-archeron-100 mb-4">
          Create User
        </h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-archeron-300 mb-1">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="input w-full"
              placeholder="username"
            />
          </div>

          <div>
            <label className="block text-sm text-archeron-300 mb-1">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input w-full"
              placeholder="user@example.com"
            />
          </div>

          <div>
            <label className="block text-sm text-archeron-300 mb-1">
              Full Name
            </label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="input w-full"
              placeholder="John Doe"
            />
          </div>

          <div>
            <label className="block text-sm text-archeron-300 mb-1">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input w-full"
              placeholder="••••••••"
            />
          </div>

          <div>
            <label className="block text-sm text-archeron-300 mb-1">
              Role
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="input w-full"
            >
              <option value="viewer">Viewer</option>
              <option value="analyst">Analyst</option>
              <option value="senior_analyst">Senior Analyst</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button
            onClick={onClose}
            className="btn btn-secondary flex-1"
            disabled={createMutation.isPending}
          >
            Cancel
          </button>
          <button
            onClick={() => createMutation.mutate()}
            className="btn btn-primary flex-1"
            disabled={createMutation.isPending || !username || !email || !password}
          >
            {createMutation.isPending ? 'Creating...' : 'Create User'}
          </button>
        </div>
      </div>
    </div>
  )
}
