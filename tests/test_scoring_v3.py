from __future__ import annotations

from bench_loop.models import BenchmarkRun, SpeedMetrics, SuiteResult, TaskResult


def _suite(
    name: str, score: float, *, passed: bool = False, execution_ok: bool = True
) -> SuiteResult:
    task = TaskResult(
        task_id=f"{name}-1",
        suite=name,
        passed=passed,
        score=score,
        execution_ok=execution_ok,
    )
    return SuiteResult(
        suite=name,
        score=score,
        task_count=1,
        pass_count=int(passed),
        fail_count=int(not passed),
        tasks=[task],
    )


def test_v3_weighted_quality_and_execution_reliability() -> None:
    run = BenchmarkRun(
        requested_profile="core",
        speed_metrics=SpeedMetrics(generation_tok_per_sec=50),
        suites={
            "speed": _suite("speed", 70),
            "toolcall": _suite("toolcall", 80),
            "coding": _suite("coding", 60),
            "dataextract": _suite("dataextract", 100),
            "instructfollow": _suite("instructfollow", 40),
            "reasonmath": _suite("reasonmath", 20, execution_ok=False),
        },
    )
    run.compute_aggregates()

    assert run.quality_score == 57.0
    # Correctness failures do not masquerade as transport/runtime failures.
    assert run.reliability_score == 83.33
    assert run.speed_score == 70.0
    assert run.overall_score == 61.57


def test_missing_speed_uses_quality_reliability_formula() -> None:
    run = BenchmarkRun(
        requested_profile="smoke",
        suites={
            "toolcall": _suite("toolcall", 100, passed=True),
            "reasonmath": _suite("reasonmath", 0, passed=False),
        },
    )
    run.compute_aggregates()
    assert run.quality_score == 45.0
    assert run.reliability_score == 100.0
    assert run.overall_score == 50.5
