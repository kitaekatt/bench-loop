from __future__ import annotations

import asyncio

from bench_loop.models import BenchmarkTask
from bench_loop.suites.dataextract import DataExtractSuite
from bench_loop.suites.instructfollow import InstructFollowSuite
from bench_loop.suites.reasonmath import ReasonMathSuite
from bench_loop.suites.toolcall import ToolCallSuite


def _task(task_id: str, suite: str, *, validation: dict | None = None) -> BenchmarkTask:
    return BenchmarkTask(
        id=task_id,
        suite=suite,
        messages=[],
        validation=validation or {},
    )


def _call(name: str, arguments: dict) -> dict:
    return {"function": {"name": name, "arguments": arguments}}


def test_toolcall_multi_call_golden_scores() -> None:
    task = _task("tc-09", "toolcall")
    complete = ToolCallSuite().evaluate(
        task,
        {
            "content": "",
            "tool_calls": [
                _call("get_weather", {"location": "London"}),
                _call("get_stock_price", {"ticker": "MSFT"}),
            ],
        },
    )
    partial = ToolCallSuite().evaluate(
        task,
        {"content": "", "tool_calls": [_call("get_weather", {"location": "London"})]},
    )
    assert complete.score == 100
    assert complete.passed is True
    assert partial.score == 50
    assert partial.passed is False


def test_dataextract_atomic_field_golden_scores() -> None:
    task = _task(
        "de-golden",
        "dataextract",
        validation={"expected": {"name": "Ada", "age": 36}, "scenario_id": "DE-GOLDEN"},
    )
    exact = DataExtractSuite().evaluate(task, {"content": '{"name":"Ada","age":36}'})
    partial = DataExtractSuite().evaluate(task, {"content": '{"name":"Ada","age":99}'})
    invalid = DataExtractSuite().evaluate(task, {"content": "not json"})
    assert exact.score == 100
    assert partial.score == 50
    assert invalid.score == 0


def test_dataextract_recovers_json_without_relaxing_field_scoring() -> None:
    task = _task(
        "de-golden",
        "dataextract",
        validation={"expected": {"name": "Ada", "age": 36}, "scenario_id": "DE-GOLDEN"},
    )
    fenced = DataExtractSuite().evaluate(
        task,
        {"content": 'Result:\n```json\n{"name":"Ada","age":36}\n```'},
    )
    prose_wrapped = DataExtractSuite().evaluate(
        task,
        {"content": 'The extracted record is {"name":"Ada","age":99}.'},
    )

    assert fenced.score == 100
    assert fenced.metadata["json_extraction_method"] == "fenced"
    assert prose_wrapped.score == 50
    assert prose_wrapped.metadata["json_extraction_method"] == "bracket_scan"


def test_instruction_following_golden_scores() -> None:
    task = _task("if-02", "instructfollow")
    exact = InstructFollowSuite().evaluate(
        task,
        {"content": "Oceans cover Earth\nWaves shape rocky shores\nCurrents move heat"},
    )
    partial = InstructFollowSuite().evaluate(
        task,
        {"content": "Oceans cover Earth\nWaves shape shores\nCurrents move heat"},
    )
    assert exact.score == 100
    assert partial.score == 50


def test_reasonmath_pair_golden_scores() -> None:
    task = _task("rm-03", "reasonmath")
    exact = ReasonMathSuite().evaluate(
        task,
        {
            "content": "Calculation complete.\nANSWER: new_original_price=100; saved_money=yes"
        },
    )
    partial = ReasonMathSuite().evaluate(
        task,
        {"content": "ANSWER: new_original_price=100; saved_money=no"},
    )
    assert exact.score == 100
    assert partial.score == 50


def test_provider_error_is_separate_from_quality_failure() -> None:
    task = _task("if-02", "instructfollow")
    result = InstructFollowSuite().evaluate(
        task,
        {"content": "", "error": "HTTP 500 from endpoint"},
    )
    assert result.passed is False
    assert result.execution_ok is False
    assert result.metadata["provider_error"] == "HTTP 500 from endpoint"


def test_raised_provider_error_becomes_a_task_reliability_failure() -> None:
    class RaisingProvider:
        @staticmethod
        async def chat(**_kwargs):
            raise TimeoutError("endpoint stalled")

    task = _task("if-02", "instructfollow")
    result = asyncio.run(
        InstructFollowSuite().run_task(
            RaisingProvider,
            "http://localhost",
            "test-model",
            task,
        )
    )
    assert result.execution_ok is False
    assert "TimeoutError" in result.metadata["provider_error"]
