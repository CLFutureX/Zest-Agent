import { useState } from 'react'

import type { ZestEvent } from '../../types/zest'
import type { ConversationEventRecord, TodoItem, MemoryReviewPayload } from '../../types/workspace'
import type {
  ConfirmationState,
  MemoryReviewActionArgs,
  MemoryReviewSimilarExperience,
  RuntimeAgentStatus,
} from '../../types/runtimeState'

import { ChatMessageList } from './ChatMessageList'
import { MessageComposer } from './MessageComposer'
import { ZestTodoList } from './ZestTodoList'

type LlmConfigOption = {
  value: string
  label: string
}

type ChatWorkspaceProps = {
  historicalRecords?: ConversationEventRecord[]
  liveEvents?: ZestEvent[]
  todos?: TodoItem[]
  busy: boolean
  isLoading?: boolean
  defaultModel?: string
  defaultLlmConfigId?: string
  llmConfigOptions?: LlmConfigOption[]
  welcomeMode?: boolean
  conversationTitle?: string
  agentState?: RuntimeAgentStatus
  confirmationBusy?: boolean
  confirmationState?: ConfirmationState
  isPanelOpen?: boolean
  onOpenPanel?: () => void
  onSubmit: (input: { content: string; model?: string; llmConfigId?: string }) => Promise<void>
  onRespondToConfirmation?: (input: {
    accept: boolean
    reason?: string
    payload?: MemoryReviewPayload
  }) => Promise<void>
}

function asSimilarList(value: unknown): MemoryReviewSimilarExperience[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
    .map((item) => ({
      id: String(item.id ?? ''),
      question: String(item.question ?? ''),
      solution: String(item.solution ?? ''),
      trace_summary: Array.isArray(item.trace_summary)
        ? item.trace_summary.map((t) => String(t))
        : [],
      feedback_type: String(item.feedback_type ?? ''),
    }))
    .filter((item) => item.id !== '')
}

function MemoryReviewBanner({
  actionArgs,
  busy,
  onRespond,
}: {
  actionArgs: Record<string, unknown> | null | undefined
  busy: boolean
  onRespond: (input: { accept: boolean; payload?: MemoryReviewPayload; reason?: string }) => void
}) {
  const args = (actionArgs ?? {}) as MemoryReviewActionArgs
  const similar = asSimilarList(args.similar_experiences)
  const defaultContent = typeof args.new_content === 'string' ? args.new_content : ''
  const [selectedId, setSelectedId] = useState<string>(similar[0]?.id ?? '')
  const [editedContent, setEditedContent] = useState<string>(defaultContent)

  if (similar.length === 0) {
    return (
      <div className="df-confirmation-banner">
        <div className="df-confirmation-copy">
          <strong>记忆审核</strong>
          <span>未发现相似经验，请直接确认或拒绝。</span>
        </div>
        <div className="df-confirmation-actions">
          <button
            type="button"
            className="df-confirmation-btn df-confirmation-btn--accept"
            disabled={busy}
            onClick={() => onRespond({ accept: true })}
          >
            {busy ? '处理中…' : '确认'}
          </button>
          <button
            type="button"
            className="df-confirmation-btn df-confirmation-btn--reject"
            disabled={busy}
            onClick={() => onRespond({ accept: false, reason: 'User rejected memory review.' })}
          >
            拒绝
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="df-confirmation-banner df-memory-review-banner">
      <div className="df-confirmation-copy">
        <strong>记忆审核：检测到相似经验</strong>
        <span>请选择要更新的经验（可选编辑 solution），确认后覆盖该经验。</span>
      </div>
      <div className="df-memory-review-list">
        {similar.map((exp) => (
          <label key={exp.id} className="df-memory-review-item">
            <input
              type="radio"
              name="memory-review-selected"
              checked={selectedId === exp.id}
              onChange={() => setSelectedId(exp.id)}
              disabled={busy}
            />
            <div className="df-memory-review-item-body">
              <div className="df-memory-review-item-q">问题：{exp.question}</div>
              <div className="df-memory-review-item-s">原方案：{exp.solution}</div>
              {exp.trace_summary.length > 0 && (
                <div className="df-memory-review-item-t">轨迹：{exp.trace_summary.join(' → ')}</div>
              )}
              <div className="df-memory-review-item-f">反馈：{exp.feedback_type}</div>
            </div>
          </label>
        ))}
      </div>
      <div className="df-memory-review-edit">
        <label className="df-memory-review-edit-label">新 solution（可编辑）</label>
        <textarea
          className="df-memory-review-edit-input"
          value={editedContent}
          onChange={(e) => setEditedContent(e.target.value)}
          disabled={busy}
          rows={6}
        />
      </div>
      <div className="df-confirmation-actions">
        <button
          type="button"
          className="df-confirmation-btn df-confirmation-btn--accept"
          disabled={busy || !selectedId}
          onClick={() =>
            onRespond({
              accept: true,
              payload: {
                tool_name: 'memory_review',
                selected_id: selectedId,
                edited_content: editedContent,
              },
            })
          }
        >
          {busy ? '处理中…' : '确认更新该经验'}
        </button>
        <button
          type="button"
          className="df-confirmation-btn df-confirmation-btn--reject"
          disabled={busy}
          onClick={() => onRespond({ accept: false, reason: 'User rejected memory review.' })}
        >
          拒绝（不更新）
        </button>
      </div>
    </div>
  )
}

export function ChatWorkspace({
  historicalRecords = [],
  liveEvents = [],
  todos = [],
  busy,
  isLoading,
  defaultModel,
  defaultLlmConfigId,
  llmConfigOptions,
  welcomeMode = false,
  conversationTitle,
  agentState = 'idle',
  confirmationBusy = false,
  confirmationState = { pending: false, actionId: null, toolName: null, toolCallId: null, summary: null },
  isPanelOpen = false,
  onOpenPanel,
  onSubmit,
  onRespondToConfirmation,
}: ChatWorkspaceProps) {
  const isMemoryReview = confirmationState?.toolName === 'memory_review'

  return (
    <div className="df-chat-area">
      {!welcomeMode && (
        <header className="df-chat-header">
          <div className="df-chat-header-copy">
            <span className="df-chat-title">{conversationTitle ?? 'Conversation'}</span>
            <span className={`df-chat-status df-chat-status--${agentState}`}>
              {agentState === 'waiting_for_confirmation' ? '等待确认' : agentState}
            </span>
          </div>
          {!isPanelOpen && onOpenPanel && (
            <button
              type="button"
              className="df-chat-panel-trigger"
              onClick={onOpenPanel}
              aria-label="打开事件与资源面板"
            >
              打开侧栏
            </button>
          )}
        </header>
      )}

      {!welcomeMode && (
        <div className="df-chat-messages">
          {confirmationState.pending && (
            isMemoryReview ? (
              <MemoryReviewBanner
                actionArgs={confirmationState.actionArgs}
                busy={confirmationBusy}
                onRespond={(input) => {
                  if (!onRespondToConfirmation) return
                  void onRespondToConfirmation(input)
                }}
              />
            ) : (
              <div className="df-confirmation-banner">
                <div className="df-confirmation-copy">
                  <strong>Agent 正在等待人工确认</strong>
                  <span>
                    {confirmationState.toolName ? `工具: ${confirmationState.toolName}` : '存在待确认动作'}
                    {confirmationState.summary ? ` | ${confirmationState.summary}` : ''}
                  </span>
                </div>
                <div className="df-confirmation-actions">
                  <button
                    type="button"
                    className="df-confirmation-btn df-confirmation-btn--accept"
                    disabled={confirmationBusy}
                    onClick={() => {
                      if (!onRespondToConfirmation) return
                      void onRespondToConfirmation({ accept: true })
                    }}
                  >
                    {confirmationBusy ? '处理中…' : '确认执行'}
                  </button>
                  <button
                    type="button"
                    className="df-confirmation-btn df-confirmation-btn--reject"
                    disabled={confirmationBusy}
                    onClick={() => {
                      if (!onRespondToConfirmation) return
                      void onRespondToConfirmation({
                        accept: false,
                        reason: confirmationState.summary
                          ? `User rejected action: ${confirmationState.summary}`
                          : 'User rejected the action.',
                      })
                    }}
                  >
                    拒绝执行
                  </button>
                </div>
              </div>
            )
          )}
          <ZestTodoList todos={todos} inline className="df-chat-todos" />
          <ChatMessageList
            historicalRecords={historicalRecords}
            liveEvents={liveEvents}
            isLoading={isLoading}
          />
        </div>
      )}

      <div className={`df-chat-composer${welcomeMode ? ' df-chat-composer--centered' : ''}`}>
        {welcomeMode && (
          <div className="df-welcome-copy">
            <span className="df-welcome-badge">Zest Agent</span>
            <h2 className="df-welcome-title">连接会话、事件与记忆，从一条指令开始。</h2>
            <p className="df-welcome-subtitle">
              选择一个 LLM 配置，用首条消息启动新的会话流。
            </p>
          </div>
        )}

        <MessageComposer
          busy={busy || confirmationBusy}
          defaultModel={defaultModel}
          defaultLlmConfigId={defaultLlmConfigId}
          llmConfigOptions={llmConfigOptions}
          welcomeMode={welcomeMode}
          onSubmit={onSubmit}
        />
      </div>
    </div>
  )
}
