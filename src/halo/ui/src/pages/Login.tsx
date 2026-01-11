import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  IconShieldCheck,
  IconSmartphone,
  IconBuilding,
  IconLoader,
  IconQrCode,
  IconAlertCircle,
  IconCheckCircle,
  IconPlay,
} from '@/components/icons'
import { authApi } from '@/services/api'
import clsx from 'clsx'

type AuthMethod = 'bankid' | 'oidc' | 'demo'

interface BankIDStatus {
  status: 'pending' | 'complete' | 'failed' | 'userSign' | 'started'
  hint_code?: string
  access_token?: string
  refresh_token?: string
  user?: {
    personnummer: string
    name: string
  }
}

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/'

  const [authMethod, setAuthMethod] = useState<AuthMethod>('demo')
  const [error, setError] = useState<string | null>(null)

  // BankID state
  const [bankIdOrderRef, setBankIdOrderRef] = useState<string | null>(null)
  const [qrData, setQrData] = useState<string | null>(null)
  const [autoStartUrl, setAutoStartUrl] = useState<string | null>(null)
  const [bankIdStatus, setBankIdStatus] = useState<BankIDStatus | null>(null)

  // Get available OIDC providers
  const { data: oidcProviders } = useQuery({
    queryKey: ['auth', 'oidc-providers'],
    queryFn: () => authApi.getOIDCProviders().then(r => r.data),
    staleTime: 5 * 60 * 1000, // 5 minutes
  })

  // BankID init mutation
  const bankIdInitMutation = useMutation({
    mutationFn: () => authApi.bankidInit(),
    onSuccess: (response) => {
      setBankIdOrderRef(response.data.order_ref)
      setAutoStartUrl(response.data.auto_start_url)
    },
    onError: (err: Error & { response?: { data?: { message?: string } } }) => {
      setError(err.response?.data?.message || 'Kunde inte starta BankID')
    },
  })

  // BankID QR polling
  const { data: qrResponse } = useQuery({
    queryKey: ['bankid', 'qr', bankIdOrderRef],
    queryFn: () => authApi.bankidQR({ order_ref: bankIdOrderRef! }),
    enabled: !!bankIdOrderRef && authMethod === 'bankid',
    refetchInterval: 1000, // Refresh QR every second
  })

  useEffect(() => {
    if (qrResponse?.data?.qr_data) {
      setQrData(qrResponse.data.qr_data)
    }
  }, [qrResponse])

  // BankID status polling
  const { data: statusResponse } = useQuery({
    queryKey: ['bankid', 'status', bankIdOrderRef],
    queryFn: () => authApi.bankidCollect({ order_ref: bankIdOrderRef! }),
    enabled: !!bankIdOrderRef && authMethod === 'bankid',
    refetchInterval: 2000, // Poll every 2 seconds
  })

  // Handle status response changes
  useEffect(() => {
    if (statusResponse?.data) {
      const data = statusResponse.data as BankIDStatus
      setBankIdStatus(data)
      if (data.status === 'complete' && data.access_token) {
        // Store tokens and redirect
        localStorage.setItem('access_token', data.access_token)
        if (data.refresh_token) {
          localStorage.setItem('refresh_token', data.refresh_token)
        }
        navigate(from, { replace: true })
      } else if (data.status === 'failed') {
        setError(getHintMessage(data.hint_code))
        setBankIdOrderRef(null)
      }
    }
  }, [statusResponse, from, navigate])

  // OIDC init mutation
  const oidcInitMutation = useMutation({
    mutationFn: (provider: string) => authApi.oidcInit({ provider }),
    onSuccess: (response) => {
      // Redirect to OIDC provider
      window.location.href = response.data.authorization_url
    },
    onError: (err: Error & { response?: { data?: { message?: string } } }) => {
      setError(err.response?.data?.message || 'Kunde inte starta OIDC-inloggning')
    },
  })

  const handleBankIdStart = () => {
    setError(null)
    bankIdInitMutation.mutate()
  }

  const handleBankIdCancel = () => {
    if (bankIdOrderRef) {
      authApi.bankidCancel({ order_ref: bankIdOrderRef })
    }
    setBankIdOrderRef(null)
    setQrData(null)
    setBankIdStatus(null)
  }

  const handleOIDCLogin = (provider: string) => {
    setError(null)
    oidcInitMutation.mutate(provider)
  }

  const handleDemoLogin = async () => {
    setError(null)
    try {
      const response = await authApi.login({ username: 'demo', password: 'demo' })
      localStorage.setItem('access_token', response.data.access_token)
      if (response.data.refresh_token) {
        localStorage.setItem('refresh_token', response.data.refresh_token)
      }
      // Force full page reload to pick up new auth state
      window.location.href = from
    } catch {
      setError('Demo login failed')
    }
  }

  const getHintMessage = (hintCode?: string): string => {
    const hints: Record<string, string> = {
      outstandingTransaction: 'En annan BankID-session pågår redan',
      noClient: 'BankID-appen svarar inte',
      userCancel: 'Inloggningen avbröts',
      cancelled: 'Inloggningen avbröts',
      startFailed: 'Kunde inte starta BankID-appen',
      expiredTransaction: 'BankID-sessionen har gått ut',
    }
    return hints[hintCode || ''] || 'Ett fel uppstod'
  }

  const getStatusMessage = (status: BankIDStatus): string => {
    switch (status.status) {
      case 'pending':
        if (status.hint_code === 'outstandingTransaction') {
          return 'En annan BankID-session pågår...'
        }
        return 'Öppna BankID-appen på din telefon'
      case 'userSign':
        return 'Skriv in din säkerhetskod i BankID-appen'
      case 'started':
        return 'Letar efter BankID...'
      case 'complete':
        return 'Inloggning lyckades!'
      default:
        return 'Väntar...'
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-archeron-950 p-4">
      <div className="w-full max-w-md">
        {/* Logo and Title */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-xl bg-accent-600/20 mb-4">
            <IconShieldCheck className="w-8 h-8 text-accent-400" />
          </div>
          <h1 className="text-2xl font-bold text-white">Halo</h1>
          <p className="text-archeron-400 mt-2">
            Swedish-Sovereign Intelligence Platform
          </p>
        </div>

        {/* Auth Method Tabs */}
        <div className="flex border-b border-archeron-800 mb-6">
          <button
            onClick={() => setAuthMethod('demo')}
            className={clsx(
              'flex-1 py-3 px-4 text-sm font-medium border-b-2 transition-colors',
              authMethod === 'demo'
                ? 'border-accent-500 text-accent-400'
                : 'border-transparent text-archeron-400 hover:text-white'
            )}
          >
            <IconPlay className="w-4 h-4 inline-block mr-2" />
            Demo
          </button>
          <button
            onClick={() => setAuthMethod('bankid')}
            className={clsx(
              'flex-1 py-3 px-4 text-sm font-medium border-b-2 transition-colors',
              authMethod === 'bankid'
                ? 'border-accent-500 text-accent-400'
                : 'border-transparent text-archeron-400 hover:text-white'
            )}
          >
            <IconSmartphone className="w-4 h-4 inline-block mr-2" />
            BankID
          </button>
          <button
            onClick={() => setAuthMethod('oidc')}
            className={clsx(
              'flex-1 py-3 px-4 text-sm font-medium border-b-2 transition-colors',
              authMethod === 'oidc'
                ? 'border-accent-500 text-accent-400'
                : 'border-transparent text-archeron-400 hover:text-white'
            )}
          >
            <IconBuilding className="w-4 h-4 inline-block mr-2" />
            Organisation
          </button>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center gap-2 text-red-400 text-sm">
            <IconAlertCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Demo Auth */}
        {authMethod === 'demo' && (
          <div className="card p-6 space-y-6">
            <div className="text-center">
              <h2 className="text-lg font-medium text-white mb-2">
                Demo Mode
              </h2>
              <p className="text-archeron-400 text-sm">
                Access the platform with real Swedish company data
              </p>
            </div>
            <div className="bg-accent-500/10 border border-accent-500/20 rounded-lg p-4">
              <p className="text-sm text-accent-300">
                This demo includes <strong>1,112 real companies</strong> extracted from Bolagsverket with directors, pattern detection, and network analysis.
              </p>
            </div>
            <button
              onClick={handleDemoLogin}
              className="btn-primary w-full py-3 flex items-center justify-center gap-2"
            >
              <IconPlay className="w-5 h-5" />
              Enter Demo
            </button>
          </div>
        )}

        {/* BankID Auth */}
        {authMethod === 'bankid' && (
          <div className="card p-6 space-y-6">
            {!bankIdOrderRef ? (
              <>
                <div className="text-center">
                  <h2 className="text-lg font-medium text-white mb-2">
                    Logga in med BankID
                  </h2>
                  <p className="text-archeron-400 text-sm">
                    Använd BankID-appen på din telefon för att logga in
                  </p>
                </div>
                <button
                  onClick={handleBankIdStart}
                  disabled={bankIdInitMutation.isPending}
                  className="btn-primary w-full py-3 flex items-center justify-center gap-2"
                >
                  {bankIdInitMutation.isPending ? (
                    <IconLoader className="w-5 h-5 animate-spin" />
                  ) : (
                    <IconSmartphone className="w-5 h-5" />
                  )}
                  Starta BankID
                </button>
              </>
            ) : (
              <div className="space-y-6">
                {/* QR Code */}
                {qrData && (
                  <div className="flex justify-center">
                    <div className="bg-white p-4 rounded-lg">
                      <IconQrCode className="w-48 h-48 text-archeron-900" />
                      {/* In production, render actual QR code from qrData */}
                    </div>
                  </div>
                )}

                {/* Status */}
                <div className="text-center">
                  {bankIdStatus?.status === 'complete' ? (
                    <div className="flex items-center justify-center gap-2 text-green-400">
                      <IconCheckCircle className="w-5 h-5" />
                      Inloggning lyckades!
                    </div>
                  ) : (
                    <>
                      <IconLoader className="w-6 h-6 animate-spin text-accent-400 mx-auto mb-2" />
                      <p className="text-archeron-300">
                        {bankIdStatus ? getStatusMessage(bankIdStatus) : 'Skapar QR-kod...'}
                      </p>
                    </>
                  )}
                </div>

                {/* Auto-start link */}
                {autoStartUrl && (
                  <a
                    href={autoStartUrl}
                    className="block text-center text-sm text-accent-400 hover:text-accent-300"
                  >
                    Öppna BankID på samma enhet
                  </a>
                )}

                {/* Cancel */}
                <button
                  onClick={handleBankIdCancel}
                  className="btn-secondary w-full py-2"
                >
                  Avbryt
                </button>
              </div>
            )}
          </div>
        )}

        {/* OIDC Auth */}
        {authMethod === 'oidc' && (
          <div className="card p-6 space-y-4">
            <div className="text-center mb-4">
              <h2 className="text-lg font-medium text-white mb-2">
                Logga in via din organisation
              </h2>
              <p className="text-archeron-400 text-sm">
                Välj din organisations inloggningsmetod
              </p>
            </div>

            {oidcProviders?.providers?.map((provider: { id: string; name: string }) => (
              <button
                key={provider.id}
                onClick={() => handleOIDCLogin(provider.id)}
                disabled={oidcInitMutation.isPending}
                className="btn-secondary w-full py-3 flex items-center justify-center gap-2"
              >
                <IconBuilding className="w-5 h-5" />
                {provider.name}
              </button>
            )) ?? (
              <p className="text-archeron-500 text-center text-sm">
                Inga organisationsanslutningar konfigurerade
              </p>
            )}

            {/* SITHS option */}
            <button
              onClick={() => handleOIDCLogin('inera')}
              disabled={oidcInitMutation.isPending}
              className="btn-secondary w-full py-3 flex items-center justify-center gap-2"
            >
              <IconShieldCheck className="w-5 h-5" />
              SITHS (via Inera)
            </button>
          </div>
        )}

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-archeron-500 text-xs">
            Genom att logga in godkänner du användningsvillkoren
          </p>
        </div>
      </div>
    </div>
  )
}
