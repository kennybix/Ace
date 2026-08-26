from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ace_api import db
from ace_api.config import settings

bearer = HTTPBearer(auto_error=False)


def make_token(user_id: int) -> str:
    return jwt.encode({"sub": str(user_id),
                       "exp": datetime.now(timezone.utc) + timedelta(days=90)},
                      settings().jwt_secret, algorithm="HS256")


async def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not cred:
        raise HTTPException(401, "missing bearer token")
    try:
        data = jwt.decode(cred.credentials, settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid token")
    user = await db.fetch_one("SELECT * FROM users WHERE id=%s", (int(data["sub"]),))
    if not user:
        raise HTTPException(401, "user not found")
    return user


def new_otp() -> str:
    return f"{secrets.randbelow(1000000):06d}"


async def owned_exam(exam_id: int, user: dict) -> dict:
    exam = await db.fetch_one("SELECT * FROM exams WHERE id=%s AND user_id=%s", (exam_id, user["id"]))
    if not exam:
        raise HTTPException(404, "exam not found")
    return exam
