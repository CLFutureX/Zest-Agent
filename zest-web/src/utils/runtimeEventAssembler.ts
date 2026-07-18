import type {
  RuntimeEvent,
  StreamAccumulator,
  RuntimeEventResult,
  TimelineKind,
} from '../types/runtimeEvents'
import type { TimelineSection } from '../types/workspace'

// Helpers
function asString(v: unknown): string | null {
  return typeof v === 'string' && v.trim() ? v : null
}

function asNumber(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

function readContentText(v: unknown): string | null {
  if (typeof v === 'string') return v
  if (Array.isArray(v)) {
    const t = v
      .map((i) => {
        if (typeof i === 'string') return i
        if (i && typeof i === 'object' && 'text' in i)
          return typeof i.text === 'string' ? i.text : ''
        return ''
      })
      .join('')
      .trim()
    return t || null
  }
  return null
}

function readObj(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null
}

// Resolve kind: message | action | observation | status
function resolveKind(event: RuntimeEvent): TimelineKind {
  if (event.type === 'tool_call') return 'action'
  if (event.type === 'tool_result' || event.type === 'observation')
    return 'observation'
  if (
    event.type === 'error' ||
    event.type === 'system' ||
    event.type === 'confirmation' ||
    event.type === 'agent_state_changed' ||
    event.type === 'status_update'
  )
    return 'status'
  // Check for structured action/observation patterns
  if (event.source === 'agent' && event.action) return 'action'
  if (event.source === 'environment' && event.observation) return 'observation'
  return 'message'
}

function resolveRole(event: RuntimeEvent): StreamAccumulator['role'] {
  if (event.role === 'user') return 'user'
  if (
    event.type === 'error' ||
    event.type === 'system' ||
    event.source === 'environment'
  )
    return 'system'
  return 'assistant'
}

function resolveToolName(event: RuntimeEvent): string | null {
  return (
    asString(event.tool_name) ??
    asString(event.name) ??
    asString(event.tool) ??
    asString(event.action_type)
  )
}

function resolveStreamId(event: RuntimeEvent): string {
  return (
    asString(event.message_id) ??
    asString(event.id) ??
    asString(event.event_id) ??
    asString(event.tool_call_id) ??
    `${Date.now()}-${Math.random()}`
  )
}

function resolvePairId(
  event: RuntimeEvent,
  kind: TimelineKind,
): string | null {
  if (kind === 'action')
    return asString(event.tool_call_id) ?? asString(event.id)
  if (kind === 'observation')
    return asString(event.tool_call_id) ?? asString(event.action_id)
  return null
}

function extractEventText(event: RuntimeEvent): string | null {
  return (
    asString(event.delta) ??
    asString(event.text) ??
    asString(event.content) ??
    readContentText(event.content) ??
    asString(event.message)
  )
}

// Section builders per event kind
function buildSections(
  event: RuntimeEvent,
  kind: TimelineKind,
): TimelineSection[] {
  const action = readObj(event.action)
  const observation = readObj(event.observation)

  // Action sections
  if (kind === 'action' && action) {
    const k = asString(action.kind) ?? ''
    if (k.includes('ExecuteBash'))
      return [{ label: 'Command', value: asString(action.command) ?? '', code: true }].filter(
        (s) => s.value,
      )
    if (k.includes('FileEditor') || k.includes('StrReplace'))
      return [
        { label: 'Command', value: asString(action.command) ?? '' },
        { label: 'Path', value: asString(action.path) ?? '' },
      ].filter((s) => s.value)
    if (k.includes('TaskTracker'))
      return [
        { label: 'Command', value: asString(action.command) ?? '' },
        { label: 'Tasks', value: `${Array.isArray(action.task_list) ? action.task_list.length : 0}` },
      ]
    if (k.includes('MCPTool'))
      return [{ label: 'Args', value: JSON.stringify(action.data ?? {}, null, 2), code: true }]
    if (k.includes('Think'))
      return [{ label: 'Thought', value: asString(action.thought) ?? '' }].filter((s) => s.value)
    if (k.includes('Finish'))
      return [{ label: 'Message', value: asString(action.message) ?? '' }].filter((s) => s.value)
    if (k.startsWith('Browser'))
      return [
        { label: 'Action', value: k.replace('Action', '') },
        { label: 'URL', value: asString(action.url) ?? '' },
      ].filter((s) => s.value)
    return []
  }

  // Observation sections
  if (kind === 'observation' && observation) {
    const k = asString(observation.kind) ?? ''
    if (k.includes('ExecuteBash')) {

      const code = asNumber(observation.exit_code)

      return [

        { label: 'Command', value: asString(observation.command) ?? '', code: true },

        {

          label: 'Exit',

          value: code === null ? 'running' : `${code}`,

          tone: code === 0 ? ('success' as const) : code === null ? ('warning' as const) : ('error' as const),

        },

        { label: 'Output', value: asString(observation.output) ?? '', code: true },

      ].filter((s) => s.value)

    }

    if (k.includes('FileEditor') || k.includes('StrReplace'))

      return [

        { label: 'Command', value: asString(observation.command) ?? '' },

        { label: 'Path', value: asString(observation.path) ?? '' },

      ].filter((s) => s.value)

    if (k.includes('Browser'))

      return [

        { label: 'Output', value: asString(observation.output) ?? '' },

        { label: 'Error', value: asString(observation.error) ?? '', tone: 'error' as const },

      ].filter((s) => s.value)
    if (k.includes('TaskTracker'))
      return [
        { label: 'Command', value: asString(observation.command) ?? '' },
        { label: 'Tasks', value: `${Array.isArray(observation.task_list) ? observation.task_list.length : 0}` },
      ]
    if (k.includes('Finish') || k.includes('Think'))
      return [{ label: 'Result', value: asString(observation.message) ?? asString(observation.content) ?? '' }].filter(
        (s) => s.value,
      )
    if (k.includes('MCPTool'))
      return [{ label: 'Tool', value: asString(observation.tool_name) ?? '' }].filter((s) => s.value)
    return []
  }

  // Status sections
  if (kind === 'status')
    return [
      {
        label: 'Status',
        value:
          asString(event.agent_status) ??
          asString(event.status) ??
          asString(event.message) ??
          '',
      },
    ].filter((s) => s.value)

  return []
}

function buildSummary(
  event: RuntimeEvent,
  kind: TimelineKind,
  fallback: string,
): string {
  const action = readObj(event.action)
  const observation = readObj(event.observation)

  if (kind === 'action' && action) {
    const k = asString(action.kind) ?? ''
    if (k.includes('ExecuteBash')) return asString(action.command) ?? fallback
    if (k.includes('FileEditor') || k.includes('StrReplace'))
      return `${asString(action.command) ?? 'edit'} ${asString(action.path) ?? ''}`.trim()
    if (k.includes('Think')) return asString(action.thought) ?? 'Thinking'
    if (k.includes('Finish')) return asString(action.message) ?? 'Finished'
    if (k.startsWith('Browser'))
      return `${k.replace('Action', '')} ${asString(action.url) ?? ''}`.trim()
  }
  if (kind === 'observation' && observation) {
    const k = asString(observation.kind) ?? ''
    if (k.includes('ExecuteBash')) return asString(observation.command) ?? 'Command result'
    if (k.includes('FileEditor') || k.includes('StrReplace'))
      return `${asString(observation.command) ?? 'edit'} ${asString(observation.path) ?? ''}`.trim()
    if (k.includes('Finish')) return asString(observation.message) ?? 'Finished'
  }
  if (kind === 'status')
    return asString(event.agent_status) ?? asString(event.status) ?? fallback
  return fallback
}

function isStreamingAssistantMessage(
  event: RuntimeEvent,
  kind: TimelineKind,
  text: string,
) {
  if (kind !== 'message') return false
  if (event.type === 'message' || event.type === 'delta' || event.type === 'chunk') return true
  if (event.role === 'assistant' || event.role === 'agent') return true
  return text.length < 240
}

function makeEntry(
  event: RuntimeEvent,
  body: string,
  id: string,
  paired: boolean,
): StreamAccumulator {
  const kind = resolveKind(event)
  const summary = buildSummary(event, kind, body)
  return {
    id,
    role: resolveRole(event),
    kind,
    title: resolveToolName(event) ? `Tool · ${resolveToolName(event)}` : kind === 'status' ? 'Status' : kind === 'action' ? 'Action' : kind === 'observation' ? 'Observation' : summary,
    body,
    rawEvent: event,
    pairId: resolvePairId(event, kind),
    paired,
    toolName: resolveToolName(event),
    summary,
    sections: buildSections(event, kind),
    success:
      kind === 'observation'
        ? buildSections(event, kind).some((s) => s.tone === 'success')
          ? 'success'
          : buildSections(event, kind).some((s) => s.tone === 'error')
            ? 'error'
            : undefined
        : undefined,
  }
}

export function buildTimelineEntryFromRuntimeEvent(
  event: RuntimeEvent,
): RuntimeEventResult {
  const text = extractEventText(event)
  const kind = resolveKind(event)
  const role = resolveRole(event)

  if (!text) {
    return {
      mode: 'append',
      entry: makeEntry(
        event,
        JSON.stringify(event, null, 2),
        `${Date.now()}-${Math.random()}`,
        false,
      ),
    }
  }

  if (isStreamingAssistantMessage(event, kind, text) && role === 'assistant') {
    return {
      mode: 'upsert',
      entry: makeEntry(event, text, resolveStreamId(event), false),
    }
  }

  return {
    mode: 'append',
    entry: makeEntry(
      event,
      text,
      `${resolveStreamId(event)}-${Date.now()}`,
      false,
    ),
  }
}
