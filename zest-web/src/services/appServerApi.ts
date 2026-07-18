import { env } from '../config/env'
import type {
  AgentServerListResponse,
  ConfirmationResponseInput,
  ConversationEventPage,
  ConversationMemoryRecord,
  ConversationResponse,
  ConversationStateView,
  PromptConfigSummary,
  SkillProfileSummary,
  SubAgentConfigSummary,
  UserLlmConfigSummary,
} from '../types/workspace'

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `Request failed with status ${response.status}`)
  }
  return (await response.json()) as T
}

export async function listConversations(input: {
  userId: string
  limit?: number
  offset?: number
}): Promise<ConversationResponse[]> {
  const response = await fetch(
    `${env.appApiBase}/conversation/users/${input.userId}/conversations?limit=${input.limit ?? 20}&offset=${input.offset ?? 0}`,
  )
  const data = await parseResponse<{ conversation?: ConversationResponse[] }>(response)
  return data.conversation ?? []
}

export async function openConversation(input: {
  userId: string
  title: string
  initialMessage?: string
  workspace?: string
  model?: string
}): Promise<ConversationResponse> {
  const response = await fetch(`${env.appApiBase}/conversation/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.userId,
      model: input.model,
      initial_message: input.initialMessage?.trim() || null,
      metadata: {
        title: input.title,
        workspace: input.workspace ?? '',
      },
    }),
  })
  const data = await parseResponse<ConversationResponse>(response)
  return {
    ...data,
    snapshot: {
      ...data.snapshot,
      summary: {
        ...data.snapshot?.summary,
        last_user_message: data.snapshot?.summary?.last_user_message ?? input.initialMessage?.trim() ?? null,
      },
    },
  }
}

export async function getConversation(conversationId: string): Promise<ConversationResponse> {
  const response = await fetch(`${env.appApiBase}/conversation/${conversationId}`)
  return parseResponse<ConversationResponse>(response)
}

export async function getConversationEvents(
  conversationId: string,
  userId: string,
  limit = 20,
  cursor?: string,
): Promise<ConversationEventPage> {
  const query = new URLSearchParams({
    user_id: userId,
    limit: String(limit),
  })
  if (cursor) {
    query.set('cursor', cursor)
  }
  const response = await fetch(`${env.appApiBase}/conversation/${conversationId}/events?${query.toString()}`)
  return parseResponse<ConversationEventPage>(response)
}

export async function getConversationStateView(
  conversationId: string,
): Promise<ConversationStateView | null> {
  try {
    const response = await fetch(`${env.appApiBase}/conversation/${conversationId}/state`)
    if (response.status === 404) {
      return null
    }
    return parseResponse<ConversationStateView>(response)
  } catch {
    return null
  }
}

export async function respondToConfirmation(
  conversationId: string,
  input: ConfirmationResponseInput,
): Promise<{ success: boolean }> {
  const response = await fetch(
    `${env.appApiBase}/conversation/${conversationId}/respond_to_confirmation`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        accept: input.accept,
        reason: input.reason ?? 'User rejected the action.',
      }),
    },
  )

  return parseResponse<{ success: boolean }>(response)
}

export async function getConversationBaseMemories(
  conversationId: string,
  userId: string,
): Promise<ConversationMemoryRecord[]> {
  const query = new URLSearchParams({ user_id: userId })
  const response = await fetch(`${env.appApiBase}/conversation/${conversationId}/memories/base?${query.toString()}`)
  return parseResponse<ConversationMemoryRecord[]>(response)
}

export async function getConversationExperienceMemories(
  conversationId: string,
  userId: string,
): Promise<ConversationMemoryRecord[]> {
  const query = new URLSearchParams({ user_id: userId })
  const response = await fetch(`${env.appApiBase}/conversation/${conversationId}/memories/experience?${query.toString()}`)
  return parseResponse<ConversationMemoryRecord[]>(response)
}

export async function listBaseMemories(userId: string): Promise<ConversationMemoryRecord[]> {
  const query = new URLSearchParams({ user_id: userId })
  const response = await fetch(`${env.appApiBase}/conversation/_/memories/base?${query.toString()}`)
  return parseResponse<ConversationMemoryRecord[]>(response)
}

export async function listExperienceMemories(userId: string): Promise<ConversationMemoryRecord[]> {
  const query = new URLSearchParams({ user_id: userId })
  const response = await fetch(`${env.appApiBase}/conversation/_/memories/experience?${query.toString()}`)
  return parseResponse<ConversationMemoryRecord[]>(response)
}

export async function listAgentServers(status?: string): Promise<AgentServerListResponse> {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  const response = await fetch(`${env.appApiBase}/agentservers${query}`)
  return parseResponse<AgentServerListResponse>(response)
}

export async function listLlmConfigs(userId: string): Promise<UserLlmConfigSummary[]> {
  const query = new URLSearchParams({ user_id: userId })
  const response = await fetch(`${env.appApiBase}/agent-config/llm-configs?${query.toString()}`)
  return parseResponse<UserLlmConfigSummary[]>(response)
}

export async function createLlmConfig(input: {
  id?: string
  userId: string
  usageId: string
  model: string
  apiKey: string
  baseUrl?: string
}): Promise<UserLlmConfigSummary> {
  const response = await fetch(`${env.appApiBase}/agent-config/llm-configs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.userId,
      usage_id: input.usageId,
      model: input.model,
      api_key: input.apiKey,
      base_url: input.baseUrl || null,
      max_tokens: null,
      extra: null,
    }),
  })
  return parseResponse<UserLlmConfigSummary>(response)
}

export async function listSkills(userId: string, enabled?: boolean): Promise<SkillProfileSummary[]> {
  const query = new URLSearchParams({ user_id: userId })
  if (enabled !== undefined) {
    query.set('enabled', String(enabled))
  }
  const response = await fetch(`${env.appApiBase}/agent-config/skills?${query.toString()}`)
  return parseResponse<SkillProfileSummary[]>(response)
}

export type SkillInput = {
  userId: string
  name: string
  content: string
  description?: string
  source?: string
  enabled?: boolean
}

export async function createSkill(input: SkillInput & { id?: string }): Promise<SkillProfileSummary> {
  const response = await fetch(`${env.appApiBase}/agent-config/skills`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.userId,
      name: input.name,
      content: input.content,
      description: input.description || null,
      source: input.source || null,
      trigger: null,
      enabled: input.enabled ?? true,
    }),
  })
  return parseResponse<SkillProfileSummary>(response)
}

export async function updateSkill(
  skillId: string,
  input: SkillInput,
): Promise<SkillProfileSummary> {
  const response = await fetch(`${env.appApiBase}/agent-config/skills/${skillId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.userId,
      name: input.name,
      content: input.content,
      description: input.description || null,
      source: input.source || null,
      trigger: null,
      enabled: input.enabled ?? true,
    }),
  })
  return parseResponse<SkillProfileSummary>(response)
}

export async function listPrompts(userId: string, enabled?: boolean): Promise<PromptConfigSummary[]> {
  const query = new URLSearchParams({ user_id: userId })
  if (enabled !== undefined) {
    query.set('enabled', String(enabled))
  }
  const response = await fetch(`${env.appApiBase}/agent-config/prompts?${query.toString()}`)
  return parseResponse<PromptConfigSummary[]>(response)
}

export type PromptInput = {
  userId: string
  name: string
  content: string
  description?: string
  source?: string
  enabled?: boolean
}

export async function createPrompt(input: PromptInput & { id?: string }): Promise<PromptConfigSummary> {
  const response = await fetch(`${env.appApiBase}/agent-config/prompts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.userId,
      name: input.name,
      content: input.content,
      description: input.description || null,
      source: input.source || null,
      trigger: null,
      enabled: input.enabled ?? true,
    }),
  })
  return parseResponse<PromptConfigSummary>(response)
}

export async function updatePrompt(
  promptId: string,
  input: PromptInput,
): Promise<PromptConfigSummary> {
  const response = await fetch(`${env.appApiBase}/agent-config/prompts/${promptId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.userId,
      name: input.name,
      content: input.content,
      description: input.description || null,
      source: input.source || null,
      trigger: null,
      enabled: input.enabled ?? true,
    }),
  })
  return parseResponse<PromptConfigSummary>(response)
}

export async function listSubAgentConfigs(userId: string, enabled?: boolean): Promise<SubAgentConfigSummary[]> {
  const query = new URLSearchParams({ user_id: userId })
  if (enabled !== undefined) {
    query.set('enabled', String(enabled))
  }
  const response = await fetch(`${env.appApiBase}/agent-config/subagent-configs?${query.toString()}`)
  return parseResponse<SubAgentConfigSummary[]>(response)
}

export type SubAgentConfigInput = {
  userId: string
  name: string
  model?: string
  selectedToolNames?: string[]
  description?: string
  customSystemPrompt?: string
  systemPromptFilename?: string
  enabled?: boolean
  config: Record<string, unknown>
}

export async function createSubAgentConfig(
  input: SubAgentConfigInput & { id?: string },
): Promise<SubAgentConfigSummary> {
  const response = await fetch(`${env.appApiBase}/agent-config/subagent-configs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.userId,
      name: input.name,
      model: input.model || null,
      selected_tool_names: input.selectedToolNames ?? [],
      description: input.description || null,
      custom_system_prompt: input.customSystemPrompt || null,
      system_prompt_filename: input.systemPromptFilename || null,
      enabled: input.enabled ?? true,
      config: input.config,
    }),
  })
  return parseResponse<SubAgentConfigSummary>(response)
}

export async function updateSubAgentConfig(
  configId: string,
  input: SubAgentConfigInput,
): Promise<SubAgentConfigSummary> {
  const response = await fetch(`${env.appApiBase}/agent-config/subagent-configs/${configId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.userId,
      name: input.name,
      model: input.model || null,
      selected_tool_names: input.selectedToolNames ?? [],
      description: input.description || null,
      custom_system_prompt: input.customSystemPrompt || null,
      system_prompt_filename: input.systemPromptFilename || null,
      enabled: input.enabled ?? true,
      config: input.config,
    }),
  })
  return parseResponse<SubAgentConfigSummary>(response)
}
