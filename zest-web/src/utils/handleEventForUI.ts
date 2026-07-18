import type { ZestEvent } from '../types/zest'



export function handleEventForUI(

  event: ZestEvent,

  uiEvents: ZestEvent[],

): ZestEvent[] {

  // Deduplicate by id: if the same event id already exists, skip
  if (uiEvents.some((e) => e.id === event.id)) {

    return uiEvents

  }

  return [...uiEvents, event]

}
