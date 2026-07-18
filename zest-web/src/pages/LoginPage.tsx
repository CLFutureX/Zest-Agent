import { useState, type FormEvent } from 'react'
import { useAuthStore } from '../stores/useAuthStore'

type Mode = 'login' | 'register'

type LoginPageProps = {
  embedded?: boolean
  onClose?: () => void
}

export function LoginPage({ embedded = false, onClose }: LoginPageProps) {
  const { login, register, loading, error, clearError } = useAuthStore()
  const [mode, setMode] = useState<Mode>('login')

  // Login fields
  const [account, setAccount] = useState('')
  const [loginPwd, setLoginPwd] = useState('')

  // Register fields
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [regPwd, setRegPwd] = useState('')
  const [regPwdConfirm, setRegPwdConfirm] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  async function handleLogin(e: FormEvent) {
    e.preventDefault()
    setLocalError(null)
    try {
      await login(account.trim(), loginPwd)
    } catch {
      // store.error already set
    }
  }

  async function handleRegister(e: FormEvent) {
    e.preventDefault()
    setLocalError(null)
    if (regPwd !== regPwdConfirm) {
      setLocalError('Passwords do not match')
      return
    }
    try {
      await register(username.trim(), email.trim(), regPwd)
    } catch {
      // store.error already set
    }
  }

  const displayError = localError ?? error

  return (
    <div className={`login-page${embedded ? ' login-page--embedded' : ''}`}>
      <div className="login-card panel panel-feature">
        <div className="login-brand">
          {embedded && (
            <button type="button" className="auth-dialog-close" onClick={onClose} aria-label="关闭登录窗口">
              ×
            </button>
          )}
          <span className="eyebrow">Zest Agent</span>
          <h1>{mode === 'login' ? 'Sign in' : 'Create account'}</h1>
          <p className="login-subtitle">先浏览工作区，登录后再保存配置、创建会话与使用个人记忆。</p>
        </div>

        {/* tab switcher */}
        <div className="auth-tabs">
          <button
            type="button"
            className={`auth-tab${mode === 'login' ? ' active' : ''}`}
            onClick={() => { setMode('login'); setLocalError(null); clearError() }}
          >
            Sign in
          </button>
          <button
            type="button"
            className={`auth-tab${mode === 'register' ? ' active' : ''}`}
            onClick={() => { setMode('register'); setLocalError(null); clearError() }}
          >
            Register
          </button>
        </div>

        {mode === 'login' ? (
          <form className="login-form" onSubmit={handleLogin}>
            <div className="form-field">
              <label htmlFor="account">Username / Email</label>
              <input
                id="account"
                type="text"
                value={account}
                onChange={(e) => setAccount(e.target.value)}
                autoComplete="username"
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="loginPwd">Password</label>
              <input
                id="loginPwd"
                type="password"
                value={loginPwd}
                onChange={(e) => setLoginPwd(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
            {displayError && <p className="login-error">{displayError}</p>}
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? 'Signing in\u2026' : 'Sign in'}
            </button>
          </form>
        ) : (
          <form className="login-form" onSubmit={handleRegister}>
            <div className="form-field">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                minLength={2}
                maxLength={64}
              />
            </div>
            <div className="form-field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="regPwd">Password</label>
              <input
                id="regPwd"
                type="password"
                value={regPwd}
                onChange={(e) => setRegPwd(e.target.value)}
                autoComplete="new-password"
                required
                minLength={6}
              />
            </div>
            <div className="form-field">
              <label htmlFor="regPwdConfirm">Confirm password</label>
              <input
                id="regPwdConfirm"
                type="password"
                value={regPwdConfirm}
                onChange={(e) => setRegPwdConfirm(e.target.value)}
                autoComplete="new-password"
                required
                minLength={6}
              />
            </div>
            {displayError && <p className="login-error">{displayError}</p>}
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? 'Creating account\u2026' : 'Create account'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
