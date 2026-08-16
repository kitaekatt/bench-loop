from __future__ import annotations

import math

from bench_loop.models import BenchmarkTask
from bench_loop.runner.orchestrator import _percentile
from bench_loop.suites.speed import SpeedSuite


def _task() -> BenchmarkTask:
    return BenchmarkTask(id="speed-test", suite="speed", messages=[])


def _response(*, remote: bool) -> dict:
    return {
        "content": "ok",
        "generation_tok_per_sec": 30.0,
        "prompt_eval_tok_per_sec": 100.0,
        "ttft_ms": 2000.0,
        "total_ms": 3000.0,
        "_benchloop_remote": remote,
    }


def test_local_timing_is_never_inferred_as_cloud() -> None:
    result = SpeedSuite().evaluate(_task(), _response(remote=False))
    expected = 12.54 * math.log2(30.0) + 0.9
    assert result.score == round(expected, 2)
    assert result.metadata["speed_mode"] == "local"


def test_remote_mode_uses_cloud_curve_explicitly() -> None:
    result = SpeedSuite().evaluate(_task(), _response(remote=True))
    assert result.metadata["speed_mode"] == "remote"
    assert result.score != SpeedSuite().evaluate(_task(), _response(remote=False)).score


def test_percentiles_are_deterministic_for_short_runs() -> None:
    assert _percentile([], 0.95) == 0.0
    assert _percentile([10], 0.95) == 10
    assert _percentile([10, 20, 30], 0.5) == 20
    assert _percentile([10, 20, 30], 0.95) == 29
