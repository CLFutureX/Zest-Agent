// Event types aligned with Zest V1

// Reference: D:/spacex/Zest/frontend/src/types/v1/core/



export type EventID = string | number

export type ToolCallID = string



export type EventSource = 'agent' | 'user' | 'environment'

export type MessageRole = 'user' | 'assistant' | 'system'



export interface TextContent {

  type: 'text'

  text: string

}



export interface ImageUrlContent {

  type: 'image_url'

  image_url: { url: string }

}



export type MessageContent = string | Array<TextContent | ImageUrlContent>



export interface BaseEvent {

  id: string

  source: EventSource

  timestamp: string

  message?: string

  kind?: string

  [key: string]: unknown

}



export type ActionKind =

  | 'MCPToolAction'

  | 'FinishAction'

  | 'ThinkAction'

  | 'ExecuteBashAction'

  | 'FileEditorAction'

  | 'StrReplaceEditorAction'

  | 'TaskTrackerAction'

  | 'BrowserNavigateAction'

  | 'BrowserClickAction'

  | 'BrowserTypeAction'

  | 'BrowserGetStateAction'

  | 'BrowserGetContentAction'

  | 'BrowserScrollAction'

  | 'BrowserGoBackAction'

  | 'BrowserListTabsAction'

  | 'BrowserSwitchTabAction'

  | 'BrowserCloseTabAction'



export type ObservationKind =

  | 'MCPToolObservation'

  | 'FinishObservation'

  | 'ThinkObservation'

  | 'BrowserObservation'

  | 'ExecuteBashObservation'

  | 'FileEditorObservation'

  | 'StrReplaceEditorObservation'

  | 'TaskTrackerObservation'



export interface Action {

  kind: ActionKind

  [key: string]: unknown

}



export interface Observation {

  kind: ObservationKind

  [key: string]: unknown

}



export interface ActionEvent extends BaseEvent {

  source: 'agent'

  thought?: TextContent[]

  action: Action

  tool_name: string

  tool_call_id: ToolCallID

  security_risk?: string

}



export interface ObservationEvent extends BaseEvent {

  source: 'environment'

  observation: Observation

  action_id: EventID

  tool_call_id: ToolCallID

  tool_name: string

}



export interface MessageEvent extends BaseEvent {

  llm_message: {

    role: MessageRole

    content: MessageContent

  }

}



export interface AgentErrorEvent extends BaseEvent {



  source: 'agent'



  error: string



  tool_name: string



  tool_call_id: ToolCallID



}







export interface ConversationErrorEvent extends BaseEvent {



  source: 'environment'



  kind: 'ConversationErrorEvent'



  code?: string



  detail: string



}







export interface ConversationStateUpdateEvent extends BaseEvent {



  kind: 'ConversationStateUpdateEvent'



  key?: 'full_state' | 'agent_status' | string



  value?: unknown



}



export interface AgentStateUpdateEvent extends BaseEvent {



  kind: 'AgentStateUpdateEvent'



  agent_id: string



  key: string



  value?: unknown



}







export interface StateUpdateEvent extends BaseEvent {



  agent_status?: string



  status?: string



}







export type ZestEvent =



  | ActionEvent



  | ObservationEvent



  | MessageEvent



  | AgentErrorEvent



  | ConversationErrorEvent



  | ConversationStateUpdateEvent



  | AgentStateUpdateEvent



  | StateUpdateEvent



  | BaseEvent
