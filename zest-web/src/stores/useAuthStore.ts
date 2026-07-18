import { create } from 'zustand'
import type { AuthUser } from '../types/auth'
import { getAuthSession, loginWithPassword, logout as apiLogout, register as apiRegister } from '../services/authApi'

type AuthState = {
  user: AuthUser | null
  authenticated: boolean
  loading: boolean
  sessionLoading: boolean
  error: string | null
  loadSession: () => Promise<void>
  login: (account: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<void>
  clearError: () => void
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  authenticated: false,
  loading: false,
  sessionLoading: false,
  error: null,

  loadSession: async () => {
    set({ sessionLoading: true, error: null })
    try {
      const session = await getAuthSession()
      set({
        authenticated: session.authenticated,
        user: session.user,
        sessionLoading: false,
      })
    } catch (e) {
      set({ sessionLoading: false, error: String(e) })
    }
  },

  login: async (account, password) => {
    set({ loading: true, error: null })
    try {
      const user = await loginWithPassword({ account, password })
      set({ authenticated: true, user, loading: false })
    } catch (e) {
      set({ loading: false, error: '账号或密码错误' })
      throw e
    }
  },

  register: async (username, email, password) => {
    set({ loading: true, error: null })
    try {
      const user = await apiRegister({ username, email, password })
      set({ authenticated: true, user, loading: false })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Registration failed'
      set({ loading: false, error: msg })
      throw e
    }
  },

  clearError: () => set({ error: null }),

  logout: async () => {
    await apiLogout()
    set({ authenticated: false, user: null, error: null })
  },
}))
