"""Lightweight auth helpers for the finance workbench."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from sqlalchemy.orm import Session

from app.config import config
from app.models import MembershipModel, UserModel, WorkspaceModel

try:
    from passlib.context import CryptContext
except Exception:  # pragma: no cover - fallback for minimal local envs
    CryptContext = None


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") if CryptContext else None


def hash_password(password: str) -> str:
    if _pwd_context:
        return _pwd_context.hash(password)
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return "pbkdf2$" + base64.urlsafe_b64encode(salt + digest).decode()


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$2") and _pwd_context:
        return _pwd_context.verify(password, password_hash)
    if password_hash.startswith("pbkdf2$"):
        raw = base64.urlsafe_b64decode(password_hash.split("$", 1)[1].encode())
        salt, expected = raw[:16], raw[16:]
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
        return hmac.compare_digest(actual, expected)
    return False


def _sign(payload_b64: str) -> str:
    digest = hmac.new(config.AUTH_SECRET.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def create_token(user_id: int) -> str:
    payload = {
        "sub": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + config.AUTH_TOKEN_TTL_SECONDS,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{payload_b64}.{_sign(payload_b64)}"


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        payload_b64, signature = token.split(".", 1)
        if not hmac.compare_digest(_sign(payload_b64), signature):
            return None
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def ensure_default_workspace(db: Session, user: UserModel) -> WorkspaceModel:
    membership = db.query(MembershipModel).filter(MembershipModel.user_id == user.id).first()
    if membership:
        return membership.workspace

    workspace = WorkspaceModel(name="Finance Research", slug=f"finance-{user.id}")
    db.add(workspace)
    db.flush()
    db.add(MembershipModel(user_id=user.id, workspace_id=workspace.id, role="admin"))
    db.commit()
    db.refresh(workspace)
    return workspace


def authenticate_or_bootstrap(db: Session, email: str, password: str, name: str | None = None) -> UserModel | None:
    normalized = email.strip().lower()
    user = db.query(UserModel).filter(UserModel.email == normalized).first()
    if user:
        return user if verify_password(password, user.password_hash) and user.is_active else None

    has_users = db.query(UserModel).first() is not None
    if has_users:
        return None

    user = UserModel(
        email=normalized,
        name=name or normalized.split("@", 1)[0],
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    ensure_default_workspace(db, user)
    db.refresh(user)
    return user


def get_user_by_token(db: Session, token: str | None) -> UserModel | None:
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    return db.query(UserModel).filter(UserModel.id == int(payload["sub"])).first()
