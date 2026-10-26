# Guide: from a bare GPU to a measured set of local models

This is the method behind the repository, written so that a person or an AI agent can follow it on any machine.
Every number below is a rule of thumb to be **verified by the benchmark**, not a fact about your hardware.

## 1. Learn the machine

```bash
pwsh -File scripts/detect-hardware.ps1          # human-readable
pwsh -File scripts/detect-hardware.ps1 -Json    # for agents
```

You need five facts: GPU VRAM, number of **physical** CPU cores, RAM, free disk on the drive that will hold models,
and which Python command exists. The script prints them and derives the first sizing rule:

> largest GGUF that runs fully on the GPU ≈ VRAM − KV cache at your context − 1 GB overhead

KV cache size depends on the architecture: at q8_0 and 32k tokens, count roughly 1–3 GB for a 7–9B dense model,
much less for hybrid-attention models, more for older ones; f16 doubles it. Halve your context before you drop the
KV cache below q8_0, which hurts more than weight quantization.

## 2. Fill in `config/local-ai.json`

Copy `config/local-ai.example.json`; each key has a `_comment` explaining it. The decisions:

- `llamacpp_dir`: the folder with `llama-server` and `llama-bench` from a release built for your backend.
- `hf_cache`: one cache for all GGUF files, on the largest fast drive. Set `HF_HUB_CACHE` to it when downloading.
- `threads`: physical cores (never logical threads).
- `models_max`: 1 unless two models plus KV caches fit at once.
- `python_cmd`: what `detect-hardware` found.

## 3. Shortlist candidate models

Work per **role** you want to cover, for example: reasoning/planning, coding agent (tool calling), fast everyday
chat, creative writing, a domain specialist. For each role, shortlist two or three candidates:

1. Start from the maintainers' GGUF repositories on Hugging Face (quantizers who publish imatrix/"dynamic" quants
   and keep chat templates current). Avoid unverified community merges for tool-calling roles.
2. Read the **model card** for the recommended sampling parameters, whether the model thinks by default, how to
   toggle thinking, and the context limit. Copy these into the preset and into `eval/models.json`.
3. Pick the quant by size: the largest that fits the rule from step 1, with Q4_K_M as the floor for tool calling.
4. For a role that needs more capability than fits, look at **mixture-of-experts** models (names like `35B-A3B`):
   only the active parameters run per token, so experts can live in RAM. Rough need: file size + 4 GB free RAM.
5. Prefer current model generations; a model from two years ago rarely beats a smaller current one.

Download with the Hugging Face CLI into the shared cache:

```bash
HF_HUB_CACHE=<hf_cache> hf download <org>/<repo>-GGUF <file>.gguf
```

## 4. Write the presets (`llamacpp/model.ini`)

Copy `llamacpp/model.ini.example`. One `[Section]` per tier, named after its role. Shared flags go in `[*]`:
context size, `n-gpu-layers = 99`, flash attention, q8_0 KV cache, `jinja = true` (mandatory for tool calling),
`reasoning-format = deepseek` (keeps thoughts out of `content`), `threads`. Per tier: the `hf` repo and quant, the
model card's sampling, `reasoning = on|off` (off for presets used by coding agents), and for MoE models
`n-cpu-moe = N`.

Install the launcher and start the router:

```bash
pwsh -File scripts/install.ps1
pwsh -File llamacpp/run-llama-server.ps1
curl http://127.0.0.1:8080/v1/models
```

The presets appear by name; each loads on first request.

## 5. Measure speed

```bash
pwsh -File scripts/benchmark.ps1 -Reps 2                          # every GGUF in the cache
pwsh -File scripts/benchmark.ps1 -Filter <moe-name> -MoeSweep "20,24,28,32,36,40"
```

Dense models run fully offloaded with a short and an agent-sized prompt. MoE models sweep `n-cpu-moe`: lower keeps
more experts on the GPU and is faster until VRAM overflows (the run fails or speed collapses); take the lowest value
that survives, then confirm with the server at your real context size and check free VRAM. Decide a usability
floor for generation speed (many people use 10–15 tokens/s for chat, more for agents) and drop what misses it.

## 6. Describe the tiers for evaluation (`eval/models.json`)

Copy `eval/models.example.json`. For each tier: the sampling from the model card, `chat_template_kwargs` for
thinking, `roles` (which suites apply: `reasoning`, `coding`, `tools`, `everyday`, `creative`, `security`),
`thinking_allowance` for tiers that reason (reasoning tokens count toward `max_tokens`), and `languages` if you
want language-specific cases. Then:

```bash
<python_cmd> -I scripts/smoke_toolcall.py <AgentTier>   # structured tool call + final answer?
npm run eval:setup                                       # generates eval/tiers/<Tier>.env from models.json
npm run eval -- --env-file eval/tiers/<Tier>.env         # one tier at a time
npm run eval:view
```

Scorecards land in `eval/results/<Tier>_scorecard.md`: one table per KPI with pass/fail against the suite's
threshold, and a `needs-judge` section for rubric cases. Grade those 1–5 against their rubric yourself, or configure
a grader model (`eval/README.md`).

## 7. Decide, then re-measure only what changed

A tier must meet the KPIs of its roles: an agent tier must pass tool calling and coding; a reasoning tier must pass
reasoning; everything must pass integrity, long-context recall and instruction following. For a miss: try the next
quant up if it fits, then thinking on/off, then the next candidate. Re-run only the failed suites
(`-- --filter-pattern "^tools/"`); the scorecard merges them into the tier's records.

Keep `results/` local unless you want to publish your machine's numbers; the framework stays generic.

## Appendix: reading llama-bench

`pp512` is prompt processing (tokens/s while reading your prompt), `tg128` is generation. Agents care about both:
a 4k-token prompt at 1,000 tokens/s costs 4 s before the first output token. The MoE sweep rows show the
trade-off directly.
