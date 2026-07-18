/**
 * Scan historical conversation events and extract unique file paths
 * produced by write/edit tools (FileEditor, StrReplace, write_file, etc.)
 *
 * Each ConversationEventRecord.payload may carry an `action` or `observation`
 * sub-object whose `kind` string identifies the tool.  We look for:
 *   - action.kind  includes 'FileEditor' | 'StrReplace'
 *   - observation.kind includes 'FileEditor' | 'StrReplace'
 *   - payload.tool_name === 'write_file' | 'edit' | 'file_editor'
 *
 * The file path lives in action.path / observation.path.
 */

import type { ConversationEventRecord } from '../types/workspace'

const FILE_TOOL_KINDS = ['FileEditor', 'StrReplace']
const FILE_TOOL_NAMES = new Set(['write_file', 'edit', 'file_editor', 'str_replace_editor'])

function asStr(v: unknown): string | null {
  return typeof v === 'string' && v.trim() ? v : null
}

function readObj(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null
}

function extractPathFromPayload(payload: Record<string, unknown>): string | null {
  // tool_name or name at top level (e.g. "file_editor")
  const toolName = asStr(payload.tool_name) ?? asStr(payload.name)
  if (toolName && FILE_TOOL_NAMES.has(toolName)) {
    // Direct path field
    const directPath = asStr(payload.path) ?? asStr(payload.file_path)
    if (directPath) return directPath

    // Path may be embedded in content[].text like "File created successfully: /path/to/file"
    const contentPath = extractPathFromContent(payload.content)
    if (contentPath) return contentPath
  }

  // action sub-object
  const action = readObj(payload.action)
  if (action) {
    const kind = asStr(action.kind) ?? ''
    if (FILE_TOOL_KINDS.some((k) => kind.includes(k))) {
      return asStr(action.path)
    }
  }

  // observation sub-object
  const obs = readObj(payload.observation)
  if (obs) {
    const kind = asStr(obs.kind) ?? ''
    if (FILE_TOOL_KINDS.some((k) => kind.includes(k))) {
      return asStr(obs.path)
    }
  }

  return null
}

/**
 * Extract file path from content like:
 *   "File created successfully: D:\\spacex\\...\\file.md"
 *   "File edited successfully: /path/to/file"
 *   content can be string or Array<{type:"text", text:string}>
 */
function extractPathFromContent(content: unknown): string | null {
  let text: string | null = null

  if (typeof content === 'string') {
    text = content
  } else if (Array.isArray(content)) {
    for (const item of content) {
      if (item && typeof item === 'object' && typeof item.text === 'string') {
        text = item.text
        break
      }
    }
  }

  if (!text) return null

  // Match patterns like "File created successfully: /path" or "File edited successfully: /path"
  const match = text.match(/(?:created|edited|written|updated)\s+successfully:\s*(.+)/i)
  if (match && match[1].trim()) return match[1].trim()

  // Fallback: if the text looks like a file path (starts with / or drive letter)
  const trimmed = text.trim()
  if (/^[A-Za-z]:\\|^\/[a-zA-Z]/.test(trimmed)) return trimmed

  return null
}

/**
 * Returns deduplicated file paths from write/edit events in the event history.
 */
export function extractArtifactsFromEvents(events: ConversationEventRecord[]): string[] {
  const seen = new Set<string>()
  for (const record of events) {
    const path = extractPathFromPayload(record.payload)
    if (path && !seen.has(path)) {
      seen.add(path)
    }
  }
  return Array.from(seen)
}

