/**
 * Auth state management — mirrors time_jedi_bot/web/frontend/src/store/auth.ts
 *
 * - Stores JWT + user in localStorage
 * - React Context for global auth state
 * - Listens for AUTH_LOST_EVENT from API client to auto-logout
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  createElement,
  Fragment,
} from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { AUTH_LOST_EVENT, type AuthLostDetail } from '../lib/authSession'

const TOKEN_KEY = 'flib_token'
const USER_KEY = 'flib_user'

export interface AuthUser {
  user_id: number
  first_name: string
  username?: string | null
  photo_url?: string | null
}

interface AuthState {
  user: AuthUser | null
  token: string | null
  isAuthenticated: boolean
  login: (token: string, user: AuthUser) => void
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

function loadFromStorage(): { token: string | null; user: AuthUser | null } {
  try {
    const token = localStorage.getItem(TOKEN_KEY)
    const userRaw = localStorage.getItem(USER_KEY)
    const user = userRaw ? (JSON.parse(userRaw) as AuthUser) : null
    return { token, user }
  } catch {
    return { token: null, user: null }
  }
}

/** Listens for auth-lost custom event and triggers logout + redirect. */
function AuthSessionLostListener({ logout }: { logout: () => void }) {
  const navigate = useNavigate()
  useEffect(() => {
    const handler = (evt: Event) => {
      const e = evt as CustomEvent<AuthLostDetail>
      const returnUrl = e.detail?.returnUrl ?? '/'
      logout()
      if (window.location.pathname !== '/login') {
        navigate('/login', { replace: true, state: { from: returnUrl } })
      }
    }
    window.addEventListener(AUTH_LOST_EVENT, handler)
    return () => window.removeEventListener(AUTH_LOST_EVENT, handler)
  }, [logout, navigate])
  return null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const initial = loadFromStorage()
  const [token, setToken] = useState<string | null>(initial.token)
  const [user, setUser] = useState<AuthUser | null>(initial.user)

  const login = useCallback((newToken: string, newUser: AuthUser) => {
    localStorage.setItem(TOKEN_KEY, newToken)
    localStorage.setItem(USER_KEY, JSON.stringify(newUser))
    setToken(newToken)
    setUser(newUser)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
  }, [])

  return createElement(
    AuthContext.Provider,
    {
      value: {
        user,
        token,
        isAuthenticated: !!token && !!user,
        login,
        logout,
      },
    },
    createElement(Fragment, null, createElement(AuthSessionLostListener, { logout }), children)
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}
