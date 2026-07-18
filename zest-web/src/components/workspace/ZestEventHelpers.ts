import type { MessageEvent, ZestEvent } from '../../types/zest'



import {



  isActionEvent,



  isAgentErrorEvent,



  isConversationErrorEvent,



  isConversationStateUpdateEvent,



  isMessageEvent,



  isObservationEvent,



} from '../../types/zestGuards'







const NO_RENDER_ACTION_TYPES = ['ThinkAction']



const NO_RENDER_OBSERVATION_TYPES = ['ThinkObservation']







export function shouldRenderEvent(event: ZestEvent): boolean {



  if (isConversationStateUpdateEvent(event)) {



    return false



  }







  if (isActionEvent(event)) {







    const actionType = event.action.kind







    return !NO_RENDER_ACTION_TYPES.includes(actionType)



  }







  if (isObservationEvent(event)) {



    return !NO_RENDER_OBSERVATION_TYPES.includes(event.observation.kind)



  }







  if (isMessageEvent(event) || isAgentErrorEvent(event) || isConversationErrorEvent(event)) {



    return true



  }







  return false



}







export function parseMessageFromEvent(event: MessageEvent): string {



  const message = event.llm_message



  if (!message || !message.content) {



    return ''



  }







  if (Array.isArray(message.content)) {



    return message.content



      .filter((content) => content.type === 'text')



      .map((content) => content.text)



      .join('\n')



  }







  return typeof message.content === 'string' ? message.content : ''



}
