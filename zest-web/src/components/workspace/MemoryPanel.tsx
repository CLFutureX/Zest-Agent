import { useEffect, useMemo, useState } from 'react'

import type { ConversationMemoryRecord } from '../../types/workspace'
import type { WorkspacePanelTab } from '../../hooks/useWorkspacePanel'

type MemoryPanelProps = {
  selectedTab: WorkspacePanelTab
  baseMemories: ConversationMemoryRecord[]
  experienceMemories: ConversationMemoryRecord[]
  className?: string
}

function resolveTitle(tab: WorkspacePanelTab): string {
  return tab === 'baseMemories' ? '基础记忆' : '经验记忆'
}

function resolveNote(tab: WorkspacePanelTab): string {
  return tab === 'baseMemories' ? '记录偏好、事实与长期上下文' : '记录排障经验、执行策略与案例沉淀'
}

function resolveMemoryTypeLabel(memory: ConversationMemoryRecord): string {
  return memory.memory_type === 'base' ? '基础' : memory.memory_type === 'experience' ? '经验' : memory.memory_type
}

function formatMemoryMeta(memory: ConversationMemoryRecord): string[] {
  return [resolveMemoryTypeLabel(memory), memory.category, memory.score != null ? `score ${memory.score.toFixed(2)}` : null].filter(
    (item): item is string => Boolean(item),
  )
}

function readRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function parseJsonRecord(value: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(value) as unknown
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

function normalizeMemoryContent(memory: ConversationMemoryRecord): string {
  const parsed = parseJsonRecord(memory.content)
  if (!parsed) {
    return memory.content.trim() || '暂无内容'
  }

  const fields = ['summary', 'content', 'experience', 'insight', 'reasoning', 'observation', 'text']
  for (const field of fields) {
    const value = parsed[field]
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
  }

  return JSON.stringify(parsed, null, 2)
}

function buildMemoryPreview(memory: ConversationMemoryRecord): string {
  const normalized = normalizeMemoryContent(memory).replace(/\s+/g, ' ').trim()
  if (!normalized) return '暂无内容'
  return normalized.length > 88 ? `${normalized.slice(0, 88)}...` : normalized
}

function getMetadata(memory: ConversationMemoryRecord): Record<string, unknown> {
  return readRecord(memory.metadata) ?? {}
}

function getExecuteTrace(memory: ConversationMemoryRecord): Array<{ toolName: string; choiceReason: string }> {
  const metadata = getMetadata(memory)
  const trace = metadata.execute_trace
  if (!Array.isArray(trace)) return []

  return trace
    .map((step) => {
      const record = readRecord(step)
      return {
        toolName: readString(record?.tool_name) ?? '未知工具',
        choiceReason: readString(record?.choice_reason) ?? '暂无说明',
      }
    })
    .filter((step) => step.toolName || step.choiceReason)
}

function formatDetailFields(memory: ConversationMemoryRecord): Array<{ label: string; value: string }> {
  const metadata = getMetadata(memory)
  const fields: Array<{ label: string; value: string | null }> = [
    { label: '记忆类型', value: resolveMemoryTypeLabel(memory) },
    { label: '分类', value: readString(memory.category) },
    { label: '创建时间', value: readString(metadata.created_at) },
    { label: '更新时间', value: readString(metadata.updated_at) },
  ]

  if (memory.memory_type === 'experience') {
    fields.splice(2, 0,
      { label: '领域', value: readString(metadata.domain_type) },
      { label: '反馈类型', value: readString(metadata.feedback_type) },
    )
  }

  return fields
    .filter((field): field is { label: string; value: string } => Boolean(field.value))
}

function renderEmptyDetail(tab: WorkspacePanelTab) {
  return (
    <div className="memory-panel-detail memory-panel-detail--empty">
      <p>{tab === 'baseMemories' ? '选择一条基础记忆查看完整内容' : '选择一条经验记忆查看完整内容'}</p>
    </div>
  )
}

function MemoryDetail({ memory }: { memory: ConversationMemoryRecord }) {
  const metadata = getMetadata(memory)
  const fields = formatDetailFields(memory)
  const executeTrace = getExecuteTrace(memory)
  const description = readString(metadata.description)

  return (
    <div className="memory-panel-detail">
      <div className="memory-panel-detail__header">
        <div>
          <p className="memory-panel-detail__eyebrow">{memory.memory_type === 'experience' ? 'Experience Memory' : 'Base Memory'}</p>
          <h3>{memory.title?.trim() || '未命名记忆'}</h3>
        </div>
        <span className="memory-panel-detail__id" title={memory.id}>{memory.id}</span>
      </div>

      {fields.length > 0 && (
        <div className="memory-panel-detail__grid">
          {fields.map((field) => (
            <div key={`${memory.id}-${field.label}`} className="memory-panel-detail__meta">
              <span>{field.label}</span>
              <strong>{field.value}</strong>
            </div>
          ))}
        </div>
      )}

      {description && (
        <section className="memory-panel-detail__section">
          <h4>说明</h4>
          <p>{description}</p>
        </section>
      )}

      <section className="memory-panel-detail__section">
        <h4>完整记忆</h4>
        <p className="memory-panel-detail__content">{normalizeMemoryContent(memory)}</p>
      </section>

      {executeTrace.length > 0 && (
        <section className="memory-panel-detail__section">
          <h4>执行轨迹</h4>
          <div className="memory-panel-trace">
            {executeTrace.map((step, index) => (
              <article key={`${memory.id}-${step.toolName}-${index}`} className="memory-panel-trace__item">
                <span className="memory-panel-trace__index">{index + 1}</span>
                <div className="memory-panel-trace__body">
                  <strong>{step.toolName}</strong>
                  <p>{step.choiceReason}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function MemoryList({
  memories,
  selectedMemoryId,
  onSelect,
}: {
  memories: ConversationMemoryRecord[]
  selectedMemoryId: string | null
  onSelect: (memoryId: string) => void
}) {
  return (
    <div className="memory-panel-list" role="listbox" aria-label="记忆列表">
      {memories.map((memory) => {
        const tags = formatMemoryMeta(memory)
        const isActive = selectedMemoryId === memory.id
        return (
          <button
            key={memory.id}
            type="button"
            className={`config-card config-card-interactive memory-panel-item${isActive ? ' active' : ''}`}
            onClick={() => onSelect(memory.id)}
          >
            <div className="memory-panel-item__header">
              <h3>{memory.title?.trim() || '未命名记忆'}</h3>
              {tags.length > 0 && (
                <div className="memory-panel-card__tags">
                  {tags.map((tag) => (
                    <span key={`${memory.id}-${tag}`} className="memory-panel-card__tag">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <p className="memory-panel-item__preview">{buildMemoryPreview(memory)}</p>
          </button>
        )
      })}
    </div>
  )
}

export function MemoryPanel({ className, ...props }: MemoryPanelProps) {
  const panelClassName = className ? `memory-panel-root ${className}` : 'memory-panel-root'

  const memories = useMemo(
    () => (props.selectedTab === 'baseMemories' ? props.baseMemories : props.experienceMemories),
    [props.baseMemories, props.experienceMemories, props.selectedTab],
  )

  const [selectedMemoryId, setSelectedMemoryId] = useState<string | null>(null)

  useEffect(() => {
    if (memories.length === 0) {
      setSelectedMemoryId(null)
      return
    }

    if (!selectedMemoryId || !memories.some((memory) => memory.id === selectedMemoryId)) {
      setSelectedMemoryId(memories[0]!.id)
    }
  }, [memories, selectedMemoryId])

  const selectedMemory = memories.find((memory) => memory.id === selectedMemoryId) ?? null

  return (
    <section className={panelClassName}>
      {memories.length === 0 ? (
        <section className="panel config-list-panel">
          <div className="section-heading">
            <div className="memory-panel-heading__copy">
              <h2>{resolveTitle(props.selectedTab)}</h2>
              <span className="section-note">{resolveNote(props.selectedTab)}</span>
            </div>
            <span className="memory-panel-count">0 条</span>
          </div>
          <p className="memory-panel-empty">
            {props.selectedTab === 'baseMemories' ? '暂无基础记忆' : '暂无经验记忆'}
          </p>
        </section>
      ) : (
        <div className="config-center-grid memory-panel-grid">
          <section className="panel config-form-panel memory-panel-list-column" aria-label="记忆条目列表">
            <div className="memory-panel-column-heading">
              <div className="memory-panel-heading__copy">
                <h2>{resolveTitle(props.selectedTab)}</h2>
                <span className="section-note">{resolveNote(props.selectedTab)}</span>
              </div>
              <span className="memory-panel-count">{memories.length} 条</span>
            </div>
            <MemoryList
              memories={memories}
              selectedMemoryId={selectedMemory?.id ?? null}
              onSelect={setSelectedMemoryId}
            />
          </section>
          <section className="panel config-list-panel memory-panel-detail-column" aria-label="记忆详情">
            <div className="section-heading memory-panel-detail-heading">
              <div className="memory-panel-heading__copy">
                <h2>条目详情</h2>
                <span className="section-note">查看选中记忆的完整内容与结构化信息</span>
              </div>
              <span className="memory-panel-count">{selectedMemory ? '已选中' : '未选择'}</span>
            </div>
            {selectedMemory ? <MemoryDetail memory={selectedMemory} /> : renderEmptyDetail(props.selectedTab)}
          </section>
        </div>
      )}
    </section>
  )
}
