"""Persist benchmark results."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from rich.console import Console

from bench_loop.benchmark_manifest import (
    BENCHMARK_ID,
    BENCHMARK_VERSION,
    DEFAULT_PROFILE,
    SCORE_SCHEMA_VERSION,
    classify_suites,
    profile_coverage,
    resolve_suites,
)
from bench_loop.hardware import detect_hardware
from bench_loop.models import BenchmarkRun

RUNS_DIR = Path.home() / ".bench-loop" / "runs"

# Temporary compatibility path for the pre-account leaderboard. New installs
# remain private unless the user explicitly pairs and publishes a run.
LEADERBOARD_SUBMIT_URL = os.environ.get(
    "BENCHLOOP_SUBMIT_URL", "https://api.bench-loop.com/submit"
)
_LEGACY_AUTO_SUBMIT = os.environ.get("BENCHLOOP_LEGACY_AUTO_SUBMIT", "").lower() in {
    "1",
    "true",
    "yes",
}


def _coalesce_profile(publish_profile: dict | None = None) -> dict[str, str]:
    raw = {
        "name": (publish_profile or {}).get("name")
        or os.environ.get("BENCHLOOP_PROFILE_NAME", ""),
        "avatar_url": (publish_profile or {}).get("avatar_url")
        or os.environ.get("BENCHLOOP_PROFILE_AVATAR_URL", ""),
        "profile_url": (publish_profile or {}).get("profile_url")
        or os.environ.get("BENCHLOOP_PROFILE_URL", ""),
    }
    return {
        key: str(value).strip()
        for key, value in raw.items()
        if str(value or "").strip()
    }


def _submit_to_leaderboard(payload: dict, console: Console) -> None:
    """Submit to public leaderboard. Short timeout, never raises.

    Runs synchronously so the CLI doesn't exit before the HTTP request
    completes. Total worst-case added latency: 5s on network failure.
    """
    if not _LEGACY_AUTO_SUBMIT:
        return

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(LEADERBOARD_SUBMIT_URL, json=payload)
            if resp.status_code == 200:
                console.print(
                    "[dim green]→ published to https://bench-loop.com/leaderboard[/dim green]"
                )
            else:
                console.print(
                    f"[dim yellow]Leaderboard submit returned {resp.status_code}: {resp.text[:120]}[/dim yellow]"
                )
    except Exception as e:  # noqa: BLE001
        console.print(
            f"[dim yellow]Leaderboard submit skipped (offline?): {type(e).__name__}[/dim yellow]"
        )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return slug.strip("-") or "run"


def _endpoint_identifier(endpoint: str | None) -> str:
    if not endpoint:
        return "local"
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    host = (parsed.hostname or "").strip().lower()
    if host in {"", "localhost", "127.0.0.1", "::1"}:
        return "local"
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", host):
        return f"remote-{host.split('.')[-1]}"
    return f"remote-{_slugify(host)}"


def save_run(
    run: BenchmarkRun,
    endpoint: str | None = None,
    console: Console | None = None,
    publish_profile: dict | None = None,
    command_used: str | None = None,
    user_id: str | None = None,
) -> Path:
    console = console or Console()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    endpoint_id = _endpoint_identifier(endpoint)
    run_dir = (
        RUNS_DIR
        / f"{timestamp}-{_slugify(run.model.model_id)}-{endpoint_id}-{_slugify(run.provider)}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    output_path = run_dir / "run.json"
    run_dict = run.to_dict()
    profile = _coalesce_profile(publish_profile)
    if profile:
        run_dict["profile"] = profile
    if command_used and str(command_used).strip():
        run_dict["command_used"] = str(command_used).strip()
    if user_id:
        run_dict["user_id"] = user_id
    # The folder name is the authenticated publishing idempotency key. Persist
    # it in the local receipt so a retry cannot create a second public run.
    run_dict["run_id"] = run_dir.name
    output_path.write_text(json.dumps(run_dict, indent=2), encoding="utf-8")
    console.print(f"Saved results to [bold]{output_path}[/bold]")

    _submit_to_leaderboard(run_dict, console)

    return output_path


def save_failed_run(
    *,
    run_id: str,
    model: str,
    endpoint: str,
    provider: str,
    harness: str,
    suites: list[str] | None,
    error: str,
    traceback_text: str | None = None,
    events: list[dict] | None = None,
    publish_profile: dict | None = None,
    command_used: str | None = None,
    console: Console | None = None,
    user_id: str | None = None,
    benchmark_profile: str = DEFAULT_PROFILE,
) -> Path:
    console = console or Console()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    endpoint_id = _endpoint_identifier(endpoint)
    run_dir = (
        RUNS_DIR
        / f"{timestamp}-{_slugify(model)}-{endpoint_id}-{_slugify(provider)}-failed"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    machine = detect_hardware(endpoint=endpoint)
    requested_suites = resolve_suites(benchmark_profile, suites)
    classified_profile = classify_suites(requested_suites)
    coverage_profile = (
        classified_profile if classified_profile != "custom" else benchmark_profile
    )
    coverage = profile_coverage(coverage_profile, requested_suites)
    run_dict = {
        "run_id": run_id,
        "status": "failed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": {
            "model_id": model,
            "family": "",
            "parameter_count": "",
            "quantization": "",
        },
        "machine": machine,
        "provider": provider,
        "harness": harness,
        "requested_suites": requested_suites,
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "benchmark_profile": classified_profile,
        "requested_profile": benchmark_profile,
        "score_schema_version": SCORE_SCHEMA_VERSION,
        "manifest_hash": "",
        "coverage_score": coverage,
        "comparable": False,
        "suites": {},
        "overall_score": 0,
        "quality_score": 0,
        "speed_score": 0,
        "reliability_score": 0,
        "value_score": 0,
        "speed_metrics": {},
        "total_runtime_sec": 0,
        "error": error,
        "traceback": traceback_text or "",
        "events": events or [],
    }
    profile = _coalesce_profile(publish_profile)
    if profile:
        run_dict["profile"] = profile
    if command_used and str(command_used).strip():
        run_dict["command_used"] = str(command_used).strip()
    if user_id:
        run_dict["user_id"] = user_id

    output_path = run_dir / "run.json"
    output_path.write_text(json.dumps(run_dict, indent=2), encoding="utf-8")
    console.print(f"Saved failed run to [bold]{output_path}[/bold]")
    return output_path
