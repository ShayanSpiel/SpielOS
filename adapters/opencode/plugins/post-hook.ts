import type { Plugin } from "@opencode-ai/plugin"
import { existsSync, writeFileSync, mkdirSync, renameSync } from "node:fs"
import { join, dirname } from "node:path"

const VAULT = process.env.VAULT_DIR || process.cwd()

interface MessagePart {
  type?: string
  text?: string
  content?: string | MessagePart[]
}

interface SessionMessage {
  info?: { role?: string; type?: string }
  parts?: MessagePart[]
}

function extractText(part: MessagePart): string {
  if (typeof part.text === "string") return part.text
  if (part.content && typeof part.content === "string") return part.content
  if (Array.isArray(part.content)) {
    return part.content.map(extractText).filter(Boolean).join("\n")
  }
  return ""
}

function readMessages(client: any, sessionID: string) {
  const user: string[] = []
  const assistant: string[] = []
  let toolCalls = 0
  let totalLines = 0
  try {
    const result = client.session.messages({ path: { id: sessionID } })
    const data = result?.data || []
    for (const m of data as SessionMessage[]) {
      if (!m) continue
      totalLines++
      const role = m.info?.role || m.info?.type || ""
      const parts = m.parts || []
      const texts: string[] = []
      for (const p of parts) {
        if (p?.type === "tool_use") toolCalls++
        const t = extractText(p)
        if (t.trim()) texts.push(t)
      }
      const combined = texts.join("\n").trim()
      if (combined) {
        if (role === "user") user.push(combined)
        else if (role === "assistant") assistant.push(combined)
      }
    }
  } catch (e) {
  }
  return { user, assistant, toolCalls, totalLines }
}

function atomicWrite(path: string, content: string): void {
  mkdirSync(dirname(path), { recursive: true })
  const tmp = path + ".tmp"
  writeFileSync(tmp, content, "utf-8")
  renameSync(tmp, path)
}

function generateRunId(dateStr: string): string {
  const marker = join(VAULT, "content", ".run-counter")
  let n = 1
  try {
    if (existsSync(marker)) {
      const stored = JSON.parse(require("node:fs").readFileSync(marker, "utf-8"))
      if (stored.date === dateStr) n = (stored.n || 0) + 1
    }
  } catch {}
  require("node:fs").writeFileSync(marker, JSON.stringify({ date: dateStr, n }), "utf-8")
  return `${dateStr}-${String(n).padStart(3, "0")}`
}

function writeSessionFile(mode: string, inputText: string, data: any, dateStr: string): string {
  const sessionPath = join(VAULT, "content", "sessions", "current.md")
  const lines: string[] = [
    "---",
    `date: ${dateStr}`,
    `mode: ${mode}`,
    `captured_at: ${new Date().toISOString()}`,
    "captured_by: post-hook.ts (opencode plugin)",
    `transcript_lines: ${data.totalLines || 0}`,
    `user_messages: ${data.user?.length || 0}`,
    `assistant_messages: ${data.assistant?.length || 0}`,
    `tool_calls: ${data.toolCalls || 0}`,
    "---",
    "",
    "# Session Capture",
    "",
  ]
  if (mode === "topic") {
    lines.push("## Input (topic)", "", inputText, "")
  } else {
    lines.push("## User Messages", "")
    data.user?.forEach((m: string, i: number) => {
      lines.push(`### ${i + 1}`, "", m, "")
    })
    lines.push("## Assistant Messages", "")
    data.assistant?.forEach((m: string, i: number) => {
      lines.push(`### ${i + 1}`, "", m, "")
    })
    lines.push("## Tool Activity", "", `- Tool calls: ${data.toolCalls || 0}`, "")
  }
  atomicWrite(sessionPath, lines.join("\n"))
  return sessionPath
}

function writeCurrentMd(mode: string, inputText: string, runId: string): string {
  const currentPath = join(VAULT, "content", "current.md")
  const inputYaml = mode === "topic" ? `"${inputText}"` : '""'
  const content = [
    "---",
    `mode: ${mode}`,
    `input: ${inputYaml}`,
    "session: content/sessions/current.md",
    "status: routing",
    `run_id: ${runId}`,
    `created_at: ${new Date().toISOString()}`,
    "captured_by: post-hook.ts (opencode plugin)",
    "---",
    "",
  ].join("\n")
  atomicWrite(currentPath, content)
  return currentPath
}

export const PostHookPlugin: Plugin = async ({ client }) => {
  return {
    "tui.command.execute": async (input, output) => {
      if (input.command !== "post") return

      const args = input.args?.trim() || ""
      const mode = args ? "topic" : "session"
      const dateStr = new Date().toISOString().slice(0, 10)

      let data = { user: [] as string[], assistant: [] as string[], toolCalls: 0, totalLines: 0 }
      if (mode === "session" && input.sessionID) {
        data = readMessages(client, input.sessionID)
      }

      const runId = generateRunId(dateStr)
      const sessionPath = writeSessionFile(mode, args, data, dateStr)
      const currentPath = writeCurrentMd(mode, args, runId)

      try {
        await client.tui.appendPrompt({
          body: {
            text: `\n\nExecution context prepared.\n\nNEXT ACTION REQUIRED:\nInvoke @director.\n\nSource of truth:\n  - ${currentPath}\n  - ${sessionPath}\n\nDo not interpret, modify, or explain. Dispatch @director immediately.\n`,
          },
        })
      } catch {}
    },
  }
}
