import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'



import type { ReactNode } from 'react'



import { env } from '../config/env'

import { connectConversationSocket } from '../services/websocketClient'

import type { ZestEvent } from '../types/zest'

import {

  isActionEvent,

  isAgentErrorEvent,

  isConversationStateUpdateEvent,

  isExecuteBashActionEvent,

  isExecuteBashObservationEvent,

  isUserMessageEvent,

  isV1Event,

} from '../types/zestGuards'

import type { ConversationAccessInfo, ConversationResponse } from '../types/workspace'

import { useEventStore } from '../stores/useEventStore'



type ConversationWebSocketContextValue = {

  conversation: ConversationAccessInfo | null

  conversationRecord: ConversationResponse | null

  connectionLabel: string

  sendMessage: (content: string) => Promise<void>

  setConversationRecord: (conversation: ConversationResponse | null) => void

  setEventHandlers: (handlers: ConversationEventHandlers) => void

}



type ConversationEventHandlers = {

  onOpen?: (access: ConversationAccessInfo) => void

  onMessage?: (payload: ZestEvent) => void

  onRawMessage?: (raw: string) => void

  onError?: () => void

  onClose?: (event: CloseEvent) => void

}



const ConversationWebSocketContext = createContext<ConversationWebSocketContextValue | null>(null)



type ConversationWebSocketProviderProps = {

  children: ReactNode

}



function toConversationAccessInfo(record: ConversationResponse | null): ConversationAccessInfo | null {

  if (!record?.conversation_id || !record.base_url) {

    return null

  }

  return {

    conversation_id: record.conversation_id,

    base_url: record.base_url,

    session_api_key: record.session_api_key,

    resend_all: true,

  }

}



export function ConversationWebSocketProvider({ children }: ConversationWebSocketProviderProps) {

  const [conversationRecord, setConversationRecordState] = useState<ConversationResponse | null>(null)

  const [conversation, setConversationState] = useState<ConversationAccessInfo | null>(null)

  const [connectionLabel, setConnectionLabel] = useState('未连接')

  const socketRef = useRef<WebSocket | null>(null)

  const reconnectTimerRef = useRef<number | null>(null)

  const reconnectAttemptsRef = useRef(0)

  const shouldReconnectRef = useRef(false)
  // 引用，外部回调函数，避免引起状态变更导致渲染了
  const handlersRef = useRef<ConversationEventHandlers>({})
  //ff 2 调用方法添加到本地持久状态
  const addEvent = useEventStore((state) => state.addEvent)
 

  // 前面这里都只是定义函数，后面使用
  const clearReconnectTimer = useCallback(() => {

    if (reconnectTimerRef.current !== null) {

      window.clearTimeout(reconnectTimerRef.current)

      reconnectTimerRef.current = null

    }

  }, [])



  const setEventHandlers = useCallback((handlers: ConversationEventHandlers) => {

    handlersRef.current = handlers

  }, [])



  const handleSocketMessage = useCallback((payload: Record<string, unknown>) => {

    if (!isV1Event(payload)) {

      return

    }


    //ff 1 后端返回数据，将其添加到zustand本地存储中。
    addEvent(payload)


    // 如果是异常的agentEvent，调用外部回调函数处理
    if (isAgentErrorEvent(payload)) {

      handlersRef.current.onError?.()

    }

    
    // 如果是用户消息则返回
    if (isUserMessageEvent(payload)) {

      return

    }


    // 如果是会话状态更新或实现等，泰永外部的onMessage回调函数
    if (isConversationStateUpdateEvent(payload) || isActionEvent(payload) || isExecuteBashActionEvent(payload) || isExecuteBashObservationEvent(payload)) {

      handlersRef.current.onMessage?.(payload)

      return

    }



    handlersRef.current.onMessage?.(payload)
  
  }, [addEvent])



  const connect = useCallback(

    (access: ConversationAccessInfo) => {

      clearReconnectTimer()

      // Close any existing socket cleanly with a "switching" code so its
      // onClose handler does NOT trigger a reconnect cycle.
      shouldReconnectRef.current = false
      const prev = socketRef.current
      if (prev) {
        try {
          prev.close(1000, 'switching')
        } catch {
          // ignore
        }
      }

      shouldReconnectRef.current = true
      setConnectionLabel('连接中...')

      socketRef.current = connectConversationSocket(access, {
        onOpen: () => {
          reconnectAttemptsRef.current = 0
          setConnectionLabel('已连接')
          handlersRef.current.onOpen?.(access)
        },

        onMessage: handleSocketMessage,

        onRawMessage: (raw) => {
          handlersRef.current.onRawMessage?.(raw)
        },

        onError: (event) => {
          // eslint-disable-next-line no-console
          console.warn(
            '[ws] onError',
            'readyState=',
            socketRef.current?.readyState,
            event,
          )
          setConnectionLabel('连接异常')
          handlersRef.current.onError?.()
        },

        onClose: (event) => {
          setConnectionLabel('已断开')
          handlersRef.current.onClose?.(event)

          if (!shouldReconnectRef.current) {
            // Intentional close (e.g. switching conversations) — do not retry.
            return
          }

          // Classify close code:
          //   1000 (Normal), 1001 (GoingAway)        -> user/server intent, no retry
          //   4001 (conv deleted), 4002 (paused)     -> business intent, no retry
          //   1006 (Abnormal), 1011 (Server error),
          //   4xxx (other app codes)                 -> retry with backoff
          const code = event.code
          const isIntentional =
            code === 1000 ||
            code === 1001 ||
            code === 4001 ||
            code === 4002 ||
            code === 4003
          if (isIntentional && event.wasClean) {
            return
          }

          if (reconnectAttemptsRef.current >= env.wsReconnectMaxRetries) {
            setConnectionLabel('重连失败')
            return
          }

          reconnectAttemptsRef.current += 1
          const attempt = reconnectAttemptsRef.current
          const baseDelay = env.wsReconnectDelayMs
          // Exponential backoff with jitter, capped at 30s.
          const delay = Math.min(
            baseDelay * Math.pow(2, attempt - 1) + Math.floor(Math.random() * 500),
            30000,
          )
          setConnectionLabel(`重连中(${attempt})...`)
          clearReconnectTimer()
          reconnectTimerRef.current = window.setTimeout(() => {
            connect(access)
          }, delay)
        },
      })

    },

    [clearReconnectTimer, handleSocketMessage],

  )



  const setConversationRecord = useCallback(

    (nextConversation: ConversationResponse | null) => {

      setConversationRecordState(nextConversation)

      const access = toConversationAccessInfo(nextConversation)

      setConversationState(access)

      shouldReconnectRef.current = Boolean(access)

      reconnectAttemptsRef.current = 0

      clearReconnectTimer()

      if (!access) {

        setConnectionLabel('未连接')

        socketRef.current?.close()

        return

      }
      //ff 5 连接
      connect(access)

    },

    [clearReconnectTimer, connect],

  )



  const sendMessage = useCallback(

    async (content: string) => {

      if (!conversation) {

        throw new Error('当前没有可用会话连接。')

      }

      if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {

        throw new Error('WebSocket 未连接。')

      }

      socketRef.current.send(

        JSON.stringify({

          role: 'user',

          content: [{ type: 'text', text: content }],

        }),

      )

    },

    [conversation],

  )



  useEffect(() => {

    return () => {

      shouldReconnectRef.current = false

      clearReconnectTimer()

      socketRef.current?.close()

    }

  }, [clearReconnectTimer])



  const value = useMemo(

    () => ({ conversation, conversationRecord, connectionLabel, sendMessage, setConversationRecord, setEventHandlers }),

    [conversation, conversationRecord, connectionLabel, sendMessage, setConversationRecord, setEventHandlers],

  )



  return <ConversationWebSocketContext.Provider value={value}>{children}</ConversationWebSocketContext.Provider>

}



export function useConversationWebSocket() {

  return useContext(ConversationWebSocketContext)

}
