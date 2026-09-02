# Qwen3.8 Local Optimization Plan

## Objective

Find the best practical Qwen3.8-27B configuration on the RTX 5090. The original
goal was strict Pareto dominance; after E02, the user explicitly accepted a
small quality loss when it buys a significant speed increase. Optimize for:

- generation speed and overall score are improved materially;
- quality loss is measured, bounded, and justified by the speed gain;
- reliability remains 100%;
- no important suite regression is concealed by the aggregate score.

Peak tokens/second alone is not the objective. The winning configuration must
remain correct on structured extraction, code, tool calls, instructions, and
reasoning.

Current tolerance: prefer quality >= 77.2 (the reproducible E02 result), reject
any candidate below 76.9 without explicit review, and continue seeking a setup
that recovers the 77.9 control quality while retaining most of E02's speed.

## Recorded control

| Field | Value |
|---|---|
| Model | `Qwen3.8-27B-UD-Q4_K_XL.gguf` |
| Runtime | llama.cpp `0.2.0-dev`, commit `f280b26` |
| GPU | NVIDIA GeForce RTX 5090, 32 GB |
| API | OpenAI-compatible, `http://127.0.0.1:8080` |
| Context | 262,144 |
| KV cache | K=`q8_0`, V=`q8_0` |
| Harness | `raw` |
| Profile | BenchLoop `core`, benchmark `3.0.0`, 81 tasks |
| Overall | 76.3 |
| Quality | 77.9 |
| Speed | 67.0; 40.32 generation tok/s |
| Reliability | 100.0 |
| Result | `/home/christina/.bench-loop/runs/20260827-152653-qwen3.8-27b-local-openai_compat/run.json` |

Suite control scores: speed 67.0, toolcall 86.7, coding 77.1,
dataextract 62.9, instructfollow 90.0, reasonmath 73.3.

## Gates

### Screening gate

- reliability = 100%;
- generation speed >= 40 tok/s;
- quality >= 76.9 (temporary one-point non-inferiority allowance);
- no obvious output corruption or systematic structured-output failure.

### Final gate

- minimum three comparable `core` trials for both control and finalist;
- finalist mean quality >= 77.2 unless a larger loss is explicitly reviewed;
- finalist mean generation speed >= control mean generation speed;
- reliability = 100% in every run;
- no material suite regression (normally >2 points) without explicit review;
- record real-request behavior as well as the BenchLoop aggregate.

## Experimental method

1. Record exact artifact hashes, runtime commit/build, launch flags, harness,
   benchmark manifest, and result paths.
2. Change one major variable per screening comparison.
3. Use `smoke` only to reject broken configurations. A candidate cannot win
   without comparable `core` runs.
4. Promote plausible candidates to three-trial `core` comparisons.
5. Inspect failed task outputs, especially timeouts, malformed JSON, code, and
   tool calls. Fast corrupted output is a failed experiment.
6. Update this plan's status table and `RESULTS.md` after every completed run.

## Experiment matrix

| ID | Candidate | Primary hypothesis | Priority | Status |
|---|---|---|---:|---|
| E01 | Current Q4, `qwen` harness | Better Qwen formatting/reasoning extraction raises quality without slowing decode | 1 | complete: neutral, not promoted |
| E02 | Current Q4 + DFlash2 Q8 draft | Target verification preserves quality while speculative decoding raises speed | 1 | complete: superseded by E10 |
| E03 | Current Q4 + native MTP | Embedded MTP raises speed with less overhead than an external draft | 1 | repeat 2 complete: quality exact; 68.0 tok/s two-run mean; third trial pending |
| E04 | Current Q4, thinking disabled for structured workloads | Avoid timeouts and improve exact/JSON output while reducing latency | 1 | queued |
| E05 | Dynamic V3 Q5 + DFlash2 | Higher-precision target improves quality while DFlash recovers speed | 2 | queued |
| E06 | Qwen3.8 NVFP4 + MTP/NextN in SGLang or vLLM | Blackwell-native kernels provide a large speed gain with non-inferior quality | 2 | queued |
| E07 | Qwopus3.6-27B-v2-MTP Q5 | Fine-tuning plus embedded MTP may improve both quality and speed | 3 | queued |
| E08 | Dynamic V3 Q3 + DFlash2 | High-throughput fallback if Q3 proves quality-noninferior | 3 | queued |
| E09 | Unleashed Q3/Q5 + DFlash2 | Quant/fine-tune frontier; must justify quality loss with speed | 2 | Q5 192K/Q8 leader; exact repeats pending |
| E13 | Unleashed Q5 + native MTP | Removing external draft may permit 262K/Q8 and improve the sampling/quality path | 2 | complete: rejected |
| E10 | Current Q4 + DFlash2 depth 6, backend sampling off | Recover target behavior/quality while retaining speculative speed | 1 | complete: incumbent, 79.3 overall / 78.86 tok/s |
| E11 | Current Q4 + DFlash2 local depth sweep 5/6 + thresholds | Improve acceptance/throughput around the depth-6 winner | 2 | complete: depth 5 raw-speed leader; thresholds rejected |
| E12 | Unleashed Q3 + native MTP depth 3 | MTP may recover the Q3 quality path while retaining quant speed | 2 | complete: rejected, quality recovery insufficient |

## Sequencing notes

- Run E01 without disturbing the active server.
- For E02 and E03, keep target weights and benchmark settings fixed and change
  only speculative decoding. Run sequentially to avoid VRAM contention.
- Test DFlash acceptance and malformed-output gates before spending time on a
  full core run.
- For E05, try Q5 with DFlash at a smaller context/Q8 KV and at full context/Q4
  KV as separate subexperiments.
- E06 is the highest-upside platform change but needs an isolated environment,
  exact CUDA/runtime provenance, and careful parser configuration.
- Q3 and abliterated weights are not assumed improvements; they must earn
  promotion through the same gates.

## E02 DFlash2 recipe and tuning matrix

User-provided recommendation (2026-08-27): build llama.cpp with DFlash2 support
from PR #27342 and begin with the existing Q4 target as the standard-quality
control. The installed build exposed the flags but could not load the official
draft artifact, so PR commit `2f3923bc8` was built with CUDA for the RTX 5090.

Candidate server shape:

```text
-ngl all -ngld all -c 262144 -np 1 -fa on
-ctk q8_0 -ctv q8_0 -b 2048 -ub 512 -bs
--spec-type draft-dflash
--spec-draft-n-min 1
--spec-draft-n-max <4|6|7>
--spec-draft-p-min 0.0
--ctx-checkpoints 4 --checkpoint-min-step 16384
--temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0
--jinja --metrics
```

Draft depths 4, 6, and 7 were screened with the same deterministic coding probe
at full 262,144-token context. All returned identical correct code. Depth 6 won
the screen at 162.22 tok/s and 94.23% acceptance versus depth 4 at 127.15 tok/s
and 86.54%, and depth 7 at 156.00 tok/s and 81.32%. Promote depth 6 to a
BenchLoop speed-suite screen, then run a full comparable `core` profile if it
is reliable.

After Q4+DFlash establishes the acceleration effect, test the downloaded
Unleashed `UD-Q3_K_XL` as a separate model/quant candidate using the winning
DFlash parameters. It must pass the quality gates; uncensored behavior alone is
not treated as a quality improvement.

## Immediate next actions

1. Tune DFlash depth/thresholds as E11 against the E10 throughput incumbent.
2. Test Q5+DFlash and Unleashed Q3+DFlash frontier candidates.
3. Run two exact E09 192K repeats, E03 trial 3, and an exact E10 repeat before
   final promotion.
4. Test Q5+DFlash for quality recovery, then Unleashed Q3+DFlash for the
   high-throughput frontier.
5. Repeat the final control and finalist configuration before declaring the
   optimization loop complete.

## Loop policy

Continue experiments autonomously in priority order. After every completed
probe or benchmark, update this file and `RESULTS.md`, select the next experiment
from measured evidence, and continue. Stop only for a material authorization
boundary, an unrecoverable external dependency, or when a clearly best recipe
has survived repeat full-core trials.

Current finalists:

- best measured aggregate/capacity balance: E09 Unleashed Q5 DFlash depth 5
  at 192K/Q8 KV — 80.6 overall, 79.6 quality, 75.75 tok/s; identical quality
  suites across 64K, 128K, and 192K Q8 trials;
- balanced/quality: E03 native MTP depth 3 — 79.99/79.98 overall and 79.41
  quality on two trials; 69.80/66.17 tok/s (67.99 mean);
- maximum verified Q4 throughput: E10 DFlash depth 6 without `-bs` — 79.3
  overall, 77.2 quality, 78.86 tok/s.
- maximum measured full-core generation rate: E11 DFlash depth 5 — 79.2
  overall, 77.2 quality, 80.24 tok/s.
- absolute speed option: E09 Unleashed Q3 DFlash depth 6 — 77.8 overall,
  74.8 quality, 94.80 tok/s; below the normal quality floor.
3. Test native MTP independently as E03.
4. Test native MTP independently as E03.
5. Test the staged Unleashed Q3 candidate only after same-weight acceleration.

## Server lifecycle

Use `./local-optimization/server.sh start|stop|restart|status|adopt` for experiments.
It scopes the PID and log to the project `tmp` directory, validates the process
before stopping it, and accepts environment overrides for model/runtime/flags.
Do not run multiple 27B candidates concurrently on the same GPU.
