"""Authenticated BenchLoop cloud pairing and run publishing."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import time
import webbrowser
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
import keyring

from bench_loop import __version__

DEFAULT_API_URL = "https://api.bench-loop.com/v1"
KEYRING_SERVICE = "benchloop-cli"


class CloudError(RuntimeError):
    """A user-actionable account or publishing failure."""


@dataclass(frozen=True)
class Account:
    api_url: str
    device_id: str
    handle: str
    paired_at: str = ""


@dataclass(frozen=True)
class PairingSession:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


def api_url(value: str | None = None) -> str:
    return (value or os.environ.get("BENCHLOOP_API_URL") or DEFAULT_API_URL).rstrip("/")


def config_dir() -> Path:
    return Path(
        os.environ.get("BENCHLOOP_HOME", Path.home() / ".bench-loop")
    ).expanduser()


def account_path() -> Path:
    return config_dir() / "account.json"


def _credential_name(base_url: str) -> str:
    digest = hashlib.sha256(base_url.encode("utf-8")).hexdigest()[:16]
    return f"device-token:{digest}"


def load_account() -> Account | None:
    path = account_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Account(
            api_url=str(raw["api_url"]),
            device_id=str(raw["device_id"]),
            handle=str(raw["handle"]),
            paired_at=str(raw.get("paired_at", "")),
        )
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise CloudError(f"BenchLoop account metadata is unreadable: {path}") from exc


def save_account(account: Account, token: str) -> None:
    try:
        keyring.set_password(KEYRING_SERVICE, _credential_name(account.api_url), token)
    except Exception as exc:
        raise CloudError(
            "Could not save the Runner token in the operating-system keychain. "
            "Configure a keyring backend or use BENCHLOOP_TOKEN for this session."
        ) from exc

    path = account_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(account), indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        try:
            keyring.delete_password(KEYRING_SERVICE, _credential_name(account.api_url))
        except keyring.errors.KeyringError:
            pass
        raise CloudError(f"Could not write BenchLoop account metadata: {path}") from exc
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_token(base_url: str | None = None) -> str | None:
    environment_token = os.environ.get("BENCHLOOP_TOKEN", "").strip()
    if environment_token:
        return environment_token
    resolved = api_url(base_url)
    try:
        return keyring.get_password(KEYRING_SERVICE, _credential_name(resolved))
    except Exception as exc:
        raise CloudError(
            "Could not read the Runner token from the operating-system keychain."
        ) from exc


def clear_account() -> None:
    account = load_account()
    if account:
        try:
            keyring.delete_password(KEYRING_SERVICE, _credential_name(account.api_url))
        except keyring.errors.PasswordDeleteError:
            pass
        except Exception as exc:
            raise CloudError(
                "Could not remove the Runner token from the operating-system keychain."
            ) from exc
    try:
        account_path().unlink()
    except FileNotFoundError:
        pass


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": f"benchloop-cli/{__version__}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise CloudError(
            f"BenchLoop API returned invalid JSON (HTTP {response.status_code})."
        ) from exc
    if not isinstance(payload, dict):
        raise CloudError("BenchLoop API returned an unexpected response.")
    return payload


def start_pairing(
    *, base_url: str | None = None, device_name: str | None = None
) -> PairingSession:
    resolved = api_url(base_url)
    default_names = {
        "Darwin": "Mac Runner",
        "Windows": "Windows Runner",
        "Linux": "Linux Runner",
    }
    name = (
        device_name or default_names.get(platform.system(), "BenchLoop Runner")
    ).strip()[:100]
    try:
        response = httpx.post(
            f"{resolved}/runner/pair/start",
            json={"device_name": name, "capabilities": {"benchmark_schema": "3.0.0"}},
            headers=_headers(),
            timeout=10,
        )
    except httpx.HTTPError as exc:
        raise CloudError(f"Could not reach the BenchLoop API at {resolved}.") from exc
    if response.status_code not in {200, 201}:
        detail = _json_response(response).get("error", response.text[:160])
        raise CloudError(
            f"Pairing could not start (HTTP {response.status_code}): {detail}"
        )
    payload = _json_response(response)
    try:
        return PairingSession(
            device_code=str(payload["device_code"]),
            user_code=str(payload["user_code"]),
            verification_uri=str(payload["verification_uri"]),
            expires_in=int(payload.get("expires_in", 600)),
            interval=max(1, int(payload.get("interval", 3))),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CloudError("BenchLoop API returned an invalid pairing response.") from exc


def await_pairing(
    session: PairingSession,
    *,
    base_url: str | None = None,
    on_wait: Callable[[], None] | None = None,
) -> Account:
    resolved = api_url(base_url)
    deadline = time.monotonic() + session.expires_in
    interval = session.interval
    while time.monotonic() < deadline:
        if on_wait:
            on_wait()
        time.sleep(interval)
        try:
            response = httpx.post(
                f"{resolved}/runner/pair/token",
                json={"device_code": session.device_code},
                headers=_headers(),
                timeout=10,
            )
        except httpx.HTTPError:
            continue

        payload = _json_response(response)
        if (
            response.status_code == 428
            or payload.get("error") == "authorization_pending"
        ):
            continue
        if response.status_code == 429 or payload.get("error") == "slow_down":
            interval = min(interval + 2, 15)
            continue
        if response.status_code != 200:
            raise CloudError(
                str(
                    payload.get("error")
                    or f"Pairing failed with HTTP {response.status_code}."
                )
            )

        try:
            account = Account(
                api_url=resolved,
                device_id=str(payload["device_id"]),
                handle=str(payload["handle"]),
                paired_at=str(payload.get("paired_at", "")),
            )
            token = str(payload["token"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CloudError(
                "BenchLoop API returned an invalid device credential."
            ) from exc
        save_account(account, token)
        return account
    raise CloudError("The pairing code expired. Run `benchloop auth login` again.")


def open_verification_page(session: PairingSession) -> bool:
    separator = "&" if "?" in session.verification_uri else "?"
    return webbrowser.open(
        f"{session.verification_uri}{separator}code={session.user_code}"
    )


def publish_run(
    run_path: Path,
    *,
    base_url: str | None = None,
    visibility: str = "public",
    create_post: bool = True,
) -> dict[str, Any]:
    resolved = api_url(base_url)
    token = load_token(resolved)
    if not token:
        raise CloudError("This Runner is not paired. Run `benchloop auth login` first.")
    try:
        run = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CloudError(f"Could not read benchmark result: {run_path}") from exc
    required = {
        "benchmark_id",
        "benchmark_version",
        "benchmark_profile",
        "score_schema_version",
        "manifest_hash",
        "timestamp",
        "model",
        "machine",
        "suites",
    }
    missing = sorted(required.difference(run))
    if missing:
        raise CloudError(f"Run is missing v3 provenance fields: {', '.join(missing)}")
    if not str(run.get("manifest_hash", "")).startswith("sha256:"):
        raise CloudError(
            "Only captured v3 runs with a SHA-256 manifest can be published."
        )

    public_run = _public_run_payload(run, run_path)

    try:
        response = httpx.post(
            f"{resolved}/runs",
            json={
                "run": public_run,
                "visibility": visibility,
                "create_post": create_post,
            },
            headers=_headers(token),
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise CloudError(f"Could not reach the BenchLoop API at {resolved}.") from exc
    payload = _json_response(response)
    if response.status_code not in {200, 201}:
        raise CloudError(
            str(
                payload.get("error")
                or f"Publish failed with HTTP {response.status_code}."
            )
        )
    return payload


def _public_run_payload(run: dict[str, Any], run_path: Path) -> dict[str, Any]:
    """Strip local endpoints, raw outputs, and task metadata."""
    machine = run.get("machine") or {}
    public_machine = {
        key: machine.get(key)
        for key in (
            "machine_id",
            "cpu",
            "gpu",
            "gpu_memory_gb",
            "system_memory_gb",
            "os",
            "backend",
            "is_remote",
            "hardware_label",
        )
        if machine.get(key) not in (None, "")
    }
    public_suites: dict[str, Any] = {}
    for suite_name, suite in (run.get("suites") or {}).items():
        if not isinstance(suite, dict):
            continue
        summary = {
            key: suite.get(key)
            for key in (
                "suite",
                "score",
                "task_count",
                "pass_count",
                "fail_count",
                "median_latency_ms",
            )
            if key in suite
        }
        summary["tasks"] = [
            {
                key: task.get(key)
                for key in (
                    "task_id",
                    "suite",
                    "passed",
                    "score",
                    "latency_ms",
                    "tokens_generated",
                    "tokens_prompt",
                    "execution_ok",
                )
                if key in task
            }
            for task in suite.get("tasks", [])
            if isinstance(task, dict)
        ]
        public_suites[str(suite_name)] = summary

    allowed = (
        "version",
        "benchmark_id",
        "benchmark_version",
        "benchmark_profile",
        "requested_profile",
        "manifest_hash",
        "score_schema_version",
        "coverage_score",
        "comparable",
        "timestamp",
        "model",
        "provider",
        "harness",
        "harness_version",
        "is_remote",
        "total_runtime_sec",
        "overall_score",
        "quality_score",
        "speed_score",
        "reliability_score",
        "value_score",
        "speed_metrics",
    )
    payload = {key: run.get(key) for key in allowed if key in run}
    payload["source_run_id"] = str(run.get("run_id") or run_path.parent.name)
    payload["machine"] = public_machine
    payload["suites"] = public_suites
    return payload


def resolve_run_path(value: str | None, runs_dir: Path) -> Path:
    if value:
        candidate = Path(value).expanduser()
        if candidate.is_dir():
            candidate = candidate / "run.json"
        if candidate.is_file():
            return candidate
        named = runs_dir / value / "run.json"
        if named.is_file():
            return named
        raise CloudError(f"Run not found: {value}")

    candidates = sorted(runs_dir.glob("*/run.json"), reverse=True)
    if not candidates:
        raise CloudError(f"No local runs found in {runs_dir}")
    return candidates[0]
