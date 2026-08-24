// SpielOS notification surfacing plugin for OpenCode.
//
// CONTRACT (opencode2 / V2, @opencode-ai/plugin@0.0.0-next-17444):
// The V2 loader validates the module's `default` export against the Plugin
// schema and requires `id` + `setup` (promise variant) or `id` + `effect`
// (effect variant). Proof from the app log (2026-08-15 16:36:57, this file
// still exporting the V1 `{ id, server }` shape):
//   failed to load plugin ... SchemaError(Missing key at ["default"]["effect"]
//   Missing key at ["default"]["setup"])
// `define()` is identity, so a plain object default
//   export default { id: "...", setup: async (ctx) => {...} }
// is valid with NO runtime import from @opencode-ai/plugin at all. The
// installed .opencode/node_modules/@opencode-ai/plugin is 1.18.15 (V1 types)
// and must never leak into this file, so the Context surface used here is
// declared structurally below (read-only reference:
// @opencode-ai/plugin/dist/promise/plugin.d.ts in the next-17444 package).
//
// V1 -> V2 API mapping (what changed in this rewrite; the V1 identifiers are
// intentionally not repeated here — the contract tests assert their absence):
//   V1 prompt-async call (path/query/body with agent + parts array)
//     -> ctx.session.prompt({ sessionID, text: { text: "..." } })   (no agent)
//   V1 event hook reading properties.sessionID
//     -> ctx.event.subscribe() async iteration, event.data.sessionID
//   V1 BunShell $ -> node:child_process execFile (python3 -B -m company ...),
//     direct argv array, no shell, no pipes, no redirects
//   V1 TUI toast -> DROPPED server-side (no TUI surface in the V2 server
//     Context; the @opencode-ai/plugin/tui entrypoint is a separate process
//     surface). runner-down / loop-wedged / stuck-goal / generic updates are
//     surfaced via ctx.session.prompt (chat-visible) instead — the user asked
//     to SEE the watchdog working, and chat is the visible channel. Toasts
//     would also require the plugin file to be loaded in the TUI process,
//     which the server log does not show.
//   V1 command execute-before stop/start hook -> DROPPED: the V2 CommandDomain
//     (list/get/update/remove + transform) has no execution hook, so there is
//     no clean equivalent. Daemon lifecycle now belongs to the OS supervisor
//     (.agents/company/runtime/supervisor.py) and RunnerService.
//
// Behavior preserved: REPORTABLE kind set (incl. watchdog_digest and
// goal_completed_followup), heartbeat file with ALIVE_STALE_MS (45s process
// liveness) and LOOP_STALE_MS (75s loop progress), 5s interval check, 300s
// per-id re-prompt throttle, runner-down and loop-wedged alerts, digest /
// follow-up prompt text built from the payload, and the new Watchdog v2 HUD
// ticker injected into the active session on its own configurable cadence.

import { readFile } from "node:fs/promises"
import { existsSync } from "node:fs"
import { join, dirname } from "node:path"
import { fileURLToPath } from "node:url"
import { execFile } from "node:child_process"
import { promisify } from "node:util"

const execFileP = promisify(execFile)

// ---------------------------------------------------------------------- //
// Local structural types (V2 contract; see header comment)               //
// ---------------------------------------------------------------------- //

type V2SessionIdleEvent = {
  type: "session.idle"
  data: { sessionID: string }
}

type V2Event = V2SessionIdleEvent | { type: string; data?: Record<string, unknown> }

type V2Context = {
  event: { subscribe(): AsyncIterable<V2Event> }
  session: {
    prompt(input: { sessionID: string; text: { text: string } }): Promise<unknown>
    synthetic(input: { sessionID: string; text: { text: string; description?: string | null } }): Promise<unknown>
  }
}

// ---------------------------------------------------------------------- //
// Constants (unchanged behavior, Watchdog v2)                             //
// ---------------------------------------------------------------------- //

const REPORTABLE = new Set([
  "approval_required",
  "action_required",
  "blocked",
  "failed",
  "run_completed",
  "goal_achieved",
  "goal_abandoned",
  "goal_expired",
  "runner_down",
  "stuck_goal",
  // Chat-visible supervision (goal-chat-visible-supervision-20260815): the
  // runner's scheduled progress digest and the terminal-state follow-up ride
  // the same REPORTABLE + 300s throttle path as every event kind, and are
  // additionally surfaced into the active session as a typed text prompt
  // built from the payload.
  "watchdog_digest",
  "goal_completed_followup",
])

// Runner-down detection (2026-08-15 wedge hardening). The runner heartbeat is
// now TWO signals: the heartbeat thread stamps `alive_at` every 10s regardless
// of tick length (PROCESS liveness), and the watch loop stamps `last_tick`
// once per cycle (LOOP progress). A normal ~3-minute measure poll therefore
// never false-alarms — `alive_at` stays fresh — while a wedged serial loop is
// still caught by a stale `last_tick` with a fresh `alive_at`.
const ALIVE_STALE_MS = 45_000        // heartbeat thread silent => process dead
const LOOP_STALE_MS = 75_000         // no cycle completed => loop wedged
const HEARTBEAT_RELATIVE = ".spielos/state/runner.heartbeat"
const LIVE_STATUS_RELATIVE = ".spielos/state/live_status.json"
const CHECK_INTERVAL_MS = 5000       // supervisor check cadence
const REPROMPT_THROTTLE_MS = 300_000 // per-id re-prompt window (5 minutes)
// Failure backoff for the catch-all around the whole check: a broken CLI or
// unreadable state must not retry hot every CHECK_INTERVAL_MS forever.
const ERROR_BACKOFF_BASE_MS = 30_000   // first failure waits one interval slot
const ERROR_BACKOFF_MAX_MS = 600_000   // capped at 10 minutes
// Watchdog v2 live HUD ticker (goal-577aaacc7d / change-7cc84900b7): a
// compact one-line live status is injected into the active session on this
// cadence while goals are active (see buildHudTicker).
const HUD_TICKER_INTERVAL_MS = 60_000

type NotificationItem = {
  id: string
  kind: string
  payload?: {
    approval_interaction?: Record<string, unknown>
    watchdog?: { signal?: string }
    summary?: {
      active_goals?: number
      pending_approvals?: number
      blockers?: number
      recent_terminal?: number
    }
    goals?: Array<{
      goal_id?: string
      name?: string
      stage?: string
      step?: string
    }>
    followup?: { goal_status?: string; recommended_next_action?: string }
    goal?: { id?: string }
    required_user_action?: string
  }
}

// ---------------------------------------------------------------------- //
// Repo-root resolution                                                    //
// ---------------------------------------------------------------------- //

// The V2 server Context has no `directory`, so the repo root (home of
// .spielos/state and the `company` CLI) is resolved by this precedence:
//   1. process.cwd() when it contains .spielos/state/runner.heartbeat — the
//      app is normally launched from the repo, so this is the fast path.
//   2. import.meta.url of this file, two directory levels up
//      (.opencode/plugins/ -> .opencode/ -> repo root) — stable regardless
//      of the launch directory.
//   3. process.cwd() as a last resort (the CLI calls then fail closed inside
//      their own try/catch, exactly like a missing heartbeat file).
const resolveRepoRoot = (): string => {
  const cwd = process.cwd()
  // 1. Launch directory: the app is normally started from the repo, and the
  //    heartbeat file's presence proves the candidate really is the repo.
  if (existsSync(join(cwd, HEARTBEAT_RELATIVE))) {
    return cwd
  }
  // 2. Module-location fallback: this file lives at
  //    <repo>/.opencode/plugins/spielos-notifications.ts, so two directory
  //    levels up is the repo root regardless of the launch directory.
  try {
    const here = dirname(fileURLToPath(import.meta.url))
    const root = dirname(dirname(here)) // .opencode/plugins -> .opencode -> root
    if (existsSync(join(root, HEARTBEAT_RELATIVE))) return root
  } catch {
    // fall through
  }
  // 3. Last resort: the launch directory. Company CLI calls then fail closed
  //    inside their own try/catch, exactly like a missing heartbeat file.
  return cwd
}

const runCompany = async (repoRoot: string, args: string[]): Promise<{ stdout: string; exitCode: number }> => {
  try {
    const { stdout } = await execFileP("python3", ["-B", "-m", ...args], {
      cwd: repoRoot,
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", PYTHONPATH: ".agents" },
      timeout: 20_000,
      maxBuffer: 4 * 1024 * 1024,
    })
    return { stdout, exitCode: 0 }
  } catch (error) {
    // execFile rejects with the exit code on non-zero exits; parse what we can.
    const stderr = (error as { stderr?: string }).stderr ?? ""
    const code = (error as { code?: unknown }).code
    if (typeof code === "number") return { stdout: stderr, exitCode: code }
    throw error
  }
}

// Scheduled-supervision prompt text (goal-chat-visible-supervision-20260815):
// both new kinds are typed into the active session with text built from the
// payload — the digest lists the active goals read from `payload.goals` plus
// the numeric `payload.summary`, and the terminal follow-up quotes the
// `payload.followup.recommended_next_action` so the chat never goes silent
// after a goal completes.
const buildSurfacePrompt = (item: NotificationItem): string => {
  const payload = item.payload ?? {}
  if (item.kind === "watchdog_digest") {
    const goals = payload.goals ?? []
    const summary = payload.summary ?? {}
    const lines = goals.map(
      (g) => `- ${g.goal_id ?? "?"} (${g.name ?? "?"}): ${g.stage ?? "?"}/${g.step ?? "?"}`,
    )
    return [
      "SpielOS progress digest (scheduled supervision).",
      `Active goals: ${summary.active_goals ?? 0} | Pending approvals: ${summary.pending_approvals ?? 0} | Blockers: ${summary.blockers ?? 0}`,
      ...lines,
      "Approve parked actions or resume waiting goals as needed; otherwise keep the runner daemon running.",
    ].join("\n")
  }
  const followup = payload.followup ?? {}
  return [
    "A SpielOS goal reached a terminal state.",
    `Goal ${payload.goal?.id ?? "?"} (${followup.goal_status ?? "?"}): ${payload.required_user_action ?? ""}`,
    `Recommended next action: ${followup.recommended_next_action ?? ""}`,
  ].join("\n")
}

// Watchdog v2 live HUD ticker (goal-577aaacc7d / change-7cc84900b7): one
// compact line rendered from the daemon's live_status.json (written once per
// watch cycle) so the pinned session shows heartbeat age, active-goal count,
// pending approvals, next digest countdown, and the retry ledger size without
// running any company CLI query inside the plugin.
const buildHudTicker = (live: Record<string, unknown>): string | null => {
  const active = Array.isArray(live.active_goals) ? (live.active_goals as Array<Record<string, unknown>>) : []
  if (!active.length) return null // nothing to tick while no goals are active
  const heartbeat = (live.heartbeat ?? {}) as Record<string, unknown>
  const aliveAt = typeof heartbeat.alive_at === "string" ? Date.parse(heartbeat.alive_at) : Number.NaN
  const aliveSeconds = Number.isNaN(aliveAt) ? null : Math.max(0, Math.round((Date.now() - aliveAt) / 1000))
  let nextDigest = "?"
  if (typeof live.next_digest_at === "string") {
    const due = Date.parse(live.next_digest_at)
    if (!Number.isNaN(due)) {
      const minutes = Math.max(0, Math.round((due - Date.now()) / 60_000))
      nextDigest = `${minutes}m`
    }
  }
  const retries = Array.isArray(live.retry_ledger) ? (live.retry_ledger as unknown[]).length : 0
  const approvals = typeof live.pending_approvals === "number" ? live.pending_approvals : 0
  return [
    "[SpielOS HUD]",
    `${active.length} active goal${active.length === 1 ? "" : "s"}`,
    `${approvals} approval${approvals === 1 ? "" : "s"} pending`,
    `next digest ${nextDigest}`,
    aliveSeconds === null ? "runner heartbeat unknown" : `runner alive ${aliveSeconds}s`,
    `${retries} retr${retries === 1 ? "y" : "ies"} on ledger`,
  ].join(" · ")
}

// ---------------------------------------------------------------------- //
// V2 plugin default export                                               //
// ---------------------------------------------------------------------- //

export default {
  id: "spielos-notifications",
  setup: async (ctx: V2Context) => {
    const repoRoot = resolveRepoRoot()
    const run = (args: string[]) => runCompany(repoRoot, args)
    let checking = false
    const prompted = new Map<string, number>()
    // Catch-all failure backoff state: consecutive failed checks suppress the
    // supervisor loop for an exponentially growing (capped) window.
    let checkFailures = 0
    let suppressChecksUntil = 0
    let activeSessionID: string | undefined
    let disposed = false
    // HUD ticker state: per-session cadence so a newly attached session gets
    // an immediate ticker instead of waiting out the interval.
    let hudLastAt = 0
    let hudSessionID: string | undefined

    const heartbeatAgeMs = async (): Promise<{ alive: number | null; tick: number | null }> => {
      try {
        const raw = await readFile(join(repoRoot, HEARTBEAT_RELATIVE), "utf8")
        const parsed = JSON.parse(raw) as { alive_at?: string; last_tick?: string }
        const alive = parsed.alive_at ? Date.parse(parsed.alive_at) : Number.NaN
        const tick = parsed.last_tick ? Date.parse(parsed.last_tick) : Number.NaN
        return {
          alive: Number.isNaN(alive) ? null : Date.now() - alive,
          tick: Number.isNaN(tick) ? null : Date.now() - tick,
        }
      } catch {
        return { alive: null, tick: null }
      }
    }

    const promptSession = async (text: string): Promise<void> => {
      if (!activeSessionID) return
      await ctx.session.prompt({ sessionID: activeSessionID, text: { text } })
    }

    const check = async () => {
      if (checking || Date.now() < suppressChecksUntil) return
      checking = true
      try {
        const status = JSON.parse(
          (await run(["company", "runner", "status", "--json"])).stdout,
        ) as { enabled?: boolean; running?: boolean }
        if (status.enabled === false) return
        // The daemon watch loop owns the tick while it is running; only tick
        // ourselves when no daemon is around, so the two never race the lease.
        if (status.running !== true) {
          await run(["company", "runner", "tick"])
        }
        // Runner-down detection (inverted silent skip): alert when the polled
        // status says not running OR the heartbeat thread's alive_at went stale.
        // A missing heartbeat file is not stale on its own (a pre-heartbeat
        // daemon must not false-positive); a dead daemon always fails the status
        // check. `last_tick` staleness with a fresh alive_at is a wedged loop:
        // the process lives but the serial watch loop is stuck (2026-08-15).
        const { alive, tick } = await heartbeatAgeMs()
        const runnerDown =
          status.running !== true ||
          (alive !== null && alive > ALIVE_STALE_MS)
        const loopWedged = alive !== null && tick !== null && tick > LOOP_STALE_MS
        const pendingRaw = (await run(["company", "notifications", "list", "--status", "pending", "--limit", "100", "--json"])).stdout
        const deliveredRaw = (await run(["company", "notifications", "list", "--status", "delivered", "--limit", "100", "--json"])).stdout
        const byID = new Map<string, NotificationItem>()
        for (const item of [
          ...(JSON.parse(deliveredRaw) as NotificationItem[]),
          ...(JSON.parse(pendingRaw) as NotificationItem[]),
        ]) {
          // Pending wins on duplicate ids: it is the fresher state.
          byID.set(item.id, item)
        }
        const recent = [...byID.values()].filter(
          (item) => REPORTABLE.has(item.kind),
        )
        const recentIDs = new Set(recent.map((item) => item.id))
        for (const id of prompted.keys()) {
          // The synthesized runner-down key is not a notification id and must
          // survive the prune or its throttle resets on every check.
          if (!recentIDs.has(id) && id !== "runner-down" && id !== "loop-wedged") prompted.delete(id)
        }
        const now = Date.now()
        const fresh = recent.filter((item) => now - (prompted.get(item.id) ?? 0) > REPROMPT_THROTTLE_MS)
        if (!fresh.length && !runnerDown) return
        fresh.forEach((item) => prompted.set(item.id, now))
        const ids = fresh.map((item) => item.id)
        const watchdog = fresh.find((item) => item.payload?.watchdog?.signal)
        const approvals = fresh.filter(
          (item) => item.kind === "approval_required" && item.payload?.approval_interaction,
        )
        if (activeSessionID) {
          for (const item of approvals) {
            // The native question is an agent tool, not a plugin API. Wake the
            // Director with one typed interaction; it must ask before acting.
            await ctx.session.prompt({
              sessionID: activeSessionID,
              text: {
                text: [
                  "A SpielOS action is parked for approval.",
                  "Immediately invoke the native question tool with exactly the supplied interaction.",
                  "Show Approve and Reject separately. Do not combine this with another approval.",
                  "Run the fallback command only after an explicit Approve answer.",
                  "On Reject, leave the action parked and report that nothing executed.",
                  JSON.stringify(item.payload?.approval_interaction),
                ].join("\n"),
              },
            })
          }
          // Scheduled supervision surfaces (digest + terminal follow-up) share
          // the active-session resolution with the approval flow; `fresh` is
          // already throttle-filtered by the 300s per-id window, so no extra
          // rate limiting is needed here.
          const surfaced = fresh.filter(
            (item) =>
              item.kind === "watchdog_digest" || item.kind === "goal_completed_followup",
          )
          for (const item of surfaced) {
            await ctx.session.prompt({
              sessionID: activeSessionID,
              text: { text: buildSurfacePrompt(item) },
            })
          }
          // Generic updates (run_completed / failed / blocked / stuck_goal /
          // ...) that did not match a dedicated flow above are surfaced as ONE
          // combined chat line instead of the V1 server toast, which does not
          // exist in the V2 server Context. `fresh` is already per-id
          // throttled, so this cannot spam faster than one line per id per
          // 5 minutes.
          const dedicated = new Set([...approvals, ...surfaced])
          const generic = fresh.filter((item) => !dedicated.has(item))
          if (generic.length) {
            const watchdogSignal = watchdog?.payload?.watchdog?.signal
            const title =
              watchdogSignal === "stuck_goal"
                ? "SpielOS stuck goal"
                : watchdogSignal === "runner_down"
                  ? "SpielOS runner down"
                  : "SpielOS Director"
            const kinds = [...new Set(generic.map((item) => item.kind))].join(", ")
            await ctx.session.prompt({
              sessionID: activeSessionID,
              text: {
                text: [
                  `${title}: ${generic.length} company run update${generic.length === 1 ? "" : "s"} ready (${kinds}).`,
                  "Inspect with `company status <goal id>` and act on the pending items; the HUD ticker keeps the live counts.",
                ].join("\n"),
              },
            })
          }
        }
        if (runnerDown) {
          // Inverted silent skip: a chat-visible alert exactly when the runner
          // is down, throttled by the same re-prompt window as notifications so
          // a long outage does not spam.
          if (now - (prompted.get("runner-down") ?? 0) > REPROMPT_THROTTLE_MS) {
            prompted.set("runner-down", now)
            await promptSession([
              "SpielOS runner down.",
              "The runner daemon is not ticking",
              alive === null ? "" : `(heartbeat age ${Math.round(alive / 1000)}s)`,
              "Restart it with `company runner start`, then verify with `company runner status`.",
            ].filter(Boolean).join(" "))
          }
        } else if (loopWedged) {
          // Process alive (heartbeat thread stamps alive_at) but the serial
          // watch loop has not completed a cycle past LOOP_STALE_MS — the
          // exact 2026-08-15 wedge. The bounded measure path completes far
          // under this, so a legit long tick never trips it.
          if (now - (prompted.get("loop-wedged") ?? 0) > REPROMPT_THROTTLE_MS) {
            prompted.set("loop-wedged", now)
            await promptSession([
              "SpielOS runner loop wedged.",
              "The runner process is alive but has not completed a watch cycle in",
              tick === null ? "" : `${Math.round(tick / 1000)}s`,
              "(wedged tick). Inspect with `company runner status`, check for a stuck goal with",
              "`company notifications list --status pending`, and restart with `company runner start`",
              "if it does not recover.",
            ].filter(Boolean).join(" "))
          }
        }
        checkFailures = 0
      } catch (error) {
        // The durable outbox remains pending, but a persistent failure (CLI
        // error, unreadable state) must not retry hot every interval. Log it
        // and back off exponentially before the next attempt.
        checkFailures += 1
        const delay = Math.min(
          ERROR_BACKOFF_BASE_MS * 2 ** (checkFailures - 1),
          ERROR_BACKOFF_MAX_MS,
        )
        suppressChecksUntil = Date.now() + delay
        console.error(
          `[spielos-notifications] company check failed ` +
            `(attempt ${checkFailures}, backing off ${Math.round(delay / 1000)}s):`,
          error instanceof Error ? error.message : error,
        )
      } finally {
        checking = false
      }
    }

    // Watchdog v2 live HUD ticker: while goals are active, inject one compact
    // live-status line into the active session on HUD_TICKER_INTERVAL_MS via
    // ctx.session.synthetic (a typed, chat-visible line that does not trigger
    // an agent turn). Reads the daemon's live_status.json — never runs a
    // company CLI query itself.
    const hudTick = async () => {
      if (!activeSessionID) return
      const now = Date.now()
      if (hudSessionID !== activeSessionID) {
        // New session attached: reset the cadence so the first line shows
        // immediately, then resume the interval.
        hudSessionID = activeSessionID
        hudLastAt = 0
      }
      if (now - hudLastAt < HUD_TICKER_INTERVAL_MS) return
      try {
        const raw = await readFile(join(repoRoot, LIVE_STATUS_RELATIVE), "utf8")
        const live = JSON.parse(raw) as Record<string, unknown>
        const line = buildHudTicker(live)
        if (line === null) return // no active goals -> nothing to tick
        hudLastAt = now
        await ctx.session.synthetic({
          sessionID: activeSessionID,
          text: { text: line, description: "SpielOS live status ticker" },
        })
      } catch {
        // Missing/stale live_status.json: no ticker this round (daemon down
        // or pre-HUD state); the runner-down alert owns that surface.
      }
    }

    const timer = setInterval(() => void check(), CHECK_INTERVAL_MS)
    const hudTimer = setInterval(() => void hudTick(), HUD_TICKER_INTERVAL_MS)

    // Event subscription (V2): async iteration over ctx.event.subscribe().
    // session.idle events carry data.sessionID (NOT properties.sessionID).
    void (async () => {
      for await (const event of ctx.event.subscribe()) {
        if (disposed) break
        if (event.type === "session.idle") {
          activeSessionID = (event as V2SessionIdleEvent).data.sessionID
          await check()
          await hudTick()
        }
      }
    })()

    return async () => {
      disposed = true
      clearInterval(timer)
      clearInterval(hudTimer)
    }
  },
}
