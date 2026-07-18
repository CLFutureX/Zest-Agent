import type { ZestEvent } from '../../types/zest'



import { isActionEvent, isAgentErrorEvent, isConversationErrorEvent, isMessageEvent } from '../../types/zestGuards'



import {



  ErrorEventMessage,



  FinishEventMessage,



  GenericEventMessageWrapper,



  ObservationPairEventMessage,



  UserAssistantEventMessage,



} from './event-message-components'







type ZestEventMessageProps = {



  event: ZestEvent



  hasObservationPair: boolean



  isLastMessage: boolean



}







export function ZestEventMessage({



  event,



  hasObservationPair,



  isLastMessage,



}: ZestEventMessageProps) {



  if (isAgentErrorEvent(event) || isConversationErrorEvent(event)) {



    return <ErrorEventMessage event={event} />



  }







  if (hasObservationPair && isActionEvent(event)) {



    return <ObservationPairEventMessage event={event} />



  }







  if (isActionEvent(event) && event.action.kind === 'FinishAction') {



    return <FinishEventMessage event={event} />



  }







  if (isMessageEvent(event)) {



    return <UserAssistantEventMessage event={event} isLastMessage={isLastMessage} />



  }







  return <GenericEventMessageWrapper event={event} />



}
