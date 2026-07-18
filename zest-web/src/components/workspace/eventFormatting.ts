import type { TimelineItem, TimelineSection } from '../../types/workspace'

function truncate(value: string, limit = 240) {
  return value.length > limit ? `${value.slice(0, limit)}…` : value
}

/**
 * Zest V1 rendering rule:
 * - message (user/assistant): show full body
 * - action: show title only, body empty, details in collapsible sections
 * - observation: show title only + success/error indicator, details in collapsible sections
 * - status: show title only
 */
export function formatEventTitle(item: TimelineItem): string {
  return item.summary?.trim() || item.title
}

export function formatEventBody(item: TimelineItem): string {
  if (item.kind === 'message') return truncate(item.body)
  // action/observation/status: no body shown by default
  return ''
}

export function formatEventSections(item: TimelineItem): TimelineSection[] {
  return item.sections ?? []
}

export function formatEventSuccess(item: TimelineItem): 'success' | 'error' | undefined {
  if (item.kind !== 'observation') return undefined
  return item.success
}
