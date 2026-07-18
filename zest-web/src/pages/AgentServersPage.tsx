import { AlertBanner } from '../components/workspace/AlertBanner'
import { AgentServerPanel } from '../components/workspace/AgentServerPanel'
import { useAgentServers } from '../hooks/useAgentServers'

export function AgentServersPage() {
  const { servers, loading, errorMessage, refresh, statusFilter, setStatusFilter } = useAgentServers()

  return (
    <div className="workspace-shell">
      <div className="aurora aurora-one" />
      <div className="aurora aurora-two" />
      <header className="topbar">
        <div className="topbar-copy">
          <span className="eyebrow">Infrastructure</span>
          <h1>Agent Servers</h1>
          <p>集中查看节点健康、负载与能力。</p>
        </div>
      </header>
      <main className="workspace-page-body">

        {errorMessage ? <AlertBanner message={errorMessage} onClose={() => undefined} /> : null}

        <AgentServerPanel

          servers={servers}

          loading={loading}

          errorMessage={errorMessage}

          onRefresh={refresh}

          statusFilter={statusFilter}

          onChangeStatusFilter={setStatusFilter}

        />
      </main>
    </div>
  )
}
