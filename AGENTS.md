# BenchLoop Working Context

The active ongoing effort in this repository is local Qwen optimization on an
NVIDIA RTX 5090. The objective is to find a configuration that maintains or
improves both model quality and generation speed relative to the recorded
Qwen3.8-27B control, while keeping reliability at 100%.

Before doing optimization work, read and follow:

1. [`local-optimization/AGENTS.md`](local-optimization/AGENTS.md) for operating
   instructions.
2. [`local-optimization/PLAN.md`](local-optimization/PLAN.md) for the control,
   acceptance gates, experiment matrix, and current status.
3. [`local-optimization/RESULTS.md`](local-optimization/RESULTS.md) for completed
   and active experiment records.

This is a persistent, evidence-driven experiment program. Update the plan and
results immediately after each experiment completes, including failed or
invalid runs. Do not optimize for peak tokens/second at the expense of quality,
reliability, structured output, code, or tool-call correctness.

