"""X (Twitter) OAuth 2.0 authentication."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["auth"])

# X OAuth credentials
X_CLIENT_ID = os.environ.get("BENCHLOOP_X_CLIENT_ID", "")
X_CLIENT_SECRET = os.environ.get("BENCHLOOP_X_CLIENT_SECRET", "")
X_REDIRECT_URI = os.environ.get("BENCHLOOP_X_REDIRECT_URI", "http://localhost:8877/api/auth/x/callback")

# Reuse session/user storage from auth.py
from .auth import _sessions, _users, _save_users


@router.get("/x")
async def x_login():
    """Redirect to X OAuth."""
    if not X_CLIENT_ID:
        raise HTTPException(status_code=500, detail="X OAuth not configured")
    
    state = secrets.token_urlsafe(32)
    # X OAuth 2.0 PKCE flow
    code_verifier = secrets.token_urlsafe(32)
    
    # Store state for verification
    _sessions[f"state_{state}"] = {"code_verifier": code_verifier}
    
    import hashlib
    import base64
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip("=")
    
    url = (
        f"https://twitter.com/i/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={X_CLIENT_ID}"
        f"&redirect_uri={X_REDIRECT_URI}"
        f"&scope=users.read%20tweet.read"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )
    return RedirectResponse(url)


@router.get("/x/callback")
async def x_callback(code: str, state: str):
    """Handle X OAuth callback."""
    if not X_CLIENT_ID or not X_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="X OAuth not configured")
    
    # Verify state
    state_data = _sessions.get(f"state_{state}")
    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid state")
    
    code_verifier = state_data["code_verifier"]
    del _sessions[f"state_{state}"]
    
    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        # X requires Basic auth for token exchange
        import base64
        auth_string = base64.b64encode(
            f"{X_CLIENT_ID}:{X_CLIENT_SECRET}".encode()
        ).decode()
        
        token_resp = await client.post(
            "https://api.twitter.com/2/oauth2/token",
            data={
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": X_REDIRECT_URI,
                "code_verifier": code_verifier,
            },
            headers={
                "Authorization": f"Basic {auth_string}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {token_resp.text}")
        
        token_data = token_resp.json()
        access_token = token_data["access_token"]
        
        # Fetch user info
        user_resp = await client.get(
            "https://api.twitter.com/2/users/me",
            params={"user.fields": "profile_image_url,description"},
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )
        
        if user_resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"User fetch failed: {user_resp.text}")
        
        user_data = user_resp.json()["data"]
    
    # Create or update user
    x_id = user_data["id"]
    session_token = secrets.token_urlsafe(32)
    
    _users[f"x_{x_id}"] = {
        "x_id": x_id,
        "login": user_data["username"],
        "avatar_url": user_data.get("profile_image_url", ""),
        "html_url": f"https://x.com/{user_data['username']}",
        "name": user_data.get("name"),
        "bio": user_data.get("description"),
        "session_token": session_token,
        "provider": "x",
    }
    _save_users()
    
    _sessions[session_token] = {"user_id": f"x_{x_id}"}
    
    # Redirect to dashboard with session cookie
    response = RedirectResponse("/", status_code=302)
    response.set_cookie(
        key="benchloop_session",
        value=session_token,
        httponly=True,
        max_age=60 * 60 * 24 * 30,  # 30 days
    )
    return response
