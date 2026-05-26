"""User profile management and API keys."""
from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import _sessions, _users, _save_users, get_current_user_id

router = APIRouter(prefix="/users", tags=["users"])


class ProfileUpdate(BaseModel):
    bio: str | None = Field(None, max_length=500)
    x_handle: str | None = None
    github_username: str | None = None
    website: str | None = None


class APIKeyResponse(BaseModel):
    api_key: str
    created_at: str


@router.get("/me")
async def get_my_profile(user_id: str = Depends(get_current_user_id)):
    """Get current user's profile."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = _users.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user_id,
        "login": user.get("login"),
        "avatar_url": user.get("avatar_url"),
        "html_url": user.get("html_url"),
        "name": user.get("name"),
        "bio": user.get("bio"),
        "x_handle": user.get("x_handle"),
        "github_username": user.get("github_username"),
        "website": user.get("website"),
        "api_key": user.get("api_key"),
        "run_count": user.get("run_count", 0),
    }


@router.put("/me")
async def update_my_profile(
    update: ProfileUpdate,
    user_id: str = Depends(get_current_user_id),
):
    """Update current user's profile."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = _users.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update fields
    if update.bio is not None:
        user["bio"] = update.bio
    if update.x_handle is not None:
        user["x_handle"] = update.x_handle
    if update.github_username is not None:
        user["github_username"] = update.github_username
    if update.website is not None:
        user["website"] = update.website
    
    _save_users()
    
    return {"ok": True, "user": user}


@router.post("/me/api-key")
async def generate_api_key(user_id: str = Depends(get_current_user_id)):
    """Generate a new API key for CLI uploads."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = _users.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Generate new API key
    api_key = f"benchloop_{secrets.token_urlsafe(32)}"
    user["api_key"] = api_key
    
    import datetime
    user["api_key_created_at"] = datetime.datetime.now().isoformat()
    
    _save_users()
    
    return {
        "api_key": api_key,
        "created_at": user["api_key_created_at"],
    }


@router.delete("/me/api-key")
async def revoke_api_key(user_id: str = Depends(get_current_user_id)):
    """Revoke current API key."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = _users.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.pop("api_key", None)
    user.pop("api_key_created_at", None)
    _save_users()
    
    return {"ok": True}


@router.get("/{user_id}")
async def get_user_profile(user_id: str):
    """Get a user's public profile."""
    user = _users.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Return only public fields
    return {
        "id": user_id,
        "login": user.get("login"),
        "avatar_url": user.get("avatar_url"),
        "html_url": user.get("html_url"),
        "name": user.get("name"),
        "bio": user.get("bio"),
        "x_handle": user.get("x_handle"),
        "github_username": user.get("github_username"),
        "website": user.get("website"),
        "run_count": user.get("run_count", 0),
    }


@router.get("/me/runs")
async def get_my_runs(
    user_id: str = Depends(get_current_user_id),
    limit: int = 50,
):
    """Get current user's benchmark runs."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Load runs from disk
    from .benchmark import RUNS_DIR
    import json
    
    if not RUNS_DIR.exists():
        return {"runs": []}
    
    runs = []
    for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
        if len(runs) >= limit:
            break
        
        run_file = run_dir / "run.json"
        if not run_file.exists():
            continue
        
        try:
            data = json.loads(run_file.read_text())
            
            # Filter by user_id
            if data.get("user_id") != user_id:
                continue
            
            runs.append({
                "id": run_dir.name,
                "timestamp": data.get("timestamp", ""),
                "model": data.get("model", {}).get("model_id", "unknown"),
                "overall_score": data.get("overall_score", 0),
                "quality_score": data.get("quality_score", 0),
                "speed_score": data.get("speed_score", 0),
                "reliability_score": data.get("reliability_score", 0),
                "is_remote": data.get("is_remote", False),
            })
        except Exception:
            continue
    
    return {"runs": runs}


def verify_api_key(api_key: str | None = None) -> str | None:
    """Verify API key and return user_id."""
    if not api_key:
        return None
    
    for user_id, user in _users.items():
        if user.get("api_key") == api_key:
            return user_id
    
    return None
