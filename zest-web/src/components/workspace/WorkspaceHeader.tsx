import type { ReactNode } from 'react'



type WorkspaceHeaderProps = {

  title: string

  runtimeMeta: string

  connectionLabel: string

  actions?: ReactNode

}



export function WorkspaceHeader({ title, runtimeMeta, connectionLabel, actions }: WorkspaceHeaderProps) {

  const badgeClassName = `badge ${connectionLabel === '已连接' ? 'success' : connectionLabel === '连接异常' ? 'error' : ''}`



  return (

    <header className="topbar">

      <div className="topbar-copy">

        <span className="eyebrow">Agent canvas</span>

        <h1>{title}</h1>

        <p>{runtimeMeta}</p>

      </div>

      <div className="topbar-actions">

        {actions}

        <div className={badgeClassName}>{connectionLabel}</div>

      </div>

    </header>

  )

}
