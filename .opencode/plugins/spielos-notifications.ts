// SpielOS OpenCode adapter for the stable 1.x plugin contract.
//
// Every model request receives one bounded, read-only company projection. On
// session idle, pending runtime attention is surfaced as synthetic messages.

import type { Plugin, PluginModule } from "@opencode-ai/plugin"

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

const companyRunner = (directory: string) => async (args: string[]): Promise<any> => {
  const vendoredPythonPath = `${directory}/.agents`
  const pythonPath = process.env.PYTHONPATH
    ? `${vendoredPythonPath}:${process.env.PYTHONPATH}`
    : vendoredPythonPath
  const child = Bun.spawn({
    cmd: ["python3", "-B", "-m", "company", ...args],
    cwd: directory,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      PYTHONDONTWRITEBYTECODE: "1",
      PYTHONPATH: pythonPath,
    },
  })
  const [code, stdout, stderr] = await Promise.all([
    child.exited,
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
  ])
  if (code !== 0) {
    const detail = stderr.trim().split("\n").at(-1) || `exit ${code}`
    throw new Error(`company command failed: ${detail}`)
  }
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

const surfacePending = async (
  client: any,
  directory: string,
  sessionID: string,
  runCompany: (args: string[]) => Promise<any>,
) => {
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
  const messages = [
    ...approvals.map(formatNotification),
    ...([...preferred.values()].length
      ? [`SpielOS company update\n\n${[...preferred.values()].map(formatNotification).join("\n\n")}`]
      : []),
  ]
  for (const text of messages) {
    await client.session.prompt({
      path: { id: sessionID },
      query: { directory },
      body: {
        noReply: true,
        parts: [{ type: "text", text, synthetic: true }],
      },
    })
  }
  for (const item of reportable) {
    await runCompany(["notifications", "ack", item.id, "--json"])
  }
}

export const SpielOSContext: Plugin = async ({ client, directory }) => {
  const runCompany = companyRunner(directory)
  const prompts = new Map<string, string>()
  const seen = new Set<string>()
  return {
    "chat.message": async (input, output) => {
      prompts.set(input.sessionID, output.parts
        .filter((part) => part.type === "text")
        .map((part) => "text" in part ? part.text : "")
        .join("\n"))
    },
    "experimental.chat.system.transform": async (input, output) => {
      const sessionID = input.sessionID || ""
      try {
        const args = [
          "context", "--prompt", prompts.get(sessionID) || "",
          "--owner", "director",
        ]
        if (!seen.has(sessionID)) args.push("--boot")
        args.push("--json")
        const projection = await runCompany(args) as { context?: string }
        if (!projection.context) throw new Error("empty context projection")
        output.system.push(projection.context)
        seen.add(sessionID)
      } catch (error) {
        const detail = error instanceof Error ? error.message : "unknown host error"
        output.system.push(
          "SpielOS context unavailable for this request. Do not search the repository " +
          "or guess company state. Tell the owner that host context injection failed " +
          `and report this diagnostic: ${detail}`,
        )
      }
    },
    event: async ({ event }) => {
      if (event.type !== "session.idle") return
      try {
        await surfacePending(client, directory, event.properties.sessionID, runCompany)
      } catch {
        // Persistence is the fallback. Failed delivery remains pending.
      }
    },
  }
}

const plugin: PluginModule = {
  id: "spielos-notifications",
  server: SpielOSContext,
}

export default plugin
