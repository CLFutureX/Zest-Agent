import type {



  ZestEvent,



  ActionEvent,



  ObservationEvent,



  MessageEvent,



  AgentErrorEvent,



  AgentStateUpdateEvent,



  ConversationErrorEvent,



  StateUpdateEvent,



} from './zest'







type BaseEventLike = {



  id: string | number



  source: string



  timestamp: string



}







function isBaseEvent(value: unknown): value is BaseEventLike {



  return (



    value !== null



    && typeof value === 'object'



    && 'id' in value



    && 'timestamp' in value



    && 'source' in value



    && typeof value.id === 'string'



    && value.id.length > 0



    && typeof value.timestamp === 'string'



    && value.timestamp.length > 0



    && typeof value.source === 'string'



    && ['agent', 'user', 'environment'].includes(value.source)



  )



}







export function isV1Event(value: unknown): value is ZestEvent {



  return isBaseEvent(value)



}







export const isObservationEvent = (event: ZestEvent): event is ObservationEvent => (



  event.source === 'environment' && 'action_id' in event && 'observation' in event



)







export const isActionEvent = (event: ZestEvent): event is ActionEvent => (



  event.source === 'agent'



  && 'action' in event



  && 'tool_name' in event



  && 'tool_call_id' in event



  && typeof event.tool_name === 'string'



  && typeof event.tool_call_id === 'string'



)







export const isMessageEvent = (event: ZestEvent): event is MessageEvent => (



  'llm_message' in event



  && typeof event.llm_message === 'object'



  && event.llm_message !== null



  && 'role' in event.llm_message



  && 'content' in event.llm_message



)







export const isUserMessageEvent = (event: ZestEvent): event is MessageEvent => (



  isMessageEvent(event) && event.llm_message.role === 'user'



)







export const isAgentErrorEvent = (event: ZestEvent): event is AgentErrorEvent => (



  event.source === 'agent'



  && 'tool_name' in event



  && 'tool_call_id' in event



  && 'error' in event



  && typeof event.tool_name === 'string'



  && typeof event.tool_call_id === 'string'



  && typeof event.error === 'string'



)







export const isConversationErrorEvent = (event: ZestEvent): event is ConversationErrorEvent => (



  event.source === 'environment'



  && 'kind' in event



  && event.kind === 'ConversationErrorEvent'



  && 'detail' in event



  && typeof event.detail === 'string'



)







export const isConversationStateUpdateEvent = (event: ZestEvent): event is StateUpdateEvent => (



  'kind' in event && event.kind === 'ConversationStateUpdateEvent'



)







export const isAgentStateUpdateEvent = (event: ZestEvent): event is AgentStateUpdateEvent => (



  'kind' in event



  && event.kind === 'AgentStateUpdateEvent'



  && 'agent_id' in event



  && 'key' in event



)







export const isExecuteBashActionEvent = (event: ZestEvent): event is ActionEvent => (



  isActionEvent(event) && event.action.kind === 'ExecuteBashAction'



)







export const isExecuteBashObservationEvent = (event: ZestEvent): event is ObservationEvent => (



  isObservationEvent(event) && event.observation.kind === 'ExecuteBashObservation'



)
