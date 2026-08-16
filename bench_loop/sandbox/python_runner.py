"""Restricted execution for model-generated Python.

Generated code is parsed before execution, receives a reduced builtin set and
an import allowlist, runs in an isolated interpreter and temporary directory,
and is subject to wall-clock and OS resource limits where available.

This is defense in depth for benchmark fixtures, not a general multi-tenant
container boundary. Public deployments should still run the BenchLoop worker
inside a disposable VM or container.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ALLOWED_IMPORTS = frozenset(
    {
        "collections",
        "csv",
        "dataclasses",
        "decimal",
        "enum",
        "functools",
        "heapq",
        "itertools",
        "json",
        "math",
        "re",
        "statistics",
        "string",
        "time",
        "typing",
    }
)
DANGEROUS_NAMES = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "help",
        "input",
        "locals",
        "memoryview",
        "open",
        "os",
        "pathlib",
        "setattr",
        "socket",
        "subprocess",
        "sys",
        "vars",
    }
)
FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "bltns",
        "builtins",
        "ctypes",
        "modules",
        "os",
        "pathlib",
        "socket",
        "subprocess",
        "sys",
    }
)
MAX_OUTPUT_BYTES = 64 * 1024


@dataclass(frozen=True)
class SandboxResult:
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    rejected: bool = False
    rejection_reason: str = ""


class _PolicyValidator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[str] = []

    def _reject(self, node: ast.AST, reason: str) -> None:
        line = getattr(node, "lineno", "?")
        self.violations.append(f"line {line}: {reason}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.partition(".")[0]
            if root not in ALLOWED_IMPORTS:
                self._reject(node, f"import {root!r} is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        root = (node.module or "").partition(".")[0]
        if node.level or root not in ALLOWED_IMPORTS:
            self._reject(node, f"import from {node.module!r} is not allowed")
        for alias in node.names:
            if alias.name.startswith("_") or alias.name in FORBIDDEN_ATTRIBUTES:
                self._reject(node, f"unsafe import {alias.name!r} is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        is_private_instance_state = (
            node.attr.startswith("_")
            and not node.attr.startswith("__")
            and isinstance(node.value, ast.Name)
            and node.value.id in {"self", "cls"}
        )
        if node.attr in FORBIDDEN_ATTRIBUTES:
            self._reject(node, f"attribute access {node.attr!r} is not allowed")
        elif node.attr.startswith("_") and not is_private_instance_state:
            self._reject(node, f"private attribute access {node.attr!r} is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in DANGEROUS_NAMES:
            self._reject(node, f"builtin {node.id!r} is not allowed")
        self.generic_visit(node)


def validate_python(code: str) -> list[str]:
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return []  # Syntax reporting remains the CodingSuite's responsibility.
    validator = _PolicyValidator()
    validator.visit(tree)
    return validator.violations


def run_restricted_python(
    model_code: str,
    test_code: str,
    *,
    timeout_sec: float = 10.0,
) -> SandboxResult:
    violations = validate_python(model_code)
    if violations:
        return SandboxResult(
            returncode=None,
            rejected=True,
            rejection_reason="; ".join(violations[:5]),
        )

    wrapper = _build_wrapper(model_code, test_code)
    with tempfile.TemporaryDirectory(prefix="bench-loop-coding-") as temp_dir:
        script_path = Path(temp_dir) / "runner.py"
        script_path.write_text(wrapper, encoding="utf-8")
        stdout_path = Path(temp_dir) / "stdout.txt"
        stderr_path = Path(temp_dir) / "stderr.txt"
        environment = {
            "PATH": os.defpath,
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        try:
            with (
                stdout_path.open("w", encoding="utf-8") as stdout_file,
                stderr_path.open("w", encoding="utf-8") as stderr_file,
            ):
                completed = subprocess.run(
                    [sys.executable, "-I", "-S", "-B", str(script_path)],
                    cwd=temp_dir,
                    env=environment,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    timeout=timeout_sec,
                    check=False,
                    preexec_fn=_resource_limits if os.name == "posix" else None,
                )
            return SandboxResult(
                returncode=completed.returncode,
                stdout=_read_limited(stdout_path),
                stderr=_read_limited(stderr_path),
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                returncode=None,
                stdout=_read_limited(stdout_path),
                stderr=f"Timed out after {timeout_sec:g}s",
                timed_out=True,
            )


def _read_limited(path: Path) -> str:
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(MAX_OUTPUT_BYTES)


def _resource_limits() -> None:
    import resource

    limits = [
        (resource.RLIMIT_CPU, 5),
        (resource.RLIMIT_FSIZE, MAX_OUTPUT_BYTES),
        (resource.RLIMIT_NOFILE, 32),
    ]
    if hasattr(resource, "RLIMIT_NPROC"):
        limits.append((resource.RLIMIT_NPROC, 16))
    # RLIMIT_AS is reliable on Linux; on macOS the interpreter reserves a
    # large virtual address space before user code starts.
    if sys.platform.startswith("linux") and hasattr(resource, "RLIMIT_AS"):
        limits.append((resource.RLIMIT_AS, 512 * 1024 * 1024))
    for kind, value in limits:
        try:
            resource.setrlimit(kind, (value, value))
        except (OSError, ValueError):
            continue


def _build_wrapper(model_code: str, test_code: str) -> str:
    allowed_imports = repr(sorted(ALLOWED_IMPORTS))
    safe_names = repr(
        [
            "ArithmeticError",
            "AssertionError",
            "AttributeError",
            "BaseException",
            "Exception",
            "IndexError",
            "KeyError",
            "LookupError",
            "NotImplementedError",
            "OverflowError",
            "RuntimeError",
            "StopIteration",
            "TypeError",
            "ValueError",
            "ZeroDivisionError",
            "__build_class__",
            "abs",
            "all",
            "any",
            "bin",
            "bool",
            "bytearray",
            "bytes",
            "callable",
            "chr",
            "classmethod",
            "complex",
            "dict",
            "divmod",
            "enumerate",
            "filter",
            "float",
            "format",
            "frozenset",
            "hash",
            "hex",
            "int",
            "isinstance",
            "issubclass",
            "iter",
            "len",
            "list",
            "map",
            "max",
            "min",
            "next",
            "object",
            "oct",
            "ord",
            "pow",
            "property",
            "range",
            "repr",
            "reversed",
            "round",
            "set",
            "slice",
            "sorted",
            "staticmethod",
            "str",
            "sum",
            "super",
            "tuple",
            "type",
            "zip",
        ]
    )
    return f"""\
import builtins as _builtins

_ALLOWED_IMPORTS = frozenset({allowed_imports})
_SAFE_NAMES = {safe_names}
_real_import = _builtins.__import__
_module_type = type(_builtins)

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.partition(".")[0]
    if level or root not in _ALLOWED_IMPORTS:
        raise ImportError("import is not allowed in BenchLoop coding evaluation: " + name)
    module = _real_import(name, globals, locals, fromlist, level)
    for imported_name in fromlist or ():
        value = getattr(module, imported_name, None)
        if isinstance(value, _module_type):
            imported_root = value.__name__.partition(".")[0]
            if imported_root not in _ALLOWED_IMPORTS:
                raise ImportError("module re-export is not allowed: " + imported_name)
    return module

_output_bytes = 0
def _limited_print(*values, sep=" ", end="\\n", file=None, flush=False):
    global _output_bytes
    if file is not None:
        raise ValueError("redirected print is not allowed")
    rendered = sep.join(str(value) for value in values) + end
    _output_bytes += len(rendered.encode("utf-8", errors="replace"))
    if _output_bytes > {MAX_OUTPUT_BYTES}:
        raise RuntimeError("output limit exceeded")
    _builtins.print(rendered, end="", flush=flush)

_safe_builtins = {{name: getattr(_builtins, name) for name in _SAFE_NAMES}}
_safe_builtins["__import__"] = _safe_import
_safe_builtins["print"] = _limited_print
_namespace = {{"__builtins__": _safe_builtins, "__name__": "__main__"}}

exec(compile({model_code!r}, "<model-output>", "exec"), _namespace, _namespace)
exec(compile({test_code!r}, "<benchmark-tests>", "exec"), _namespace, _namespace)
"""


__all__ = ["SandboxResult", "run_restricted_python", "validate_python"]
