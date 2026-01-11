import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi } from '@/services/api'

interface User {
  id: string
  username: string
  email?: string
  name?: string
  role: string
  personnummer?: string
}

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (credentials: { username: string; password: string }) => Promise<void>
  logout: () => Promise<void>
  refreshToken: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()

  // Get stored token
  const getStoredToken = () => localStorage.getItem('access_token')
  const getRefreshToken = () => localStorage.getItem('refresh_token')

  // Check if we have a token
  const [hasToken, setHasToken] = useState(!!getStoredToken())

  // Fetch current user
  const { data: user, isLoading, error } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: () => authApi.getMe().then(r => r.data),
    enabled: hasToken,
    retry: false,
    staleTime: 5 * 60 * 1000, // 5 minutes
  })

  // Handle auth error (token invalid/expired)
  useEffect(() => {
    if (error && hasToken) {
      // Try to refresh token
      const refreshToken = getRefreshToken()
      if (refreshToken) {
        authApi.refreshToken({ refresh_token: refreshToken })
          .then(response => {
            localStorage.setItem('access_token', response.data.access_token)
            if (response.data.refresh_token) {
              localStorage.setItem('refresh_token', response.data.refresh_token)
            }
            queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
          })
          .catch(() => {
            // Refresh failed, clear tokens and redirect to login
            localStorage.removeItem('access_token')
            localStorage.removeItem('refresh_token')
            setHasToken(false)
            navigate('/login', { state: { from: location } })
          })
      } else {
        // No refresh token, redirect to login
        localStorage.removeItem('access_token')
        setHasToken(false)
        navigate('/login', { state: { from: location } })
      }
    }
  }, [error, hasToken, navigate, location, queryClient])

  // Login mutation
  const loginMutation = useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      authApi.login(credentials),
    onSuccess: (response) => {
      localStorage.setItem('access_token', response.data.access_token)
      if (response.data.refresh_token) {
        localStorage.setItem('refresh_token', response.data.refresh_token)
      }
      setHasToken(true)
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
    },
  })

  // Logout mutation
  const logoutMutation = useMutation({
    mutationFn: () => authApi.logout(),
    onSettled: () => {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      setHasToken(false)
      queryClient.clear()
      navigate('/login')
    },
  })

  const login = async (credentials: { username: string; password: string }) => {
    await loginMutation.mutateAsync(credentials)
  }

  const logout = async () => {
    await logoutMutation.mutateAsync()
  }

  const refreshToken = async () => {
    const token = getRefreshToken()
    if (!token) {
      throw new Error('No refresh token')
    }
    const response = await authApi.refreshToken({ refresh_token: token })
    localStorage.setItem('access_token', response.data.access_token)
    if (response.data.refresh_token) {
      localStorage.setItem('refresh_token', response.data.refresh_token)
    }
    queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
  }

  const value: AuthContextType = {
    user: user || null,
    isLoading,
    isAuthenticated: !!user,
    login,
    logout,
    refreshToken,
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

// Route guard component
interface RequireAuthProps {
  children: ReactNode
  roles?: string[]
}

export function RequireAuth({ children, roles }: RequireAuthProps) {
  const { user, isLoading, isAuthenticated } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate('/login', { state: { from: location }, replace: true })
    }
  }, [isLoading, isAuthenticated, navigate, location])

  // Check role authorization
  useEffect(() => {
    if (user && roles && !roles.includes(user.role)) {
      navigate('/unauthorized', { replace: true })
    }
  }, [user, roles, navigate])

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-archeron-950">
        <div className="spinner h-8 w-8" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null // Will redirect in useEffect
  }

  if (roles && user && !roles.includes(user.role)) {
    return null // Will redirect in useEffect
  }

  return <>{children}</>
}
