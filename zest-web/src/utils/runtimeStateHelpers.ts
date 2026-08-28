import type { RuntimeEvent } from '../types/runtimeEvents'
import type { ZestEvent } from '../types/zest'
import type { ConfirmationState, RuntimeAgentStatus } from '../types/runtimeState'
import {
  isActionEvent,
  isAgentErrorEvent,
  isAgentStateUpdateEvent,
  isConversationErrorEvent,
  isConversationStateUpdateEvent,
  isMessageEvent,
} from '../types/zestGuards'

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function readTextContent(value: unknown): string | null {
  if (typeof value === 'string') {
    return value.trim() || null
  }

  if (!Array.isArray(value)) {
    return null
  }

  const text = value
    .map((item) => {
      if (typeof item === 'string') return item
      if (item && typeof item === 'object' && 'text' in item) {
        return typeof item.text === 'string' ? item.text : ''
      }
      return ''
    })
    .join('')
    .trim()

  return text || null
}

function normalizeStatus(value: unknown): RuntimeAgentStatus | null {
  const raw = asString(value)?.toLowerCase()
  if (!raw) return null

  if (
    raw === 'idle'
    || raw === 'running'
    || raw === 'paused'
    || raw === 'waiting_for_confirmation'
    || raw === 'finished'
    || raw === 'error'
    || raw === 'stuck'
  ) {
    return raw
  }

  return 'unknown'
}

function isZestEvent(event: RuntimeEvent): event is ZestEvent {
  return !!event && typeof event === 'object' && typeof event.id === 'string' && typeof event.source === 'string'
}

export function extractRuntimeStatus(event: RuntimeEvent): RuntimeAgentStatus | null {
  if (!isZestEvent(event)) {
    return null
  }

  if (isConversationStateUpdateEvent(event)) {
    if (event.key === 'execution_status') {
      return normalizeStatus(event.value)
    }

    if (event.key === 'full_state') {
      const state = asRecord(event.value)
      const mainAgentState = asRecord(state?.main_agent_state)
      return normalizeStatus(mainAgentState?.execution_status ?? state?.execution_status)
    }
  }

  if (isAgentStateUpdateEvent(event) && event.key === 'execution_status') {
    return normalizeStatus(event.value)
  }

  if (isConversationErrorEvent(event) || isAgentErrorEvent(event)) {
    return 'error'
  }

  return null
}

export function extractLatestMessageText(event: RuntimeEvent): string | null {
  if (!isZestEvent(event)) {
    return null
  }

  if (isMessageEvent(event)) {
    return readTextContent(event.llm_message.content)
  }

  if (isConversationErrorEvent(event)) {
    return event.detail
  }

  if (isAgentErrorEvent(event)) {
    return event.error
  }

  if ('message' in event) {
    return asString(event.message)
  }

  return null
}

export function extractTodosFromEvent(event: RuntimeEvent): Array<{ content: string; status: string }> | null {
  if (!isZestEvent(event)) {
    return null
  }

  if (!isConversationStateUpdateEvent(event) || event.key !== 'full_state') {
    return null
  }

  const state = asRecord(event.value)
  const mainAgentState = asRecord(state?.main_agent_state)
  const rawTodos = mainAgentState?.todos
  if (!Array.isArray(rawTodos)) {
    return null
  }

  return rawTodos
    .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
    .map((item) => ({
      content: String(item.content ?? ''),
      status: String(item.status ?? 'pending'),
    }))
}

export function extractConfirmationState(event: RuntimeEvent): ConfirmationState | null {
  if (!isZestEvent(event)) {
    return null
  }

  const status = extractRuntimeStatus(event)
  if (status && status !== 'waiting_for_confirmation') {
    return {
      pending: false,
      actionId: null,
      toolName: null,
      toolCallId: null,
      summary: null,
    }
  }

  if (!isActionEvent(event)) {
    if (status === 'waiting_for_confirmation') {
      return {
        pending: true,
        actionId: null,
        toolName: null,
        toolCallId: null,
        summary: '等待人工确认后继续执行',
      }
    }
    return null
  }

  const action = asRecord(event.action)
  if (asString(action?.confirmation_state) !== 'awaiting_confirmation') {
    return null
  }

  return {
    pending: true,
    actionId: event.id,
    toolName: event.tool_name,
    toolCallId: event.tool_call_id,
    summary:
      asString(action?.command)
      ?? asString(action?.path)
      ?? asString(action?.message)
      ?? asString(action?.kind)
      ?? null,
    actionArgs: action ?? null,
  }
}

export function formatRuntimeMeta(input: {
  conversationId?: string | null
  agentStatus: RuntimeAgentStatus
  latestMessage: string
  confirmation: ConfirmationState
}): string {
  const parts: string[] = []

  if (input.conversationId) {
    parts.push(`conversation=${input.conversationId}`)
  }

  parts.push(`status=${input.agentStatus}`)

  if (input.confirmation.pending) {
    parts.push('需要人工确认')
    if (input.confirmation.toolName) {
      parts.push(`tool=${input.confirmation.toolName}`)
    }
  }

  if (input.latestMessage) {
    parts.push(`latest=${input.latestMessage.slice(0, 80)}`)
  }

  return parts.join(' | ')
}
