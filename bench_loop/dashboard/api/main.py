"""BenchLoop API — FastAPI backend for local LLM benchmarking.

When this module is loaded from inside the installed `benchloop-cli` package
(`bench_loop.dashboard.api.main`), the `bench_loop` package is already on
`sys.path` and there is nothing to bootstrap. The legacy bench-loop-web repo
layout placed this file under `bench-loop-web/api/`, where it needed to add
`../bench-loop` to `sys.path` manually. The block below preserves that legacy
behaviour without hardcoding any paths or any specific user's home directory.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import bench_loop  # noqa: F401
    _bench_loop_already_importable = True
except ImportError:
    _bench_loop_already_importable = False

if not _bench_loop_already_importable:
    # Legacy bench-loop-web layout: this file lives in `bench-loop-web/api/`,
    # so `bench-loop/` should be a sibling.
    candidates = []
    if env_path := os.environ.get("BENCH_LOOP_DIR"):
        candidates.append(Path(env_path))
    candidates.append(Path(__file__).resolve().parent.parent.parent / "bench-loop")
    for c in candidates:
        if (c / "bench_loop").is_dir():
            sys.path.insert(0, str(c.resolve()))
            print(f"[bench-loop-api] using bench_loop from: {c.resolve()}", flush=True)
            break

# Ensure api package root is importable for routes
api_root = Path(__file__).resolve().parent
if str(api_root) not in sys.path:
    sys.path.insert(0, str(api_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from routes import auth, auth_x, benchmark, chat, hardware, health, models, users, share_card, rankings

app = FastAPI(title="BenchLoop", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(benchmark.router, prefix="/api")
app.include_router(hardware.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(auth_x.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(share_card.router, prefix="/api")
app.include_router(rankings.router, prefix="/api")

# Serve the bundled UI (built React SPA) at /
_ui_dir = Path(__file__).resolve().parent.parent / "ui"
if _ui_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_ui_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def _spa_fallback(full_path: str):
        # Serve specific static files when they exist, else fall back to index.html.
        candidate = _ui_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_ui_dir / "index.html")
