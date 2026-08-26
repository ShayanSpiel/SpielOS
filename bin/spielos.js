#!/usr/bin/env node
"use strict";

// Thin shim: spielos is a Python application (python3 -m company). This bin
// delegates to it so `npm i -g spielos && spielos --version` actually invokes
// the real CLI instead of a stub.

const { spawnSync } = require("child_process");

const args = process.argv.slice(2);
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
