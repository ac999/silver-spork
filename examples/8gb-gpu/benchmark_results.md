# Example benchmark log (8 GB GPU)

Produced by `scripts/benchmark.ps1`; dates are when the example was measured.

# Local LLM Benchmark Results - 2026-10-25 21:43
Host: consumer GPU with 8 GB VRAM, 12-core desktop CPU, 32 GB RAM. llama.cpp 0.7.0-dev (build 11729)
Columns: pp = prompt processing t/s, tg = generation t/s. KV cache q8_0, flash attention on, 2 repetitions.

## Meta-Llama-3.1-8B-Instruct-Q5_K_M.gguf (5.34 GiB)
| model | size | params | backend | ngl | type_k | type_v | fa | test | t/s |
|---|---|---|---|---|---|---|---|---|---|
| llama 8B Q5_K - Medium         |   5.33 GiB |     8.03 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           pp512 |      2978.91 ┬▒ 66.69 |
| llama 8B Q5_K - Medium         |   5.33 GiB |     8.03 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           tg128 |         67.44 ┬▒ 0.08 |
| llama 8B Q5_K - Medium         |   5.33 GiB |     8.03 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |          pp4096 |       2831.43 ┬▒ 0.48 |
| llama 8B Q5_K - Medium         |   5.33 GiB |     8.03 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |            tg64 |         66.41 ┬▒ 0.14 |

## Qwopus3.5-9B-coder-Exp-Q4_K_M.gguf (5.24 GiB)
| model | size | params | backend | ngl | type_k | type_v | fa | test | t/s |
|---|---|---|---|---|---|---|---|---|---|
| qwen35 9B Q4_K - Medium        |   5.23 GiB |     8.95 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           pp512 |      2794.11 ┬▒ 71.81 |
| qwen35 9B Q4_K - Medium        |   5.23 GiB |     8.95 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           tg128 |         67.48 ┬▒ 0.78 |
| qwen35 9B Q4_K - Medium        |   5.23 GiB |     8.95 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |          pp4096 |       2788.12 ┬▒ 1.38 |
| qwen35 9B Q4_K - Medium        |   5.23 GiB |     8.95 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |            tg64 |         67.45 ┬▒ 0.29 |

## Foundation-Sec-8B-Instruct.Q5_K_M.gguf (5.34 GiB)
| model | size | params | backend | ngl | type_k | type_v | fa | test | t/s |
|---|---|---|---|---|---|---|---|---|---|
| llama 8B Q5_K - Medium         |   5.33 GiB |     8.03 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           pp512 |      2974.89 ┬▒ 55.01 |
| llama 8B Q5_K - Medium         |   5.33 GiB |     8.03 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           tg128 |         67.74 ┬▒ 0.04 |
| llama 8B Q5_K - Medium         |   5.33 GiB |     8.03 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |          pp4096 |       2810.27 ┬▒ 5.06 |
| llama 8B Q5_K - Medium         |   5.33 GiB |     8.03 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |            tg64 |         67.42 ┬▒ 0.30 |

## Hermes-3-Llama-3.1-8B.Q5_K_M.gguf (5.34 GiB)
| model | size | params | backend | ngl | type_k | type_v | fa | test | t/s |
|---|---|---|---|---|---|---|---|---|---|
| llama 8B Q5_K - Medium         |   5.33 GiB |     8.03 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           pp512 |      2967.35 ┬▒ 68.57 |
| llama 8B Q5_K - Medium         |   5.33 GiB |     8.03 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           tg128 |         67.51 ┬▒ 0.17 |
| llama 8B Q5_K - Medium         |   5.33 GiB |     8.03 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |          pp4096 |      2785.21 ┬▒ 17.60 |
| llama 8B Q5_K - Medium         |   5.33 GiB |     8.03 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |            tg64 |         65.31 ┬▒ 0.31 |

## gemma-4-E4B-it-Q5_K_M.gguf (5.11 GiB)
| model | size | params | backend | ngl | type_k | type_v | fa | test | t/s |
|---|---|---|---|---|---|---|---|---|---|
| gemma4 E4B Q5_K - Medium       |   5.09 GiB |     7.52 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           pp512 |     3905.85 ┬▒ 132.70 |
| gemma4 E4B Q5_K - Medium       |   5.09 GiB |     7.52 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           tg128 |         81.41 ┬▒ 2.03 |
| gemma4 E4B Q5_K - Medium       |   5.09 GiB |     7.52 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |          pp4096 |       4007.32 ┬▒ 2.20 |
| gemma4 E4B Q5_K - Medium       |   5.09 GiB |     7.52 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |            tg64 |         81.58 ┬▒ 1.30 |

## Qwen3.5-4B-UD-Q8_K_XL.gguf (5.54 GiB)
| model | size | params | backend | ngl | type_k | type_v | fa | test | t/s |
|---|---|---|---|---|---|---|---|---|---|
| qwen35 4B Q8_0                 |   5.53 GiB |     4.21 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           pp512 |     4462.81 ┬▒ 274.20 |
| qwen35 4B Q8_0                 |   5.53 GiB |     4.21 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           tg128 |         60.98 ┬▒ 0.01 |
| qwen35 4B Q8_0                 |   5.53 GiB |     4.21 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |          pp4096 |       4493.67 ┬▒ 8.94 |
| qwen35 4B Q8_0                 |   5.53 GiB |     4.21 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |            tg64 |         60.43 ┬▒ 0.15 |

## Qwen3.5-9B-UD-Q4_K_XL.gguf (5.56 GiB)
| model | size | params | backend | ngl | type_k | type_v | fa | test | t/s |
|---|---|---|---|---|---|---|---|---|---|
| qwen35 9B Q4_K - Medium        |   5.55 GiB |     8.95 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           pp512 |      2856.42 ┬▒ 78.03 |
| qwen35 9B Q4_K - Medium        |   5.55 GiB |     8.95 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |           tg128 |         64.79 ┬▒ 0.14 |
| qwen35 9B Q4_K - Medium        |   5.55 GiB |     8.95 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |          pp4096 |       2785.62 ┬▒ 8.37 |
| qwen35 9B Q4_K - Medium        |   5.55 GiB |     8.95 B | CUDA       |  99 |   q8_0 |   q8_0 |   1 |            tg64 |         64.03 ┬▒ 0.39 |


# Local LLM Benchmark Results - 2026-10-25 22:40 (MoE n-cpu-moe sweep)
Host: consumer GPU with 8 GB VRAM, 12-core desktop CPU, 32 GB RAM. llama.cpp 0.7.0-dev (build 11729)
Columns: pp = prompt processing t/s, tg = generation t/s. KV cache q8_0, flash attention on, 2 repetitions, -ngl 99.

## Qwen3.5-35B-A3B-UD-IQ4_XS.gguf (16.29 GiB)
| model | n_cpu_moe | pp512 t/s | tg128 t/s | note |
|---|---|---|---|---|
| qwen35moe 35B.A3B IQ4_XS | 24 | 157.5 | 9.3 | VRAM overflow, unstable |
| qwen35moe 35B.A3B IQ4_XS | 27 | 478.8 | 40.7 |  |
| qwen35moe 35B.A3B IQ4_XS | 30 | 534.2 | 40.7 | chosen for [Deep] |
| qwen35moe 35B.A3B IQ4_XS | 33 | 493.0 | 39.3 |  |
| qwen35moe 35B.A3B IQ4_XS | 36 | 474.2 | 37.9 |  |
| qwen35moe 35B.A3B IQ4_XS | 40 | 436.8 | 33.8 |  |

# Local LLM Benchmark Results - 2026-10-26 (candidates)
Host: consumer GPU with 8 GB VRAM, 12-core desktop CPU, 32 GB RAM. llama.cpp build 11729.
Columns: pp = prompt processing t/s, tg = generation t/s. KV cache q8_0, flash attention on, 2 repetitions, -ngl 99.

## Dense candidates (fully on the GPU)
| model | size | pp512 | tg128 | pp4096 | tg64 |
|---|---|---|---|---|---|
| Ornith-1.0-9B UD-Q4_K_XL | 5.56 GiB | 2842 | 64.6 | 2814 | 64.0 |
| gemma-4-12B-it QAT q4_0 | 6.48 GiB | 1989 | 48.9 | 1837 | 47.3 |

## gemma-4-26B-A4B-it-UD-IQ4_XS.gguf (12.65 GiB, 30 layers, 128 experts / 8 active)
| model | n_cpu_moe | pp512 t/s | tg128 t/s | note |
|---|---|---|---|---|
| gemma4 26B.A4B IQ4_XS | 6 | 204.8 | 18.5 | spills into shared GPU memory |
| gemma4 26B.A4B IQ4_XS | 10 | 187.0 | 22.3 | spills |
| gemma4 26B.A4B IQ4_XS | 14 | 186.2 | 27.1 | spills |
| gemma4 26B.A4B IQ4_XS | 16 | 183.9 | 27.6 | spills |
| gemma4 26B.A4B IQ4_XS | 18 | 817.9 | 40.7 | fastest, no headroom at 32k |
| gemma4 26B.A4B IQ4_XS | 20 | 756.8 | 38.8 | chosen for [Quick] and [Muse] |
| gemma4 26B.A4B IQ4_XS | 22 | 703.4 | 33.6 |  |
| gemma4 26B.A4B IQ4_XS | 26 | 594.9 | 31.0 |  |
| gemma4 26B.A4B IQ4_XS | 30 | 557.4 | 28.3 |  |
