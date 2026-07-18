import { AlertBanner } from '../components/workspace/AlertBanner'
import { ChatWorkspace } from '../components/workspace/ChatWorkspace'
import { ConversationListPanel } from '../components/workspace/ConversationListPanel'
import { WorkspaceResourcePanel } from '../components/workspace/WorkspaceResourcePanel'
import { ConversationWebSocketProvider } from '../contexts/ConversationWebSocketContext'
import { useWorkspacePanel } from '../hooks/useWorkspacePanel'
import { useWorkspaceRuntime } from '../hooks/useWorkspaceRuntime'
import { useEventStore } from '../stores/useEventStore'

function WorkspacePageContent() {
  const {
    isRightPanelShown,
    rightPanelWidth,
    isRightPanelFullscreen,
    openRightPanel,
    closeRightPanel,
    setRightPanelWidth,
    toggleRightPanelFullscreen,
  } = useWorkspacePanel()
  const {
    conversationRecord,
    conversation,
    conversationList,
    busy,
    errorMessage,
    selectedModel,
    selectedLlmConfigId,
    llmConfigs,
    splitView,
    agentState,
    confirmationBusy,
    confirmationState,
    newConversation,
    selectConversation,
    respondToConfirmation,
    sendMessage,
    dismissError,
  } = useWorkspaceRuntime()

  const uiEvents = useEventStore((state) => state.uiEvents)

  const conversationItems = conversationList.map((item) => {
    const snap = item.snapshot
    const title =
      snap?.summary?.last_user_message?.trim() ||
      `Conversation ${item.conversation_id.slice(0, 8)}`

    const summary =
      item.error_message ||
      snap?.summary?.last_user_message ||
      (item.base_url ? '会话已建立，可继续聊天' : '等待首条消息启动会话')

    return {
      id: item.conversation_id,
      title,
      status: snap?.runtime?.status,
      summary,
      updatedAt: snap?.runtime?.updated_at ?? item.created_at,
    }
  })

  const llmConfigOptions = llmConfigs.map((config) => ({
    value: config.id,
    label: config.model,
  }))

  const activeLlmLabel = llmConfigs.find((c) => c.id === selectedLlmConfigId)?.model || 'default'
  const hasActiveConversation = Boolean(conversation || conversationRecord)
  const shouldShowRightPanel = hasActiveConversation && isRightPanelShown

  return (
    <div className="df-shell">
      <div className="aurora aurora-one" />
      <div className="aurora aurora-two" />

      {errorMessage && <AlertBanner message={errorMessage} onClose={dismissError} />}

      <div className="df-layout">
        <ConversationListPanel
          items={conversationItems}
          activeConversationId={conversationRecord?.conversation_id ?? null}
          onCreateConversation={newConversation}
          onSelectConversation={selectConversation}
          mode="conversations"
          selectedMemoryTab="baseMemories"
          baseMemories={splitView.baseMemories}
          experienceMemories={splitView.experienceMemories}
        />

        <ChatWorkspace
          historicalRecords={splitView.events}
          liveEvents={uiEvents}
          todos={splitView.todos}
          busy={busy}
          isLoading={busy}
          defaultModel={selectedModel}
          defaultLlmConfigId={selectedLlmConfigId}
          llmConfigOptions={llmConfigOptions}
          welcomeMode={!hasActiveConversation}
          conversationTitle={
            conversationRecord?.snapshot?.summary?.last_user_message?.trim() || activeLlmLabel
          }
          agentState={agentState}
          confirmationBusy={confirmationBusy}
          confirmationState={confirmationState}
          isPanelOpen={shouldShowRightPanel}
          onOpenPanel={hasActiveConversation ? openRightPanel : undefined}
          onSubmit={sendMessage}
          onRespondToConfirmation={respondToConfirmation}
        />

        {shouldShowRightPanel && (
          <WorkspaceResourcePanel
            isRightPanelShown={isRightPanelShown}
            isFullscreen={isRightPanelFullscreen}
            width={rightPanelWidth}
            onClose={closeRightPanel}
            onResize={setRightPanelWidth}
            onToggleFullscreen={toggleRightPanelFullscreen}
            artifacts={splitView.artifacts}
            historicalRecords={splitView.events}
            liveEvents={uiEvents}
          />
        )}
      </div>
    </div>
  )
}

export function WorkspacePage() {
  return (
    <ConversationWebSocketProvider>
      <WorkspacePageContent />
    </ConversationWebSocketProvider>
  )
}
