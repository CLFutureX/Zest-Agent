/**
 * ZestMessageGroup — collapsible tool-call chain.
 * Aligned with deer-flow's MessageGroup (ChainOfThought style):
 *   - Shows the last active tool step prominently
 *   - Older steps are collapsed under a "more steps" toggle
 *   - Reasoning / thought text shown in a separate collapsible
 */
import { useMemo, useState } from 'react'

import type { ZestMessage } from '../../utils/groupZestMessages'

const DEFAULT_VISIBLE_STEPS = 3

const TOOL_ICON: Record<string, string> = {
  ExecuteBash: '⚡',
  FileEditor: '📝',
  StrReplace: '✏️',
  Browser: '🌐',
  MCPTool: '🔧',
  Finish: '✅',
  Think: '💭',
  Default: '🔩',
}

function toolIcon(actionKind?: string): string {
  if (!actionKind) return TOOL_ICON.Default
  for (const [key, icon] of Object.entries(TOOL_ICON)) {
    if (actionKind.includes(key)) return icon
  }
  return TOOL_ICON.Default
}

function toolLabel(msg: ZestMessage): string {
  if (msg.toolName) return msg.toolName
  if (msg.actionKind) {
    return msg.actionKind.replace(/Action$/, '').replace(/([A-Z])/g, ' $1').trim()
  }
  return 'Tool'
}

function normalizeEventType(msg: ZestMessage): string | undefined {
  if (msg.rawKind) return msg.rawKind
  return msg.eventType
}

function resolveStepDescription(msg: ZestMessage): string | null {
  const eventType = normalizeEventType(msg)
  if (eventType === 'ActionEvent') return '正在执行工具'
  if (eventType === 'ObservationEvent') return '工具执行结果'
  if (msg.content.trim()) return msg.content.trim()
  if (msg.reasoningContent?.trim()) return msg.reasoningContent.trim()
  return null
}

function resolveDetailBlock(title: string, value?: string) {
  if (!value?.trim()) return null
  return (
    <details className="zest-tool-step-detail">
      <summary>{title}</summary>
      <pre className="zest-tool-step-output">{value}</pre>
    </details>
  )
}

function resolveStepTone(msg: ZestMessage): 'action' | 'observation' | 'status' {
  const eventType = normalizeEventType(msg)
  if (eventType === 'ActionEvent') return 'action'
  if (eventType === 'ObservationEvent') return 'observation'
  return 'status'
}

interface ToolStepProps {
  msg: ZestMessage
  isLast?: boolean
  isLoading?: boolean
}

function ToolStep({ msg, isLast, isLoading }: ToolStepProps) {
  const description = resolveStepDescription(msg)
  const eventType = normalizeEventType(msg)
  const tone = resolveStepTone(msg)

  return (
    <div className={`zest-tool-step tone-${tone}${isLast ? ' is-last' : ''}${isLoading && isLast ? ' is-loading' : ''}`}>
      <span className="zest-tool-step-icon">{toolIcon(msg.actionKind)}</span>
      <div className="zest-tool-step-body">
        <div className="zest-tool-step-header">
          <span className="zest-tool-step-label">{toolLabel(msg)}</span>
          {eventType && <span className={`zest-tool-step-type tone-${tone}`}>{eventType}</span>}
        </div>
        {description && <p className="zest-tool-step-description">{description}</p>}
        {msg.filePath && <code className="zest-tool-step-path">{msg.filePath}</code>}
        {msg.reasoningContent && <p className="zest-tool-step-thought">{msg.reasoningContent}</p>}
        {msg.thought && msg.thought !== msg.reasoningContent && (
          <p className="zest-tool-step-thought">{msg.thought}</p>
        )}
        {resolveDetailBlock('参数', msg.toolArgs)}
        {resolveDetailBlock('结果', msg.toolResult)}
        {!msg.toolResult && msg.commandOutput && <pre className="zest-tool-step-output">{msg.commandOutput}</pre>}
        {msg.exitCode !== undefined && msg.exitCode !== null && (
          <span className={`zest-tool-step-exit ${msg.exitCode === 0 ? 'success' : 'error'}`}>
            exit {msg.exitCode}
          </span>
        )}
      </div>
    </div>
  )
}

interface Props {
  messages: ZestMessage[]
  isLoading?: boolean
}

export function ZestMessageGroup({ messages, isLoading }: Props) {
  const [showAll, setShowAll] = useState(false)

  const dedupedMessages = useMemo(() => {
    const merged = new Map<string, ZestMessage>()

    messages.forEach((message) => {
      const key = message.toolCallId || `${message.toolName || message.actionKind || 'tool'}-${message.id}`
      const existing = merged.get(key)
      if (!existing) {
        merged.set(key, message)
        return
      }

      merged.set(key, {
        ...existing,
        ...message,
        content: message.content || existing.content,
        thought: existing.thought || message.thought,
        reasoningContent: existing.reasoningContent || message.reasoningContent,
        toolArgs: existing.toolArgs || message.toolArgs,
        toolResult: existing.toolResult || message.toolResult,
        commandOutput: existing.commandOutput || message.commandOutput,
        filePath: existing.filePath || message.filePath,
        eventType: existing.eventType || message.eventType,
        rawKind: existing.rawKind || message.rawKind,
        exitCode: message.exitCode ?? existing.exitCode,
      })
    })

    return Array.from(merged.values())
  }, [messages])

  if (dedupedMessages.length === 0) return null

  const alwaysVisibleMessages = dedupedMessages.slice(-DEFAULT_VISIBLE_STEPS)
  const collapsedMessages = dedupedMessages.slice(0, -DEFAULT_VISIBLE_STEPS)
  const lastVisibleMessage = alwaysVisibleMessages[alwaysVisibleMessages.length - 1]!

  return (
    <div className="zest-msg-group">
      {collapsedMessages.length > 0 && (
        <button
          type="button"
          className="zest-msg-group-toggle"
          onClick={() => setShowAll(!showAll)}
        >
          {showAll ? '隐藏更早步骤' : `展开更早的 ${collapsedMessages.length} 步`}
          <span className={`zest-msg-group-chevron${showAll ? ' open' : ''}`}>›</span>
        </button>
      )}

      {showAll && collapsedMessages.map((msg) => (
        <ToolStep key={msg.id} msg={msg} />
      ))}

      {alwaysVisibleMessages.map((msg) => (
        <ToolStep
          key={msg.id}
          msg={msg}
          isLast={msg.id === lastVisibleMessage.id}
          isLoading={isLoading && msg.id === lastVisibleMessage.id}
        />
      ))}
    </div>
  )
}
