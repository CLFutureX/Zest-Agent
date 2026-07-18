export type RuntimeEvent = Record<string, unknown>



export type TimelineRole = 'assistant' | 'user' | 'system'

export type TimelineKind = 'message' | 'action' | 'observation' | 'status'



export type TimelineSection = {

  label: string

  value: string

  code?: boolean

  tone?: 'success' | 'warning' | 'error'

}



export type StreamAccumulator = {

  id: string

  role: TimelineRole

  kind: TimelineKind

  title: string

  body: string

  rawEvent?: RuntimeEvent

  pairId?: string | null

  paired?: boolean

  toolName?: string | null

  summary?: string | null

  sections?: TimelineSection[]

  success?: 'success' | 'error'

}

export type RuntimeEventResult = {
  mode: 'append' | 'upsert'
  entry: StreamAccumulator
}

// Re-export Zest types
export type {
  ZestEvent,
  ActionEvent,
  ObservationEvent,
  MessageEvent,
  AgentErrorEvent,
  StateUpdateEvent,
  ActionKind,
  ObservationKind,
} from './zest'
