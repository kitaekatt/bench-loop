"""Deterministic long-context retrieval suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bench_loop.config import TASKS_DIR
from bench_loop.models import BenchmarkTask, TaskResult
from bench_loop.suites.base import BenchmarkSuite


class LongContextSuite(BenchmarkSuite):
    """Needle retrieval at several approximate prompt-token tiers.

    Tokenizers differ, so the fixture declares an approximate target and each
    result also records the provider-reported prompt-token count when present.
    """

    name = "longcontext"
    task_file = Path(TASKS_DIR) / "longcontext" / "tasks.yaml"

    async def load_tasks(self) -> list[BenchmarkTask]:
        tasks = await super().load_tasks()
        for task in tasks:
            target_tokens = int(task.metadata.get("target_context_tokens") or 0)
            needle = str(task.validation.get("expected") or "")
            position = float(task.metadata.get("needle_position") or 0.5)
            context = self._generate_context(target_tokens, needle, position)
            for message in task.messages:
                message["content"] = message["content"].replace("{{CONTEXT}}", context)
            task.metadata["generated_context_chars"] = len(context)
        return tasks

    @staticmethod
    def _generate_context(target_tokens: int, needle: str, position: float) -> str:
        target_chars = max(1_000, target_tokens * 4)
        lines: list[str] = []
        index = 0
        generated_chars = 0
        while generated_chars < target_chars:
            checksum = (index * 7919 + 104729) % 1_000_003
            line = (
                f"Archive entry {index:05d}: routine telemetry was nominal; "
                f"the unrelated checksum was {checksum:06d}."
            )
            lines.append(line)
            generated_chars += len(line) + 1
            index += 1
        insertion = min(len(lines), max(0, round(len(lines) * position)))
        lines.insert(
            insertion,
            f"AUTHORITATIVE RECORD: Project Aurora's access code is {needle}. "
            "This record supersedes all unrelated checksums.",
        )
        return "\n".join(lines)

    def evaluate(self, task: BenchmarkTask, response: dict[str, Any]) -> TaskResult:
        output = self.response_text(response).strip()
        expected = str(task.validation.get("expected") or "")
        passed = bool(expected) and expected.casefold() in output.casefold()
        return self.build_result(
            task=task,
            passed=passed,
            score=100.0 if passed else 0.0,
            response=response,
            output=output,
            error="" if passed else "Expected access code was not recovered",
            metadata={
                "target_context_tokens": int(
                    task.metadata.get("target_context_tokens") or 0
                ),
                "generated_context_chars": int(
                    task.metadata.get("generated_context_chars") or 0
                ),
                "needle_position": float(task.metadata.get("needle_position") or 0.0),
                "provider_prompt_tokens": int(response.get("tokens_prompt") or 0),
            },
        )
