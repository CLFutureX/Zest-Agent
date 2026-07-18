import type { AgentServerSummary } from '../../types/workspace'



export type AgentServerPanelProps = {



  servers: AgentServerSummary[]



  loading: boolean



  errorMessage: string



  statusFilter: string



  onChangeStatusFilter: (status: string) => void



  onRefresh: () => Promise<void> | void



}



function formatTime(value: string) {



  const date = new Date(value)



  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()



}



function formatMetricValue(value: unknown) {



  if (typeof value === 'number') {

    return Number.isInteger(value) ? `${value}` : value.toFixed(2)

  }



  if (Array.isArray(value)) {

    return value.join(', ')

  }



  return typeof value === 'object' ? JSON.stringify(value) : String(value)



}



function buildMetricItems(server: AgentServerSummary): Array<{ label: string; value: unknown }> {







  const metrics = server.metrics ?? {}



  const capabilities = server.capabilities ?? {}







  return [



    { label: 'CPU', value: metrics.cpu_percent },



    { label: 'Memory', value: metrics.memory_percent },



    { label: 'Active Sessions', value: metrics.active_sessions },



    { label: 'Max Sessions', value: capabilities.max_concurrent_sessions },



    { label: 'Models', value: capabilities.supported_models },



    { label: 'Tools', value: capabilities.supported_tools },



  ].filter((item) => item.value !== undefined && item.value !== null && item.value !== '')



}







function renderMetricList(server: AgentServerSummary) {







  const items = buildMetricItems(server)







  if (!items.length) {







    return <span className="agent-server-empty">暂无指标</span>







  }







  return items.slice(0, 6).map((item) => (







    <div key={item.label} className="agent-server-metric">







      <span>{item.label}</span>







      <strong>{formatMetricValue(item.value)}</strong>







    </div>







  ))







}



export function AgentServerPanel({

  servers,

  loading,

  errorMessage,

  statusFilter,

  onChangeStatusFilter,

  onRefresh,

}: AgentServerPanelProps) {



  return (



    <aside className="chat-sidebar panel panel-feature">



      <div className="section-heading">



        <h2>Agent Servers</h2>



        <span className="section-note">Runtime nodes & metrics</span>



      </div>



      <div className="agent-server-toolbar">



        <span className="agent-server-count">当前 {servers.length} 个节点</span>



        <button type="button" className="ghost-button" onClick={() => void onRefresh()}>



          刷新



        </button>



      </div>



      <div className="agent-server-filters">

        {[

          ['all', '全部'],

          ['healthy', 'Healthy'],

          ['degraded', 'Degraded'],

          ['unhealthy', 'Unhealthy'],

        ].map(([value, label]) => (

          <button

            key={value}

            type="button"

            className={`workspace-tab ${statusFilter === (value === 'all' ? '' : value) ? 'active' : ''}`}

            onClick={() => onChangeStatusFilter(value === 'all' ? '' : value)}

          >

            {label}

          </button>

        ))}

      </div>



      {loading ? <div className="agent-server-empty">正在加载节点信息...</div> : null}



      {errorMessage ? <div className="agent-server-error">{errorMessage}</div> : null}



      {!loading && !errorMessage && !servers.length ? <div className="agent-server-empty">暂无匹配的 AgentServer</div> : null}



      <div className="agent-server-grid">



        {servers.map((server) => (



          <article key={server.server_id} className={`agent-server-card status-${server.status}`}>



            <header>



              <div className="agent-server-heading">



                <strong>{server.server_id}</strong>



                <span>{server.host}:{server.port}</span>



              </div>



              <span className={`agent-server-status status-${server.status}`}>{server.status}</span>



            </header>



            <div className="agent-server-meta-row">

              <span>{server.version ?? 'unknown version'}</span>

              <span>{server.tags?.join(' · ') || 'no tags'}</span>

            </div>



            <div className="agent-server-metrics">{renderMetricList(server)}</div>



            <footer>



              <span>Heartbeat {formatTime(server.last_heartbeat)}</span>



              <span>Registered {formatTime(server.registered_at)}</span>



            </footer>



          </article>



        ))}



      </div>



    </aside>



  )



}
