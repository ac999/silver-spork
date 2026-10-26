# Worked example: five role-based tiers on a consumer GPU with 8 GB of VRAM

This is the framework applied end to end on one machine class: a desktop with a **consumer GPU with 8 GB of VRAM**,
a 12-core CPU and 32 GB of RAM, running the Windows CUDA build of llama.cpp (build 11729). Paths are placeholders;
model names, quantizations and the measured numbers are real. The matching instance files are in
[`examples/8gb-gpu/`](../examples/8gb-gpu/): copy them over the three templates and replace the paths.

The goal was a Claude-style workflow run fully offline: a deep thinker for planning and hard problems, a model for a
coding agent, a fast everyday model, a creative writer and a defensive-security specialist, each at a usable speed
(floor: 15 tokens/s for chat, 10 for the thinker).

## 1. Sizing

`scripts/detect-hardware.ps1` reported 8 GB of VRAM and 12 physical cores, and derived:

> largest GGUF that runs fully on the GPU at 32k context with a q8_0 KV cache ≈ 8 − 1.5 − 1 ≈ **5.5 GB**

That rules out dense models above about 9B at Q4, and any 12B above Q4_0 once the KV cache is counted. Two ways
past the limit were considered: a **mixture-of-experts** model with experts in RAM (`n-cpu-moe`), or CPU layer
offload of a dense model. An earlier measurement had already shown the second path to be hopeless here: a dense 27B
at IQ4_XS produced about 3 tokens/s.

## 2. Candidates and the presets

| Tier (role) | Model | Quant | File | Why |
|---|---|---|---|---|
| Deep (reasoning, planning, hard coding) | Qwen3.5-35B-A3B | UD-IQ4_XS | 16.3 GiB | MoE with 3B active parameters: experts fit in RAM, attention and KV on the GPU |
| Dev (coding agent, tool calling) | Qwen3.5-9B | UD-Q4_K_XL | 5.6 GiB | largest current dense model that fits fully; strong tool-calling template |
| Quick (everyday chat) | gemma-4-26B-A4B-it | UD-IQ4_XS | 12.7 GiB | MoE with 4B active parameters, strong multilingual; chosen in the second round (see §5) |
| Muse (creative, low refusal) | gemma-4-26B-A4B-it (same file) | UD-IQ4_XS | – | best creative scores measured; replaced Hermes-3-Llama-3.1-8B in the second round |
| Sentinel (defensive security) | Foundation-Sec-8B-Instruct | Q5_K_M | 5.3 GiB | security-domain fine-tune (threat intel, SOC work) |

Three earlier files were removed after the first comparison: a 4B at Q8 (superseded by the 9B), a 2024-generation
8B, and an unverified 9B community merge that had been the coding preset and the probable cause of agent loops. The
first-round picks for Quick (gemma-4-E4B-it Q5_K_M, then the Dev file) and Muse (Hermes-3-Llama-3.1-8B Q5_K_M) were
replaced after the second round.

Shared flags in `[*]`: 32k context, `n-gpu-layers = 99`, flash attention, q8_0 KV cache, `jinja = true`,
`reasoning-format = deepseek`. Deep has `reasoning = on`; Dev, Quick and Muse have `reasoning = off` because a thinking
model behind an OpenAI-compatible agent puts its tool call in `reasoning_content` and the agent sees an empty answer.
Sampling per preset came from each model card (the full file is `examples/8gb-gpu/model.ini`).

## 3. Speed (`scripts/benchmark.ps1`, llama-bench, 2 repetitions)

Dense models, fully on the GPU, q8_0 KV cache:

| Model | pp512 tok/s | tg128 tok/s | pp4096 tok/s | tg64 tok/s |
|---|---:|---:|---:|---:|
| gemma-4-E4B-it Q5_K_M | 3,906 | 81.4 | 4,007 | 81.6 |
| Foundation-Sec-8B-Instruct Q5_K_M | 2,975 | 67.7 | 2,810 | 67.4 |
| Hermes-3-Llama-3.1-8B Q5_K_M | 2,967 | 67.5 | 2,785 | 65.3 |
| Qwen3.5-9B UD-Q4_K_XL | 2,856 | 64.8 | 2,786 | 64.0 |
| Ornith-1.0-9B UD-Q4_K_XL (second round) | 2,842 | 64.6 | 2,814 | 64.0 |
| gemma-4-12B-it QAT q4_0 (second round) | 1,989 | 48.9 | 1,837 | 47.3 |

Every dense candidate was far above the floor, so speed did not decide anything among them.

Qwen3.5-35B-A3B UD-IQ4_XS, `n-cpu-moe` sweep (40 layers):

| n-cpu-moe | 24 | 27 | 30 | 33 | 36 | 40 |
|---|---:|---:|---:|---:|---:|---:|
| tg128 tok/s | 9.3 (VRAM overflow) | 40.7 | **40.7** | 39.3 | 37.9 | 33.8 |
| pp512 tok/s | 157 | 479 | 534 | 493 | 474 | 437 |

30 was chosen: same speed as 27 with about 1 GB of VRAM headroom (7.1 GB used with the server at 32k context).
For comparison, plain layer offload of the same file had reached 18 tok/s; expert offload more than doubled it.

gemma-4-26B-A4B-it UD-IQ4_XS, `n-cpu-moe` sweep (30 layers):

| n-cpu-moe | 16 | 18 | 20 | 22 | 26 | 30 |
|---|---:|---:|---:|---:|---:|---:|
| tg128 tok/s | 27.6 (spills) | 40.7 | **38.8** | 33.6 | 31.0 | 28.3 |
| pp512 tok/s | 184 | 818 | 757 | 703 | 595 | 557 |

Below 18 the weights spill into shared GPU memory, which shows first as prompt processing collapsing to ~190 tok/s.
20 was chosen over 18 for headroom: 7.5 GB used with the server at 32k context. In the eval it averaged ~36 tok/s.
The full log is `examples/8gb-gpu/benchmark_results.md`.

## 4. Quality (`npm run eval` / `run_eval.py`, one tier at a time)

Suites were selected by role. Deterministic suites count passes against the threshold stored with the suite; the
everyday and creative suites were graded 1–5 by a reviewer against each case's rubric (two independent passes).

| Suite (threshold) | Deep | Dev | Quick (gemma) | Muse | Sentinel |
|---|---|---|---|---|---|
| Output integrity (10/10) | 10/10 | 10/10 | 10/10 | 8/10 | 10/10 |
| Long-context recall 8k–24k (≥8/9) | 9/9 | 9/9 | 9/9 | 9/9 | 9/9 |
| Instruction following (≥5/6) | 6/6 | 5/6 | 4/6 | 4/6 | 4/6 |
| Reasoning (Deep ≥8, Dev ≥6 of 10) | 10/10 | 9/10 | – | – | – |
| Coding, hidden tests executed (≥6/8) | 7/8 | 6/8 | – | – | – |
| Tool calling, multi-turn (≥8/10) | 8/10 | 7/10 (8/10 with thinking on) | – | – | – |
| Everyday tasks, judged (mean ≥4.0) | – | 3.88 | 3.50 / 3.25 | – | – |
| Creative, judged (mean ≥4.0, 0 refusals) | – | – | – | 2.75 / 2.57, 0 refusals | – |
| Defensive security facts (≥13/15) | – | – | – | – | 13/15 |

Second round, with Romanian (`ro`) cases enabled, judged the same way (one pass):

| Suite (threshold) | gemma-4-26B-A4B (Quick, Muse) | gemma-4-12B QAT | Ornith-1.0-9B (Dev candidate) |
|---|---|---|---|
| Output integrity (10/10) | 10/10 | 10/10 | 10/10 |
| Long-context recall 8k–24k (≥8/9) | 9/9 | 9/9 | 9/9 |
| Instruction following (≥5/6) | 6/6 | 6/6 | 6/6 |
| Reasoning (≥8/10) | – | – | 9/10 |
| Coding, hidden tests executed (≥6/8) | – | – | 6/8 |
| Tool calling, multi-turn (≥8/10) | – | – | 7/10 |
| Everyday tasks, judged (mean ≥4.0) | **4.25** (EN→RO 4/5) | 3.63 (EN→RO 1/5) | – |
| Creative, judged (mean ≥4.0, 0 refusals) | 3.63, 0 refusals | 3.50, 0 refusals | – |

Two lessons came out of the first Deep run, both now encoded in the framework:

- Reasoning tokens count toward `max_tokens`. A one-word case with a 32-token budget came back empty because the
  model spent the budget thinking. The eval config now has a `thinking_allowance` per thinking tier.
- Over-quantized or merged models fail tool calling in characteristic ways (loops, mistyped calls, template tokens
  in the output). Keeping the agent tier at Q4_K_XL or better and on a maintained quantizer's upload removed them.

## 5. Decisions

- **Deep: keep.** All six KPIs met at about 40 tok/s with thinking on. It is the planning and escalation tier.
- **Dev: keep with a caveat.** Tool calling is 7/10 with thinking off (loops on a read-modify-write edit, one
  unnecessary tool call); 8/10 with thinking on at the same speed. Planning tasks go to Deep.
- **Quick: replaced twice.** gemma-4-E4B was the fastest model measured (81 tok/s) but scored 3.50 and 3.25 on
  everyday tasks (merged headings, option menus instead of one rewrite, a mistranslated date). Qwen3.5-9B with
  thinking off did better (3.88) but still missed 4.0 and failed the English-to-Romanian case. In the second round
  gemma-4-26B-A4B with experts in RAM scored 4.25, the first model to meet the bar, and the only one whose Romanian
  translation was usable. It costs speed (~36 vs ~55 tok/s in the eval) and a model reload when switching from Dev.
- **Muse: replaced.** Hermes-3-Llama-3.1-8B had zero refusals and good format compliance but generic prose, a
  limerick that does not rhyme and an existing brand proposed as a startup name (2.75). gemma-4-26B-A4B scored 3.63:
  strong on outlines, brainstorms and product copy, still clichéd in voice-driven pieces, so the 4.0 bar stays unmet.
- **Rejected in the second round.** Ornith-1.0-9B, an agentic-coding post-train of the Dev model, tied Dev on every
  suite (its exploratory tool use overruns scripted scenarios). gemma-4-12B QAT ran fully on the GPU at 49 tok/s but
  lost to the 26B MoE on both everyday and creative tasks.
- **Sentinel: keep for its domain.** 13/15 on security facts with no fabricated CVE identifiers; weak on strict
  output formats, which matters little for its role.

## 6. Reproducing this example

```bash
cp examples/8gb-gpu/local-ai.json config/local-ai.json      # then replace the placeholder paths
cp examples/8gb-gpu/model.ini      llamacpp/model.ini
cp examples/8gb-gpu/models.json    eval/models.json
pwsh -File scripts/install.ps1
pwsh -File llamacpp/run-llama-server.ps1
pwsh -File scripts/benchmark.ps1 -Reps 2
pwsh -File scripts/benchmark.ps1 -Filter 35B-A3B -MoeSweep "24,27,30,33,36,40"
pwsh -File scripts/benchmark.ps1 -Filter 26B-A4B -MoeSweep "16,18,20,22,26,30"
npm run eval:setup
npm run eval -- --env-file eval/tiers/Dev.env       # repeat per tier
```

The first request to each preset downloads its GGUF into your Hugging Face cache (about 40 GB for the four files; Quick and Muse share one).
Your numbers will differ with driver, build and thermals; the method does not.
