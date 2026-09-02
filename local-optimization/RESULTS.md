# Local Optimization Results

## Control C00 — Qwen3.8 Q4, raw harness, no speculative decoding

- Status: complete
- Date: 2026-08-27
- Model: `Qwen3.8-27B-UD-Q4_K_XL.gguf`
- Runtime: llama.cpp `0.2.0-dev` commit `f280b26`
- Launch: `-ngl 99 -c 262144 --cache-type-k q8_0 --cache-type-v q8_0
  --flash-attn on --jinja --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0`
- BenchLoop: `core`, raw harness, OpenAI-compatible
- Overall: 76.3
- Quality: 77.9
- Speed: 67.0; 40.32 tok/s (p95 43.83)
- Reliability: 100.0
- Suites: speed 67.0; toolcall 86.7; coding 77.1; dataextract 62.9;
  instructfollow 90.0; reasonmath 73.3
- Runtime: 1298.9 seconds
- Result: `/home/christina/.bench-loop/runs/20260827-152653-qwen3.8-27b-local-openai_compat/run.json`
- Observation: several zero-score tasks took about 44 seconds, making reasoning
  budget/final-answer completion and timeout behavior important follow-up areas.

## E01 — Current Q4 with Qwen harness

- Status: complete; neutral, not promoted
- Purpose: isolate harness effects while leaving model, runtime, endpoint,
  context, KV precision, and server sampling unchanged.
- Command: `benchloop run --model qwen3.8-27b --provider openai_compat
  --endpoint http://127.0.0.1:8080 --profile core --harness qwen --local`
- Attempt 1: aborted intentionally at 8/81 on 2026-08-27 while establishing
  controlled server lifecycle. This partial run is invalid and has no score.
- Valid run date: 2026-08-27
- Overall: 76.4 (control 76.3; delta +0.1)
- Quality: 77.9 (control 77.9; delta 0.0)
- Speed: 67.5 and 40.23 tok/s (control 67.0 and 40.32 tok/s)
- Reliability: 100.0 (control 100.0)
- Suites: speed 67.5; toolcall 86.7; coding 77.1; dataextract 62.9;
  instructfollow 90.0; reasonmath 73.3. Every quality suite exactly matched
  the control.
- Runtime: 1300.9 seconds
- Result: `/home/christina/.bench-loop/runs/20260827-162127-qwen3.8-27b-local-openai_compat/run.json`
- Decision: the Qwen harness is behaviorally and operationally neutral for
  this endpoint. Do not spend repeat-trial budget on it; retain raw as the
  comparison harness unless another candidate specifically requires Qwen tags.

## E02 — Current Q4 with DFlash2 Q8 draft

- Status: in progress; depth 6 selected for BenchLoop screening
- Target: retain the current Q4 weights as the standard-quality control.
- Source: user-provided recommendation from a trusted peer.
- Draft artifact: `Qwen3.8-27B-DFlash2-Q8_0.gguf`, 2,056,414,752 bytes,
  SHA-256 `7f1c9a31a6ed40044c69f6508b50fd63b87abd8e1fb7fe4290303df549153751`
  (matches the Hugging Face LFS object ID).
- Runtime: llama.cpp PR #27342 commit `2f3923bc8`, CUDA build for compute
  capability 12.0. The prior installed runtime `f280b26` recognized DFlash
  flags but rejected this draft with `expected 81, got 58` tensors.
- Runtime recipe: DFlash2 support associated with llama.cpp PR #27342; 262K
  context; Q8 KV; batch 2048; ubatch 512; one slot; four context checkpoints;
  checkpoint minimum step 16,384; published Qwen sampler values.
- Screening matrix: `--spec-draft-n-max` = 4, 6, 7 with minimum 1 and
  probability minimum 0.0.
- Deterministic probe: request a single fenced Python `is_prime` function at
  temperature 0 and maximum 256 tokens. Every depth produced the same correct
  174-token answer.

| Max draft depth | Generation tok/s | Draft accepted | Acceptance | Mean accepted length |
|---:|---:|---:|---:|---:|
| 4 | 127.15 | 135 / 156 | 86.54% | 4.46 |
| 6 | 162.22 | 147 / 156 | 94.23% | 6.65 |
| 7 | 156.00 | 148 / 182 | 81.32% | not captured |

- Decision: depth 6 wins this workload. Depth 7 generated more draft tokens
  but lost throughput because its acceptance rate fell sharply. Run the
  BenchLoop speed suite on depth 6 before spending a full core run.
- Depth-6 speed-suite screen: complete, 9/9 tasks passed, reliability 100%,
  speed score 78.4, generation 73.09 tok/s, p95 104.21 tok/s, runtime 64.2
  seconds. This is +32.77 tok/s or +81.3% over the 40.32 tok/s control; the
  custom suite is intentionally not an overall-score comparison.
- Speed-screen result: `/home/christina/.bench-loop/runs/20260827-164114-qwen3.8-27b-local-openai_compat/run.json`
- Promotion: passed. Run the full 81-task `core` profile to verify quality and
  suite-level non-inferiority.
- Core trial 1: complete in 545.9 seconds. Overall 78.8, quality 77.2, speed
  78.9 / 77.14 tok/s (p95 107.34), reliability 100%.
- Core suites: speed 78.9; toolcall 86.7; coding 75.0; dataextract 62.6;
  instructfollow 83.3; reasonmath 77.0.
- Versus control: overall +2.5; quality -0.7; generation +36.82 tok/s (+91.3%);
  toolcall 0.0; coding -2.1; dataextract -0.3; instructfollow -6.7;
  reasonmath +3.7. Runtime fell from 1298.9 to 545.9 seconds (-58.0%).
- Core result: `/home/christina/.bench-loop/runs/20260827-165039-qwen3.8-27b-local-openai_compat/run.json`
- Decision: passes the screening gate but not yet the final gate. The aggregate
  quality delta is within the temporary allowance, but instruction following
  and coding require task-level inspection and repeat trials before promotion.
- Task inspection: instruction tasks `if-08` and `if-12` failed identically in
  the control. The 6.7-point instruction delta is entirely `if-03`, which gave
  a semantically correct three-sentence answer but used single newlines rather
  than blank-line paragraph separators. The coding delta is the rate-limiter
  task scoring 0 instead of the control's partial 25.
- Core trial 2: complete in 530.5 seconds. Overall 78.3, quality 77.2, speed
  77.0 / 70.62 tok/s (p95 91.19), reliability 100%. Suites repeated exactly:
  toolcall 86.7; coding 75.0; dataextract 62.6; instructfollow 83.3;
  reasonmath 77.0.
- Trial-2 result: `/home/christina/.bench-loop/runs/20260827-170009-qwen3.8-27b-local-openai_compat/run.json`
- Two-trial DFlash mean: overall 78.55, quality 77.2, generation 73.88 tok/s,
  reliability 100%. Quality behavior is reproducible in this configuration,
  so another identical trial is low value; isolate backend sampling/runtime
  behavior before the next full run.
- Publishing status: all five captured runs published publicly on 2026-08-27,
  including both DFlash core trials. DFlash trial 1 is post 7 and trial 2 is
  post 8. The WSL environment lacks an OS-keychain backend, so publication used
  a one-shot device token held only in process memory.
- Cleanup request: keep posts 4 and 7; remove posts 5, 6, and 8. The hosted API
  currently exposes no owner delete/hide route for runs or posts. `DELETE
  /runs/:id` is handled identically to GET and leaves the record intact, which
  was verified after attempted cleanup. Server-side support or administrator
  action is required; no local benchmark files were deleted.

## E10 — Current Q4 with DFlash2 depth 6, backend sampling disabled

- Status: complete; current incumbent
- Change from E02: removed only the boolean `-bs` / backend-sampling flag.
- Deterministic probe: identical correct 174-token `is_prime` answer at 159.14
  tok/s, with 147/156 draft tokens accepted (94.23%). E02's comparable probe
  was 162.22 tok/s with the same accepted-token counts.
- Speed-suite screen: complete, 9/9 passed, reliability 100%, speed score 81.2,
  generation 80.11 tok/s, p95 111.36 tok/s, runtime 59.8 seconds.
- Comparisons: +7.02 tok/s (+9.6%) versus the E02 speed screen and +39.79 tok/s
  (+98.7%) versus the original control.
- Result: `/home/christina/.bench-loop/runs/20260827-171756-qwen3.8-27b-local-openai_compat/run.json`
- Decision: promote to full core to measure whether target behavior and quality
  improve without backend sampling.
- Full core: overall 79.3, quality 77.2, speed 80.9 / 78.86 tok/s (p95
  112.70), reliability 100%, runtime 523.2 seconds.
- Suites: toolcall 86.7; coding 75.0; dataextract 62.6; instructfollow 83.3;
  reasonmath 77.0. Quality behavior exactly matches both E02 core trials.
- Core result: `/home/christina/.bench-loop/runs/20260827-172659-qwen3.8-27b-local-openai_compat/run.json`
- Versus best E02 core: overall +0.5, quality 0.0, generation +1.72 tok/s
  (+2.2%), runtime -22.7 seconds. Versus original control: overall +3.0,
  quality -0.7, generation +38.54 tok/s (+95.6%), runtime -59.7%.
- Decision: removing backend sampling strictly improves E02 on observed full
  core results. E10 becomes the incumbent recipe; proceed to native MTP.

## E03 — Current Q4 with embedded native MTP

- Status: complete; balanced/quality incumbent pending repeat
- Runtime/target: same PR #27342 build and Q4 target as E10, no external draft;
  `--spec-type draft-mtp`, Q8 KV, 262K context, backend sampling disabled.
- Correctness probe: depths 3, 4, 5, and 6 all returned correct fenced Python.
  Probe generation rates were 109.06, 119.94, 131.31, and 131.71 tok/s,
  respectively. Acceptance fell as depth increased: 86.93%, 82.93%, 79.43%,
  and 73.44%.
- Depth-3 speed suite: 9/9 passed, 70.67 tok/s, speed score 77.8, p95 82.73,
  runtime 66.6 seconds. Result:
  `/home/christina/.bench-loop/runs/20260827-172932-qwen3.8-27b-local-openai_compat/run.json`
- Depth-6 speed suite: 9/9 passed, 63.26 tok/s, speed score 76.5, p95 79.80,
  runtime 73.1 seconds. Result:
  `/home/christina/.bench-loop/runs/20260827-173255-qwen3.8-27b-local-openai_compat/run.json`
- Decision: deeper MTP wins the narrow probe but loses the varied speed suite.
  Use depth 3 for a full core comparison. It is 11.8% slower than E10's speed
  screen but 75.3% faster than the original control, leaving room to win if it
  recovers enough quality.
- Full core: overall 79.9, quality 79.4, speed 77.4 / 69.80 tok/s (p95 82.88),
  reliability 100%, runtime 644.5 seconds.
- Suites: toolcall 86.7; coding 77.1; dataextract 73.2; instructfollow 90.0;
  reasonmath 73.3.
- Core result: `/home/christina/.bench-loop/runs/20260827-174430-qwen3.8-27b-local-openai_compat/run.json`
- Versus original control: overall +3.6; quality +1.5; generation +29.48 tok/s
  (+73.1%); runtime -654.4 seconds (-50.4%). Coding, instruction following,
  tool calling, and reason/math match control; data extraction improves +10.3.
- Versus E10: overall +0.6 and quality +2.2, but generation -9.06 tok/s
  (-11.5%) and runtime +121.3 seconds. E03 is the first measured configuration
  to strictly improve both quality and speed over the original control.
- Decision: retain E03 as the balanced/quality incumbent and repeat it before
  final promotion. Continue frontier tests so the user can choose the final
  quality/throughput tradeoff from a complete matrix.
- Repeat 2 full core: overall 79.98, quality 79.41, speed score 77.55,
  66.17 tok/s (p95 83.46), reliability 100%, runtime 665.5 seconds. Every
  quality suite reproduced exactly: toolcall 86.67; coding 77.08; dataextract
  73.17; instructfollow 90.00; reasonmath 73.33. Result:
  `/home/christina/.bench-loop/runs/20260827-183739-qwen3.8-27b-local-openai_compat/run.json`
- Two-run stability: quality is exact at 79.41 on both trials; generation is
  69.80 and 66.17 tok/s (mean 67.99, range 3.63, 5.3% of the mean). Overall is
  79.95 mean. Run the planned third exact trial before final confidence claims.

## E11 — Current Q4 DFlash tuning around the E10 winner

- Status: complete; depth 5 retained as raw-speed leader
- Depth-5 change: E10 recipe with `--spec-draft-n-max 5` instead of 6; backend
  sampling remains disabled and all other target/draft/context settings match.
- Speed suite: 9/9 passed, 80.72 tok/s, speed score 80.2, p95 102.92, runtime
  59.4 seconds.
- Result: `/home/christina/.bench-loop/runs/20260827-174630-qwen3.8-27b-local-openai_compat/run.json`
- Comparison: +0.61 tok/s (+0.8%) versus E10's speed screen. Promote to core
  because depth also changes the reproducible sampling/output path and could
  alter quality even when raw throughput is nearly tied.
- Depth-5 full core: overall 79.2, quality 77.2, speed score 80.7,
  80.24 tok/s (p95 113.39), reliability 100%, runtime 533.9 seconds.
- Suites exactly match E10: toolcall 86.7; coding 75.0; dataextract 62.6;
  instructfollow 83.3; reasonmath 77.0.
- Core result: `/home/christina/.bench-loop/runs/20260827-175548-qwen3.8-27b-local-openai_compat/run.json`
- Comparison with E10 full core: generation +1.38 tok/s (+1.7%), but speed
  score -0.2, overall -0.1, and runtime +10.7 seconds due to the per-task speed
  distribution. Retain depth 5 as the raw-generation leader, while depth 6
  remains the DFlash overall-score leader. Test confidence thresholds before
  closing E11.
- Depth 5 with `--spec-draft-p-min 0.1`: 9/9 speed tasks passed, 80.49 tok/s,
  speed score 80.5, p95 105.82, runtime 59.2 seconds. Result:
  `/home/christina/.bench-loop/runs/20260827-175743-qwen3.8-27b-local-openai_compat/run.json`
- Threshold decision: reject 0.1 because it did not improve unthresholded depth
  5 (80.72 tok/s). Do not spend a core run or finer threshold sweep on a
  candidate that failed its primary speed hypothesis.

## E09 — Unleashed alternate-quant frontier

- Status: in progress; Q3 complete, Q5 screening underway
- Artifact: `Qwen3.8-27B-Unleashed-UD-Q3_K_XL.gguf`, 13,223,069,536 bytes,
  SHA-256 `b4c9721ab6ed1b7d1d1863b8f43e2fbce6a88dab39ea4333d2e74a7ad69580fe`.
  Local size and hash exactly match the Hugging Face LFS metadata.
- Initial recipe: DFlash external Q8 draft, depth 5 and 6 speed screens at full
  262K/Q8 KV if they fit; promote the fastest healthy depth to core. Treat
  uncensored behavior separately from benchmark quality.
- Depth-5 probe: the 256-token budget truncated the visible answer after a
  correct prefix because this model used more reasoning tokens. At 512 tokens
  it completed the same correct fenced `is_prime` implementation, finishing in
  296 generated tokens at 169.37 tok/s with 234/305 draft tokens accepted.
- Depth-5 speed suite: 9/9 passed, 95.14 tok/s, speed score 82.0, p95 101.28,
  runtime 54.7 seconds. Result:
  `/home/christina/.bench-loop/runs/20260827-180054-qwen3.8-27b-unleashed-q3-local-openai_compat/run.json`
- Comparison: +14.42 tok/s (+17.9%) over the Q4 depth-5 speed screen and
  +54.82 tok/s (+136.0%) over the original control. Screen depth 6 before core.
- Depth-6 speed suite: 9/9 passed, 95.52 tok/s, speed score 81.9, p95 100.61,
  runtime 55.3 seconds. Result:
  `/home/christina/.bench-loop/runs/20260827-180238-qwen3.8-27b-unleashed-q3-local-openai_compat/run.json`
- Depth decision: depth 6 is +0.38 tok/s over depth 5, while depth 5 has a
  0.1-point suite-score edge from its per-task distribution. Promote depth 6
  as the raw-throughput winner to full core; preserve depth 5 as a fallback if
  the full result exposes workload-specific instability.
- Depth-6 full core: overall 77.8, quality 74.8, speed score 81.6,
  94.80 tok/s (p95 106.67), reliability 100%, runtime 499.7 seconds.
- Suites: toolcall 80.0; coding 77.1; dataextract 60.3; instructfollow 81.1;
  reasonmath 73.3.
- Core result: `/home/christina/.bench-loop/runs/20260827-181117-qwen3.8-27b-unleashed-q3-local-openai_compat/run.json`
- Versus original control: overall +1.5, quality -3.1, generation +54.48 tok/s
  (+135.1%), runtime -61.5%. Versus E03: overall -2.1, quality -4.6,
  generation +25.00 tok/s (+35.8%).
- Decision: fails the normal 76.9 quality floor. Retain only as an explicit
  maximum-throughput option, not a balanced finalist. Proceed to Q5 to test
  whether higher precision recovers quality while DFlash retains enough speed.
- Q5 artifact: `Qwen3.8-27B-Unleashed-UD-Q5_K_M.gguf`, 19,772,245,856 bytes,
  SHA-256 `9c49503acd6468666dc5f3a30e2a68ba002e85542b1335ac2a05651a936de12e`;
  local hash exactly matches Hugging Face LFS metadata.
- Q5 DFlash depth-6 speed screen at 65,536 context with Q8 KV: 9/9 passed,
  69.69 tok/s, speed score 77.7, p95 84.63, runtime 68.8 seconds. Result:
  `/home/christina/.bench-loop/runs/20260827-184308-qwen3.8-27b-unleashed-q5-local-openai_compat/run.json`
- Context note: 64K/Q8 is intentionally a distinct capacity point. The larger
  19.77 GB target leaves insufficient margin for an apples-to-apples 262K/Q8
  target+draft configuration on 32 GB; full-context testing will use Q4 KV and
  be labeled separately. Screen depth 5 before selecting the Q5 core recipe.
- Q5 DFlash depth-5 speed screen at 65,536 context/Q8 KV: 9/9 passed,
  75.99 tok/s, speed score 78.9, p95 90.50, runtime 66.0 seconds. Result:
  `/home/christina/.bench-loop/runs/20260827-184522-qwen3.8-27b-unleashed-q5-local-openai_compat/run.json`
- Depth decision: depth 5 improves generation by 6.30 tok/s (+9.0%) and the
  speed score by 1.2 over depth 6. Promote depth 5 to full core to measure
  whether Q5 quality recovery offsets its lower throughput than Q4 DFlash.
- Q5 depth-5 full core at 65,536 context/Q8 KV: overall 80.6, quality 79.6,
  speed score 79.5, 78.53 tok/s (p95 105.12), reliability 100%, runtime 600.5
  seconds. Suites: toolcall 86.7; coding 75.0; dataextract 80.0;
  instructfollow 87.8; reasonmath 73.3. Result:
  `/home/christina/.bench-loop/runs/20260827-185537-qwen3.8-27b-unleashed-q5-local-openai_compat/run.json`
- Versus E03 Q4 native MTP trial 1: overall +0.7, quality +0.2, generation
  +8.73 tok/s (+12.5%), and runtime -44.0 seconds. Versus E10 Q4 DFlash:
  overall +1.3, quality +2.4, generation -0.33 tok/s (-0.4%), runtime +77.3
  seconds. Q5 gains 17.4 points in data extraction over E10 while losing 2.1
  coding, 3.7 instruction following, and 3.7 reason/math.
- Decision: new aggregate/Pareto leader at 64K, subject to repeat stability and
  an explicit capacity qualification. Test 262K with Q4 KV next; do not imply
  that the 64K/Q8 result provides the 262K capacity of the Q4 finalists.
- Q5 depth-5 full-context screen at 262,144 context/Q4 KV: 9/9 passed,
  72.85 tok/s, speed score 78.2, p95 87.60, runtime 63.5 seconds. Result:
  `/home/christina/.bench-loop/runs/20260827-185750-qwen3.8-27b-unleashed-q5-local-openai_compat/run.json`
- Capacity cost: -5.68 tok/s (-7.2%) versus the 64K/Q8 full-core generation
  rate and -3.14 tok/s (-4.1%) versus its speed screen. Promote to core because
  Q4 KV may change output quality and this is the maximum-context Q5 recipe.
- Q5 depth-5 full core at 262,144 context/Q4 KV: overall 76.9, quality 74.3,
  speed score 79.5, 72.66 tok/s (p95 98.06), reliability 100%, runtime 618.3
  seconds. Suites: toolcall 86.7; coding 58.3; dataextract 79.1;
  instructfollow 81.1; reasonmath 73.3. Result:
  `/home/christina/.bench-loop/runs/20260827-190825-qwen3.8-27b-unleashed-q5-local-openai_compat/run.json`
- Decision: reject 262K/Q4 KV. Versus 64K/Q8, quality falls 5.3 points,
  coding -16.7 and instruction following -6.7, while generation falls 5.87
  tok/s. Test the largest feasible Q8-KV midpoint, beginning at 128K, before
  finalizing Q5's capacity recommendation.
- Q5 depth-5 128K/Q8-KV speed screen: the configuration fits on the 5090 and
  passes 9/9 at 78.82 tok/s, speed score 79.3, p95 92.19, runtime 63.1 seconds.
  Result: `/home/christina/.bench-loop/runs/20260827-191035-qwen3.8-27b-unleashed-q5-local-openai_compat/run.json`
- Decision: promote 128K/Q8 to core. Its screen is within measurement noise of
  the 64K winner and offers twice the context without KV precision reduction.
- Q5 depth-5 full core at 131,072 context/Q8 KV: overall 80.6, quality 79.6,
  speed score 79.7, 74.17 tok/s (p95 95.93), reliability 100%, runtime 553.4
  seconds. Suites exactly match 64K/Q8: toolcall 86.7; coding 75.0;
  dataextract 80.0; instructfollow 87.8; reasonmath 73.3. Result:
  `/home/christina/.bench-loop/runs/20260827-192005-qwen3.8-27b-unleashed-q5-local-openai_compat/run.json`
- Decision: 128K/Q8 replaces 64K/Q8 as the practical Q5 leader. It doubles
  capacity with identical measured quality and a better aggregate speed score;
  generation is 4.36 tok/s lower in this core trial, so repeat variance must be
  measured. Probe one higher Q8 context boundary before locking capacity.
- Capacity probes: 160K/Q8 loaded at 29,549 MiB GPU memory with 2,639 MiB free;
  192K/Q8 loaded at 30,797 MiB with 1,391 MiB free. Stop at 192K as the
  operational ceiling rather than consuming nearly all headroom at 224K.
- Q5 depth-5 192K/Q8 speed screen: 9/9 passed, 81.42 tok/s, speed score 80.1,
  p95 95.94, runtime 63.2 seconds. Result:
  `/home/christina/.bench-loop/runs/20260827-192326-qwen3.8-27b-unleashed-q5-local-openai_compat/run.json`
- Decision: promote 192K/Q8 to core; it is the best Q5 speed screen and retains
  1.4 GB measured VRAM headroom.
- Q5 depth-5 full core at 196,608 context/Q8 KV: overall 80.6, quality 79.6,
  speed score 79.7, 75.75 tok/s (p95 94.99), reliability 100%, runtime 556.3
  seconds. Suites again exactly match 64K and 128K Q8: toolcall 86.7; coding
  75.0; dataextract 80.0; instructfollow 87.8; reasonmath 73.3. Result:
  `/home/christina/.bench-loop/runs/20260827-193303-qwen3.8-27b-unleashed-q5-local-openai_compat/run.json`
- Decision: retain 192K/Q8 as the Q5 DFlash capacity leader. Quality has now
  reproduced exactly at three Q8 context sizes, isolating the 262K regression
  to Q4 KV rather than context length. Test Q5 native MTP at 262K/Q8 next;
  removing the external draft may recover enough VRAM for full precision KV.

## E12 — Unleashed Q3 with native MTP depth 3

- Status: complete; rejected
- Hypothesis: Q4 native MTP produced a substantially better quality path than
  DFlash. Test whether the same backend/model interaction recovers Q3 quality
  while retaining useful quantized throughput.
- Speed suite: 9/9 passed, 78.64 tok/s, speed score 79.0, p95 90.03, runtime
  62.1 seconds.
- Result: `/home/christina/.bench-loop/runs/20260827-181404-qwen3.8-27b-unleashed-q3-local-openai_compat/run.json`
- Comparison: -16.50 tok/s (-17.3%) versus Q3+DFlash depth 5 and -0.22 tok/s
  versus E10's full-core generation rate. Promote only to test the strong
  quality-recovery hypothesis; it cannot win as a pure speed configuration.
- Full core: overall 77.6, quality 75.0, speed score 80.4, 84.45 tok/s (p95
  95.24), reliability 100%, runtime 666.9 seconds.
- Suites: toolcall 80.0; coding 75.0; dataextract 64.8; instructfollow 81.1;
  reasonmath 73.3.
- Core result: `/home/christina/.bench-loop/runs/20260827-182532-qwen3.8-27b-unleashed-q3-local-openai_compat/run.json`
- Versus Q3+DFlash: overall -0.2, quality +0.2, generation -10.35 tok/s,
  runtime +167.2 seconds. Extraction improves +4.5, coding falls -2.1, and
  other quality suites are unchanged.
- Decision: reject. The 0.2 aggregate-quality recovery does not justify the
  10.9% throughput loss or 33.5% runtime increase. Q3+DFlash remains the Q3
  speed option; neither Q3 configuration meets the normal quality floor.

## E13 — Unleashed Q5 with native MTP depth 3

- Status: complete; rejected
- Recipe: 262,144 context, Q8 KV, native MTP depth 3, no external draft. It
  loaded at 31,559 MiB GPU memory with 629 MiB free.
- Speed screen: 9/9 passed, 55.76 tok/s, speed score 74.5, p95 73.36, runtime
  83.8 seconds. Result:
  `/home/christina/.bench-loop/runs/20260827-193546-qwen3.8-27b-unleashed-q5-local-openai_compat/run.json`
- Decision: cannot win on speed (-26.1% versus 192K Q5 DFlash core), but run
  one core trial because Q4 native MTP demonstrated a materially different,
  higher-quality output path and this preserves full 262K context with Q8 KV.
- Full core: overall 78.0, quality 77.4, speed score 75.4, 64.17 tok/s (p95
  72.04), reliability 100%, runtime 813.7 seconds. Suites: toolcall 90.0;
  coding 66.7; dataextract 72.7; instructfollow 90.0; reasonmath 73.3. Result:
  `/home/christina/.bench-loop/runs/20260827-194938-qwen3.8-27b-unleashed-q5-local-openai_compat/run.json`
- Decision: reject. Versus 192K Q5 DFlash it is -2.6 overall, -2.2 quality,
  -11.58 tok/s, and +257.4 seconds runtime. Tool calling +3.3 and instruction
  following +2.2 do not offset coding -8.3 and extraction -7.3.
