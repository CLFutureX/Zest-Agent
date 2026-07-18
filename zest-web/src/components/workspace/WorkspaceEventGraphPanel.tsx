import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'

import type { ZestEvent } from '../../types/zest'
import type { ConversationEventRecord } from '../../types/workspace'
import {
  buildEventGraphNodes,
  type EventGraphKind,
  type EventGraphLane,
  type EventGraphNode,
} from '../../utils/buildEventGraph'

// 右侧面板当前提供的基础筛选能力。
type EventGraphFilter = 'all' | 'user' | 'action' | 'observation' | 'error'

// 事件图依赖完整的历史事件和 websocket 实时事件共同渲染。
type WorkspaceEventGraphPanelProps = {
  historicalRecords: ConversationEventRecord[]
  liveEvents: ZestEvent[]
}

// 泳道顺序决定节点横向布局和连接线落点。
const LANE_ORDER: EventGraphLane[] = ['user', 'agent', 'tool', 'system']

// 工具栏里的筛选按钮配置。
const FILTER_OPTIONS: Array<{ value: EventGraphFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'user', label: '用户' },
  { value: 'action', label: '调用' },
  { value: 'observation', label: '结果' },
  { value: 'error', label: '错误' },
]

// 统一格式化时间，保证节点和详情区展示一致。
function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return timestamp

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date)
}

// 节点角标使用更短的标签，避免占用过多卡片空间。
function formatKindLabel(kind: EventGraphKind): string {
  if (kind === 'message') return '消息'
  if (kind === 'action') return '调用'
  if (kind === 'observation') return '结果'
  if (kind === 'error') return '错误'
  return '状态'
}

// 筛选器基于泳道或语义类型过滤当前图上的节点。
function matchesFilter(node: EventGraphNode, filter: EventGraphFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'user') return node.lane === 'user'
  return node.kind === filter
}

// 起点和终点圆点仍然使用绝对定位，所以需要单独计算横向百分比。
function buildConnectorStyle(fromLane: EventGraphLane, toLane: EventGraphLane) {
  const fromIndex = LANE_ORDER.indexOf(fromLane)
  const toIndex = LANE_ORDER.indexOf(toLane)
  const fromCenter = 12.5 + fromIndex * 25
  const toCenter = 12.5 + toIndex * 25
  const left = Math.min(fromCenter, toCenter)
  const width = Math.abs(toCenter - fromCenter)

  return {
    from: { left: `${fromCenter}%` } as CSSProperties,
    across: { left: `${left}%`, width: `${width}%` } as CSSProperties,
    to: { left: `${toCenter}%` } as CSSProperties,
  }
}

// SVG 曲线让跨泳道流转更接近“拓扑图”而不是简单表格连线。
function buildConnectorPath(fromLane: EventGraphLane, toLane: EventGraphLane): string {
  const fromIndex = LANE_ORDER.indexOf(fromLane)
  const toIndex = LANE_ORDER.indexOf(toLane)
  const fromCenter = 12.5 + fromIndex * 25
  const toCenter = 12.5 + toIndex * 25
  const controlY = fromLane === toLane ? 32 : 18

  return `M ${fromCenter} 2 C ${fromCenter} ${controlY}, ${toCenter} ${controlY}, ${toCenter} 46`
}

// 内部泳道值转换成可展示标签，避免视图层散落判断逻辑。
function formatLaneLabel(lane: EventGraphLane): string {
  if (lane === 'user') return '用户'
  if (lane === 'agent') return 'Agent'
  if (lane === 'tool') return '工具'
  return '系统'
}

// 节点右上角状态标签优先体现执行状态，其次回退到主体泳道标签。
function formatStatusLabel(node: EventGraphNode): string {
  if (node.status === 'error') return '异常'
  if (node.status === 'running') return '进行中'
  if (node.status === 'done') return '完成'
  return formatLaneLabel(node.lane)
}

function formatDetailLabel(kind: EventGraphKind): string {
  if (kind === 'message') return '消息'
  if (kind === 'action') return '工具调用'
  if (kind === 'observation') return '工具结果'
  if (kind === 'error') return '错误事件'
  return '状态事件'
}

export function WorkspaceEventGraphPanel({
  historicalRecords,
  liveEvents,
}: WorkspaceEventGraphPanelProps) {
  const [filter, setFilter] = useState<EventGraphFilter>('all')
  const [mergeRepeated, setMergeRepeated] = useState(true)
  const [followLatest, setFollowLatest] = useState(true)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)

  // 仅保存最后一行引用，用于“跟随最新”自动滚动。
  const latestRowRef = useRef<HTMLDivElement | null>(null)

  // 事件图节点模型在视图层只计算一次，避免重复转换历史与实时数据。
  const nodes = useMemo(
    () => buildEventGraphNodes(historicalRecords, liveEvents, mergeRepeated),
    [historicalRecords, liveEvents, mergeRepeated],
  )

  // 筛选结果单独派生，方便后续扩展更多过滤条件。
  const filteredNodes = useMemo(
    () => nodes.filter((node) => matchesFilter(node, filter)),
    [nodes, filter],
  )

  // 当前选中节点失效时，默认退回到最新节点，保持详情区始终有内容。
  useEffect(() => {
    if (filteredNodes.length === 0) {
      setSelectedNodeId(null)
      return
    }

    if (!selectedNodeId || !filteredNodes.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(filteredNodes[filteredNodes.length - 1]!.id)
    }
  }, [filteredNodes, selectedNodeId])

  // 实时事件流入时，按开关决定是否自动滚动到最新一行。
  useEffect(() => {
    if (!followLatest) return
    latestRowRef.current?.scrollIntoView({ block: 'nearest' })
  }, [filteredNodes, followLatest])

  // hover 优先级高于 click，便于用户临时预览某个节点的上下游关系。
  const activeNodeId = hoveredNodeId ?? selectedNodeId
  const selectedNode = filteredNodes.find((node) => node.id === selectedNodeId) ?? null
  const activeNode = filteredNodes.find((node) => node.id === activeNodeId) ?? selectedNode
  const activeIndex = activeNode ? filteredNodes.findIndex((node) => node.id === activeNode.id) : -1
  const relatedKey = activeNode?.relationKey

  // 相关节点集合同时包含当前节点、前后相邻节点，以及同 relationKey 的节点。
  const relatedNodeIds = useMemo(() => {
    if (!activeNode) return new Set<string>()

    const ids = new Set<string>([activeNode.id])
    if (activeIndex > 0) ids.add(filteredNodes[activeIndex - 1]!.id)
    if (activeIndex >= 0 && activeIndex < filteredNodes.length - 1) ids.add(filteredNodes[activeIndex + 1]!.id)

    if (relatedKey) {
      filteredNodes.forEach((node) => {
        if (node.relationKey === relatedKey) ids.add(node.id)
      })
    }

    return ids
  }, [activeIndex, activeNode, filteredNodes, relatedKey])

  if (nodes.length === 0) {
    return (
      <div className="workspace-event-graph workspace-event-graph--empty">
        <div className="workspace-event-graph__empty-title">暂无事件链路</div>
        <p className="workspace-event-graph__empty-copy">
          当会话通过 WebSocket 收到事件后，这里会按角色和时间展示完整交互链路。
        </p>
      </div>
    )
  }

  return (
    <div className="workspace-event-graph">
      <div className="workspace-event-graph__toolbar">
        <div>
          <p className="workspace-event-graph__count">最近 {filteredNodes.length} / {nodes.length} 个事件</p>
        </div>
        <div className="workspace-event-graph__filters" role="tablist" aria-label="事件筛选">
          {FILTER_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`workspace-event-graph__filter${filter === option.value ? ' active' : ''}`}
              onClick={() => setFilter(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="workspace-event-graph__toggles">
          <label className="workspace-event-graph__toggle">
            <input
              type="checkbox"
              checked={mergeRepeated}
              onChange={(event) => setMergeRepeated(event.target.checked)}
            />
            <span>合并重复</span>
          </label>
          <label className="workspace-event-graph__toggle">
            <input
              type="checkbox"
              checked={followLatest}
              onChange={(event) => setFollowLatest(event.target.checked)}
            />
            <span>跟随最新</span>
          </label>
        </div>
      </div>

      <div className="workspace-event-graph__lanes">
        {LANE_ORDER.map((lane) => (
          <div key={lane} className="workspace-event-graph__lane-label">
            {formatLaneLabel(lane)}
          </div>
        ))}
      </div>

      <div className="workspace-event-graph__rows">
        {filteredNodes.length === 0 ? (
          <div className="workspace-event-graph__empty-state">当前筛选条件下没有匹配事件</div>
        ) : (
          filteredNodes.map((node, index) => {
            const previousNode = filteredNodes[index - 1]
            const connectorStyle = previousNode ? buildConnectorStyle(previousNode.lane, node.lane) : null
            const connectorPath = previousNode ? buildConnectorPath(previousNode.lane, node.lane) : null
            const isSelected = node.id === selectedNode?.id
            const isFocused = node.id === activeNode?.id
            const isRelated = relatedNodeIds.has(node.id) && !isFocused
            const connectorIsActive = Boolean(
              previousNode && activeNode && relatedNodeIds.has(previousNode.id) && relatedNodeIds.has(node.id),
            )
            const toolCallLabel = node.toolCallId ? node.toolCallId.slice(0, 10) : null

            // 节点卡片单独提成局部变量，避免 JSX 结构过深影响可读性。
            const nodeCard = (
              <button
                type="button"
                className={`workspace-event-node kind-${node.kind} status-${node.status}${isSelected ? ' is-selected' : ''}${isFocused ? ' is-focused' : ''}${isRelated ? ' is-related' : ''}`}
                onClick={() => setSelectedNodeId(node.id)}
                onMouseEnter={() => setHoveredNodeId(node.id)}
                onMouseLeave={() => setHoveredNodeId((current) => (current === node.id ? null : current))}
              >
                <span className="workspace-event-node__header">
                  <span className="workspace-event-node__badge">{formatKindLabel(node.kind)}</span>
                  <span className={`workspace-event-node__status status-${node.status}`}>{formatStatusLabel(node)}</span>
                </span>
                <span className="workspace-event-node__title" title={node.title}>{node.title}</span>
                {node.subtitle && <span className="workspace-event-node__subtitle" title={node.subtitle}>{node.subtitle}</span>}
                <span className="workspace-event-node__summary" title={node.summary || node.eventType || 'No summary'}>
                  {node.summary || node.eventType || 'No summary'}
                </span>
                <span className="workspace-event-node__meta">
                  {formatTime(node.timestamp)}
                  {node.aggregateCount > 1 ? ` · x${node.aggregateCount}` : ''}
                </span>
                <span className="workspace-event-node__footer">
                  <span className="workspace-event-node__event-type">{node.eventType || 'UnknownEvent'}</span>
                  {toolCallLabel && <span className="workspace-event-node__relation">{toolCallLabel}</span>}
                </span>
              </button>
            )

            return (
              <div
                key={node.id}
                className="workspace-event-graph__row"
                ref={index === filteredNodes.length - 1 ? latestRowRef : null}
              >
                {connectorStyle && (
                  // 连接层独立渲染，便于按 hover/selected 状态统一高亮整段链路。
                  <div
                    className={`workspace-event-graph__connector${connectorIsActive ? ' is-active' : ''}${previousNode?.lane !== node.lane ? ' is-cross-lane' : ''}`}
                    aria-hidden="true"
                  >
                    <span className="workspace-event-graph__connector-point workspace-event-graph__connector-point--from" style={connectorStyle.from} />
                    <svg className="workspace-event-graph__connector-svg" viewBox="0 0 100 48" preserveAspectRatio="none">
                      <path className="workspace-event-graph__connector-path workspace-event-graph__connector-path--glow" d={connectorPath ?? ''} />
                      <path className="workspace-event-graph__connector-path workspace-event-graph__connector-path--main" d={connectorPath ?? ''} />
                    </svg>
                    <span className="workspace-event-graph__connector-point workspace-event-graph__connector-point--to" style={connectorStyle.to} />
                  </div>
                )}
                {LANE_ORDER.map((lane) => (
                  <div key={lane} className="workspace-event-graph__lane-slot">
                    {lane === node.lane ? nodeCard : null}
                  </div>
                ))}
              </div>
            )
          })
        )}
      </div>

      <div className="workspace-event-graph__detail">
        {selectedNode ? (
          <>
            {/* 详情区固定展示当前 click 选中的节点，避免 hover 干扰阅读。 */}
            <div className="workspace-event-graph__detail-header">
              <span className={`workspace-event-graph__detail-kind kind-${selectedNode.kind}`}>
                {formatDetailLabel(selectedNode.kind)}
              </span>
              <span className="workspace-event-graph__detail-title">{selectedNode.title}</span>
            </div>

            <dl className="workspace-event-graph__detail-grid">
              <div>
                <dt>时间</dt>
                <dd>{formatTime(selectedNode.timestamp)}</dd>
              </div>
              <div>
                <dt>来源</dt>
                <dd>{selectedNode.source || 'unknown'}</dd>
              </div>
              <div>
                <dt>类型</dt>
                <dd>{selectedNode.eventType || 'unknown'}</dd>
              </div>
              <div>
                <dt>泳道</dt>
                <dd>{formatLaneLabel(selectedNode.lane)}</dd>
              </div>
              {selectedNode.toolName && (
                <div>
                  <dt>工具</dt>
                  <dd>{selectedNode.toolName}</dd>
                </div>
              )}
              {selectedNode.toolCallId && (
                <div>
                  <dt>调用 ID</dt>
                  <dd>{selectedNode.toolCallId}</dd>
                </div>
              )}
              {selectedNode.filePath && (
                <div className="workspace-event-graph__detail-wide">
                  <dt>文件</dt>
                  <dd>{selectedNode.filePath}</dd>
                </div>
              )}
              {selectedNode.summary && (
                <div className="workspace-event-graph__detail-wide">
                  <dt>摘要</dt>
                  <dd>{selectedNode.summary}</dd>
                </div>
              )}
              {selectedNode.toolArgs && (
                <div className="workspace-event-graph__detail-wide">
                  <dt>参数</dt>
                  <dd>
                    <pre>{selectedNode.toolArgs}</pre>
                  </dd>
                </div>
              )}
              {selectedNode.toolResult && (
                <div className="workspace-event-graph__detail-wide">
                  <dt>结果</dt>
                  <dd>
                    <pre>{selectedNode.toolResult}</pre>
                  </dd>
                </div>
              )}
              {selectedNode.exitCode !== undefined && selectedNode.exitCode !== null && (
                <div>
                  <dt>退出码</dt>
                  <dd>{selectedNode.exitCode}</dd>
                </div>
              )}
            </dl>

            <details className="workspace-event-graph__raw">
              <summary>展开原始 payload</summary>
              <pre>{selectedNode.rawText}</pre>
            </details>
          </>
        ) : (
          <div className="workspace-event-graph__detail-empty">选择一个事件查看详情</div>
        )}
      </div>
    </div>
  )
}
