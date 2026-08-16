# BenchLoop Benchmark Specification v3

BenchLoop v3 makes benchmark results identifiable and reproducible. A result is
not just a score: it records the benchmark version, score schema, named profile,
coverage, and a SHA-256 manifest of every prompt, generation setting, and
validator used in the run.

## Profiles

| Profile | Suites | Tasks | Intended use |
|---|---|---:|---|
| `smoke` | speed, toolcall, reasonmath | 39 | Endpoint and quality sanity check |
| `core` | speed, toolcall, coding, dataextract, instructfollow, reasonmath | 81 | Default comparable daily-driver run |
| `full` | core + longcontext + agent | 93 | Capability audit including 2K–32K retrieval and multi-turn tools |

Supplying `--suites` creates a `custom` run unless the suite set exactly matches
a named profile. Custom and partial runs retain their component scores but are
marked `comparable=false`; they must not be presented as complete profile runs.

## Provenance fields

Each `run.json` includes:

- `benchmark_id` and `benchmark_version`
- `benchmark_profile` and `requested_profile`
- `score_schema_version`
- `manifest_hash`
- `coverage_score` and `comparable`

Scores should only be compared directly when benchmark version, score schema,
profile, and manifest hash match. Harness, provider mode, sampling settings, and
hardware must remain visible dimensions of the comparison.

## Scoring

Quality uses fixed, declared weights instead of changing every time a suite is
added or removed. Core weights are:

| Suite | Weight |
|---|---:|
| toolcall | 20% |
| coding | 25% |
| dataextract | 15% |
| instructfollow | 15% |
| reasonmath | 25% |

Full gives agent 20% and long-context 15%, with the remaining 65% distributed
across the core quality domains as declared in `benchmark_manifest.py`.

The v3 composite is:

```text
overall = 0.70 × quality + 0.25 × speed + 0.05 × reliability
```

When no speed suite is present:

```text
overall = 0.90 × quality + 0.10 × reliability
```

Reliability means provider/runtime execution success. It is intentionally not
the task pass rate; task correctness is already represented by quality and must
not be counted twice.

## Speed protocol

- Each speed prompt runs three trials by default (`--trials` changes this).
- Trial 1 is warmup when more than one trial is requested.
- The representative post-warmup trial is the median-scoring trial.
- Run-level throughput and latency are medians; p50/p95 and sample count are
  persisted alongside the headline values.
- Local and remote/cloud curves are selected from explicit run mode. Timing
  fields returned by a local engine never silently switch the scoring curve.
- The speed fixtures vary output length. Long-context prefill and retrieval are
  measured separately by the `longcontext` suite.

## Long-context protocol

The full profile performs deterministic needle retrieval at approximate 2K,
8K, 16K, and 32K context tiers and records both target size and provider-reported
prompt tokens. Approximate tiers are used because tokenization differs across
model families. The exact generated context is included in the manifest hash.

## Generated-code execution

Coding responses are never run as unrestricted host Python. The evaluator:

- parses the AST and blocks non-allowlisted imports, filesystem/process/network
  primitives, private reflection, and dynamic-code builtins;
- executes with reduced builtins and an import allowlist;
- uses isolated interpreter flags, a fresh temporary working directory, a
  minimal environment, wall-clock timeout, output cap, and POSIX resource caps.

This is defense in depth for local benchmark fixtures, not a general hostile
multi-tenant security boundary. A public BenchLoop worker should additionally
run inside a disposable VM or container.

## Known limits

The fixtures and deterministic validators are public, so v3 is a reproducible
engineering benchmark rather than a secret contamination-proof evaluation.
Vision, energy-per-token, peak GPU memory, and seeded private challenge sets are
recommended future profile additions. They should receive new benchmark and
score-schema versions instead of changing historical scores in place.
