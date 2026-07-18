import { create } from 'zustand'

import type { ZestEvent } from '../types/zest'

import { isV1Event } from '../types/zestGuards'

import { handleEventForUI } from '../utils/handleEventForUI'



export type UIEvent = ZestEvent



type EventState = {

  events: UIEvent[]

  uiEvents: UIEvent[]

  addEvent: (event: UIEvent) => void

  clearEvents: () => void

}


//
export const useEventStore = create<EventState>()((set) => ({

  events: [],

  uiEvents: [],

  addEvent: (event) =>

    set((state) => ({

      events: [...state.events, event],

      uiEvents: isV1Event(event) ? handleEventForUI(event, state.uiEvents) : [...state.uiEvents, event],

    })),

  clearEvents: () =>

    set(() => ({

      events: [],

      uiEvents: [],

    })),

}))
