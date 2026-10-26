# AGENTS.md - how an AI agent works in this repository

This repository is a **framework** for benchmarking and evaluating local LLMs served by llama.cpp. It contains no
facts about any particular machine. Everything specific to the computer you are running on lives in local files
you create from templates. Treat the user's machine, models and results as theirs: measure, report, recommend; do
not delete models or change presets without an explicit OK.

## Rules
1. **Never hardcode.** Paths, ports, thread counts, model names, tier names, interpreter names and hardware facts
   come from `config/local-ai.json`, `llamacpp/model.ini` and `eval/models.json` (all gitignored, created from the
   `.example` files). If a value is missing, derive it with `scripts/detect-hardware.ps1 -Json` or ask; do not guess.
2. **Never commit instance data.** `git status` must never show `config/local-ai.json`, `llamacpp/model.ini`,
   `eval/models.json`, `eval/tiers/` or anything under `results/`. Before any commit, grep the tracked files for the
   user's GPU name, drive letters, user name and model names; the result must be empty.
3. **Never delete model files** from the Hugging Face cache without the user's explicit OK in this conversation.
4. **One tier at a time.** The router keeps `models_max` presets loaded (usually 1). Running two tiers concurrently
   makes it swap models on every request. Benchmarks and evals are sequential by design; keep them that way.
5. **Prefer the tools already here**: `llama-bench` for speed, `promptfoo` for quality, `hf` for downloads. The only
   custom code is thin glue in `scripts/` and `eval/lib/`.
6. **Interpreter**: use the command in `config/local-ai.json` -> `python_cmd` (`py` on Windows with the launcher,
   `python3` elsewhere) and always pass `-I`. PowerShell scripts run with
   `pwsh -NoProfile -ExecutionPolicy Bypass -File <script>`; list-like parameters are comma-separated strings
   (`-MoeSweep "24,28,32"`).

## The pipeline (same commands for humans)
| Step | Command | Output you act on |
|---|---|---|
| Learn the machine | `pwsh -File scripts/detect-hardware.ps1 -Json` | VRAM, physical cores (-> `threads`), RAM, free disk, `python_cmd`, max GGUF size that fits fully on the GPU |
| Create instance files | copy the three `.example` files, fill them in per [docs/guide.md](docs/guide.md) | - |
| Install launcher | `pwsh -File scripts/install.ps1` | `.bat` in the llama.cpp folder calling `llamacpp/run-llama-server.ps1` |
| Start the router | `pwsh -File llamacpp/run-llama-server.ps1 -NoPause` (background) | `curl <server_url>/health` -> ok; `curl <server_url>/v1/models` lists the presets |
| Speed | `pwsh -File scripts/benchmark.ps1 -Reps 2` or `-Filter <name> -MoeSweep "..."` | `results/benchmark_results.md`: tg (generation) and pp (prompt) tokens/s per model |
| Tool-calling sanity | `<python_cmd> -I scripts/smoke_toolcall.py <Tier>` | PASS / PARTIAL / FAIL |
| Quality | `npm run eval:setup`, then `npm run eval -- --env-file eval/tiers/<Tier>.env` per tier | `eval/results/<Tier>_scorecard.md`: KPI pass/fail against thresholds, `needs-judge` rows |
| Judge rubric rows | grade `needs-judge` rows 1-5 against their rubric (see `eval/README.md`), or configure a grader | judged mean vs threshold |
| Decide | compare scorecards; a tier must meet the core KPI of its role | keep / keep with caveat / replace |

## Where things live
- `config/local-ai.example.json` - every key explained, including how to obtain its value.
- `llamacpp/model.ini.example` - how presets work, sizing rules, thinking toggles, MoE offload.
- `eval/models.example.json` - per-tier sampling (from the model card), `roles` (which suites apply), `languages`,
  `thinking_allowance`.
- `eval/tests/*.json` - suites with `applies_to` roles and thresholds; `eval/README.md` documents the case schema.
- `docs/guide.md` - the method, including how to shortlist candidate models for a given VRAM budget.

## Known pitfalls
- A model that loops, mistypes tool calls or emits template tokens is usually over-quantized (Q2/Q3) or an
  unverified merge. Stay at Q4_K_M or better for tool use and never quantize the KV cache below q8_0.
- Thinking-by-default models hide tool calls in `reasoning_content`. Agent presets: `reasoning = off`.
- Reasoning tokens count toward `max_tokens`: thinking tiers need `thinking_allowance` in `eval/models.json`.
- `--fit` is a no-op when `n-gpu-layers` is set; MoE sizing is `n-cpu-moe`, found by sweeping.
- promptfoo's `outputPath` is relative to the working directory: run npm scripts from the repo root.
