"""Authentication routes - GitHub OAuth."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

# GitHub OAuth credentials (from environment)
GITHUB_CLIENT_ID = os.environ.get("BENCHLOOP_GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("BENCHLOOP_GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.environ.get("BENCHLOOP_GITHUB_REDIRECT_URI", "http://localhost:8877/api/auth/github/callback")

# Session storage (in production, use Redis or database)
_sessions: dict[str, dict] = {}
_users: dict[str, dict] = {}

# Load users from disk on startup
_USERS_FILE = Path.home() / ".bench-loop" / "users.json"
if _USERS_FILE.exists():
    import json
    _users = json.loads(_USERS_FILE.read_text())


def _save_users():
    """Persist users to disk."""
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    _USERS_FILE.write_text(json.dumps(_users, indent=2))


class GitHubUser(BaseModel):
    login: str
    id: int
    avatar_url: str
    html_url: str
    name: str | None = None
    bio: str | None = None


@router.get("/github")
async def github_login():
    """Redirect to GitHub OAuth."""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")
    
    state = secrets.token_urlsafe(32)
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI}"
        f"&scope=user:email"
        f"&state={state}"
    )
    return RedirectResponse(url)


@router.get("/github/callback")
async def github_callback(code: str, state: str):
    """Handle GitHub OAuth callback."""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")
    
    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )
        token_data = token_resp.json()
        
        if "error" in token_data:
            raise HTTPException(status_code=400, detail=token_data["error"])
        
        access_token = token_data["access_token"]
        
        # Fetch user info
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        user_data = user_resp.json()
    
    # Create or update user
    github_id = str(user_data["id"])
    session_token = secrets.token_urlsafe(32)
    
    _users[github_id] = {
        "github_id": github_id,
        "login": user_data["login"],
        "avatar_url": user_data["avatar_url"],
        "html_url": user_data["html_url"],
        "name": user_data.get("name"),
        "bio": user_data.get("bio"),
        "session_token": session_token,
    }
    _save_users()
    
    _sessions[session_token] = {"github_id": github_id}
    
    # Redirect to dashboard with session cookie
    response = RedirectResponse("/", status_code=302)
    response.set_cookie(
        key="benchloop_session",
        value=session_token,
        httponly=True,
        max_age=60 * 60 * 24 * 30,  # 30 days
    )
    return response


@router.get("/me")
async def get_current_user(benchloop_session: str | None = None):
    """Get current authenticated user."""
    if not benchloop_session or benchloop_session not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    github_id = _sessions[benchloop_session]["github_id"]
    user = _users.get(github_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "login": user["login"],
        "avatar_url": user["avatar_url"],
        "html_url": user["html_url"],
        "name": user.get("name"),
        "bio": user.get("bio"),
    }


@router.post("/logout")
async def logout(benchloop_session: str | None = None):
    """Logout current user."""
    if benchloop_session and benchloop_session in _sessions:
        del _sessions[benchloop_session]
    
    response = Response()
    response.delete_cookie("benchloop_session")
    return {"ok": True}


def get_current_user_id(benchloop_session: str | None = None) -> str | None:
    """Dependency to get current user ID."""
    if not benchloop_session or benchloop_session not in _sessions:
        return None
    return _sessions[benchloop_session]["github_id"]
