// Compatibility-only OpenCode adapter for SpielOS1.
//
// Runtime progression belongs to `company runner watch`; attached-session
// wakeups belong to `company runner wake`. This adapter deliberately owns no
// timers, polling, heartbeat checks, or fallback advancement.

type V2SessionIdleEvent = {
  type: "session.idle"
  data: { sessionID: string }
}

type V2Event = V2SessionIdleEvent | { type: string; data?: Record<string, unknown> }

type V2Context = {
  event: { subscribe(): AsyncIterable<V2Event> }
}

export default {
  id: "spielos-notifications",
  setup: async (ctx: V2Context) => {
    let disposed = false
    void (async () => {
      for await (const event of ctx.event.subscribe()) {
        if (disposed) break
        // Retain only V2 load compatibility. A host wake is explicitly
        // requested by the Director through `company runner wake`.
        if (event.type === "session.idle") continue
      }
    })()
    return async () => { disposed = true }
  },
}
