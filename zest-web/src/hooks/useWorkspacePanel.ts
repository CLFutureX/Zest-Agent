import { useMemo, useState } from 'react'

export type WorkspacePanelTab = 'baseMemories' | 'experienceMemories'

const DEFAULT_RIGHT_PANEL_WIDTH = 420
const MIN_RIGHT_PANEL_WIDTH = 320
const MAX_RIGHT_PANEL_WIDTH = 860

function clampPanelWidth(width: number) {
  return Math.min(MAX_RIGHT_PANEL_WIDTH, Math.max(MIN_RIGHT_PANEL_WIDTH, width))
}

export function useWorkspacePanel() {
  const [isRightPanelShown, setIsRightPanelShown] = useState(false)
  const [rightPanelWidth, setRightPanelWidthState] = useState(DEFAULT_RIGHT_PANEL_WIDTH)
  const [isRightPanelFullscreen, setIsRightPanelFullscreen] = useState(false)

  const actions = useMemo(
    () => ({
      openRightPanel: () => {
        setIsRightPanelShown(true)
      },
      closeRightPanel: () => {
        setIsRightPanelShown(false)
        setIsRightPanelFullscreen(false)
      },
      toggleRightPanel: () => {
        setIsRightPanelShown((current) => {
          const next = !current
          if (!next) {
            setIsRightPanelFullscreen(false)
          }
          return next
        })
      },
      setRightPanelWidth: (width: number) => {
        setRightPanelWidthState(clampPanelWidth(width))
      },
      toggleRightPanelFullscreen: () => {
        setIsRightPanelShown(true)
        setIsRightPanelFullscreen((current) => !current)
      },
    }),
    [],
  )

  return {
    isRightPanelShown,
    rightPanelWidth,
    isRightPanelFullscreen,
    ...actions,
  }
}
