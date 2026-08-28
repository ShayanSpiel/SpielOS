// SpielOS1 event-driven notification surface.
//
// The durable runner advances deterministic work. This adapter does one host
// job on session.idle: display pending runtime attention, then acknowledge
// only the exact ids successfully shown. It owns no timer, advancement,
// heartbeat, watchdog, or second scheduling loop.

type V2SessionIdleEvent = {
  type: "session.idle"
  data: { sessionID: string }
}

type V2Event = V2SessionIdleEvent | { type: string; data?: Record<string, unknown> }

type V2Context = {
  event: { subscribe(): AsyncIterable<V2Event> }
  session: {
    synthetic(input: { sessionID: string; text: { text: string } }): Promise<unknown>
  }
}

type Notification = {
  id: string
  kind: string
  goal_id: string
  run_id?: string
  payload?: Record<string, any>
  why_next?: string
}

const REPORTABLE = new Set([
  "approval_required", "action_required", "blocked", "stuck_goal",
  "goal_achieved", "goal_abandoned", "goal_expired",
  "goal_completed_followup", "watchdog_digest", "runner_down",
])

const runCompany = async (args: string[]): Promise<any> => {
  const child = Bun.spawn({
    cmd: ["python3", "-B", "-m", "company", ...args],
    cwd: process.cwd(),
    stdout: "pipe",
    stderr: "pipe",
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
  })
  const [code, stdout] = await Promise.all([
    child.exited,
    new Response(child.stdout).text(),
  ])
  if (code !== 0) throw new Error(`company command failed (${code})`)
  return JSON.parse(stdout)
}

const formatNotification = (item: Notification): string => {
  const payload = item.payload || {}
  const interaction = payload.approval_interaction || {}
  const result = payload.result || {}
  const followup = payload.followup || {}
  const lines = [
    `SpielOS attention · ${item.kind}`,
    `Goal: ${payload.goal?.name || item.goal_id}`,
  ]
  if (result.message) lines.push(`Result: ${result.message}`)
  if (interaction.question) lines.push(`Question: ${interaction.question}`)
  if (interaction.action) lines.push(`Action: ${interaction.action}`)
  if (interaction.destination) lines.push(`Destination: ${interaction.destination}`)
  if (interaction.scope) lines.push(`Scope: ${interaction.scope}`)
  if (interaction.risk) lines.push(`Risk: ${interaction.risk}`)
  if (interaction.consequence) lines.push(`Consequence: ${interaction.consequence}`)
  const next = payload.required_user_action
    || followup.recommended_next_action
    || item.why_next
  if (next) lines.push(`Next: ${next}`)
  if (interaction.fallback_command) lines.push(`Command: ${interaction.fallback_command}`)
  return lines.join("\n")
}

const surfacePending = async (ctx: V2Context, sessionID: string) => {
  const rows = await runCompany([
    "notifications", "list", "--status", "pending", "--limit", "20", "--json",
  ]) as Notification[]
  const reportable = rows.filter((row) => REPORTABLE.has(row.kind))
  const approvals = reportable.filter((row) => row.kind === "approval_required")
  const ordinary = reportable.filter((row) => row.kind !== "approval_required")
  const preferred = new Map<string, Notification>()
  for (const item of ordinary) {
    const key = `${item.goal_id}:${item.run_id || ""}`
    const current = preferred.get(key)
    if (!current || item.kind === "goal_completed_followup") preferred.set(key, item)
  }
  for (const item of approvals) {
    await ctx.session.synthetic({
      sessionID,
      text: { text: formatNotification(item) },
    })
  }
  if (preferred.size) {
    const sections = [...preferred.values()].map(formatNotification)
    await ctx.session.synthetic({
      sessionID,
      text: { text: `SpielOS company update\n\n${sections.join("\n\n")}` },
    })
  }
  for (const item of reportable) {
    await runCompany(["notifications", "ack", item.id, "--json"])
  }
}

export default {
  id: "spielos-notifications",
  setup: async (ctx: V2Context) => {
    let disposed = false
    void (async () => {
      for await (const event of ctx.event.subscribe()) {
        if (disposed) break
        if (event.type !== "session.idle") continue
        try {
          await surfacePending(ctx, event.data.sessionID)
        } catch {
          // Persistence is the fallback. A failed host surface leaves every
          // notification pending for the next idle event or `company status`.
        }
      }
    })()
    return async () => { disposed = true }
  },
}
