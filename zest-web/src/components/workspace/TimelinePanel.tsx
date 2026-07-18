import { useState } from 'react'
import type { TimelineItem, TimelineSection } from '../../types/workspace'
import { formatEventBody, formatEventSections, formatEventTitle } from './eventFormatting'

type TimelinePanelProps = { items: TimelineItem[] }

function EventDetail({ sections }: { sections: TimelineSection[] }) {
  const [expanded, setExpanded] = useState(false)
  if (!sections.length) return null
  return (
    <div className="event-detail">
      <button type="button" className="event-detail-toggle" onClick={() => setExpanded((v) => !v)}>
        {expanded ? '▼' : '▶'}
      </button>
      {expanded && (
        <div className="event-detail-content">
          {sections.map((s) => (
            <section key={s.label} className={`event-section ${s.tone ?? 'default'} ${s.code ? 'code' : ''}`}>
              <label>{s.label}</label>
              <pre>{s.value}</pre>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

export function TimelinePanel({ items }: TimelinePanelProps) {
  return (
    <section className="panel panel-feature grow">
      <div className="section-heading">
        <h2>会话时间线</h2>
        <span className="section-note">Live narrative</span>
      </div>
      <div className="timeline">
        {items.map((item) => {
          const sections = formatEventSections(item)
          const body = formatEventBody(item)
          return (
            <article key={item.id} className={`timeline-item ${item.role} ${item.kind} ${item.paired ? 'paired' : ''}`}>
              <header>
                <div className="timeline-meta">
                  <strong>{formatEventTitle(item)}</strong>
                  {item.toolName ? <span>{item.toolName}</span> : null}
                </div>
                <time>{item.time}</time>
              </header>
              {body ? <p>{body}</p> : null}
              <EventDetail sections={sections} />
            </article>
          )
        })}
      </div>
    </section>
  )
}
