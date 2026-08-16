from __future__ import annotations

import asyncio

from bench_loop.models import BenchmarkTask
from bench_loop.suites.agent import AgentSuite


class _TwoTurnProvider:
    calls = 0

    @classmethod
    async def chat(cls, **_kwargs):
        cls.calls += 1
        if cls.calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression": "2+2"}',
                        }
                    }
                ],
                "total_ms": 100,
                "tokens_generated": 3,
                "tokens_prompt": 10,
            }
        return {
            "content": "4",
            "tool_calls": [],
            "total_ms": 200,
            "tokens_generated": 2,
            "tokens_prompt": 20,
        }


class _ErrorProvider:
    @staticmethod
    async def chat(**_kwargs):
        return {"content": "", "error": "endpoint unavailable", "total_ms": 50}


def _task() -> BenchmarkTask:
    return BenchmarkTask(
        id="agent-telemetry",
        suite="agent",
        messages=[{"role": "user", "content": "Calculate 2+2."}],
        validation={
            "max_turns": 3,
            "tools": ["calculator"],
            "must_call": [{"name": "calculator", "args_contains": {}}],
            "expected_contains": ["4"],
        },
    )


def test_agent_accumulates_metrics_across_model_turns() -> None:
    _TwoTurnProvider.calls = 0
    result = asyncio.run(
        AgentSuite().run_task(
            _TwoTurnProvider,
            "http://localhost",
            "test-model",
            _task(),
            provider_name="openai_compat",
        )
    )
    assert result.passed is True
    assert result.execution_ok is True
    assert result.latency_ms == 300
    assert result.tokens_generated == 5
    assert result.tokens_prompt == 30
    assert result.metadata["model_turns"] == 2


def test_agent_provider_failure_is_a_reliability_failure() -> None:
    result = asyncio.run(
        AgentSuite().run_task(
            _ErrorProvider,
            "http://localhost",
            "test-model",
            _task(),
        )
    )
    assert result.execution_ok is False
    assert result.metadata["stop_reason"] == "provider_error"
    assert result.metadata["provider_errors"] == ["endpoint unavailable"]
