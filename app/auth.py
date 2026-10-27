"""Authentication: who is this, and can we prove it?

Three ideas live here, each an industry standard:

1. PASSWORD HASHING (bcrypt). We never store passwords — we store a
   bcrypt HASH: a one-way scramble. Login re-scrambles the typed password
   and compares scrambles. If our database ever leaks, attackers get
   unusable scrambles, not passwords. bcrypt is deliberately SLOW, which
   cripples guessing attacks.

2. TOKENS (JWT — JSON Web Token). After login we hand the client a
   signed note: "user 42, valid until Friday — signed, ClearDoc". The
   client sends it with every request (Authorization header). The
   signature means we can verify it WITHOUT a database lookup, and nobody
   can forge or alter it without our secret key.

3. RATE LIMITING. Login/signup allow only a few attempts per minute per
   address — password guessing becomes impractically slow.
"""

import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# The signing secret. In production this comes from the environment
# (Azure Key Vault later) — the dev fallback is fine ONLY locally.
SECRET = os.environ.get("CLEARDOC_SECRET", "dev-only-secret-change-me-0123456789abcdef")
TOKEN_LIFETIME_HOURS = 24


# ------------------------------------------------------------ passwords --

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# --------------------------------------------------------------- tokens --

def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,  # "subject": whom this token is about
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_LIFETIME_HOURS),
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


bearer = HTTPBearer(auto_error=False)


def current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    """Dependency: every protected endpoint asks 'who is calling?'
    No valid token → 401 Unauthorized, request never reaches the endpoint."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Login required.")
    try:
        payload = jwt.decode(credentials.credentials, SECRET, algorithms=["HS256"])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired — log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


# --------------------------------------------------------- rate limiting --

_attempts: dict[str, list[float]] = defaultdict(list)


def rate_limit(request: Request, limit: int = 10, window_seconds: int = 60):
    """Allow at most `limit` calls per `window_seconds` per client address."""
    key = request.client.host if request.client else "unknown"
    now = time.time()
    _attempts[key] = [t for t in _attempts[key] if now - t < window_seconds]
    if len(_attempts[key]) >= limit:
        raise HTTPException(status_code=429, detail="Too many attempts — wait a minute.")
    _attempts[key].append(now)
