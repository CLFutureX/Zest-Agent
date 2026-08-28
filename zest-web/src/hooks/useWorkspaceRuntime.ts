import { useEffect, useMemo, useRef, useState } from 'react'

import { useConversationWebSocket } from '../contexts/ConversationWebSocketContext'

import {
  respondToConfirmation,
  getConversation,
  getConversationEvents,
  listConversations,
  listLlmConfigs,
  openConversation,
  getConversationStateView,
} from '../services/appServerApi'

import { buildWebSocketUrl } from '../services/runtimeUrl'

import { useAuthStore } from '../stores/useAuthStore'
import { useEventStore } from '../stores/useEventStore'

import type {
  ConversationResponse,
  ConversationSplitView,
  MemoryReviewPayload,
  TodoItem,
  UserLlmConfigSummary,
} from '../types/workspace'

import { requestAuthDialog } from '../utils/authEvents'
import { extractArtifactsFromEvents } from '../utils/extractArtifacts'
import {
  extractConfirmationState,
  extractLatestMessageText,
  extractRuntimeStatus,
  extractTodosFromEvent,
  formatRuntimeMeta,
} from '../utils/runtimeStateHelpers'

import { useRuntimeState } from './useRuntimeState'
import { useTimeline } from './useTimeline'

// 常量定义
const EMPTY_SPLIT_VIEW: ConversationSplitView = {
  events: [],
  baseMemories: [],
  experienceMemories: [],
  artifacts: [],
  todos: [],
}

export function useWorkspaceRuntime() {
  // State 定义
  const [runtimeMeta, setRuntimeMeta] = useState('等待打开会话...')
  const [busy, setBusy] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [selectedModel, setSelectedModel] = useState('')
  const [selectedLlmConfigId, setSelectedLlmConfigId] = useState('')
  const [llmConfigs, setLlmConfigs] = useState<UserLlmConfigSummary[]>([])
  const [conversationList, setConversationList] = useState<ConversationResponse[]>([])
  const [splitView, setSplitView] = useState<ConversationSplitView>(EMPTY_SPLIT_VIEW)

  // 外部自定义 hook 取值
  const { timeline, eventLogText } = useTimeline()
  const runtimeState = useRuntimeState()
  const websocket = useConversationWebSocket()
  const clearEvents = useEventStore((state) => state.clearEvents)
  const currentUser = useAuthStore((state) => state.user)
  const currentUserId = currentUser?.id ?? ''

  // Ref 持久缓存变量
  const initialSplitViewLoadRef = useRef<string | null>(null)

  // 快捷取值
  const conversation = websocket?.conversation ?? null
  const conversationRecord = websocket?.conversationRecord ?? null
  const connectionLabel = websocket?.connectionLabel ?? '未连接'

  // 重置错误提示
  const resetError = () => {
    setErrorMessage('')
  }

  // 用户登录后加载模型列表、会话列表
  useEffect(() => {
    if (!currentUserId) {
      setLlmConfigs([])
      setConversationList([])
      return
    }

    let cancelled = false
    const loadWorkspaceBootstrap = async () => {
      try {
        const [configs, conversations] = await Promise.all([
          listLlmConfigs(currentUserId),
          listConversations({ userId: currentUserId, limit: 20, offset: 0 }),
        ])

        if (cancelled) return
        setLlmConfigs(configs)
        setConversationList(conversations)

        // 保留原有选中模型，不存在则默认第一个
        setSelectedLlmConfigId((current) => {
          if (current && configs.some((c) => c.id === current)) return current
          return configs[0]?.id ?? ''
        })
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : '加载工作区配置失败。')
        }
      }
    }

    void loadWorkspaceBootstrap()
    return () => {
      cancelled = true
    }
  }, [currentUserId])

  // 绑定 websocket 消息回调
  useEffect(() => {
    if (!websocket) return

    websocket.setEventHandlers({
      onOpen: (access) => {
        setRuntimeMeta(`conversation=${access.conversation_id}`)
      },
      // 消息监听回调
      onMessage: (payload) => {
        runtimeState.setLastEvent(payload)

        const status = extractRuntimeStatus(payload)
        if (status) {
          runtimeState.setAgentState(status)
        }

        const text = extractLatestMessageText(payload)
        if (text) {
          runtimeState.setLatestMessage(text)
        }

        const confirmationState = extractConfirmationState(payload)
        if (confirmationState) {
          runtimeState.setConfirmationState(confirmationState)
        }

        const rawTodos = extractTodosFromEvent(payload)
        if (rawTodos) {
          const todos: TodoItem[] = rawTodos.map((t) => ({
            content: t.content,
            status: t.status as TodoItem['status'],
          }))
          setSplitView((prev) => ({ ...prev, todos }))
        }

        setRuntimeMeta(
          formatRuntimeMeta({
            conversationId: conversation?.conversation_id ?? conversationRecord?.conversation_id ?? null,
            agentStatus: status ?? runtimeState.agentState,
            latestMessage: text ?? runtimeState.latestMessage,
            confirmation: confirmationState ?? runtimeState.confirmationState,
          }),
        )
      },
      onRawMessage: () => undefined,
      onError: () => {
        runtimeState.setAgentState('error')
        runtimeState.setConfirmationState({
          pending: false,
          actionId: null,
          toolName: null,
          toolCallId: null,
          summary: null,
        })
        setErrorMessage('WebSocket 连接异常，请稍后重试。')
      },
      onClose: () => undefined,
    })
  }, [conversation?.conversation_id, conversationRecord?.conversation_id, runtimeState, websocket])

  // 切换会话全量加载页面数据（事件、待办、产物）
  useEffect(() => {
    const conversationId = conversationRecord?.conversation_id
    if (!conversationId || !currentUserId) {
      setSplitView(EMPTY_SPLIT_VIEW)
      return
    }

    let cancelled = false
    const loadSplitView = async () => {
      initialSplitViewLoadRef.current = conversationId
      try {
        const [eventPage, stateView] = await Promise.all([
          getConversationEvents(conversationId, currentUserId, 20),
          getConversationStateView(conversationId),
        ])

        if (cancelled) return
        setSplitView({
          events: eventPage.items,
          baseMemories: [],
          experienceMemories: [],
          artifacts: extractArtifactsFromEvents(eventPage.items),
          todos: stateView?.todos ?? [],
        })
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : '加载会话视图失败。')
        }
      } finally {
        if (initialSplitViewLoadRef.current === conversationId) {
          initialSplitViewLoadRef.current = null
        }
      }
    }

    void loadSplitView()
    return () => {
      cancelled = true
    }
  }, [conversationRecord?.conversation_id, currentUserId])

  // 创建新会话
  const handleOpenConversation = async (input: {
    title: string
    initialMessage?: string
    workspace?: string
    model?: string
  }) => {
    if (!currentUserId) {
      setErrorMessage('请先登录后创建会话。')
      requestAuthDialog('workspace')
      return null
    }

    resetError()
    setBusy(true)
    clearEvents()
    setSplitView(EMPTY_SPLIT_VIEW)

    try {
      const data = await openConversation({
        userId: currentUserId,
        title: input.title,
        initialMessage: input.initialMessage,
        workspace: input.workspace,
        model: input.model,
      })

      if (data.error_message) {
        setRuntimeMeta('会话创建存在异常')
        setErrorMessage(data.error_message)
        websocket?.setConversationRecord(null)
      } else if (websocket && data.base_url) {
        setRuntimeMeta(`conversation=${data.conversation_id}`)
        websocket.setConversationRecord(data)
        // 置顶当前会话
        setConversationList((current) => {
          const rest = current.filter((item) => item.conversation_id !== data.conversation_id)
          return [data, ...rest]
        })
      } else {
        setRuntimeMeta('会话已创建，但未返回 runtime access')
        setErrorMessage('当前会话缺少 runtime 连接信息。')
      }
      return data
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '打开会话失败。')
      return null
    } finally {
      setBusy(false)
    }
  }

  // 切换已有会话
  const handleSelectConversation = async (conversationId: string) => {
    const selected = conversationList.find((item) => item.conversation_id === conversationId)
    if (!selected || !websocket) return

    resetError()
    setBusy(true)
    clearEvents()
    setSplitView(EMPTY_SPLIT_VIEW)
    setRuntimeMeta(`conversation=${selected.conversation_id} resuming...`)

    try {
      const resumed = await getConversation(conversationId)
      if (resumed.error_message) {
        setRuntimeMeta('会话恢复存在异常')
        setErrorMessage(resumed.error_message)
        websocket.setConversationRecord(null)
        return
      }

      if (!resumed.base_url) {
        setRuntimeMeta('会话已恢复，但未返回 runtime access')
        setErrorMessage('当前会话缺少 runtime 连接信息。')
        websocket.setConversationRecord(null)
        return
      }

      setRuntimeMeta(`conversation=${resumed.conversation_id}`)
      websocket.setConversationRecord(resumed)
      // 置顶
      setConversationList((current) => {
        const rest = current.filter((item) => item.conversation_id !== resumed.conversation_id)
        return [resumed, ...rest]
      })
    } catch (error) {
      setRuntimeMeta('会话恢复失败')
      setErrorMessage(error instanceof Error ? error.message : '切换会话失败。')
      websocket.setConversationRecord(null)
    } finally {
      setBusy(false)
    }
  }

  // 清空会话，回到等待新建状态
  const handleNewConversation = () => {
    if (!websocket) return
    resetError()
    clearEvents()
    setSplitView(EMPTY_SPLIT_VIEW)
    setRuntimeMeta('等待打开会话...')
    runtimeState.setAgentState('idle')
    runtimeState.setLatestMessage('')
    runtimeState.setConfirmationState({
      pending: false,
      actionId: null,
      toolName: null,
      toolCallId: null,
      summary: null,
    })
    websocket.setConversationRecord(null)
  }

  // 发送消息，无会话则自动创建
  const handleSendMessage = async (input: { content: string; model?: string }) => {
    if (!websocket) return
    resetError()
    setBusy(true)

    try {
      if (input.model !== undefined) setSelectedModel(input.model)
      // 无会话自动新建
      if (!conversation) {
        await handleOpenConversation({
          title: '新的 Agent 会话',
          initialMessage: input.content,
          model: input.model,
        })
        return
      }
      await websocket.sendMessage(input.content)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '发送消息失败。')
    } finally {
      setBusy(false)
    }
  }

  const handleRespondToConfirmation = async (input: { accept: boolean; reason?: string; payload?: MemoryReviewPayload }) => {
    const conversationId = conversationRecord?.conversation_id ?? conversation?.conversation_id
    if (!conversationId) {
      setErrorMessage('当前没有可操作的会话。')
      return
    }

    resetError()
    runtimeState.setConfirmationBusy(true)

    try {
      await respondToConfirmation(conversationId, input)

      runtimeState.setConfirmationState({
        pending: false,
        actionId: null,
        toolName: null,
        toolCallId: null,
        summary: null,
      })
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '确认操作失败。')
    } finally {
      runtimeState.setConfirmationBusy(false)
    }
  }

  // 计算缓存
  const websocketUrl = useMemo(
    () => (conversation ? buildWebSocketUrl(conversation) : ''),
    [conversation],
  )

  return {
    conversationRecord,
    conversation,
    conversationList,
    connectionLabel,
    runtimeMeta,
    websocketUrl,
    busy,
    errorMessage,
    selectedModel,
    selectedLlmConfigId,
    llmConfigs,
    splitView,
    agentState: runtimeState.agentState,
    latestMessage: runtimeState.latestMessage,
    confirmationBusy: runtimeState.confirmationBusy,
    confirmationState: runtimeState.confirmationState,
    lastEvent: runtimeState.lastEvent,
    timeline,
    eventLogText,
    openConversation: handleOpenConversation,
    selectConversation: handleSelectConversation,
    newConversation: handleNewConversation,
    sendMessage: handleSendMessage,
    respondToConfirmation: handleRespondToConfirmation,
    setSelectedLlmConfigId,
    dismissError: resetError,
  }
}
