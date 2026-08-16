from __future__ import annotations

import pytest

from bench_loop.sandbox import run_restricted_python, validate_python


def test_restricted_python_runs_valid_fixture_code() -> None:
    result = run_restricted_python(
        """
import csv
def parse_csv(text):
    rows = csv.DictReader(text.splitlines())
    return list(rows)
""",
        """
assert parse_csv('name,age\\nAda,36\\n') == [{'name': 'Ada', 'age': '36'}]
print('PASS')
""",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PASS"


@pytest.mark.parametrize(
    "code, expected",
    [
        ("open('/tmp/escape', 'w')", "builtin 'open'"),
        ("import socket", "import 'socket'"),
        ("getattr(object, '__subclasses__')()", "builtin 'getattr'"),
        (
            "import collections\ncollections._sys.modules",
            "private attribute access '_sys'",
        ),
        ("from dataclasses import sys\nsys.modules", "unsafe import 'sys'"),
        ("import enum\nenum.bltns.open('escape', 'w')", "attribute access 'bltns'"),
    ],
)
def test_policy_rejects_host_escape_primitives(code: str, expected: str) -> None:
    violations = validate_python(code)
    assert any(expected in violation for violation in violations)
    result = run_restricted_python(code, "print('PASS')")
    assert result.rejected is True
    assert result.returncode is None


def test_private_instance_state_remains_available() -> None:
    result = run_restricted_python(
        """
class Counter:
    def __init__(self):
        self._value = 0
    def increment(self):
        self._value += 1
        return self._value
""",
        "assert Counter().increment() == 1\nprint('PASS')",
    )
    assert result.returncode == 0, result.stderr
