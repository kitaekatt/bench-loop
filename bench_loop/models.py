"""Core data models for BenchLoop results and configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SuiteName(str, Enum):
    SPEED = "speed"
    CODING = "coding"
    TOOL_CALLING = "tool_calling"
    REASONING = "reasoning"
    INSTRUCTION = "instruction_following"
    STRUCTURED = "structured_output"
    AGENT_LOOP = "agent_loop"


@dataclass
class MachineInfo:
    machine_id: str
    cpu: str = ""
    gpu: str = ""
    gpu_memory_gb: float = 0.0
    system_memory_gb: float = 0.0
    os: str = ""
    backend: str = ""
    is_remote: bool = False
    remote_host: str = ""
    endpoint: str = ""
    hardware_label: str = ""

    def summary(self) -> str:
        parts: list[str] = []
        if self.hardware_label:
            return self.hardware_label
        if self.gpu:
            parts.append(self.gpu)
        if self.gpu_memory_gb:
            parts.append(f"{self.gpu_memory_gb:.0f}GB VRAM")
        if self.cpu:
            parts.append(self.cpu)
        if self.system_memory_gb and self.cpu and not self.gpu:
            parts.append(f"{self.system_memory_gb:.0f}GB RAM")
        return " / ".join(parts) if parts else self.machine_id


@dataclass
class ModelInfo:
    model_id: str
    family: str = ""
    parameter_count: str = ""
    quantization: str = ""


@dataclass
class BenchmarkTask:
    id: str
    suite: str
    messages: list[dict[str, str]]
    title: str = ""
    difficulty: str = ""
    capability_tags: list[str] = field(default_factory=list)
    verifier_type: str = ""
    expected_turns: int | None = None
    notes: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    task_id: str
    suite: str
    passed: bool
    score: float
    latency_ms: float = 0.0
    tokens_generated: int = 0
    tokens_prompt: int = 0
    error: str = ""
    output: str = ""
    execution_ok: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SuiteResult:
    suite: str
    score: float
    task_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    median_latency_ms: float = 0.0
    tasks: list[TaskResult] = field(default_factory=list)


@dataclass
class SpeedMetrics:
    ttft_ms: float = 0.0
    prompt_eval_tok_per_sec: float = 0.0
    generation_tok_per_sec: float = 0.0
    total_latency_ms: float = 0.0
    generation_tok_per_sec_p50: float = 0.0
    generation_tok_per_sec_p95: float = 0.0
    ttft_ms_p50: float = 0.0
    ttft_ms_p95: float = 0.0
    sample_count: int = 0


@dataclass
class BenchmarkRun:
    """Top-level result for one complete benchmark run."""

    version: str = "0.3.0"
    benchmark_id: str = "benchloop"
    benchmark_version: str = "3.0.0"
    benchmark_profile: str = "custom"
    requested_profile: str = "core"
    manifest_hash: str = ""
    score_schema_version: str = "3.0.0"
    coverage_score: float = 0.0
    comparable: bool = False
    timestamp: str = ""
    model: ModelInfo = field(default_factory=lambda: ModelInfo(model_id="unknown"))
    machine: MachineInfo = field(
        default_factory=lambda: MachineInfo(machine_id="unknown")
    )
    provider: str = "ollama"
    harness: str = "raw"
    harness_version: str = ""
    is_remote: bool = False
    total_runtime_sec: float = 0.0
    overall_score: float = 0.0
    quality_score: float = 0.0
    speed_score: float = 0.0
    reliability_score: float = 0.0
    value_score: float = 0.0
    speed_metrics: SpeedMetrics = field(default_factory=SpeedMetrics)
    suites: dict[str, SuiteResult] = field(default_factory=dict)

    def compute_aggregates(self) -> None:
        # Import lazily to keep the core dataclasses free of an import cycle.
        from bench_loop.benchmark_manifest import quality_weights_for

        weight_profile = (
            self.benchmark_profile
            if self.benchmark_profile != "custom"
            else self.requested_profile
        )
        weights = quality_weights_for(weight_profile, self.suites)
        if weights:
            self.quality_score = sum(
                self.suites[name].score * weight for name, weight in weights.items()
            )

        speed_suite = self.suites.get(SuiteName.SPEED) or self.suites.get(
            SuiteName.SPEED.value
        )
        if speed_suite:
            self.speed_score = speed_suite.score

        tasks = [task for suite in self.suites.values() for task in suite.tasks]
        execution_ok = sum(1 for task in tasks if task.execution_ok)
        self.reliability_score = (execution_ok / len(tasks) * 100) if tasks else 0.0

        # v3 stops counting task correctness twice. Quality owns correctness;
        # reliability is reserved for endpoint/runtime execution stability.
        if self.speed_score > 0:
            self.overall_score = (
                0.70 * self.quality_score
                + 0.25 * self.speed_score
                + 0.05 * self.reliability_score
            )
        else:
            self.overall_score = (
                0.90 * self.quality_score + 0.10 * self.reliability_score
            )

        speed_factor = (
            min(self.speed_metrics.generation_tok_per_sec / 100, 1.0)
            if self.speed_metrics.generation_tok_per_sec > 0
            else 0.5
        )
        reliability_factor = self.reliability_score / 100
        self.quality_score = round(self.quality_score, 2)
        self.speed_score = round(self.speed_score, 2)
        self.reliability_score = round(self.reliability_score, 2)
        self.overall_score = round(self.overall_score, 2)
        self.value_score = round(
            self.quality_score * speed_factor * reliability_factor, 2
        )

    def to_dict(self) -> dict[str, Any]:
        return _asdict_recursive(self)


def _asdict_recursive(obj: Any) -> Any:
    import dataclasses

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            key: _asdict_recursive(value)
            for key, value in dataclasses.asdict(obj).items()
        }
    if isinstance(obj, dict):
        return {key: _asdict_recursive(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_asdict_recursive(value) for value in obj]
    if isinstance(obj, Enum):
        return obj.value
    return obj
