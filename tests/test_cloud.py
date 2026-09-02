from __future__ import annotations

import json

import httpx
from click.testing import CliRunner

from bench_loop import cloud
from bench_loop.cli import main


def response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status, json=payload, request=httpx.Request("POST", "https://api.test")
    )


def v3_run() -> dict:
    return {
        "benchmark_id": "benchloop",
        "benchmark_version": "3.0.0",
        "benchmark_profile": "core",
        "score_schema_version": "3.0.0",
        "manifest_hash": "sha256:" + "a" * 64,
        "timestamp": "2026-08-15T22:00:00+00:00",
        "model": {"model_id": "example/model"},
        "machine": {"machine_id": "test-rig"},
        "suites": {"speed": {"score": 50}},
    }


def test_account_metadata_excludes_token_and_uses_keyring(
    tmp_path, monkeypatch
) -> None:
    stored: dict[tuple[str, str], str] = {}
    monkeypatch.setenv("BENCHLOOP_HOME", str(tmp_path))
    monkeypatch.setattr(
        cloud.keyring,
        "set_password",
        lambda service, username, password: stored.__setitem__(
            (service, username), password
        ),
    )
    monkeypatch.setattr(
        cloud.keyring,
        "get_password",
        lambda service, username: stored.get((service, username)),
    )
    account = cloud.Account("https://api.test/v1", "device-1", "eric", "now")

    cloud.save_account(account, "secret-runner-token")

    raw = cloud.account_path().read_text(encoding="utf-8")
    assert "secret-runner-token" not in raw
    assert cloud.load_account() == account
    assert cloud.load_token(account.api_url) == "secret-runner-token"


def test_pairing_waits_then_stores_scoped_token(tmp_path, monkeypatch) -> None:
    replies = iter(
        [
            response(428, {"error": "authorization_pending"}),
            response(
                200,
                {
                    "token": "device-secret",
                    "device_id": "device-9",
                    "handle": "builder",
                    "paired_at": "now",
                },
            ),
        ]
    )
    saved: list[tuple[cloud.Account, str]] = []
    monkeypatch.setattr(cloud.httpx, "post", lambda *args, **kwargs: next(replies))
    monkeypatch.setattr(cloud.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        cloud, "save_account", lambda account, token: saved.append((account, token))
    )
    session = cloud.PairingSession(
        "device-code", "ABCD-EFGH", "https://bench-loop.com/connect", 60, 1
    )

    account = cloud.await_pairing(session, base_url="https://api.test/v1")

    assert account.handle == "builder"
    assert saved == [(account, "device-secret")]


def test_publish_requires_v3_provenance(tmp_path, monkeypatch) -> None:
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"model": {}}), encoding="utf-8")
    monkeypatch.setattr(cloud, "load_token", lambda _url: "token")

    try:
        cloud.publish_run(path, base_url="https://api.test/v1")
    except cloud.CloudError as exc:
        assert "v3 provenance" in str(exc)
    else:
        raise AssertionError("invalid run should not publish")


def test_publish_sends_bearer_token_and_explicit_visibility(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "run.json"
    path.write_text(json.dumps(v3_run()), encoding="utf-8")
    captured: dict = {}
    monkeypatch.setattr(cloud, "load_token", lambda _url: "runner-token")

    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return response(201, {"run_id": 42, "url": "https://bench-loop.com/runs/42"})

    monkeypatch.setattr(cloud.httpx, "post", post)
    result = cloud.publish_run(
        path,
        base_url="https://api.test/v1",
        visibility="private",
        create_post=False,
    )

    assert captured["headers"]["Authorization"] == "Bearer runner-token"
    assert captured["json"]["visibility"] == "private"
    assert captured["json"]["create_post"] is False
    assert captured["json"]["run"]["source_run_id"] == tmp_path.name
    assert result["run_id"] == 42


def test_publish_removes_private_endpoint_and_raw_output_fields(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "run.json"
    run = v3_run()
    run["machine"] = {
        "machine_id": "private-host-id",
        "endpoint": "http://100.64.0.4:8080",
        "remote_host": "pc1.tailnet.ts.net",
        "gpu": "RTX 4090",
    }
    run["command_used"] = "/Users/eric/private/launch.sh --secret value"
    run["suites"] = {
        "coding": {
            "score": 90,
            "tasks": [
                {
                    "task_id": "code-1",
                    "passed": True,
                    "score": 100,
                    "output": "private model output",
                    "metadata": {"tool_result": "private"},
                }
            ],
        }
    }
    path.write_text(json.dumps(run), encoding="utf-8")
    monkeypatch.setattr(cloud, "load_token", lambda _url: "runner-token")
    captured: dict = {}

    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return response(201, {"run_id": 1})

    monkeypatch.setattr(cloud.httpx, "post", post)
    cloud.publish_run(path, base_url="https://api.test/v1")
    published = captured["json"]["run"]

    # machine_id is published DELIBERATELY (fleet decision, 2026-09-02): runs are
    # meant to be attributable to the machine that produced them. The endpoint and
    # remote_host are still stripped -- a tailnet hostname and a LAN address are
    # what this test actually guards.
    assert published["machine"] == {
        "machine_id": "private-host-id",
        "gpu": "RTX 4090",
    }
    assert "command_used" not in published
    assert "output" not in published["suites"]["coding"]["tasks"][0]
    assert "metadata" not in published["suites"]["coding"]["tasks"][0]


def test_resolve_run_path_uses_latest_run(tmp_path) -> None:
    older = tmp_path / "20260101-run" / "run.json"
    newer = tmp_path / "20260102-run" / "run.json"
    older.parent.mkdir()
    newer.parent.mkdir()
    older.write_text("{}", encoding="utf-8")
    newer.write_text("{}", encoding="utf-8")

    assert cloud.resolve_run_path(None, tmp_path) == newer
    assert cloud.resolve_run_path("20260101-run", tmp_path) == older


def test_cli_exposes_explicit_auth_and_publish_commands() -> None:
    runner = CliRunner()
    root_help = runner.invoke(main, ["--help"])
    run_help = runner.invoke(main, ["run", "--help"])

    assert root_help.exit_code == 0
    assert "auth" in root_help.output
    assert "publish" in root_help.output
    assert run_help.exit_code == 0
    assert "--publish / --no-publish" in run_help.output


def test_result_writer_legacy_submit_is_opt_in(monkeypatch) -> None:
    from bench_loop.runner import result_writer

    called = False

    def post(*_args, **_kwargs):
        nonlocal called
        called = True
        return response(200, {})

    monkeypatch.setattr(result_writer, "_LEGACY_AUTO_SUBMIT", False)
    monkeypatch.setattr(result_writer.httpx, "post", post)
    result_writer._submit_to_leaderboard({}, result_writer.Console())
    assert called is False
