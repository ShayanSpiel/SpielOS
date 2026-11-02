#!/usr/bin/env node
"use strict";
// Thin bridge to the same Python CLI. Never downloads a runtime or creates a home.
const {spawnSync} = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const args = process.argv.slice(2);
let cwd;
try { cwd = process.cwd(); }
catch { process.stderr.write("SpielOS needs an existing working folder. Change folders and retry.\n"); process.exit(1); }
let selected;
const explicit = args.indexOf("--home");
if (explicit >= 0 && args[explicit + 1]) selected = path.resolve(args[explicit + 1]);
else if (args.some(value => value.startsWith("--home="))) selected = path.resolve(args.find(value => value.startsWith("--home=")).slice(7));
else {
  let candidate = cwd;
  for (;;) {
    if (fs.existsSync(path.join(candidate,".agents/company/__main__.py"))) { selected = candidate; break; }
    const parent = path.dirname(candidate); if (parent === candidate) break; candidate = parent;
  }
}
const environment = {...process.env};
const command = args[0] === "--db" ? args[2] : args[0]?.startsWith("--db=") ? args[1] : args[0];
if (selected && !["init","update"].includes(command)) {
  const runtime = path.join(selected,".agents");
  environment.PYTHONPATH = runtime + (environment.PYTHONPATH ? path.delimiter + environment.PYTHONPATH : "");
}
const user = os.homedir();
const roots = [process.env.PIPX_HOME && path.join(process.env.PIPX_HOME,"venvs/spielos"),
  path.join(user,".local/share/pipx/venvs/spielos"),path.join(user,".local/pipx/venvs/spielos"),
  path.join(user,"Library/Application Support/pipx/venvs/spielos"),
  process.env.UV_TOOL_DIR && path.join(process.env.UV_TOOL_DIR,"spielos"),path.join(user,".local/share/uv/tools/spielos")].filter(Boolean);
const candidates = process.env.SPIELOS_PYTHON ? [process.env.SPIELOS_PYTHON] :
  ["python3","python",...roots.flatMap(root => [path.join(root,"bin/python"),path.join(root,"Scripts/python.exe")])];
const probe = "import sys,importlib.util; sys.exit(0 if sys.version_info>=(3,11) and importlib.util.find_spec('company.cli') is not None else 1)";
let python;
for (const candidate of candidates) {
  const result = spawnSync(candidate,["-B","-c",probe],{env:environment,cwd:selected || cwd,stdio:"ignore"});
  if (!result.error && result.status === 0) { python = candidate; break; }
}
if (!python) {
  process.stderr.write("SpielOS needs Python 3.11+ and its Python package, or an initialized vendored company home. Run the installer or set SPIELOS_PYTHON to its Python executable.\n");
  process.exit(1);
}
const result = spawnSync(python,["-B","-m","company.cli",...args],{env:environment,cwd:selected || cwd,stdio:"inherit"});
if (result.error) process.stderr.write("SpielOS could not start its Python CLI: " + result.error.message + "\n");
process.exit(result.status === null ? 1 : result.status);
