import type { ZestEvent } from '../../types/zest'
import type { ConversationEventRecord, TodoItem } from '../../types/workspace'
import type { ConfirmationState, RuntimeAgentStatus } from '../../types/runtimeState'

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
  onRespondToConfirmation?: (input: { accept: boolean; reason?: string }) => Promise<void>
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
