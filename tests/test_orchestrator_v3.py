from __future__ import annotations

import asyncio

from bench_loop.runner import orchestrator


class _FakeProvider:
    calls = 0
    requests: list[dict] = []

    @staticmethod
    async def list_models(_endpoint: str) -> list[str]:
        return ["fake-model"]

    @staticmethod
    async def get_system_info(endpoint: str) -> dict:
        return {"endpoint": endpoint}

    @classmethod
    async def chat(cls, **kwargs) -> dict:
        cls.calls += 1
        cls.requests.append(kwargs)
        return {
            "content": "benchmark output",
            "tokens_prompt": 20,
            "tokens_generated": 40,
            "ttft_ms": 25,
            "total_ms": 1000,
            "generation_tok_per_sec": 42,
            "prompt_eval_tok_per_sec": 200,
        }


def test_orchestrator_stamps_provenance_and_trial_distribution(monkeypatch) -> None:
    _FakeProvider.calls = 0
    _FakeProvider.requests = []
    monkeypatch.setitem(orchestrator.PROVIDER_REGISTRY, "fake", _FakeProvider)
    run = asyncio.run(
        orchestrator.run_benchmark(
            model="fake-model",
            endpoint="http://100.95.10.4:8080",
            provider="fake",
            suites=["speed"],
            profile="core",
            runs=2,
            remote=False,
        )
    )

    assert run.benchmark_version == "3.0.0"
    assert run.score_schema_version == "3.0.0"
    assert run.benchmark_profile == "custom"
    assert run.coverage_score == 20.0
    assert run.comparable is False
    assert run.manifest_hash.startswith("sha256:")
    assert run.is_remote is False
    assert run.speed_metrics.generation_tok_per_sec == 42
    assert run.speed_metrics.generation_tok_per_sec_p95 == 42
    assert run.speed_metrics.sample_count == 9
    assert run.reliability_score == 100
    # One global warmup + two trials for each of nine speed prompts.
    assert _FakeProvider.calls == 19
    for task in run.suites["speed"].tasks:
        assert task.metadata["warmup_dropped"] is True
        assert len(task.metadata["trials"]) == 2
        assert task.metadata["speed_mode"] == "local"


def test_quality_token_override_never_changes_speed_fixture_caps(monkeypatch) -> None:
    _FakeProvider.calls = 0
    _FakeProvider.requests = []
    monkeypatch.setitem(orchestrator.PROVIDER_REGISTRY, "fake", _FakeProvider)

    asyncio.run(
        orchestrator.run_benchmark(
            model="fake-model",
            endpoint="http://localhost:8080",
            provider="fake",
            suites=["speed"],
            runs=1,
            max_tokens=8192,
            remote=False,
        )
    )

    # The first call is the global warmup. Every subsequent call must retain
    # the speed task's own small generation cap instead of the quality override.
    speed_caps = [request["max_tokens"] for request in _FakeProvider.requests[1:]]
    assert speed_caps == [32, 48, 64, 160, 160, 160, 384, 384, 384]
