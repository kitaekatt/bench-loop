# Local Qwen Optimization

Read [PLAN.md](PLAN.md) before running, changing, or interpreting experiments in
this directory.

This workspace exists to find a Pareto improvement over the recorded control:
quality must be maintained or improved, speed must be maintained or improved,
and reliability must remain 100%. Update `PLAN.md` and `RESULTS.md` immediately
after every completed experiment, including failures and invalid runs. Preserve
the exact model, runtime, flags, harness, profile, result path, and relevant
observations so another session can continue without reconstructing context.

Change one major variable at a time during screening. Do not describe a faster
run as an improvement if quality or reliability regresses. Do not publish an
experimental run unless the user explicitly requests publication.

