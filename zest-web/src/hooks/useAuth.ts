import { useEffect } from 'react'
import { useAuthStore } from '../stores/useAuthStore'

export function useAuth() {
  const store = useAuthStore()

  useEffect(() => {
    // 首次加载时查询登录态
    store.loadSession()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    user: store.user,
    authenticated: store.authenticated,
    loading: store.loading,
    sessionLoading: store.sessionLoading,
    error: store.error,
    login: store.login,
    logout: store.logout,
  }
}
