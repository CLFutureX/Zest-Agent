export type TaskStatus = 'pending' | 'dispatching' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled'



export type ConversationAccessInfo = {

  conversation_id: string

  base_url: string

  session_api_key?: string | null

  resend_all?: boolean

}



export type UserLlmConfigSummary = {

  id: string

  user_id: string

  usage_id: string

  model: string

  api_key: string

  base_url?: string | null

}



export type SkillProfileSummary = {



  id: string



  user_id: string



  name: string



  content: string



  description?: string | null



  source?: string | null



  trigger?: Record<string, unknown> | null



  enabled: boolean



  bundle_type?: string | null



  oss_key?: string | null



  content_hash?: string | null



  version?: string | null



}







export type PromptConfigSummary = {



  id: string



  user_id: string



  name: string



  content: string



  description?: string | null



  source?: string | null



  trigger?: Record<string, unknown> | null



  enabled: boolean



}



export type SubAgentConfigSummary = {



  id: string



  user_id: string



  name: string



  model?: string | null



  selected_tool_names?: string[]



  description?: string | null



  custom_system_prompt?: string | null



  system_prompt_filename?: string | null



  enabled: boolean



  config: Record<string, unknown>



}



// --- 会话运行态快照子结构 ---



export type SnapshotRuntime = {

  status?: string | null

  updated_at?: string | null

}



export type SnapshotSummary = {

  last_user_message?: string | null

}



export type ConversationRuntimeSnapshot = {

  runtime: SnapshotRuntime

  summary: SnapshotSummary

}



// --- 会话对象 ---



export type ConversationResponse = {

  conversation_id: string

  agent_id?: string | null

  created_at?: string | null

  task_id?: string | null

  base_url?: string | null

  session_api_key?: string | null

  error_message?: string | null

  snapshot: ConversationRuntimeSnapshot

}
 
 



export type ConversationEventRecord = {

  event_id: string

  conversation_id: string

  event_type: string

  source: string

  timestamp: string

  payload: Record<string, unknown>

}



export type ConversationEventPage = {

  items: ConversationEventRecord[]

  next_cursor?: string | null

  has_more: boolean

}



export type ConversationMemoryRecord = {

  id: string

  memory_type: string

  category?: string | null

  title?: string | null

  content: string

  score?: number | null

  metadata: Record<string, unknown>

}



export type TodoItemStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'

export type TodoItem = {
  content: string
  status: TodoItemStatus
}

/** Minimal conversation state view from GET /conversation/{id}/state */
export type ConversationStateView = {
  conversation_id: string
  execution_status: string
  task_description: string
  todos: TodoItem[]
  agent_id?: string | null
}

export type MemoryReviewPayload = {
  tool_name: 'memory_review'
  selected_id?: string
  edited_content?: string
}

export type ConfirmationResponseInput = {
  accept: boolean
  reason?: string
  payload?: MemoryReviewPayload
}

export type ConversationSplitView = {
  events: ConversationEventRecord[]
  baseMemories: ConversationMemoryRecord[]
  experienceMemories: ConversationMemoryRecord[]
  /** Deduplicated file paths extracted from write/edit events */
  artifacts: string[]
  /** Agent task todo list from AgentState.todos */
  todos: TodoItem[]
}



export type AgentServerSummary = {

  server_id: string

  host: string

  port: number

  status: string

  capabilities?: Record<string, unknown>

  metrics?: Record<string, unknown>

  last_heartbeat: string

  registered_at: string

  version?: string | null

  tags?: string[]

}



export type AgentServerListResponse = {

  servers: AgentServerSummary[]

  total: number

}



export type { TimelineRole, TimelineKind, TimelineSection } from './runtimeEvents'



import type { TimelineRole, TimelineKind, TimelineSection } from './runtimeEvents'



export type TimelineItem = {

  id: string

  role: TimelineRole

  kind: TimelineKind

  title: string

  body: string

  time: string

  rawEvent?: Record<string, unknown>

  pairId?: string | null

  paired?: boolean

  toolName?: string | null

  summary?: string | null

  sections?: TimelineSection[]

  success?: 'success' | 'error'

}
 
