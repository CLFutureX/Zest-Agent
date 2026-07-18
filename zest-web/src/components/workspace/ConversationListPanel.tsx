import { MemoryPanel } from './MemoryPanel'

import type { ConversationMemoryRecord } from '../../types/workspace'

import type { WorkspacePanelTab } from '../../hooks/useWorkspacePanel'

export type WorkspaceSidebarMode = 'conversations' | 'memories'



export type ConversationListItem = {

  id: string

  title: string

  status?: string | null

  summary?: string | null

  updatedAt?: string | null

}



type ConversationListPanelProps = {

  items: ConversationListItem[]

  activeConversationId?: string | null

  onCreateConversation?: () => void

  onSelectConversation?: (conversationId: string) => void

  mode: WorkspaceSidebarMode

  selectedMemoryTab: WorkspacePanelTab

  baseMemories: ConversationMemoryRecord[]

  experienceMemories: ConversationMemoryRecord[]

}



function statusDot(status?: string | null) {

  const s = (status || 'created').toLowerCase()

  if (s === 'running') return 'status-dot running'

  if (s === 'waiting_for_confirmation') return 'status-dot running'

  if (s === 'completed') return 'status-dot completed'

  if (s === 'failed' || s === 'error') return 'status-dot error'

  return 'status-dot'

}


function resolveMemoryHeading(tab: WorkspacePanelTab) {
  return tab === 'baseMemories'
    ? { title: '基础记忆', note: '当前会话中的偏好、事实和长期上下文' }
    : { title: '经验记忆', note: '当前会话沉淀的案例、策略与处理经验' }
}



export function ConversationListPanel({

  items,

  activeConversationId,

  onCreateConversation,

  onSelectConversation,

  mode,

  selectedMemoryTab,

  baseMemories,

  experienceMemories,

}: ConversationListPanelProps) {
  const memoryHeading = resolveMemoryHeading(selectedMemoryTab)

  return (

    <aside className="df-sidebar-shell df-sidebar-shell--content">

      <div className="df-sidebar-panel">
        {mode === 'conversations' ? (
          <>
            <div className="df-sidebar-pane-header">
              <div>
                <span className="df-sidebar-pane-eyebrow">Workspace</span>
                <h2>Conversations</h2>
                <p>浏览会话列表，继续已有执行链路或开启新对话。</p>
              </div>
              <button
                type="button"
                className="df-sidebar-new-btn"
                onClick={onCreateConversation}
                title="新对话"
              >
                <span style={{ fontSize: '16px', lineHeight: 1 }}>＋</span>
                <span>新对话</span>
              </button>
            </div>

            <div className="df-sidebar-section df-sidebar-conversations df-sidebar-conversations--full">
              <span className="df-sidebar-section-label">会话列表</span>
              <div className="df-sidebar-list">
                {items.length === 0 && <div className="df-sidebar-empty">暂无会话</div>}
                {items.map((item) => {
                  const isActive = activeConversationId === item.id
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`df-sidebar-item${isActive ? ' active' : ''}`}
                      onClick={() => onSelectConversation?.(item.id)}
                      title={item.title}
                    >
                      <span className={statusDot(item.status)} />
                      <span className="df-sidebar-item-text">
                        <span className="df-sidebar-item-title">{item.title}</span>
                        {item.summary && (
                          <span className="df-sidebar-item-summary">{item.summary}</span>
                        )}
                        {item.updatedAt && (
                          <span className="df-sidebar-item-meta">{item.updatedAt}</span>
                        )}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="df-sidebar-pane-header">
              <div>
                <span className="df-sidebar-pane-eyebrow">Memory</span>
                <h2>{memoryHeading.title}</h2>
                <p>{memoryHeading.note}</p>
              </div>
            </div>

            <MemoryPanel
              className="df-sidebar-memory-panel"
              selectedTab={selectedMemoryTab}
              baseMemories={baseMemories}
              experienceMemories={experienceMemories}
            />

            <div className="df-sidebar-section df-sidebar-conversations df-sidebar-conversations--compact">
              <span className="df-sidebar-section-label">关联会话</span>
              <div className="df-sidebar-list">
                {items.length === 0 && <div className="df-sidebar-empty">暂无会话</div>}
                {items.map((item) => {
                  const isActive = activeConversationId === item.id
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`df-sidebar-item${isActive ? ' active' : ''}`}
                      onClick={() => onSelectConversation?.(item.id)}
                      title={item.title}
                    >
                      <span className={statusDot(item.status)} />
                      <span className="df-sidebar-item-text">
                        <span className="df-sidebar-item-title">{item.title}</span>
                        {item.summary && (
                          <span className="df-sidebar-item-summary">{item.summary}</span>
                        )}
                        {item.updatedAt && (
                          <span className="df-sidebar-item-meta">{item.updatedAt}</span>
                        )}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </aside>
  )
}
