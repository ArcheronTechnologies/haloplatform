// Entity types
export interface Entity {
  id: string
  entity_type: 'person' | 'company' | 'property' | 'vehicle'
  name: string
  identifier: string
  risk_level: RiskLevel
  risk_score: number
  status: string
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export type RiskLevel = 'low' | 'medium' | 'high' | 'very_high' | 'prohibited'

// Alert types
export interface Alert {
  id: string
  alert_type: string
  pattern_type: string
  severity: AlertSeverity
  confidence: number
  title: string
  description: string
  status: AlertStatus
  tier: 1 | 2 | 3  // Brottsdatalagen compliance tier
  affects_person: boolean
  entity_id?: string  // Primary entity (for backwards compat)
  entity_ids: string[]
  transaction_ids: string[]
  risk_level?: RiskLevel  // Derived from severity
  created_at: string
  reviewed_at?: string
  reviewed_by?: string
  review_duration_seconds?: number
  justification?: string
  is_rubber_stamp?: boolean
}

export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical'
export type AlertStatus = 'new' | 'open' | 'acknowledged' | 'investigating' | 'resolved' | 'dismissed'

// Case types
export interface Case {
  id: string
  case_number: string
  title: string
  description: string
  case_type: CaseType
  status: CaseStatus
  priority: CasePriority
  subjects: CaseSubject[]
  alert_ids: string[]
  sar_ids: string[]
  assigned_to?: string
  created_at: string
  updated_at?: string
  opened_at?: string
  closed_at?: string
  due_date?: string
  entities?: CaseSubject[]  // Alias for subjects
  alerts?: Alert[]  // Linked alerts (when expanded)
  notes?: CaseNote[]  // Case notes
}

export interface CaseNote {
  id: string
  content: string
  author: string
  created_at: string
}

export type CaseType = 'aml' | 'fraud' | 'sanctions' | 'pep' | 'ctf' | 'tax_evasion' | 'other'
export type CaseStatus = 'draft' | 'open' | 'closed' | 'in_progress' | 'pending_review' | 'escalated' | 'on_hold' | 'closed_confirmed' | 'closed_cleared' | 'closed_inconclusive'
export type CasePriority = 'low' | 'medium' | 'high' | 'critical'

export interface CaseSubject {
  entity_id: string
  entity_type: string
  name: string
  identifier: string
  role: string
  risk_level?: string
  risk_score?: number
}

// Transaction types
export interface Transaction {
  id: string
  amount: number
  currency: string
  timestamp: string
  transaction_type: string
  from_entity_id?: string
  from_entity_name?: string
  to_entity_id?: string
  to_entity_name?: string
  description?: string
  risk_score?: number
}

// SAR types
export interface SAR {
  id: string
  sar_type: 'str' | 'ctr' | 'sar' | 'tfar'
  status: SARStatus
  priority: 'low' | 'medium' | 'high' | 'urgent'
  summary: string
  total_amount?: number
  currency: string
  created_at: string
  submitted_at?: string
  external_reference?: string
}

export type SARStatus = 'draft' | 'pending_review' | 'approved' | 'submitted' | 'acknowledged' | 'rejected'

// Dashboard stats
export interface DashboardStats {
  alerts: {
    total: number
    by_severity: Record<AlertSeverity, number>
    new_today: number
  }
  cases: {
    total: number
    open: number
    by_priority: Record<CasePriority, number>
  }
  entities: {
    total: number
    high_risk: number
    new_this_week: number
  }
  sars: {
    draft: number
    pending: number
    submitted_this_month: number
  }
}

// API response types
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface SearchResult {
  entity_type: string
  type: 'alert' | 'entity' | 'case' | 'transaction'
  id: string
  name: string
  title: string  // Alias for name
  identifier: string
  subtitle?: string  // Secondary display text
  score: number
  highlights: Record<string, string[]>
  metadata?: Record<string, unknown>
}

// User types
export interface User {
  id: string
  username: string
  email: string
  full_name: string
  role: 'viewer' | 'analyst' | 'senior_analyst' | 'admin'
  is_active: boolean
  last_login?: string
  created_at: string
}
