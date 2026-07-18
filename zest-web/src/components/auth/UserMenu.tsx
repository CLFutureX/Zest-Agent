import { useAuthStore } from '../../stores/useAuthStore'

type UserMenuProps = {
  onRequestAuth?: () => void
}

export function UserMenu(_: UserMenuProps) {
  const { user, logout } = useAuthStore()

  if (!user) {
    return (
      <div className="user-menu user-menu--guest">
        <div className="user-menu-status">
          <span className="user-menu-dot" aria-hidden="true" />
          <span className="user-menu-name">Guest</span>
        </div>
        <span className="user-menu-note">Browse mode</span>
      </div>
    )
  }

  return (
    <div className="user-menu">
      <div className="user-menu-status">
        <span className="user-menu-dot user-menu-dot--active" aria-hidden="true" />
        <span className="user-menu-name">{user.display_name ?? user.username}</span>
      </div>
      <button
        type="button"
        className="user-menu-logout"
        onClick={() => void logout()}
      >
        Sign out
      </button>
    </div>
  )
}
