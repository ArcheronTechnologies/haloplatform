import axios from 'axios'
import type { Entity, Alert, Case, Transaction, SAR, User, DashboardStats, PaginatedResponse, SearchResult } from '@/types'

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add auth interceptor
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Add response interceptor for token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const response = await api.post('/auth/refresh', { refresh_token: refreshToken })
          localStorage.setItem('access_token', response.data.access_token)
          if (response.data.refresh_token) {
            localStorage.setItem('refresh_token', response.data.refresh_token)
          }
          originalRequest.headers.Authorization = `Bearer ${response.data.access_token}`
          return api(originalRequest)
        } catch (refreshError) {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
          return Promise.reject(refreshError)
        }
      }
    }
    return Promise.reject(error)
  }
)

// Entities
export const entitiesApi = {
  list: (params?: { page?: number; limit?: number; type?: string; risk_level?: string }) =>
    api.get<PaginatedResponse<Entity>>('/entities', { params }),

  get: (id: string) =>
    api.get<Entity>(`/entities/${id}`),

  getTransactions: (id: string, params?: { page?: number; limit?: number }) =>
    api.get<PaginatedResponse<Transaction>>(`/entities/${id}/transactions`, { params }),

  getRelationships: (id: string) =>
    api.get(`/entities/${id}/relationships`),

  getTimeline: (id: string) =>
    api.get(`/entities/${id}/timeline`),
}

// Alerts
export const alertsApi = {
  list: (params?: { page?: number; limit?: number; status?: string; risk_level?: string }) =>
    api.get<PaginatedResponse<Alert>>('/alerts', { params }),

  get: (id: string) =>
    api.get<Alert>(`/alerts/${id}`),

  acknowledge: (id: string) =>
    api.post(`/alerts/${id}/acknowledge`),

  resolve: (id: string, data: { outcome: string; notes?: string }) =>
    api.post(`/alerts/${id}/resolve`, data),

  dismiss: (id: string, data: { reason: string }) =>
    api.post(`/alerts/${id}/dismiss`, data),

  createCase: (id: string) =>
    api.post<Case>(`/alerts/${id}/create-case`),
}

// Cases
export const casesApi = {
  list: (params?: { page?: number; limit?: number; status?: string; priority?: string; case_type?: string }) =>
    api.get<PaginatedResponse<Case>>('/cases', { params }),

  get: (id: string) =>
    api.get<Case>(`/cases/${id}`),

  create: (data: Partial<Case>) =>
    api.post<Case>('/cases', data),

  update: (id: string, data: Partial<Case>) =>
    api.patch<Case>(`/cases/${id}`, data),

  updateStatus: (id: string, status: string, notes?: string) =>
    api.post(`/cases/${id}/status`, { status, notes }),

  assign: (id: string, userId: string) =>
    api.post(`/cases/${id}/assign`, { user_id: userId }),

  addNote: (id: string, content: string) =>
    api.post(`/cases/${id}/notes`, { content }),

  getTimeline: (id: string) =>
    api.get(`/cases/${id}/timeline`),

  getEvidence: (id: string) =>
    api.get(`/cases/${id}/evidence`),

  close: (id: string, data: { outcome: string; findings: string; recommendations?: string }) =>
    api.post(`/cases/${id}/close`, data),
}

// SARs
export const sarsApi = {
  list: (params?: { page?: number; limit?: number; status?: string }) =>
    api.get<PaginatedResponse<SAR>>('/sars', { params }),

  get: (id: string) =>
    api.get<SAR>(`/sars/${id}`),

  create: (data: Partial<SAR>) =>
    api.post<SAR>('/sars', data),

  update: (id: string, data: Partial<SAR>) =>
    api.patch<SAR>(`/sars/${id}`, data),

  approve: (id: string) =>
    api.post(`/sars/${id}/approve`),

  submit: (id: string) =>
    api.post(`/sars/${id}/submit`),
}

// Search
export const searchApi = {
  search: (params: { query: string; type?: string; limit?: number }) =>
    api.get<{ results: SearchResult[]; total: number }>('/search', {
      params: { q: params.query, type: params.type, limit: params.limit }
    }),

  advanced: (filters: Record<string, unknown>) =>
    api.post<{ results: SearchResult[]; total: number }>('/search/advanced', filters),
}

// Dashboard
export const dashboardApi = {
  getStats: () =>
    api.get<DashboardStats>('/dashboard/stats'),

  getRecentAlerts: (limit?: number) =>
    api.get<Alert[]>('/dashboard/recent-alerts', { params: { limit } }),

  getRecentCases: (limit?: number) =>
    api.get<Case[]>('/dashboard/recent-cases', { params: { limit } }),
}

// Audit
export const auditApi = {
  getLog: (params?: { page?: number; limit?: number; entity_id?: string; user_id?: string }) =>
    api.get('/audit', { params }),
}

// Users
export const usersApi = {
  list: (params?: { page?: number; limit?: number; role?: string; is_active?: boolean }) =>
    api.get<PaginatedResponse<User>>('/users', { params }),

  get: (id: string) =>
    api.get<User>(`/users/${id}`),

  create: (data: { username: string; email: string; full_name: string; password: string; role: string }) =>
    api.post<User>('/users', data),

  update: (id: string, data: { email?: string; full_name?: string; role?: string; is_active?: boolean }) =>
    api.patch<User>(`/users/${id}`, data),

  delete: (id: string) =>
    api.delete(`/users/${id}`),
}

// Documents
export const documentsApi = {
  list: (params?: { page?: number; limit?: number }) =>
    api.get<PaginatedResponse<any>>('/documents', { params }),

  get: (id: string) =>
    api.get(`/documents/${id}`),

  upload: (formData: FormData) =>
    api.post('/documents', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }),

  search: (params: { query: string; limit?: number }) =>
    api.get('/documents/search', { params }),
}

// Authentication
export const authApi = {
  // Password-based login
  login: (credentials: { username: string; password: string }) =>
    api.post('/auth/login', credentials),

  logout: () =>
    api.post('/auth/logout'),

  refreshToken: (data: { refresh_token: string }) =>
    api.post('/auth/refresh', data),

  getMe: () =>
    api.get('/auth/me'),

  // BankID
  bankidInit: () =>
    api.post('/auth/bankid/init'),

  bankidQR: (data: { order_ref: string }) =>
    api.post('/auth/bankid/qr', data),

  bankidCollect: (data: { order_ref: string }) =>
    api.post('/auth/bankid/collect', data),

  bankidCancel: (data: { order_ref: string }) =>
    api.post('/auth/bankid/cancel', data),

  // OIDC
  oidcInit: (data: { provider: string; redirect_uri?: string }) =>
    api.post('/auth/oidc/init', data),

  oidcCallback: (data: { code: string; state: string }) =>
    api.post('/auth/oidc/callback', data),

  getOIDCProviders: () =>
    api.get('/auth/oidc/providers'),
}

// Graph API
export const graphApi = {
  getEntity: (id: string, includeMetrics = false) =>
    api.get(`/graph/entities/${id}`, { params: { include_metrics: includeMetrics } }),

  getNeighbors: (id: string, hops = 1, edgeTypes?: string) =>
    api.get(`/graph/entities/${id}/neighbors`, { params: { hops, edge_types: edgeTypes } }),

  getNetwork: (id: string, hops = 2, maxNodes = 100) =>
    api.get(`/graph/entities/${id}/network`, { params: { hops, max_nodes: maxNodes } }),

  getCentrality: () =>
    api.get('/graph/metrics/centrality'),

  getComponents: () =>
    api.get('/graph/metrics/components'),

  getFull: (params?: { max_nodes?: number; min_shell_score?: number; mode?: string }) =>
    api.get('/graph/full', { params }),
}

// Intelligence API
export const intelligenceApi = {
  // Anomaly detection
  scoreAddress: (id: string) =>
    api.get(`/intelligence/anomaly/address/${id}`),

  scoreCompany: (id: string) =>
    api.get(`/intelligence/anomaly/company/${id}`),

  scorePerson: (id: string) =>
    api.get(`/intelligence/anomaly/person/${id}`),

  // Pattern detection
  listPatterns: (enabledOnly = true) =>
    api.get('/intelligence/patterns', { params: { enabled_only: enabledOnly } }),

  detectPatterns: (entityId: string, entityType: string, patternIds?: string) =>
    api.get(`/intelligence/patterns/detect/${entityId}`, {
      params: { entity_type: entityType, pattern_ids: patternIds }
    }),

  scanAllPatterns: (typology?: string, minSeverity?: string) =>
    api.post('/intelligence/patterns/scan', null, {
      params: { typology, min_severity: minSeverity }
    }),

  // Risk prediction
  predictRisk: (entityId: string) =>
    api.get(`/intelligence/predict/${entityId}`),

  predictRiskBatch: (entityIds: string[]) =>
    api.post('/intelligence/predict/batch', entityIds),

  explainPrediction: (entityId: string) =>
    api.get(`/intelligence/predict/${entityId}/explain`),

  // SAR generation
  generateSAR: (data: { entity_id: string; trigger_reason: string; alert_ids?: string[]; notes?: string }) =>
    api.post('/intelligence/sar/generate', data),

  // Konkurs prediction
  predictKonkurs: (companyId: string, horizonMonths = 12) =>
    api.get(`/intelligence/konkurs/${companyId}`, { params: { horizon_months: horizonMonths } }),

  analyzeContagion: (companyId: string) =>
    api.get(`/intelligence/konkurs/${companyId}/contagion`),

  // Evasion detection
  detectEvasion: (entityId: string) =>
    api.get(`/intelligence/evasion/${entityId}`),

  // Playbook detection
  listPlaybooks: () =>
    api.get('/intelligence/playbooks'),

  detectPlaybooks: (entityId: string) =>
    api.get(`/intelligence/playbooks/detect/${entityId}`),

  // Network risk
  analyzeNetworkRisk: (entityId: string, hops = 2) =>
    api.get(`/intelligence/network-risk/${entityId}`, { params: { hops } }),
}

export default api
