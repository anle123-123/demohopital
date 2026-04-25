"""
JWT Authentication Module for HOPITAL
Provides JWT token generation/verification alongside Flask session auth.
"""

import os
import jwt
import functools
from datetime import datetime, timedelta, timezone
from flask import request, session, jsonify, g

JWT_SECRET = os.getenv("JWT_SECRET", "hopital-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_DAYS = 7
REFRESH_TOKEN_DAYS = 30


def generate_tokens(user: str, role: str, manhanvien: str = None, mabenhnhan: str = None):
    """Generate access + refresh tokens."""
    now = datetime.now(timezone.utc)
    access_payload = {
        "sub": user,
        "role": role,
        "manv": manhanvien,
        "mabn": mabenhnhan,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(days=ACCESS_TOKEN_DAYS),
    }
    refresh_payload = {
        "sub": user,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_DAYS),
    }
    access_token = jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    refresh_token = jwt.encode(refresh_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return access_token, refresh_token


def verify_token(token: str):
    """Verify and decode a JWT token. Returns payload dict or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user():
    """
    Get current user from JWT header OR Flask session.
    Sets g.current_user with: user, role, manv, mabn
    Returns True if authenticated, False otherwise.
    """
    # 1. Try JWT from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = verify_token(token)
        if payload and payload.get("type") == "access":
            g.current_user = {
                "user": payload["sub"],
                "role": payload.get("role", "patient"),
                "manv": payload.get("manv"),
                "mabn": payload.get("mabn"),
            }
            return True

    # 2. Fallback to Flask session
    if session.get("user"):
        g.current_user = {
            "user": session["user"],
            "role": session.get("role", "patient"),
            "manv": session.get("manv"),
            "mabn": session.get("mabn"),
        }
        return True

    return False


def jwt_or_session(f):
    """Decorator: require auth via JWT or session. Returns 401 if neither."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


def jwt_or_session_role(*allowed_roles):
    """Decorator factory: require auth + specific role(s)."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if not get_current_user():
                return jsonify({"error": "Unauthorized"}), 401
            if g.current_user["role"] not in allowed_roles:
                return jsonify({"error": "Forbidden"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator
