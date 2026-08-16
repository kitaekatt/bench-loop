"""Benchmark suite registry."""

from __future__ import annotations

from bench_loop.benchmark_manifest import DEFAULT_PROFILE, get_profile
from bench_loop.suites.agent import AgentSuite
from bench_loop.suites.coding import CodingSuite
from bench_loop.suites.dataextract import DataExtractSuite
from bench_loop.suites.instructfollow import InstructFollowSuite
from bench_loop.suites.longcontext import LongContextSuite
from bench_loop.suites.reasonmath import ReasonMathSuite
from bench_loop.suites.speed import SpeedSuite
from bench_loop.suites.toolcall import ToolCallSuite

# v3 shipping suites. Coding uses a restricted interpreter process; public
# multi-tenant workers should additionally run BenchLoop in a disposable VM.
# `tool_use` remains deferred (lower-quality fixtures than `toolcall`).
SUITE_REGISTRY = {
    "speed": SpeedSuite,
    "toolcall": ToolCallSuite,
    "dataextract": DataExtractSuite,
    "instructfollow": InstructFollowSuite,
    "reasonmath": ReasonMathSuite,
    "coding": CodingSuite,
    "longcontext": LongContextSuite,
    "agent": AgentSuite,
}

DEFAULT_SUITES = list(get_profile(DEFAULT_PROFILE).suites)

__all__ = [
    "DEFAULT_SUITES",
    "SUITE_REGISTRY",
    "AgentSuite",
    "CodingSuite",
    "DataExtractSuite",
    "InstructFollowSuite",
    "LongContextSuite",
    "ReasonMathSuite",
    "SpeedSuite",
    "ToolCallSuite",
]
