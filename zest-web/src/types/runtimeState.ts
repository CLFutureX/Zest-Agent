export type RuntimeAgentStatus =
  | 'idle'
  | 'running'
  | 'paused'
  | 'waiting_for_confirmation'
  | 'finished'
  | 'error'
  | 'stuck'
  | 'unknown'

export type MemoryReviewSimilarExperience = {
  id: string
  question: string
  solution: string
  trace_summary: string[]
  feedback_type: string
}

export type MemoryReviewActionArgs = {
  similar_experiences?: MemoryReviewSimilarExperience[]
  new_content?: string
  question?: string
  feedback_type?: string
}

export type ConfirmationState = {
  pending: boolean
  actionId: string | null
  toolName: string | null
  toolCallId: string | null
  summary: string | null
  actionArgs?: Record<string, unknown> | null
}
