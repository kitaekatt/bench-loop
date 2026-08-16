from __future__ import annotations

from bench_loop.benchmark_manifest import (
    PROFILES,
    classify_suites,
    manifest_hash,
    profile_coverage,
    resolve_suites,
)
from bench_loop.models import BenchmarkTask


def test_profiles_have_unique_exact_classification() -> None:
    for name, profile in PROFILES.items():
        assert classify_suites(profile.suites) == name
        assert profile_coverage(name, profile.suites) == 100.0


def test_custom_suite_selection_is_not_mislabeled_full() -> None:
    suites = ["speed", "toolcall", "dataextract", "instructfollow", "reasonmath"]
    assert classify_suites(suites) == "custom"
    assert profile_coverage("core", suites) < 100.0


def test_profile_resolution_preserves_default_and_custom_order() -> None:
    assert resolve_suites("smoke") == list(PROFILES["smoke"].suites)
    assert resolve_suites("core", ["reasonmath", "speed", "reasonmath"]) == [
        "reasonmath",
        "speed",
    ]


def test_manifest_hash_is_deterministic_and_fixture_sensitive() -> None:
    task = BenchmarkTask(
        id="example",
        suite="reasonmath",
        messages=[{"role": "user", "content": "What is 2+2?"}],
        validation={"expected": "4"},
    )
    kwargs = {
        "requested_profile": "smoke",
        "selected_suites": ["reasonmath"],
        "tasks_by_suite": {"reasonmath": [task]},
    }
    first = manifest_hash(**kwargs)
    second = manifest_hash(**kwargs)
    assert first == second
    assert first.startswith("sha256:")

    changed_task = BenchmarkTask(
        id="example",
        suite="reasonmath",
        messages=[{"role": "user", "content": "What is 2+3?"}],
        validation={"expected": "5"},
    )
    changed = manifest_hash(
        **{**kwargs, "tasks_by_suite": {"reasonmath": [changed_task]}}
    )
    assert changed != first
