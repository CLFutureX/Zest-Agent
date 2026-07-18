import { WorkspaceArtifactPanel } from './WorkspaceArtifactPanel'
import { WorkspaceEventGraphPanel } from './WorkspaceEventGraphPanel'

import type { ZestEvent } from '../../types/zest'
import type { ConversationEventRecord } from '../../types/workspace'

import { useState, type PointerEvent as ReactPointerEvent } from 'react'

// 右侧资源面板当前支持产物列表和事件图两个视图。
type WorkspaceResourceTab = 'artifacts' | 'event-graph'

// 事件图需要额外接入会话事件数据，因此这里统一透传给子面板。
type WorkspaceResourcePanelProps = {
  isRightPanelShown: boolean

  isFullscreen: boolean

  width: number

  onClose: () => void

  onResize: (width: number) => void

  onToggleFullscreen: () => void

  artifacts: string[]

  historicalRecords: ConversationEventRecord[]

  liveEvents: ZestEvent[]
}



export function WorkspaceResourcePanel(props: WorkspaceResourcePanelProps) {

  const {
    isRightPanelShown,
    isFullscreen,
    width,
    onClose,
    onResize,
    onToggleFullscreen,
    artifacts,
    historicalRecords,
    liveEvents,
  } = props
  const [activeTab, setActiveTab] = useState<WorkspaceResourceTab>(
    artifacts.length > 0 ? 'artifacts' : 'event-graph',
  )

  const handleResizeStart = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const startX = event.clientX
    const startWidth = width

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const nextWidth = startWidth - (moveEvent.clientX - startX)
      onResize(nextWidth)
    }

    const handlePointerUp = () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)
  }

  return (

    <section
      className={`workspace-resource-panel${isFullscreen ? ' workspace-resource-panel--fullscreen' : ''}`}
      style={isFullscreen ? undefined : { width: `${width}px`, minWidth: `${width}px` }}
    >
      {!isFullscreen && (
        <button
          type="button"
          className="workspace-resource-panel__resize-handle"
          onPointerDown={handleResizeStart}
          aria-label="拖动调整侧栏宽度"
        />
      )}

      <div className="workspace-resource-panel__header">

        <div>

          <p className="workspace-resource-panel__eyebrow">Resources</p>

          <h2 className="workspace-resource-panel__title">

            {activeTab === 'artifacts' ? 'Artifacts' : 'Event Graph'}

          </h2>

        </div>

        <div className="workspace-resource-panel__header-actions">
          <button
            type="button"
            className="workspace-resource-panel__icon-button"
            onClick={onToggleFullscreen}
            aria-label={isFullscreen ? '退出局部全屏' : '局部全屏显示'}
          >
            {isFullscreen ? '↙' : '⛶'}
          </button>

          <button
            type="button"
            className="workspace-resource-panel__icon-button workspace-resource-panel__close"
            onClick={onClose}
            aria-label={isRightPanelShown ? '隐藏资源面板' : '显示资源面板'}
          >
            {isRightPanelShown ? '×' : '≡'}
          </button>
        </div>

      </div>

      <div className="workspace-resource-panel__tabs" role="tablist" aria-label="资源面板视图">
        <button
          type="button"
          className={`workspace-resource-panel__tab${activeTab === 'artifacts' ? ' active' : ''}`}
          onClick={() => setActiveTab('artifacts')}
        >
          Artifacts
        </button>
        <button
          type="button"
          className={`workspace-resource-panel__tab${activeTab === 'event-graph' ? ' active' : ''}`}
          onClick={() => setActiveTab('event-graph')}
        >
          Event Graph
        </button>
      </div>

      <div className="workspace-resource-panel__content workspace-resource-panel__content--plain">
        {activeTab === 'artifacts' ? (
          <WorkspaceArtifactPanel artifacts={artifacts} />
        ) : (
          <WorkspaceEventGraphPanel historicalRecords={historicalRecords} liveEvents={liveEvents} />
        )}
      </div>

    </section>

  )

}
