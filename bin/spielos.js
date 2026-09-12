#!/usr/bin/env node
"use strict";

// Thin shim: spielos is a Python application (python3 -m company). This bin
// delegates to it so `npm i -g spielos && spielos --version` actually invokes
// the real CLI instead of a stub.

const { spawnSync } = require("child_process");

const args = process.argv.slice(2);

// Pre-flight: the runtime needs Python 3.11+. A missing or too-old
// python3 would otherwise surface as an opaque import error from deep
// inside the package.
const probe = spawnSync("python3", ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"], {
  stdio: "ignore",
});
if (probe.error || probe.status !== 0) {
  if (probe.status === 1) {
    process.stderr.write(
      "spielos: Python 3.11+ is required, but this machine's python3 is older.\n" +
        "Install a current Python (https://python.org), or run the installer:\n" +
        "  curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/SpielOS/main/install.sh | sh\n"
    );
    process.exit(1);
  }
  process.stderr.write(
    `spielos: failed to run 'python3': ${probe.error ? probe.error.message : "unknown error"}\n` +
      "spielos requires Python 3.11+. Install it from https://python.org and retry.\n"
  );
  process.exit(1);
}

const result = spawnSync("python3", ["-m", "company", ...args], {
  stdio: "inherit",
});

if (result.error) {
  // python3 not found or failed to spawn.
  process.stderr.write(
    `spielos: failed to run 'python3 -m company': ${result.error.message}\n` +
      "spielos requires Python 3.11+ with the 'spielos' package installed.\n"
  );
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);
