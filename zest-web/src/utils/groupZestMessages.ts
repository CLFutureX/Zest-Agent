/**
 * groupZestMessages.ts
 *
 * Converts ConversationEventRecord[] (history) and ZestEvent[] (realtime)
 * into deer-flow-style ZestMessageGroup[] for unified rendering.
 *
 * Group types:
 *   human              — user text messages
 *   assistant          — assistant text reply (Markdown)
 *   assistant:processing — tool calls / action-observation pairs
 *   assistant:present-files — file cards produced by write/edit tools
 */
import type { ZestEvent } from '../types/zest'
import type { ConversationEventRecord } from '../types/workspace'

export type ZestMessageRole = 'user' | 'assistant' | 'system'

export type ZestMessageGroupType =
  | 'human'
  | 'assistant'
  | 'assistant:processing'
  | 'assistant:present-files'

export interface ZestMessage {
  id: string
  role: ZestMessageRole
  content: string
  timestamp: string
  toolName?: string
  toolCallId?: string
  actionKind?: string
  eventType?: string
  filePath?: string
  thought?: string
  reasoningContent?: string
  toolArgs?: string
  toolResult?: string
  exitCode?: number | null
  commandOutput?: string
  source?: string
  rawKind?: string
  hidden?: boolean
}

export interface ZestMessageGroup {
  id: string
  type: ZestMessageGroupType
  messages: ZestMessage[]
}

function asStr(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    return value
      .map((item) =>
        typeof item === 'string'
          ? item
          : item && typeof item === 'object' && 'text' in item
            ? String(item.text)
            : '',
      )
      .join('')
      .trim()
  }
  return ''
}

function readObj(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function stringifyData(value: unknown): string | undefined {
  if (value == null) return undefined
  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed || undefined
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return undefined
  }
}

function normalizeKind(payload: Record<string, unknown>): string {
  return asStr(payload.kind || payload.event_type || payload.type)
}

function extractThought(payload: Record<string, unknown>): string | undefined {
  const thought =
    asStr(payload.thought) ||
    (Array.isArray(payload.thought)
      ? (payload.thought as Array<{ type: string; text: string }>)
          .filter((item) => item.type === 'text')
          .map((item) => item.text)
          .join('\n')
      : '')

  return thought || undefined
}

function extractReasoningContent(payload: Record<string, unknown>): string | undefined {
  return asStr(payload.reasoning_content) || undefined
}

function extractPayloadText(payload: Record<string, unknown>): string {
  const llm = readObj(payload.llm_message)
  if (llm) {
    const content = asStr(llm.content)
    if (content) return content
  }

  const action = readObj(payload.action)
  if (action) {
    const actionMessage = asStr(action.message)
    if (actionMessage) return actionMessage
  }

  const observation = readObj(payload.observation)
  if (observation) {
    const observationText =
      asStr(observation.output) || asStr(observation.content) || asStr(observation.message)
    if (observationText) return observationText
  }

  return (
    asStr(payload.delta) ||
    asStr(payload.text) ||
    asStr(payload.content) ||
    asStr(payload.message) ||
    ''
  )
}

function extractFilePath(payload: Record<string, unknown>): string | null {
  const action = readObj(payload.action)
  if (action) {
    const kind = asStr(action.kind)
    if (kind.includes('FileEditor') || kind.includes('StrReplace')) {
      const path = asStr(action.path)
      if (path) return path
    }
  }

  const observation = readObj(payload.observation)
  if (observation) {
    const kind = asStr(observation.kind)
    if (kind.includes('FileEditor') || kind.includes('StrReplace')) {
      const path = asStr(observation.path)
      if (path) return path
    }
  }

  return null
}

function isHumanPayload(payload: Record<string, unknown>): boolean {
  const llm = readObj(payload.llm_message)
  if (llm && asStr(llm.role) === 'user') return true
  if (asStr(payload.role) === 'user') return true
  return asStr(payload.source ?? payload.event_source) === 'user'
}

function isHiddenPayload(payload: Record<string, unknown>): boolean {
  const kind = normalizeKind(payload)
  const action = readObj(payload.action)
  const observation = readObj(payload.observation)

  if (kind === 'SystemPromptEvent') return true
  if (kind === 'ActionEvent' && asStr(action?.kind) === 'ThinkAction') return true
  if (kind === 'ObservationEvent' && asStr(observation?.kind) === 'ThinkObservation') return true

  return false
}

function isPresentFilesPayload(payload: Record<string, unknown>): boolean {
  return extractFilePath(payload) !== null
}

function isProcessingPayload(payload: Record<string, unknown>): boolean {
  const kind = normalizeKind(payload)
  if (kind === 'ActionEvent' || kind === 'ObservationEvent') return true

  const action = readObj(payload.action)
  if (!action) return false

  const actionKind = asStr(action.kind)
  if (!actionKind) return false

  return actionKind !== 'MessageAction'
}

function classifyPayload(payload: Record<string, unknown>): ZestMessageGroupType {
  if (isHumanPayload(payload)) return 'human'
  if (isPresentFilesPayload(payload)) return 'assistant:present-files'
  if (isProcessingPayload(payload)) return 'assistant:processing'
  return 'assistant'
}

function hasRenderableMessageContent(message: ZestMessage, type: ZestMessageGroupType): boolean {
  if (message.hidden) return false
  if (type === 'assistant:processing' || type === 'assistant:present-files') return true
  if (message.role === 'user') return Boolean(message.content.trim())

  return Boolean(
    message.content.trim()
    || message.reasoningContent?.trim()
    || message.thought?.trim(),
  )
}
 

function recordToMessage(record: ConversationEventRecord): ZestMessage {
  const payload = record.payload
  const action = readObj(payload.action)
  const observation = readObj(payload.observation)
  const kind = normalizeKind(payload)

  return {
    id: record.event_id,
    role: isHumanPayload(payload) ? 'user' : 'assistant',
    content: extractPayloadText(payload),
    timestamp: record.timestamp,
    toolName: asStr(payload.tool_name) || (action ? asStr(action.kind) : '') || undefined,
    toolCallId: asStr(payload.tool_call_id) || undefined,
    actionKind: action ? asStr(action.kind) || undefined : undefined,
    eventType: kind || undefined,
    filePath: extractFilePath(payload) || undefined,
    thought: extractThought(payload),
    reasoningContent: extractReasoningContent(payload),
    toolArgs: action ? stringifyData(action.args ?? action.arguments ?? action.input) : undefined,
    toolResult: observation
      ? stringifyData(
          observation.content ??
            observation.output ??
            observation.message ??
            observation.metadata ??
            observation.extras,
        )
      : stringifyData(payload.observation ?? payload.result),
    commandOutput: observation
      ? asStr(observation.output) || asStr(observation.content) || undefined
      : undefined,
    exitCode:
      observation && typeof observation.exit_code === 'number'
        ? observation.exit_code
        : typeof payload.exit_code === 'number'
          ? payload.exit_code
          : null,
    source: asStr(payload.source ?? record.source) || undefined,
    rawKind: kind || undefined,
    hidden: isHiddenPayload(payload),
  }
}

function liveEventToMessage(event: ZestEvent): ZestMessage {
  return recordToMessage({
    event_id: String(event.id),
    conversation_id: '',
    event_type: asStr(event.kind ?? event.type),
    source: asStr(event.source),
    timestamp: event.timestamp,
    payload: event as unknown as Record<string, unknown>,
  })
}

function groupMessages(messages: ZestMessage[], types: ZestMessageGroupType[]): ZestMessageGroup[] {
  const visibleEntries = messages
    .map((message, index) => ({ message, type: types[index]! }))
    .filter((entry) => hasRenderableMessageContent(entry.message, entry.type))

  const groups: ZestMessageGroup[] = []

  visibleEntries.forEach(({ message, type }) => {
    const last = groups[groups.length - 1]

    if (type === 'assistant:processing' && last?.type === 'assistant:processing') {
      last.messages.push(message)
      return
    }

    if (type === 'assistant:present-files' && last?.type === 'assistant:present-files') {
      last.messages.push(message)
      return
    }

    groups.push({ id: message.id, type, messages: [message] })
  })

  return groups
}

export function groupConversationRecords(records: ConversationEventRecord[]): ZestMessageGroup[] {
  const messages = records.map(recordToMessage)
  const types = records.map((record) => classifyPayload(record.payload))
  return groupMessages(messages, types)
}

export function groupLiveEvents(events: ZestEvent[]): ZestMessageGroup[] {
  const messages = events.map(liveEventToMessage)
  const types = events.map((event) => classifyPayload(event as unknown as Record<string, unknown>))
  return groupMessages(messages, types)
}
