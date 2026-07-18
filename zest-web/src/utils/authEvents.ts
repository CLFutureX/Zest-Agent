export const AUTH_DIALOG_EVENT = 'zest:auth-dialog'

export function requestAuthDialog(reason?: string) {
  if (typeof window === 'undefined') return

  window.dispatchEvent(new CustomEvent(AUTH_DIALOG_EVENT, { detail: { reason } }))
}
