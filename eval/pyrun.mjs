#!/usr/bin/env node
// Runs a Python script of the eval harness with the interpreter configured for this machine, so
// package.json never hardcodes `py`, `python3` or a version:
//
//   node eval/pyrun.mjs eval/run_eval.py --list --model <Tier>
//
// Interpreter: PROMPTFOO_PYTHON env var > config/local-ai.json "python_cmd" > "python".
// The value may carry arguments ("py -3"); it is split on whitespace. `-I` (isolated mode) is
// always added. Exit code and output are passed through.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function configuredPython() {
  if (process.env.PROMPTFOO_PYTHON) return process.env.PROMPTFOO_PYTHON;
  try {
    const cfg = JSON.parse(readFileSync(resolve(repo, "config", "local-ai.json"), "utf8"));
    if (cfg && typeof cfg.python_cmd === "string" && cfg.python_cmd.trim()) return cfg.python_cmd;
  } catch {
    // no local config: fall through to the default
  }
  return "python";
}

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("usage: node eval/pyrun.mjs <script.py> [args...]");
  process.exit(2);
}
const [exe, ...exeArgs] = configuredPython().trim().split(/\s+/);
const r = spawnSync(exe, [...exeArgs, "-I", ...args], { stdio: "inherit", cwd: repo });
if (r.error) {
  console.error(`cannot start Python (${exe}): ${r.error.message}\n` +
    "Set PROMPTFOO_PYTHON (e.g. `py` on Windows, `python3` on Linux/macOS) or \"python_cmd\" in config/local-ai.json.");
  process.exit(127);
}
process.exit(r.status ?? 1);
