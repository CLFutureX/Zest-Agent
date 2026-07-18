import type { ConversationAccessInfo } from '../types/workspace'

export function buildEventsUrl(access: ConversationAccessInfo): string {
  return `${access.base_url.replace(/\/$/, '')}/conversations/${access.conversation_id}/events`
}

export function buildWebSocketUrl(access: ConversationAccessInfo): string {
  const httpUrl = new URL(access.base_url)
  const protocol = httpUrl.protocol === 'https:' ? 'wss:' : 'ws:'
  const query = new URLSearchParams()

  if (access.session_api_key) {
    query.set('session_api_key', access.session_api_key)
  }

  if (access.resend_all) {
    query.set('resend_all', 'true')
  }

  const suffix = query.toString() ? `?${query.toString()}` : ''
  return `${protocol}//${httpUrl.host}/sockets/events/${access.conversation_id}${suffix}`
}
