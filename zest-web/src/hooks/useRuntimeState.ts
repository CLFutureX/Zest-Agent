import { useState } from 'react'

import type { RuntimeEvent } from '../types/runtimeEvents'
import type { ConfirmationState, RuntimeAgentStatus } from '../types/runtimeState'

export function useRuntimeState() {
  const [lastEvent, setLastEvent] = useState<RuntimeEvent | null>(null)
  const [agentState, setAgentState] = useState<RuntimeAgentStatus>('idle')
  const [latestMessage, setLatestMessage] = useState('')
  const [confirmationBusy, setConfirmationBusy] = useState(false)
  const [confirmationState, setConfirmationState] = useState<ConfirmationState>({
    pending: false,
    actionId: null,
    toolName: null,
    toolCallId: null,
    summary: null,
  })

  return {
    lastEvent,
    setLastEvent,
    agentState,
    setAgentState,
    latestMessage,
    setLatestMessage,
    confirmationBusy,
    setConfirmationBusy,
    confirmationState,
    setConfirmationState,
  }
}
