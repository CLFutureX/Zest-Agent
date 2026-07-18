type InspectorPanelProps = {

  eventLogText: string

}



export function InspectorPanel({ eventLogText }: InspectorPanelProps) {

  return (

    <section className="panel grow inspector-panel">

      <div className="section-heading">

        <h2>事件调试流</h2>

        <span className="section-note">Runtime events</span>

      </div>

      <pre className="event-stream">{eventLogText}</pre>

    </section>

  )

}
