import type { ActionEvent, AgentErrorEvent, ConversationErrorEvent, MessageEvent, ZestEvent } from '../../types/zest'



import { isActionEvent, isObservationEvent } from '../../types/zestGuards'



import { formatEventSections, formatEventSuccess, formatEventTitle } from './eventFormatting'



import { parseMessageFromEvent } from './ZestEventHelpers'







export type EventMessageComponentProps = {



  event: ZestEvent



  isLastMessage?: boolean



}







type StructuredEventProps = {



  event: ZestEvent



  badge: string



  kindClass: 'action' | 'observation' | 'status'



  title: string



  body?: string



  success?: 'success' | 'error'



}



function EventDetail({ event }: { event: ZestEvent }) {

  const sections = formatEventSections({

    id: String(event.id),

    role: event.source === 'user' ? 'user' : event.source === 'environment' ? 'system' : 'assistant',

    kind: isActionEvent(event) ? 'action' : isObservationEvent(event) ? 'observation' : 'status',

    title: String(event.message ?? event.kind ?? 'Event'),

    body: String(event.message ?? ''),

    time: new Date(event.timestamp).toLocaleTimeString(),

    rawEvent: event,

  })



  if (!sections.length) return null



  return (

    <div className="event-detail-content is-open">

      {sections.map((section) => (

        <section key={section.label} className={`event-section ${section.tone ?? 'default'} ${section.code ? 'code' : ''}`}>

          <label>{section.label}</label>

          <pre>{section.value}</pre>

        </section>

      ))}

    </div>

  )

}



function StructuredEventMessage({ badge, body, event, kindClass, success, title }: StructuredEventProps) {

  return (

    <article className={`chat-bubble system ${kindClass}`}>

      <header>

        <div className="chat-bubble-meta">

          <span className={`chat-bubble-badge ${kindClass}`}>{badge}</span>

          <strong>{title}</strong>

          {success ? <span className={`success-dot ${success}`} /> : null}

        </div>

        <time>{new Date(event.timestamp).toLocaleTimeString()}</time>

      </header>

      {body ? <p>{body}</p> : null}

      <EventDetail event={event} />

    </article>

  )

}



export function UserAssistantEventMessage({ event, isLastMessage }: { event: MessageEvent; isLastMessage?: boolean }) {

  const role = event.llm_message.role === 'user' ? 'user' : 'assistant'

  const message = parseMessageFromEvent(event)



  return (

    <article className={`chat-bubble ${role} message ${isLastMessage ? 'last-message' : ''}`}>

      <header>

        <div className="chat-bubble-meta">

          <span className="chat-bubble-badge message">{role === 'user' ? 'User' : 'Assistant'}</span>

          <strong>{formatEventTitle({ id: String(event.id), role, kind: 'message', title: role, body: message, time: new Date(event.timestamp).toLocaleTimeString() })}</strong>

        </div>

        <time>{new Date(event.timestamp).toLocaleTimeString()}</time>

      </header>

      <p>{message}</p>

    </article>

  )

}



export function ObservationPairEventMessage({ event }: { event: ActionEvent }) {

  const thought = Array.isArray(event.thought)

    ? event.thought.filter((item) => item.type === 'text').map((item) => item.text).join('\n')

    : ''



  if (!thought) return null



  return (

    <article className="chat-bubble assistant action paired">

      <header>

        <div className="chat-bubble-meta">

          <span className="chat-bubble-badge action">Action</span>

          <strong>{formatEventTitle({ id: String(event.id), role: 'assistant', kind: 'action', title: event.action.kind, body: thought, time: new Date(event.timestamp).toLocaleTimeString(), summary: thought })}</strong>

        </div>

        <time>{new Date(event.timestamp).toLocaleTimeString()}</time>

      </header>

      <p>{thought}</p>

    </article>

  )

}







export function ErrorEventMessage({ event }: { event: AgentErrorEvent | ConversationErrorEvent }) {



  const title = 'tool_name' in event && typeof event.tool_name === 'string'

    ? event.tool_name

    : 'code' in event && typeof event.code === 'string' && event.code

      ? event.code

      : 'ConversationErrorEvent'



  const detail = 'error' in event && typeof event.error === 'string'

    ? event.error

    : 'detail' in event && typeof event.detail === 'string'

      ? event.detail

      : 'Unknown error'



  const summary = detail

    .split(/[:\n]/)

    .map((part) => part.trim())

    .find(Boolean) ?? '请求失败，请稍后重试。'



  return (

    <article className="chat-bubble system status error-message-bubble">

      <header>

        <div className="chat-bubble-meta">

          <span className="chat-bubble-badge status">Error</span>

          <strong>{title}</strong>

        </div>

        <time>{new Date(event.timestamp).toLocaleTimeString()}</time>

      </header>

      <p>{summary}</p>

      {detail !== summary ? (

        <details className="error-detail-block">

          <summary>查看详情</summary>

          <pre>{detail}</pre>

        </details>

      ) : null}

    </article>

  )

}






export function FinishEventMessage({ event }: { event: ActionEvent }) {



  return <StructuredEventMessage event={event} badge="Finish" kindClass="action" title={event.action.kind} body={String(event.message ?? event.action.message ?? 'Finished')} />



}



export function GenericEventMessageWrapper({ event }: EventMessageComponentProps) {

  const kindClass = isActionEvent(event) ? 'action' : isObservationEvent(event) ? 'observation' : 'status'

  const observationSuccess = isObservationEvent(event) && typeof event.observation.exit_code === 'number'

    ? event.observation.exit_code === 0 ? 'success' : 'error'

    : undefined

  const success = formatEventSuccess({ id: String(event.id), role: 'system', kind: kindClass, title: String(event.kind ?? event.message ?? 'Event'), body: String(event.message ?? ''), time: new Date(event.timestamp).toLocaleTimeString(), success: observationSuccess })



  return (

    <StructuredEventMessage

      event={event}

      badge={kindClass}

      kindClass={kindClass}

      title={'tool_name' in event && typeof event.tool_name === 'string' ? event.tool_name : String(event.kind ?? event.message ?? 'Event')}

      success={success}

    />

  )

}
