# silver-spork

A framework for **choosing, benchmarking and evaluating local LLMs** served by [llama.cpp](https://github.com/ggml-org/llama.cpp)
on your own hardware, so that model decisions are measured rather than guessed. It is written for humans and for AI
agents alike: every parameter is derived from your machine with a script or a documented rule, every machine-specific
value lives in a local file created from an annotated template, and nothing in this repository describes any
particular computer.

What you get:

- **Tiered presets** for `llama-server` in router mode: name your tiers after roles (a reasoning tier, a coding-agent
  tier, a fast everyday tier, ...), one section each, switched by the `model` field of any OpenAI-compatible client.
- **Speed benchmarks** with `llama-bench`: full-GPU runs for dense models and an automatic `n-cpu-moe` sweep for
  mixture-of-experts models that do not fit in VRAM.
- **Quality KPIs** with [promptfoo](https://www.promptfoo.dev): deterministic suites (output integrity, long-context
  recall, instruction following, reasoning, coding with hidden tests that actually run, multi-turn tool calling with
  scripted tool results) plus rubric suites (everyday tasks, creative writing, domain knowledge) graded by a reviewer
  model or a human. Suites are selected by the **roles** you assign to each tier.
- **A reproducible pipeline**: detect hardware -> size models -> write presets -> benchmark -> evaluate -> decide,
  with the same commands for a person and for an agent.

## Prerequisites

| Tool | Why | Check |
|---|---|---|
| llama.cpp release for your GPU backend (CUDA, ROCm, Vulkan, Metal), recent enough for router mode (`--models-preset`), `--n-cpu-moe` and `--reasoning` | serves and benchmarks the models | `llama-server --help` lists those flags |
| [Hugging Face CLI](https://huggingface.co/docs/huggingface_hub/guides/cli) `hf` | downloads GGUF files into one cache | `hf --version` |
| PowerShell 7 (`pwsh`) | scripts (Windows-first; pwsh also runs on Linux/macOS) | `pwsh --version` |
| Python 3.11+ | eval harness glue (standard library only) | `py --version` or `python3 --version` |
| Node 20+ | promptfoo | `node --version` |
| An OpenAI-compatible client or coding agent | consumes the presets | e.g. [Pi](https://pi.dev), which discovers router presets automatically |

## Quick start

```bash
# 0. install promptfoo (dev dependency) once
npm install

# 1. learn your machine: GPU VRAM, physical cores, RAM, free disk, interpreter, sizing rules
pwsh -File scripts/detect-hardware.ps1

# 2. create your local instance files from the templates (all gitignored) and fill them in
cp config/local-ai.example.json config/local-ai.json
cp llamacpp/model.ini.example  llamacpp/model.ini
cp eval/models.example.json    eval/models.json

# 3. install the launcher next to llama-server and start the router
pwsh -File scripts/install.ps1
pwsh -File llamacpp/run-llama-server.ps1

# 4. measure speed, then quality, one tier at a time
pwsh -File scripts/benchmark.ps1 -Reps 2
<python_cmd> -I scripts/smoke_toolcall.py <YourAgentTier>
npm run eval:setup
npm run eval -- --env-file eval/tiers/<YourTier>.env
npm run eval:view
```

The full walkthrough, including how to shortlist candidate models and derive every value in the templates, is in
[docs/guide.md](docs/guide.md). A complete worked example with real models, measured speeds and KPI verdicts for a
consumer GPU with 8 GB of VRAM is in [docs/example-8gb-gpu.md](docs/example-8gb-gpu.md), with ready-to-copy instance
files under [examples/8gb-gpu/](examples/8gb-gpu/). AI agents: read [AGENTS.md](AGENTS.md) first.

## How the pieces fit

```
config/local-ai.example.json   -> config/local-ai.json      paths, port, threads, interpreter (yours, gitignored)
llamacpp/model.ini.example     -> llamacpp/model.ini        router presets = your tiers (yours, gitignored)
eval/models.example.json       -> eval/models.json          per-tier sampling, roles, languages (yours, gitignored)
scripts/detect-hardware.ps1    reads the machine, prints sizing guidance (-Json for agents)
scripts/benchmark.ps1          llama-bench wrapper: dense full-offload runs, MoE n-cpu-moe sweep -> results/
scripts/smoke_toolcall.py      two-turn tool-calling check against one preset
scripts/install.ps1            writes a .bat launcher into your llama.cpp folder that calls run-llama-server.ps1
llamacpp/run-llama-server.ps1  starts the router with your presets
eval/                          promptfoo runner, suites (tests/*.json), checks, tool-loop provider, scorecards
results/, eval/results/        your numbers (gitignored by default; publish them deliberately if you want)
docs/guide.md                  the method, step by step
docs/example-8gb-gpu.md        worked example on an 8 GB GPU; examples/8gb-gpu/ holds its instance files
```

## Method in one paragraph

Size first: a GGUF must fit in VRAM together with its KV cache and about 1 GB of overhead, or it must be a
mixture-of-experts model whose experts you can park in RAM with `n-cpu-moe`. Quantize weights no lower than Q4_K_M
for anything that calls tools, and never quantize the KV cache below q8_0. Then **measure** generation and prompt
speed with `llama-bench`, discard anything below your usability floor, and **evaluate** what remains with suites
chosen by role: a coding-agent tier must pass tool-calling and coding KPIs, a reasoning tier must pass reasoning,
every tier must pass integrity, long-context recall and instruction following. Thresholds live next to each suite
and are yours to tune. A tier that misses its core KPI gets the next quant up if it fits, otherwise the next
candidate model; re-run only the failed suites.

## Lessons the framework encodes

- Looping, mistyped tool calls and template-token leaks are usually **over-quantization** (Q2/Q3) or an unverified
  community merge, not a prompt problem.
- Models that **think by default** put tool calls in `reasoning_content`; agents then see empty answers and retry
  forever. Keep `reasoning = off` on agent presets and `--reasoning-format deepseek` on the server.
- Reasoning tokens **count toward `max_tokens`**; thinking tiers need a `thinking_allowance` in the eval config or
  short-answer tests come back empty.
- `--fit` does nothing once `n-gpu-layers` is set; for MoE models the knob is `n-cpu-moe`, found by sweeping.
- With one model resident at a time, never interleave requests to different presets while benchmarking or evaluating.

## License

MIT. Model licenses are their own; check each model card.
