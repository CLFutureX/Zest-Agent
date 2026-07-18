import { useMemo, useCallback } from 'react'

import type { RuntimeEvent } from '../types/runtimeEvents'

import type { TimelineItem } from '../types/workspace'

import { useEventStore } from '../stores/useEventStore'

import { buildTimelineEntryFromRuntimeEvent } from '../utils/runtimeEventAssembler'



function now(): string {

  return new Date().toLocaleTimeString()

}



function mergePairedTimeline(

  items: TimelineItem[],

  nextItem: Omit<TimelineItem, 'time'> & { time?: string },

): TimelineItem[] {

  const itemWithTime = { ...nextItem, time: nextItem.time ?? now() }



  // Observation arrives: mark its paired action as paired=true, then append observation
  if (itemWithTime.kind === 'observation' && itemWithTime.pairId) {

    const actionIndex = items.findIndex((e) => e.kind === 'action' && e.pairId === itemWithTime.pairId)

    if (actionIndex !== -1) {

      const next = [...items]

      next[actionIndex] = { ...next[actionIndex], paired: true }

      return [...next, itemWithTime]

    }

  }



  return [...items, itemWithTime]

}



export function useTimeline() {

  const uiEvents = useEventStore((state) => state.uiEvents)

  const events = useEventStore((state) => state.events)



  const timeline = useMemo(() => {

    return uiEvents.reduce<TimelineItem[]>((current, event) => {



      const result = buildTimelineEntryFromRuntimeEvent(event)



      if (result.mode === 'upsert') {



        const index = current.findIndex((item) => item.id === result.entry.id)



        if (index !== -1) {



          const next = [...current]



          next[index] = { ...next[index], ...result.entry }



          return next



        }



      }



      return mergePairedTimeline(current, result.entry)



    }, [])

  }, [uiEvents])



  const eventLogText = useMemo(

    () => events.map((event) => JSON.stringify(event, null, 2)).reverse().join('\n\n') || '等待 websocket 事件...',

    [events],

  )



  const appendTimeline = useCallback((_item: Omit<TimelineItem, 'time'> & { time?: string }) => undefined, [])

  const appendEventLog = useCallback((_payload: unknown) => undefined, [])

  const mapRuntimeEventToTimeline = useCallback((_payload: RuntimeEvent) => undefined, [])



  return {

    timeline,

    eventLogText,

    appendTimeline,

    appendEventLog,

    mapRuntimeEventToTimeline,

  }

}


 
