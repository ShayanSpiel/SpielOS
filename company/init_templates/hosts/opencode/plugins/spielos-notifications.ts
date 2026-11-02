// Lean SpielOS context adapter. No idle polling, timer or product scheduler.
type Any = Record<string, any>

const homeAt = async (directory: string): Promise<boolean> =>
  typeof directory === "string" && !!directory &&
  await Bun.file(`${directory}/.spielos/layout.json`).exists() &&
  await Bun.file(`${directory}/.agents/company/__main__.py`).exists()

const sessionDirectoryFrom = (event: Any): string | undefined =>
  event?.directory ?? event?.location?.directory ?? event?.session?.directory
  ?? event?.properties?.directory

const pushSystem = (system: Any[], text: string): void => {
  const sample = system.find((part) => typeof part !== "undefined")
  if (typeof sample === "string") system.push(text)
  else system.push({ type: "text", text })
}

const setup = async (ctx: Any) => {
  await ctx.session.hook("context", async (event: Any) => {
    if (!Array.isArray(event?.system)) return
    try {
      let directory = sessionDirectoryFrom(event)
      const sessionID = event?.sessionID ?? event?.properties?.sessionID
      if (!directory && sessionID) {
        const session = await ctx.session.get({ path: { id: sessionID } })
        directory = session?.data?.directory ?? session?.directory
      }
      const candidates = [directory, process.env.SPIELOS_HOME].filter(Boolean) as string[]
      let home: string | undefined
      for (const candidate of candidates) {
        if (await homeAt(candidate)) { home = candidate; break }
      }
      if (!home) throw new Error("select an installed company for this session")
      const child = Bun.spawn({
        cmd: ["python3", "-B", "-m", "company", "context", "--home", home, "--prompt", String(event?.prompt ?? event?.message?.text ?? ""), "--json"],
        cwd: home, stdout: "pipe", stderr: "pipe",
        env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", PYTHONPATH: `${home}/.agents` },
      })
      const [code, stdout] = await Promise.all([child.exited, new Response(child.stdout).text()])
      if (code !== 0) throw new Error("company context is unavailable")
      const value = JSON.parse(stdout)
      if (!value?.context?.text) throw new Error("empty company context")
      const [human, machine] = value.context.text.split("\nMachine reference: ")
      let text = human + "\nCompany profile\n" + value.profile
      text += "\nAvailable workflows\n" + value.workflows.map((row: Any) => (row.purpose ?? "Workflow needs repair") + " — " + (row.readiness ?? "draft; not qualified for production")).join("\n")
      if (machine) text += "\nMachine reference: " + machine
      pushSystem(event.system, text)
    } catch {
      pushSystem(event.system, "SpielOS context injection failed. Read company status once from the explicitly selected home and report the missing projection. Do not guess company state.")
    }
  })
}

const plugin = { id: "spielos-notifications", setup }
export default plugin
