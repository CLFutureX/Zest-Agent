import { useEffect, useMemo, useState } from 'react'

import { AgentServersPage } from './pages/AgentServersPage'
import { ConfigCenterPage } from './pages/ConfigCenterPage'
import { MemoryPage } from './pages/MemoryPage'
import { WorkspacePage } from './pages/WorkspacePage'
import { LoginPage } from './pages/LoginPage'
import { UserMenu } from './components/auth/UserMenu'
import { useAuthStore } from './stores/useAuthStore'
import { AUTH_DIALOG_EVENT } from './utils/authEvents'

type NavItemId = 'conversations' | 'memory' | 'config-center' | 'agent-servers'

const PRIMARY_NAV = [
  { id: 'conversations' as const, label: 'Conversations' },
  { id: 'memory' as const, label: 'Memory' },
  { id: 'config-center' as const, label: 'Config Center' },
  { id: 'agent-servers' as const, label: 'Agent Servers' },
]

export default function App() {
  const [activePage, setActivePage] = useState<NavItemId>('conversations')
  const [authDialogOpen, setAuthDialogOpen] = useState(false)
  const [navCollapsed, setNavCollapsed] = useState(false)
  const { authenticated, loadSession } = useAuthStore()

  const shouldAutoHideNav = activePage === 'conversations'

  useEffect(() => {
    if (!shouldAutoHideNav) {
      setNavCollapsed(false)
      return
    }

    setNavCollapsed(true)
  }, [shouldAutoHideNav])

  useEffect(() => {
    loadSession()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const handleAuthDialog = () => {
      setAuthDialogOpen(true)
    }

    window.addEventListener(AUTH_DIALOG_EVENT, handleAuthDialog)
    return () => {
      window.removeEventListener(AUTH_DIALOG_EVENT, handleAuthDialog)
    }
  }, [])

  useEffect(() => {
    if (authenticated) {
      setAuthDialogOpen(false)
    }
  }, [authenticated])

  const content = useMemo(() => {
    if (activePage === 'config-center') {
      return <ConfigCenterPage />
    }
    if (activePage === 'agent-servers') {
      return <AgentServersPage />
    }
    if (activePage === 'memory') {
      return <MemoryPage />
    }
    return <WorkspacePage />
  }, [activePage])

  return (
    <>
      <div className={`app-shell${navCollapsed ? ' app-shell--nav-collapsed' : ''}`}>
        {shouldAutoHideNav ? (
          <div
            className="app-nav-edge-trigger"
            aria-hidden="true"
            onMouseEnter={() => setNavCollapsed(false)}
          />
        ) : null}

        <aside
          className={`app-nav panel panel-feature${navCollapsed ? ' is-collapsed' : ''}`}
          onMouseLeave={() => {
            if (shouldAutoHideNav) {
              setNavCollapsed(true)
            }
          }}
        >
          <div className="app-nav-brand">
            <span className="eyebrow">Zest Agent</span>
            <h1>Control Center</h1>
            {!authenticated ? (
              <button
                type="button"
                className="app-nav-auth-button"
                onClick={() => setAuthDialogOpen(true)}
              >
                Sign in
              </button>
            ) : null}
          </div>
          <nav className="app-nav-menu" aria-label="Primary">
            <div className="app-nav-section">
              <span className="app-nav-section-title">Workspace</span>
              {PRIMARY_NAV.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`app-nav-item ${activePage === item.id ? 'active' : ''}`}
                  onClick={() => {
                    setActivePage(item.id)
                    setNavCollapsed(false)
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </nav>
          <div className="app-nav-footer">
            <UserMenu onRequestAuth={() => setAuthDialogOpen(true)} />
          </div>
        </aside>

        <div className="app-content">{content}</div>
      </div>

      {authDialogOpen && (
        <div className="auth-modal-backdrop" role="presentation" onClick={() => setAuthDialogOpen(false)}>
          <div className="auth-modal" role="dialog" aria-modal="true" aria-label="登录或注册" onClick={(event) => event.stopPropagation()}>
            <LoginPage embedded onClose={() => setAuthDialogOpen(false)} />
          </div>
        </div>
      )}
    </>
  )
}
