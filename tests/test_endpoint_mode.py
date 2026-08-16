from __future__ import annotations

import pytest

from bench_loop.runner.orchestrator import endpoint_is_cloud


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://192.168.1.96:8080",
        "http://100.95.10.4:8080",
        "http://luxecorp-pc1:8080",
        "http://pc1.example-tailnet.ts.net:8080",
    ],
)
def test_local_and_tailscale_endpoints_use_local_mode(endpoint: str) -> None:
    assert endpoint_is_cloud(endpoint) is False


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://api.openai.com/v1",
        "https://openrouter.ai/api/v1",
        "https://inference.example.com/v1",
    ],
)
def test_public_api_endpoints_use_cloud_mode(endpoint: str) -> None:
    assert endpoint_is_cloud(endpoint) is True
