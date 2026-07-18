import { buildEventsUrl } from './runtimeUrl'

import type { ConversationAccessInfo } from '../types/workspace'

export async function sendConversationMessage(input: {
  conversation: ConversationAccessInfo
  content: string
}): Promise<void> {
  const { conversation, content } = input

  const response = await fetch(buildEventsUrl(conversation), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(conversation.session_api_key
        ? { 'X-Session-API-Key': conversation.session_api_key }
        : {}),
    },
    body: JSON.stringify({
      role: 'user',
      content: [{ text: content }],
      run: true,
    }),
  })

  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `Send message failed: ${response.status}`)
  }
}
