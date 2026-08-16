from __future__ import annotations

import asyncio

from bench_loop.suites.longcontext import LongContextSuite


def test_longcontext_fixtures_expand_deterministically() -> None:
    suite = LongContextSuite()
    first = asyncio.run(suite.load_tasks())
    second = asyncio.run(suite.load_tasks())

    assert [task.id for task in first] == [task.id for task in second]
    assert len(first) == 4
    for left, right in zip(first, second, strict=True):
        left_prompt = left.messages[0]["content"]
        right_prompt = right.messages[0]["content"]
        expected = left.validation["expected"]
        assert left_prompt == right_prompt
        assert "{{CONTEXT}}" not in left_prompt
        assert left_prompt.count(expected) == 1
        assert (
            left.metadata["generated_context_chars"]
            >= left.metadata["target_context_tokens"] * 4
        )


def test_longcontext_scorer_records_context_metadata() -> None:
    suite = LongContextSuite()
    task = asyncio.run(suite.load_tasks())[0]
    result = suite.evaluate(
        task,
        {
            "content": f"The code is {task.validation['expected']}",
            "tokens_prompt": 2100,
            "tokens_generated": 8,
            "total_ms": 100,
        },
    )
    assert result.passed is True
    assert result.score == 100
    assert result.metadata["provider_prompt_tokens"] == 2100
