import type { ReactNode } from 'react'

type DesktopWorkspaceLayoutProps = {
  left: ReactNode
  right: ReactNode
  isRightPanelShown: boolean
}

export function DesktopWorkspaceLayout({ left, right, isRightPanelShown }: DesktopWorkspaceLayoutProps) {
  return (
    <div className="desktop-workspace-layout">
      <section className={`desktop-chat-pane ${isRightPanelShown ? 'with-panel' : 'full'}`}>{left}</section>
      {isRightPanelShown ? <aside className="desktop-side-pane">{right}</aside> : null}
    </div>
  )
}
