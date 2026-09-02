// SpielOS OpenCode adapter for the stable 1.x plugin contract.
//
// Every model request receives one bounded, read-only company projection. On
// session idle, pending runtime attention is surfaced as synthetic messages.

import type { Plugin } from "@opencode-ai/plugin"

type Notification = {
  id: string
  kind: string
  goal_id: string
  run_id?: string
  payload?: Record<string, any>
}

// The clean core parks live actions as one kind of owner attention.
const REPORTABLE = new Set([
  "owner_input_required",
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
  const lines = [
    `SpielOS attention · ${item.kind}`,
    `Goal: ${payload.goal?.name || item.goal_id}`,
  ]
  if (payload.message) lines.push(`Message: ${payload.message}`)
  const next = payload.required_user_action
  if (next) lines.push(`Next: ${next}`)
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
  if (reportable.length) {
    const text = reportable.map(formatNotification).join("\n\n")
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
        const projection = await runCompany([
          "context", "--prompt", prompts.get(sessionID) || "",
          "--owner", "director", "--json",
        ]) as { context?: string }
        if (!projection.context) throw new Error("empty context projection")
        output.system.push(projection.context)
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
