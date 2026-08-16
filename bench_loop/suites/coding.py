"""Coding suite execution and evaluation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bench_loop.config import TASKS_DIR
from bench_loop.models import BenchmarkTask, TaskResult
from bench_loop.sandbox import run_restricted_python
from bench_loop.suites.base import BenchmarkSuite

CODE_BLOCK_RE = re.compile(r"```python\s*(.*?)```", re.DOTALL | re.IGNORECASE)
GENERIC_BLOCK_RE = re.compile(r"```\s*(.*?)```", re.DOTALL)


class CodingSuite(BenchmarkSuite):
    name = "coding"
    task_file = Path(TASKS_DIR) / "coding" / "tasks.yaml"

    def _extract_code(self, response_text: str) -> str:
        match = CODE_BLOCK_RE.search(response_text)
        if match:
            return match.group(1).strip()
        match = GENERIC_BLOCK_RE.search(response_text)
        if match:
            return match.group(1).strip()
        return response_text.strip()

    def evaluate(self, task: BenchmarkTask, response: dict[str, Any]) -> TaskResult:
        response_text = str(response.get("content") or "")
        code = self._extract_code(response_text)
        test_code = str(task.validation.get("test_code") or "")
        if not code:
            return self.build_result(
                task=task,
                passed=False,
                score=0.0,
                response=response,
                output=response_text,
                error="No code found in model response",
                metadata={"evaluation_status": "missing_code"},
            )

        try:
            compile(code, f"<{task.id}>", "exec")
        except SyntaxError as exc:
            return self.build_result(
                task=task,
                passed=False,
                score=0.0,
                response=response,
                output=code,
                error=f"SyntaxError: {exc.msg} (line {exc.lineno})",
                metadata={"evaluation_status": "syntax_error"},
            )

        sandbox_result = run_restricted_python(code, test_code, timeout_sec=10.0)
        stdout = sandbox_result.stdout
        stderr = sandbox_result.stderr

        if sandbox_result.rejected:
            passed = False
            score = 0.0
            error = f"Sandbox policy rejected code: {sandbox_result.rejection_reason}"
            status = "sandbox_policy_rejected"
        elif sandbox_result.returncode == 0 and "PASS" in stdout:
            passed = True
            score = 100.0
            error = ""
            status = "all_tests_passed"
        else:
            passed = False
            score = 25.0
            status = "tests_failed_or_runtime_error"
            combined_error = stderr.strip() or stdout.strip() or ""
            if sandbox_result.timed_out:
                error = stderr
            elif "SyntaxError" in combined_error:
                score = 0.0
                status = "syntax_error"
                error = combined_error
            elif sandbox_result.returncode != 0:
                error = combined_error or f"exit code {sandbox_result.returncode}"
            else:
                error = combined_error or "Tests did not report PASS"

        return self.build_result(
            task=task,
            passed=passed,
            score=score,
            response=response,
            output=code,
            error=error,
            metadata={
                "stdout": stdout,
                "stderr": stderr,
                "evaluation_status": status,
                "execution_mode": "restricted_python",
                "policy_rejected": sandbox_result.rejected,
                "timed_out": sandbox_result.timed_out,
            },
        )
