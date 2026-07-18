import type { ZestEvent } from '../types/zest'
import type { ConversationEventRecord } from '../types/workspace'

// 事件图按主体划分泳道，便于观察用户、Agent、工具和系统之间的流转。
export type EventGraphLane = 'user' | 'agent' | 'tool' | 'system'

// 事件图节点的语义类型，用于决定节点样式和筛选行为。
export type EventGraphKind = 'message' | 'action' | 'observation' | 'status' | 'error'

// 节点状态用于补充展示执行中的工具调用、已完成结果和错误事件。
export type EventGraphStatus = 'idle' | 'running' | 'done' | 'error'

// 前端事件图使用的标准节点结构，统一承载历史事件和实时事件。
export type EventGraphNode = {
  id: string
  lane: EventGraphLane
  kind: EventGraphKind
  status: EventGraphStatus
  title: string
  subtitle?: string
  timestamp: string
  source: string
  eventType: string
  toolName?: string
  toolCallId?: string
  filePath?: string
  relationKey?: string
  summary?: string
  toolArgs?: string
  toolResult?: string
  exitCode?: number | null
  aggregateCount: number
  rawPayload: Record<string, unknown>
  rawText: string
}

// 统一把未知值转换成字符串，兼容字符串数组和富文本数组。
function asStr(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'text' in item) {
          return String((item as { text?: unknown }).text ?? '')
        }
        return ''
      })
      .join('')
      .trim()
  }

  return ''
}

// 安全读取对象，避免直接对未知值取属性。
function readObj(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

// 为详情面板准备可读文本，复杂对象统一转成格式化 JSON。
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

// 节点上的摘要需要控制长度，避免右侧面板被长文本撑爆。
function shorten(value: string | undefined, maxLength = 72): string | undefined {
  if (!value) return undefined
  const compact = value.replace(/\s+/g, ' ').trim()
  if (!compact) return undefined
  if (compact.length <= maxLength) return compact
  return `${compact.slice(0, maxLength - 1)}…`
}

// 兼容历史事件和实时事件里不同的 kind 字段命名。
function normalizeKind(payload: Record<string, unknown>, fallback = ''): string {
  return asStr(payload.kind || payload.event_type || payload.type) || fallback
}

// 用户消息既可能来自 llm_message.role，也可能来自外层 source/role。
function isUserPayload(payload: Record<string, unknown>, source: string): boolean {
  const llmMessage = readObj(payload.llm_message)
  if (llmMessage && asStr(llmMessage.role) === 'user') return true
  if (asStr(payload.role) === 'user') return true
  return asStr(payload.source ?? source) === 'user'
}

// 工具名来自后端枚举，转成更易读的前端标签。
function formatToolLabel(kind: string | undefined): string | undefined {
  if (!kind) return undefined
  return kind
    .replace(/Observation$/, '')
    .replace(/Action$/, '')
    .replace(/([A-Z])/g, ' $1')
    .trim()
}

// 从多种事件结构中提取一段最能代表当前节点的文本。
function extractPayloadText(payload: Record<string, unknown>): string {
  const llmMessage = readObj(payload.llm_message)
  if (llmMessage) {
    const content = asStr(llmMessage.content)
    if (content) return content
  }

  const action = readObj(payload.action)
  if (action) {
    const actionMessage = asStr(action.message)
    if (actionMessage) return actionMessage
  }

  const observation = readObj(payload.observation)
  if (observation) {
    const output =
      asStr(observation.output) || asStr(observation.content) || asStr(observation.message)
    if (output) return output
  }

  return (
    asStr(payload.delta) ||
    asStr(payload.text) ||
    asStr(payload.content) ||
    asStr(payload.message) ||
    asStr(payload.detail) ||
    asStr(payload.error) ||
    ''
  )
}

// 文件编辑类事件需要额外提取 path，用于节点副标题和详情展示。
function extractFilePath(payload: Record<string, unknown>): string | undefined {
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

  return undefined
}

// 先判断事件语义类型，再决定节点颜色、筛选和详情展示。
function resolveKind(payload: Record<string, unknown>, source: string, eventType: string): EventGraphKind {
  if (eventType === 'ActionEvent') return 'action'
  if (eventType === 'ObservationEvent') return 'observation'
  if (eventType.includes('Error') || payload.error || payload.detail) return 'error'
  if (isUserPayload(payload, source) || payload.llm_message || payload.message || payload.delta) {
    return 'message'
  }
  return 'status'
}

// 节点泳道按主体划分，优先把工具调用和结果归到 Tool。 
function resolveLane(kind: EventGraphKind, payload: Record<string, unknown>, source: string): EventGraphLane {
  if (kind === 'message' && isUserPayload(payload, source)) return 'user'
  if (kind === 'action' || kind === 'observation' || payload.tool_name) return 'tool'
  if (source === 'agent') return 'agent'
  return 'system'
}

// 状态用于强调 action 正在执行、observation 已返回，以及错误分支。
function resolveStatus(
  kind: EventGraphKind,
  payload: Record<string, unknown>,
  exitCode: number | null,
): EventGraphStatus {
  if (kind === 'error') return 'error'
  if (kind === 'action') return 'running'
  if (kind === 'observation') {
    if (typeof exitCode === 'number' && exitCode !== 0) return 'error'
    return 'done'
  }
  if (typeof exitCode === 'number' && exitCode !== 0) return 'error'
  if (payload.agent_status || payload.status) return 'done'
  return 'idle'
}

// 标题只展示最关键的信息，避免节点视觉噪音过大。
function buildTitle(
  kind: EventGraphKind,
  lane: EventGraphLane,
  eventType: string,
  payloadText: string,
  toolName: string | undefined,
  actionKind: string | undefined,
  observationKind: string | undefined,
): string {
  if (kind === 'message') {
    return shorten(payloadText, 54) || (lane === 'user' ? 'User message' : 'Assistant message')
  }

  if (kind === 'action') {
    return toolName || formatToolLabel(actionKind) || 'Tool action'
  }

  if (kind === 'observation') {
    return toolName || formatToolLabel(observationKind) || 'Tool result'
  }

  if (kind === 'error') {
    return toolName || formatToolLabel(actionKind) || eventType || 'Error event'
  }

  return eventType || 'State update'
}

// 副标题补充参数、文件路径或退出码，让节点信息更完整但不过载。
function buildSubtitle(
  kind: EventGraphKind,
  payload: Record<string, unknown>,
  payloadText: string,
  filePath: string | undefined,
  exitCode: number | null,
): string | undefined {
  if (kind === 'message') {
    return filePath || shorten(payload.source as string | undefined, 24)
  }

  if (kind === 'action') {
    const action = readObj(payload.action)
    return filePath || shorten(stringifyData(action?.args ?? action?.arguments ?? action?.input), 62)
  }

  if (kind === 'observation') {
    if (typeof exitCode === 'number') return `exit ${exitCode}`
    return filePath || shorten(payloadText, 62) || 'Tool returned a result'
  }

  if (kind === 'error') {
    return filePath || shorten(asStr(payload.error) || asStr(payload.detail) || payloadText, 62)
  }

  return shorten(payloadText, 62) || shorten(stringifyData(payload.value), 62)
}

// relationKey 用来把同一工具调用或同一状态更新串成一组，供高亮联动使用。
function buildRelationKey(
  kind: EventGraphKind,
  payload: Record<string, unknown>,
  toolCallId: string | undefined,
  eventType: string,
): string | undefined {
  if (toolCallId) return `tool:${toolCallId}`
  if (kind === 'status') {
    const key = asStr(payload.key) || eventType
    return key ? `status:${key}` : undefined
  }
  return undefined
}

// 把单条历史/实时事件归一化成事件图节点。
function toNode(
  id: string,
  timestamp: string,
  source: string,
  payload: Record<string, unknown>,
): EventGraphNode {
  const eventType = normalizeKind(payload)
  const action = readObj(payload.action)
  const observation = readObj(payload.observation)
  const payloadText = extractPayloadText(payload)
  const toolName = asStr(payload.tool_name) || asStr(action?.kind) || asStr(observation?.kind) || undefined
  const toolCallId = asStr(payload.tool_call_id) || undefined
  const filePath = extractFilePath(payload)
  const exitCode =
    typeof observation?.exit_code === 'number'
      ? observation.exit_code
      : typeof payload.exit_code === 'number'
        ? payload.exit_code
        : null

  const kind = resolveKind(payload, source, eventType)
  const lane = resolveLane(kind, payload, source)
  const actionKind = asStr(action?.kind) || undefined
  const observationKind = asStr(observation?.kind) || undefined
  const status = resolveStatus(kind, payload, exitCode)

  return {
    id,
    lane,
    kind,
    status,
    title: buildTitle(kind, lane, eventType, payloadText, toolName, actionKind, observationKind),
    subtitle: buildSubtitle(kind, payload, payloadText, filePath, exitCode),
    timestamp,
    source,
    eventType,
    toolName,
    toolCallId,
    filePath,
    relationKey: buildRelationKey(kind, payload, toolCallId, eventType),
    summary: shorten(payloadText, 220),
    toolArgs: action ? stringifyData(action.args ?? action.arguments ?? action.input) : undefined,
    toolResult: observation
      ? stringifyData(
          observation.content ??
            observation.output ??
            observation.message ??
            observation.metadata ??
            observation.extras,
        )
      : undefined,
    exitCode,
    aggregateCount: 1,
    rawPayload: payload,
    rawText: stringifyData(payload) || '',
  }
}

// 重复合并只针对非消息类节点，避免把正常对话内容错误折叠。
function canMergeNodes(previous: EventGraphNode, next: EventGraphNode): boolean {
  if (previous.kind === 'message' || next.kind === 'message') return false
  if (previous.kind === 'error' || next.kind === 'error') return false

  if (previous.toolCallId && previous.toolCallId === next.toolCallId && previous.kind === next.kind) {
    return true
  }

  return (
    previous.lane === next.lane &&
    previous.kind === next.kind &&
    previous.title === next.title &&
    previous.subtitle === next.subtitle &&
    previous.eventType === next.eventType
  )
}

// 连续重复节点会被压缩成一个节点，减少图中过密的状态噪音。
function mergeNodes(nodes: EventGraphNode[]): EventGraphNode[] {
  const merged: EventGraphNode[] = []

  nodes.forEach((node) => {
    const previous = merged[merged.length - 1]
    if (!previous || !canMergeNodes(previous, node)) {
      merged.push(node)
      return
    }

    previous.timestamp = node.timestamp
    previous.summary = node.summary || previous.summary
    previous.subtitle = node.subtitle || previous.subtitle
    previous.toolArgs = previous.toolArgs || node.toolArgs
    previous.toolResult = previous.toolResult || node.toolResult
    previous.exitCode = node.exitCode ?? previous.exitCode
    previous.rawPayload = node.rawPayload
    previous.rawText = node.rawText
    previous.status = node.status === 'error' ? 'error' : node.status || previous.status
    previous.aggregateCount += node.aggregateCount
  })

  return merged
}

// 时间戳异常时退回顺序索引，保证展示顺序稳定。
function readTimestamp(value: string, fallback: number): number {
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? fallback : parsed
}

// 统一合并历史事件和实时事件，排序后输出给事件图视图层使用。
export function buildEventGraphNodes(
  historicalRecords: ConversationEventRecord[],
  liveEvents: ZestEvent[],
  mergeRepeated: boolean,
): EventGraphNode[] {
  const mergedEntries = new Map<
    string,
    {
      id: string
      timestamp: string
      source: string
      payload: Record<string, unknown>
      sequence: number
    }
  >()

  historicalRecords.forEach((record, index) => {
    mergedEntries.set(record.event_id, {
      id: record.event_id,
      timestamp: record.timestamp,
      source: asStr(record.source),
      payload: record.payload,
      sequence: index,
    })
  })

  liveEvents.forEach((event, index) => {
    mergedEntries.set(String(event.id), {
      id: String(event.id),
      timestamp: event.timestamp,
      source: asStr(event.source),
      payload: event as unknown as Record<string, unknown>,
      sequence: historicalRecords.length + index,
    })
  })

  const nodes = Array.from(mergedEntries.values())
    .sort((left, right) => {
      const leftTime = readTimestamp(left.timestamp, left.sequence)
      const rightTime = readTimestamp(right.timestamp, right.sequence)
      if (leftTime === rightTime) return left.sequence - right.sequence
      return leftTime - rightTime
    })
    .map((entry) => toNode(entry.id, entry.timestamp, entry.source, entry.payload))

  return mergeRepeated ? mergeNodes(nodes) : nodes
}
