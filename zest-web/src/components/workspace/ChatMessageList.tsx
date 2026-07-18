/**
 * ChatMessageList -- renders conversation messages in deer-flow style.
 *
 * Groups are rendered as:
 *   human                   -> ZestMessageListItem (right-aligned bubble)
 *   assistant               -> ZestMessageListItem (Markdown)
 *   assistant:processing    -> ZestMessageGroup (collapsible tool chain)
 *   assistant:present-files -> ArtifactFileList (file cards)
 */
import { useMemo } from 'react'

import type { ZestEvent } from '../../types/zest'
import type { ConversationEventRecord } from '../../types/workspace'
import {
  groupConversationRecords,
  groupLiveEvents,
  type ZestMessageGroup as ZestGroupedMessages,
} from '../../utils/groupZestMessages'

import { ArtifactFileList } from './ArtifactFileList'
import { ZestMessageGroup } from './ZestMessageGroup'
import { ZestMessageListItem } from './ZestMessageListItem'

function ChatEventLegend() {
  return (
    <div className="zest-event-legend" aria-label="消息角色与事件图例">
      <span className="zest-event-legend-item role-user">
        <span className="zest-event-legend-icon">U</span>
        User
      </span>
      <span className="zest-event-legend-item role-assistant">
        <span className="zest-event-legend-icon">A</span>
        Assistant
      </span>
      <span className="zest-event-legend-item role-system">
        <span className="zest-event-legend-icon">S</span>
        System
      </span>
      <span className="zest-event-legend-item tone-action">
        <span className="zest-event-legend-dot" />
        Action
      </span>
      <span className="zest-event-legend-item tone-observation">
        <span className="zest-event-legend-dot" />
        Observation
      </span>
      <span className="zest-event-legend-item tone-status">
        <span className="zest-event-legend-dot" />
        Status
      </span>
    </div>
  )
}

function mergeToolGroups(groups: ZestGroupedMessages[]): ZestGroupedMessages[] {
  const merged: ZestGroupedMessages[] = []

  groups.forEach((group) => {
    const last = merged[merged.length - 1]
    if (group.type === 'assistant:processing' && last?.type === 'assistant:processing') {
      last.messages.push(...group.messages)
      return
    }
    merged.push(group)
  })

  return merged
}

type RenderBlock =
  | { id: string; type: 'human'; groups: ZestGroupedMessages[] }
  | { id: string; type: 'assistant-thread'; groups: ZestGroupedMessages[] }

function buildRenderBlocks(groups: ZestGroupedMessages[]): RenderBlock[] {
  const blocks: RenderBlock[] = []

  groups.forEach((group) => {
    const last = blocks[blocks.length - 1]
    if (group.type === 'human') {
      blocks.push({ id: group.id, type: 'human', groups: [group] })
      return
    }

    if (last?.type === 'assistant-thread') {
      last.groups.push(group)
      return
    }

    blocks.push({ id: group.id, type: 'assistant-thread', groups: [group] })
  })

  return blocks
}

interface Props {
  historicalRecords?: ConversationEventRecord[]
  liveEvents?: ZestEvent[]
  isLoading?: boolean
}

export function ChatMessageList({ historicalRecords = [], liveEvents = [], isLoading }: Props) {
  const groups = useMemo(() => {
    const histGroups = groupConversationRecords(historicalRecords)
    const liveGroups = groupLiveEvents(liveEvents)
    return mergeToolGroups([...histGroups, ...liveGroups])
  }, [historicalRecords, liveEvents])

  const renderBlocks = useMemo(() => buildRenderBlocks(groups), [groups])

  if (renderBlocks.length === 0) {
    return null
  }

  const lastGroup = groups[groups.length - 1]

  return (
    <div className="zest-message-list">
      <ChatEventLegend />
      {renderBlocks.map((block) => {
        if (block.type === 'human') {
          return block.groups.flatMap((group) =>
            group.messages.map((msg) => (
              <ZestMessageListItem
                key={msg.id}
                message={msg}
                isLoading={isLoading && group === lastGroup}
              />
            )),
          )
        }

        return (
          <div key={block.id} className="zest-assistant-thread">
            {block.groups.map((group) => {
              if (group.type === 'assistant') {
                return group.messages.map((msg) => (
                  <div key={msg.id} className="zest-assistant-thread-segment zest-assistant-thread-segment--message">
                    <ZestMessageListItem
                      message={msg}
                      isLoading={isLoading && group === lastGroup}
                    />
                  </div>
                ))
              }

              if (group.type === 'assistant:processing') {
                return (
                  <div key={group.id} className="zest-assistant-thread-segment zest-assistant-thread-segment--processing">
                    <ZestMessageGroup
                      messages={group.messages}
                      isLoading={isLoading && group === lastGroup}
                    />
                  </div>
                )
              }

              if (group.type === 'assistant:present-files') {
                return (
                  <div key={group.id} className="zest-assistant-thread-segment zest-assistant-thread-segment--artifacts">
                    <ArtifactFileList messages={group.messages} />
                  </div>
                )
              }

              return null
            })}
          </div>
        )
      })}
    </div>
  )
}
