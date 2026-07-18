export type RuntimeAgentStatus =
  | 'idle'
  | 'running'
  | 'paused'
  | 'waiting_for_confirmation'
  | 'finished'
  | 'error'
  | 'stuck'
  | 'unknown'

export type ConfirmationState = {
  pending: boolean
  actionId: string | null
  toolName: string | null
  toolCallId: string | null
  summary: string | null
}
