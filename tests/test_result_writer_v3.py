from __future__ import annotations

import json

from bench_loop.runner import result_writer


def test_failed_run_retains_requested_profile_provenance(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(result_writer, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(
        result_writer,
        "detect_hardware",
        lambda endpoint: {"machine_id": "test", "endpoint": endpoint},
    )
    output = result_writer.save_failed_run(
        run_id="failed-1",
        model="test-model",
        endpoint="http://localhost:8080",
        provider="openai_compat",
        harness="raw",
        suites=None,
        benchmark_profile="full",
        error="intentional failure",
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["benchmark_profile"] == "full"
    assert payload["requested_profile"] == "full"
    assert payload["coverage_score"] == 100
    assert payload["comparable"] is False
    assert payload["manifest_hash"] == ""
    assert payload["requested_suites"][-2:] == ["longcontext", "agent"]
