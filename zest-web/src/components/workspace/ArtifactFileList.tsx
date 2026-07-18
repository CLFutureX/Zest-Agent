/**
 * ArtifactFileList — renders file cards for present-files groups.
 * Mirrors deer-flow's ArtifactFileList card design.
 */
import type { ZestMessage } from '../../utils/groupZestMessages'

const FILE_TYPE_MAP: Record<string, string> = {
  json: 'JSON', csv: 'CSV', txt: 'TXT', md: 'Markdown',
  py: 'Python', js: 'JavaScript', ts: 'TypeScript',
  tsx: 'TSX', jsx: 'JSX', html: 'HTML', css: 'CSS',
  png: 'PNG', jpg: 'JPG', jpeg: 'JPEG', svg: 'SVG',
}

function getExt(filePath: string): string {
  return filePath.split('.').pop()?.toLowerCase() ?? ''
}
function getTypeLabel(filePath: string): string {
  const ext = getExt(filePath)
  return FILE_TYPE_MAP[ext] ?? (ext.toUpperCase() || 'FILE')
}
function getFileName(filePath: string): string {
  return filePath.split(/[\\/]/).pop() ?? filePath
}

interface FileCardProps {
  filePath: string
}

function ArtifactFileCard({ filePath }: FileCardProps) {
  return (
    <div className="zest-artifact-card">
      <span className="zest-artifact-icon">📄</span>
      <div className="zest-artifact-info">
        <span className="zest-artifact-name" title={filePath}>
          {getFileName(filePath)}
        </span>
        <span className="zest-artifact-type">{getTypeLabel(filePath)} file</span>
      </div>
      <a
        className="zest-artifact-download"
        href={filePath}
        download={getFileName(filePath)}
        title="下载"
      >
        ↓
      </a>
    </div>
  )
}

interface Props {
  messages: ZestMessage[]
}

export function ArtifactFileList({ messages }: Props) {
  const files = messages.map((m) => m.filePath).filter((f): f is string => Boolean(f))
  if (files.length === 0) return null

  return (
    <div className="zest-artifact-list zest-artifact-list--assistant">
      {files.map((fp) => (
        <ArtifactFileCard key={fp} filePath={fp} />
      ))}
    </div>
  )
}

