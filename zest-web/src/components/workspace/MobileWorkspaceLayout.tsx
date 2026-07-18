import type { ReactNode } from 'react'

type MobileWorkspaceLayoutProps = {
  top: ReactNode
  bottom: ReactNode
  isRightPanelShown: boolean
}

export function MobileWorkspaceLayout({ top, bottom, isRightPanelShown }: MobileWorkspaceLayoutProps) {
  return (
    <div className="mobile-workspace-layout">
      <section className={`mobile-chat-pane ${isRightPanelShown ? 'compressed' : 'expanded'}`}>{top}</section>
      {isRightPanelShown ? <aside className="mobile-side-pane">{bottom}</aside> : null}
    </div>
  )
}
