import { useEffect, useState } from 'react'

export function useWorkspaceLayout() {
  const [isRightPanelShown, setIsRightPanelShown] = useState(true)

  useEffect(() => {
    const media = window.matchMedia('(max-width: 1024px)')
    const sync = () => setIsRightPanelShown(!media.matches)
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])

  return { isRightPanelShown, setIsRightPanelShown }
}
