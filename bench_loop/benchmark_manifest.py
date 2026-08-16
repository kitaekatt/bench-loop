"""Versioned benchmark profiles and reproducibility metadata.

This module is deliberately dependency-light so the CLI, local dashboard, and
public export path all use the same definition of a complete benchmark.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass

from bench_loop.models import BenchmarkTask

BENCHMARK_ID = "benchloop"
BENCHMARK_VERSION = "3.0.0"
SCORE_SCHEMA_VERSION = "3.0.0"
DEFAULT_PROFILE = "core"


@dataclass(frozen=True)
class BenchmarkProfile:
    name: str
    suites: tuple[str, ...]
    quality_weights: Mapping[str, float]
    description: str


PROFILES: dict[str, BenchmarkProfile] = {
    "smoke": BenchmarkProfile(
        name="smoke",
        suites=("speed", "toolcall", "reasonmath"),
        quality_weights={"toolcall": 0.45, "reasonmath": 0.55},
        description="Fast endpoint and quality sanity check.",
    ),
    "core": BenchmarkProfile(
        name="core",
        suites=(
            "speed",
            "toolcall",
            "coding",
            "dataextract",
            "instructfollow",
            "reasonmath",
        ),
        quality_weights={
            "toolcall": 0.20,
            "coding": 0.25,
            "dataextract": 0.15,
            "instructfollow": 0.15,
            "reasonmath": 0.25,
        },
        description="Comparable daily-driver benchmark across speed and five quality domains.",
    ),
    "full": BenchmarkProfile(
        name="full",
        suites=(
            "speed",
            "toolcall",
            "coding",
            "dataextract",
            "instructfollow",
            "reasonmath",
            "longcontext",
            "agent",
        ),
        quality_weights={
            "toolcall": 0.12,
            "coding": 0.18,
            "dataextract": 0.10,
            "instructfollow": 0.10,
            "reasonmath": 0.15,
            "longcontext": 0.15,
            "agent": 0.20,
        },
        description="Core benchmark plus long-context retrieval and the multi-turn agent loop.",
    ),
}


def get_profile(name: str) -> BenchmarkProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        choices = ", ".join(PROFILES)
        raise ValueError(
            f"Unknown benchmark profile: {name}. Available: {choices}"
        ) from exc


def resolve_suites(
    profile: str = DEFAULT_PROFILE, suites: Sequence[str] | None = None
) -> list[str]:
    """Resolve requested suites while preserving the caller's order."""
    if suites is None:
        return list(get_profile(profile).suites)
    return list(
        dict.fromkeys(str(item).strip() for item in suites if str(item).strip())
    )


def classify_suites(suites: Iterable[str]) -> str:
    selected = set(suites)
    for name, profile in PROFILES.items():
        if selected == set(profile.suites):
            return name
    return "custom"


def profile_coverage(requested_profile: str, suites: Iterable[str]) -> float:
    """Return weighted suite coverage for the requested profile (0..100)."""
    expected = get_profile(requested_profile)
    selected = set(suites)
    # Speed is part of every public comparison but not a quality weight.
    speed_weight = 0.20
    quality_weight = 0.80
    covered = (
        speed_weight if "speed" in selected and "speed" in expected.suites else 0.0
    )
    covered += quality_weight * sum(
        weight
        for suite, weight in expected.quality_weights.items()
        if suite in selected
    )
    return round(min(100.0, covered * 100.0), 2)


def quality_weights_for(profile: str, suites: Iterable[str]) -> dict[str, float]:
    """Return normalized quality weights for the suites present in a run."""
    selected = set(suites)
    basis = get_profile(
        profile if profile in PROFILES else DEFAULT_PROFILE
    ).quality_weights
    present = {suite: weight for suite, weight in basis.items() if suite in selected}
    total = sum(present.values())
    if total <= 0:
        return {}
    return {suite: weight / total for suite, weight in present.items()}


def manifest_hash(
    *,
    requested_profile: str,
    selected_suites: Sequence[str],
    tasks_by_suite: Mapping[str, Sequence[BenchmarkTask]],
) -> str:
    """Hash the exact prompts, configs, and validators used by a run."""
    payload = {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "score_schema_version": SCORE_SCHEMA_VERSION,
        "requested_profile": requested_profile,
        "selected_suites": list(selected_suites),
        "tasks": {
            suite: [asdict(task) for task in tasks_by_suite.get(suite, ())]
            for suite in selected_suites
        },
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def is_comparable_profile(profile: str, coverage: float) -> bool:
    return profile in PROFILES and coverage == 100.0


__all__ = [
    "BENCHMARK_ID",
    "BENCHMARK_VERSION",
    "DEFAULT_PROFILE",
    "PROFILES",
    "SCORE_SCHEMA_VERSION",
    "BenchmarkProfile",
    "classify_suites",
    "get_profile",
    "is_comparable_profile",
    "manifest_hash",
    "profile_coverage",
    "quality_weights_for",
    "resolve_suites",
]
