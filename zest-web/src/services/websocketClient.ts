import { buildWebSocketUrl } from './runtimeUrl'

import type { ConversationAccessInfo } from '../types/workspace'

type WebsocketHandlers = {
  onOpen: () => void
  onMessage: (payload: Record<string, unknown>) => void
  onRawMessage: (raw: string) => void
  onError: (event: Event) => void
  onClose: (event: CloseEvent) => void
}

export function connectConversationSocket(
  access: ConversationAccessInfo,
  handlers: WebsocketHandlers,
): WebSocket {
  const socket = new WebSocket(buildWebSocketUrl(access))

  socket.onopen = () => handlers.onOpen()
  socket.onmessage = (event) => {
    // 要发送的数据
    handlers.onRawMessage(event.data)
    try {
      const payload = JSON.parse(event.data) as Record<string, unknown>
      //响应数据
      handlers.onMessage(payload)
    } catch {
      // keep raw log only
    }
  }
  socket.onerror = () => handlers.onError()
  socket.onclose = (event) => handlers.onClose(event)

  return socket
}
