"""User rankings and badges for the public leaderboard."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/rankings", tags=["rankings"])

RUNS_DIR = Path("~/.bench-loop/runs").expanduser()
USERS_FILE = Path.home() / ".bench-loop" / "users.json"


def _load_users() -> dict:
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text())
    return {}


def _load_all_runs() -> list[dict]:
    """Load all completed runs with user_id."""
    runs = []
    if not RUNS_DIR.exists():
        return runs
    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        run_file = d / "run.json"
        if not run_file.exists():
            continue
        try:
            data = json.loads(run_file.read_text())
            if data.get("status") == "completed":
                runs.append(data)
        except Exception:
            continue
    return runs


class UserRanking(BaseModel):
    user_id: str
    login: str
    avatar_url: str
    run_count: int
    best_overall: float
    best_model: str
    badges: list[str]
    rank: int


def _compute_badges(user_runs: list[dict], all_runs: list[dict]) -> list[str]:
    """Compute badges for a user based on their runs and global stats."""
    badges = []

    if len(user_runs) >= 10:
        badges.append("🏅 Veteran (10+ runs)")
    elif len(user_runs) >= 5:
        badges.append("📊 Regular (5+ runs)")

    # Speed demon: any run over 100 tok/s
    for run in user_runs:
        tok_s = run.get("speed_metrics", {}).get("generation_tok_per_sec", 0)
        if tok_s >= 100:
            badges.append("⚡ Speed Demon (100+ tok/s)")
            break

    # Quality king: any run with quality >= 90
    for run in user_runs:
        if run.get("quality_score", 0) >= 90:
            badges.append("👑 Quality King (90+ quality)")
            break

    # Tool master: toolcall suite score >= 90
    for run in user_runs:
        suites = run.get("suites", {})
        tc = suites.get("toolcall", {})
        if tc.get("score", 0) >= 90:
            badges.append("🔧 Tool Master (90+ toolcall)")
            break

    # #1 on leaderboard
    ranked = sorted(all_runs, key=lambda r: r.get("overall_score", 0), reverse=True)
    if ranked and user_runs:
        top_run = ranked[0]
        for ur in user_runs:
            if ur.get("run_id") == top_run.get("run_id"):
                badges.append("🥇 #1 on Leaderboard")
                break

    # Cloud benchmarker
    for run in user_runs:
        if run.get("is_remote"):
            badges.append("☁️ Cloud Benchmarker")
            break

    # MTP explorer (runs with spec-type in command)
    for run in user_runs:
        cmd = run.get("command_used", "")
        if "draft-mtp" in cmd or "mtp" in cmd.lower():
            badges.append("🧪 MTP Explorer")
            break

    return badges


@router.get("/")
async def get_rankings():
    """Get user rankings with badges."""
    users = _load_users()
    all_runs = _load_all_runs()

    # Group runs by user
    user_runs_map: dict[str, list[dict]] = {}
    for run in all_runs:
        uid = run.get("user_id")
        if uid:
            user_runs_map.setdefault(uid, []).append(run)

    rankings = []
    for uid, user_data in users.items():
        u_runs = user_runs_map.get(uid, [])
        if not u_runs:
            continue

        best_run = max(u_runs, key=lambda r: r.get("overall_score", 0))
        badges = _compute_badges(u_runs, all_runs)

        rankings.append({
            "user_id": uid,
            "login": user_data.get("login", "unknown"),
            "avatar_url": user_data.get("avatar_url", ""),
            "run_count": len(u_runs),
            "best_overall": best_run.get("overall_score", 0),
            "best_model": best_run.get("model", {}).get("model_id", "unknown"),
            "badges": badges,
        })

    # Sort by best overall
    rankings.sort(key=lambda r: r["best_overall"], reverse=True)

    # Add rank numbers
    for i, r in enumerate(rankings):
        r["rank"] = i + 1

    return {"rankings": rankings}


@router.get("/badges/{user_id}")
async def get_user_badges(user_id: str):
    """Get badges for a specific user."""
    all_runs = _load_all_runs()
    user_runs = [r for r in all_runs if r.get("user_id") == user_id]

    if not user_runs:
        return {"badges": [], "run_count": 0}

    badges = _compute_badges(user_runs, all_runs)
    return {
        "user_id": user_id,
        "badges": badges,
        "run_count": len(user_runs),
    }
