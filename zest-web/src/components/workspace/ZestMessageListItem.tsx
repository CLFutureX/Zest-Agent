/**
 * ZestMessageListItem — renders a single human or assistant message.
 * Aligned with deer-flow's MessageListItem design:
 *   - Human: right-aligned bubble
 *   - Assistant: left-aligned with Markdown rendering
 */
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import type { ZestMessage } from '../../utils/groupZestMessages'

interface Props {

  message: ZestMessage

  isLoading?: boolean

}

function resolveRoleMeta(role: ZestMessage['role']) {
  if (role === 'user') return { className: 'user', label: 'User', icon: 'U' }
  if (role === 'system') return { className: 'system', label: 'System', icon: 'S' }
  return { className: 'assistant', label: 'Assistant', icon: 'A' }
}



function renderAssistantContent(message: ZestMessage, isLoading?: boolean) {

  const content = message.content.trim() || message.reasoningContent?.trim() || message.thought?.trim() || ''



  return (

    <div className={`zest-msg-markdown${isLoading ? ' is-streaming' : ''}`}>

      {content ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown> : null}

    </div>

  )

}



export function ZestMessageListItem({ message, isLoading }: Props) {

  const roleMeta = resolveRoleMeta(message.role)

  const roleClass = roleMeta.className

  const isUser = roleClass === 'user'



  return (

    <div className={`zest-msg-item zest-msg-${roleClass}`}>

      <span className={`zest-msg-badge ${roleClass}`}>

        <span className="zest-msg-badge-icon" aria-hidden="true">{roleMeta.icon}</span>

        {roleMeta.label}

      </span>

      <div className={`zest-msg-bubble ${roleClass}`}>

        {isUser ? <p className="zest-msg-text">{message.content}</p> : renderAssistantContent(message, isLoading)}

        <time className="zest-msg-time">

          {new Date(message.timestamp).toLocaleTimeString()}

        </time>

      </div>

    </div>

  )

}

