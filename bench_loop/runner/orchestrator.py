"""Benchmark orchestrator."""

from __future__ import annotations

import ipaddress
import time
from dataclasses import fields
from datetime import datetime, timezone
from statistics import median
from typing import Any
from urllib.parse import urlparse

from bench_loop.benchmark_manifest import (
    BENCHMARK_ID,
    BENCHMARK_VERSION,
    DEFAULT_PROFILE,
    SCORE_SCHEMA_VERSION,
    classify_suites,
    is_comparable_profile,
    manifest_hash,
    profile_coverage,
    resolve_suites,
)
from bench_loop.hardware import detect_hardware
from bench_loop.harness import get_harness
from bench_loop.models import (
    BenchmarkRun,
    MachineInfo,
    ModelInfo,
    SpeedMetrics,
    SuiteResult,
    TaskResult,
)
from bench_loop.providers import ollama, openai_compat
from bench_loop.suites import DEFAULT_SUITES as _DEFAULT_SUITES
from bench_loop.suites import SUITE_REGISTRY
from bench_loop.suites.speed import SpeedSuite

PROVIDER_REGISTRY = {
    "ollama": ollama,
    "openai": openai_compat,
    "openai_compat": openai_compat,
    "vmlx": openai_compat,  # vmlx exposes OpenAI-compatible /v1
}
SPEED_TRIALS = 3
DEFAULT_SUITES = _DEFAULT_SUITES  # public back-compat export


async def run_benchmark(
    *args,
    model: str | None = None,
    endpoint: str | None = None,
    provider: str = "ollama",
    suites: list[str] | None = None,
    suite_names: list[str] | None = None,  # alias for API back-compat
    harness: str = "raw",
    on_progress=None,
    runs: int | None = None,
    timeout_sec: float | None = None,  # accepted but unused
    remote: bool | None = None,  # None=auto, False=local hardware, True=cloud
    profile: str = DEFAULT_PROFILE,
    max_tokens: int | None = None,  # override every task's fixture max_tokens
) -> BenchmarkRun:
    # API back-compat: allow `run_benchmark(config)` where config has
    # the same attributes (model/endpoint/provider/suite_names/harness/...).
    if args and not (model or endpoint):
        cfg = args[0]
        model = getattr(cfg, "model", None) or model
        endpoint = (
            getattr(cfg, "endpoint", None) or getattr(cfg, "base_url", None) or endpoint
        )
        provider = getattr(cfg, "provider", None) or provider
        cfg_suites = getattr(cfg, "suite_names", None) or getattr(cfg, "suites", None)
        suites = cfg_suites or suites
        harness = getattr(cfg, "harness", None) or harness
        profile = getattr(cfg, "profile", None) or profile
        runs = getattr(cfg, "runs", None) or getattr(cfg, "trials", None) or runs
        cfg_remote = getattr(cfg, "remote", None)
        if cfg_remote is not None:
            remote = bool(cfg_remote)
        max_tokens = getattr(cfg, "max_tokens", None) or max_tokens
    elif suite_names and not suites:
        suites = suite_names

    if not model or not endpoint:
        raise ValueError("run_benchmark requires both `model` and `endpoint`")
    if provider not in PROVIDER_REGISTRY:
        raise ValueError(f"Unsupported provider: {provider}")

    # Remote means hosted/cloud scoring, not merely "another host." Private,
    # LAN, and Tailscale endpoints are local hardware for benchmark purposes.
    if remote is None:
        remote = endpoint_is_cloud(endpoint)

    provider_module = PROVIDER_REGISTRY[provider]
    selected_suites = resolve_suites(profile, suites)
    benchmark_profile = classify_suites(selected_suites)
    coverage_profile = benchmark_profile if benchmark_profile != "custom" else profile
    coverage = profile_coverage(coverage_profile, selected_suites)
    speed_trials = max(1, int(runs or SPEED_TRIALS))

    hardware = detect_hardware(endpoint=endpoint)
    machine_kwargs = {
        field.name: hardware.get(field.name, field.default)
        for field in fields(MachineInfo)
        if field.init
    }
    machine = MachineInfo(**machine_kwargs)

    system_info: dict[str, Any] = {}
    if hasattr(provider_module, "get_system_info"):
        system_info = await provider_module.get_system_info(endpoint)

    endpoint_host = _endpoint_host(endpoint)
    if endpoint_host and endpoint_host not in {"localhost", "127.0.0.1", "::1"}:
        remote_label = system_info.get("endpoint") or endpoint
        machine.machine_id = f"{machine.machine_id} ({endpoint_host})"
        machine.backend = f"{provider}:{remote_label}"
    elif not machine.backend:
        machine.backend = provider

    available_models = await provider_module.list_models(endpoint)
    if available_models and model not in available_models:
        raise ValueError(
            f"Model '{model}' not found on {endpoint}. Available: {', '.join(available_models)}"
        )

    run_started = time.perf_counter()
    await provider_module.chat(
        endpoint=endpoint,
        model=model,
        messages=[{"role": "user", "content": "Reply with: warmup"}],
        max_tokens=8,
        temperature=0.0,
    )

    harness_adapter = get_harness(harness)

    run = BenchmarkRun(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=ModelInfo(model_id=model),
        machine=machine,
        provider=provider,
        harness=harness,
        harness_version=getattr(harness_adapter, "version", ""),
        is_remote=remote,
        benchmark_id=BENCHMARK_ID,
        benchmark_version=BENCHMARK_VERSION,
        benchmark_profile=benchmark_profile,
        requested_profile=profile,
        score_schema_version=SCORE_SCHEMA_VERSION,
        coverage_score=coverage,
        comparable=is_comparable_profile(benchmark_profile, coverage),
    )

    speed_metric_samples: list[SpeedMetrics] = []

    # Pre-compute suite_task_counts for live API consumers.
    total_tasks_all = 0
    suite_task_counts: dict[str, int] = {}
    tasks_by_suite: dict[str, list[Any]] = {}
    for sn in selected_suites:
        if sn not in SUITE_REGISTRY:
            raise ValueError(f"Unknown suite: {sn}")
        tasks_by_suite[sn] = await SUITE_REGISTRY[sn]().load_tasks()
        suite_task_counts[sn] = len(tasks_by_suite[sn])
        total_tasks_all += len(tasks_by_suite[sn])
    run.manifest_hash = manifest_hash(
        requested_profile=coverage_profile,
        selected_suites=selected_suites,
        tasks_by_suite=tasks_by_suite,
    )
    if on_progress:
        try:
            on_progress(
                {
                    "type": "run_started",
                    "total_tasks": total_tasks_all,
                    "suites": list(selected_suites),
                    "suite_task_counts": suite_task_counts,
                    "benchmark_profile": benchmark_profile,
                    "requested_profile": profile,
                    "manifest_hash": run.manifest_hash,
                    "speed_trials": speed_trials,
                }
            )
        except Exception:
            pass

    completed_so_far = 0
    for suite_name in selected_suites:
        suite = SUITE_REGISTRY[suite_name]()
        tasks = tasks_by_suite[suite_name]
        if on_progress:
            try:
                on_progress(
                    {
                        "type": "suite_started",
                        "suite": suite_name,
                        "task_count": len(tasks),
                    }
                )
            except Exception:
                pass
        task_results: list[TaskResult] = []
        for task in tasks:
            if suite_name == "speed":
                # Speed fixtures use deliberately tiny caps to measure raw throughput — never override.
                result = await _run_speed_task(
                    provider_module,
                    endpoint,
                    model,
                    suite,
                    task,
                    harness=harness_adapter,
                    provider_name=provider,
                    remote=remote,
                    trials=speed_trials,
                )
            else:
                result = await suite.run_task(
                    provider_module,
                    endpoint,
                    model,
                    task,
                    harness=harness_adapter,
                    provider_name=provider,
                    max_tokens_override=max_tokens,
                )
            task_results.append(result)
            speed_meta = (
                result.metadata.get("speed_metrics")
                if isinstance(result.metadata, dict)
                else None
            )
            if isinstance(speed_meta, dict):
                speed_metric_samples.append(SpeedMetrics(**speed_meta))
            completed_so_far += 1
            if on_progress:
                try:
                    on_progress(
                        {
                            "type": "task_completed",
                            "suite": suite_name,
                            "task_id": result.task_id,
                            "score": result.score,
                            "passed": result.passed,
                            "latency_ms": result.latency_ms,
                            "error": result.error,
                            "completed_tasks": completed_so_far,
                            "total_tasks": total_tasks_all,
                        }
                    )
                except Exception:
                    pass

        latencies = [task.latency_ms for task in task_results if task.latency_ms > 0]
        score = suite.aggregate_score(task_results)
        pass_count = sum(1 for task in task_results if task.passed)
        suite_result = SuiteResult(
            suite=suite_name,
            score=score,
            task_count=len(task_results),
            pass_count=pass_count,
            fail_count=len(task_results) - pass_count,
            median_latency_ms=median(latencies) if latencies else 0.0,
            tasks=task_results,
        )
        run.suites[suite_name] = suite_result
        if on_progress:
            try:
                on_progress(
                    {
                        "type": "suite_completed",
                        "suite": suite_name,
                        "score": suite_result.score,
                        "pass_count": suite_result.pass_count,
                        "task_count": suite_result.task_count,
                    }
                )
            except Exception:
                pass

    run.total_runtime_sec = time.perf_counter() - run_started
    if speed_metric_samples:
        generation_samples = [
            item.generation_tok_per_sec for item in speed_metric_samples
        ]
        ttft_samples = [
            item.ttft_ms for item in speed_metric_samples if item.ttft_ms > 0
        ]
        run.speed_metrics = SpeedMetrics(
            ttft_ms=median(ttft_samples) if ttft_samples else 0.0,
            prompt_eval_tok_per_sec=median(
                item.prompt_eval_tok_per_sec for item in speed_metric_samples
            ),
            generation_tok_per_sec=median(generation_samples),
            total_latency_ms=median(
                item.total_latency_ms for item in speed_metric_samples
            ),
            generation_tok_per_sec_p50=median(generation_samples),
            generation_tok_per_sec_p95=_percentile(generation_samples, 0.95),
            ttft_ms_p50=median(ttft_samples) if ttft_samples else 0.0,
            ttft_ms_p95=_percentile(ttft_samples, 0.95),
            sample_count=len(speed_metric_samples),
        )
    run.compute_aggregates()
    if on_progress:
        try:
            on_progress(
                {
                    "type": "run_completed",
                    "overall_score": run.overall_score,
                    "quality_score": run.quality_score,
                    "speed_score": run.speed_score,
                    "reliability_score": run.reliability_score,
                    "total_runtime_sec": run.total_runtime_sec,
                    "benchmark_profile": run.benchmark_profile,
                    "coverage_score": run.coverage_score,
                    "comparable": run.comparable,
                }
            )
        except Exception:
            pass
    return run


async def _run_speed_task(
    provider_module: Any,
    endpoint: str,
    model: str,
    suite: SpeedSuite,
    task: Any,
    harness: Any | None = None,
    provider_name: str = "ollama",
    remote: bool = False,
    trials: int = SPEED_TRIALS,
) -> TaskResult:
    trial_results: list[TaskResult] = []
    request = (
        harness.prepare(task, provider_name=provider_name)
        if harness is not None
        else {"messages": task.messages, **task.config}
    )

    # Use streaming for remote/cloud to get real TTFT + tok/s
    use_streaming = remote and hasattr(provider_module, "chat_streaming")

    for _ in range(trials):
        started = suite.now_ms()
        try:
            if use_streaming:
                response = await provider_module.chat_streaming(
                    endpoint=endpoint,
                    model=model,
                    **request,
                )
            else:
                response = await provider_module.chat(
                    endpoint=endpoint,
                    model=model,
                    **request,
                )
            if harness is not None:
                response = harness.postprocess(response, task)
        except Exception as exc:  # preserve the run and score this as execution failure
            response = suite.runtime_error_response(exc, suite.now_ms() - started)
        # Never infer cloud/local from the presence of TTFT: local Ollama and
        # llama.cpp responses can expose TTFT-like timing fields too.
        response["_benchloop_remote"] = remote
        trial_results.append(suite.evaluate(task, response))

    scored_trials = trial_results[1:] if len(trial_results) > 1 else trial_results
    selected = min(
        scored_trials,
        key=lambda item: abs(item.score - median(t.score for t in scored_trials)),
    )
    selected.metadata = {
        **selected.metadata,
        "trials": [
            {
                "trial_index": index + 1,
                "warmup": index == 0,
                "passed": result.passed,
                "score": result.score,
                "latency_ms": result.latency_ms,
                "tokens_generated": result.tokens_generated,
                "tokens_prompt": result.tokens_prompt,
                "error": result.error,
                "speed_metrics": result.metadata.get("speed_metrics", {}),
            }
            for index, result in enumerate(trial_results)
        ],
        "selected_trial": next(
            index + 1
            for index, result in enumerate(trial_results)
            if result is selected
        ),
        "warmup_dropped": len(trial_results) > 1,
        "selection_method": "median_of_post_warmup_trials",
    }
    return selected


def _endpoint_host(endpoint: str) -> str:
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    return (parsed.hostname or "").strip().lower()


def endpoint_is_cloud(endpoint: str) -> bool:
    host = _endpoint_host(endpoint)
    if not host or host == "localhost":
        return False
    try:
        address = ipaddress.ip_address(host)
        tailscale_cgnat = address in ipaddress.ip_network("100.64.0.0/10")
        return not (
            address.is_loopback
            or address.is_private
            or address.is_link_local
            or tailscale_cgnat
        )
    except ValueError:
        local_suffixes = (".local", ".lan", ".internal", ".tailnet", ".ts.net")
        return "." in host and not host.endswith(local_suffixes)


def _percentile(values: list[float], percentile: float) -> float:
    """Linear percentile with deterministic behavior for short sample lists."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
