from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from ace_api import db
from ace_api.config import settings
from ace_api.security import make_token, new_otp

router = APIRouter(prefix="/auth", tags=["auth"])


class OtpRequest(BaseModel):
    email: EmailStr


class OtpVerify(BaseModel):
    email: EmailStr
    code: str


@router.post("/otp")
async def request_otp(body: OtpRequest):
    code = new_otp()
    await db.execute(
        "INSERT INTO otp_codes (email, code, expires_at) VALUES (%s,%s,%s)",
        (body.email.lower(), code, datetime.now(timezone.utc) + timedelta(minutes=10)))
    # Email delivery lands with beta infra; dev echoes the code so the flow is fully usable.
    return {"sent": True, **({"dev_code": code} if settings().otp_dev_echo else {})}


@router.post("/verify")
async def verify_otp(body: OtpVerify):
    row = await db.fetch_one(
        """SELECT * FROM otp_codes WHERE email=%s AND code=%s AND NOT used AND expires_at > now()
           ORDER BY expires_at DESC LIMIT 1""", (body.email.lower(), body.code))
    if not row:
        raise HTTPException(401, "invalid or expired code")
    await db.execute("UPDATE otp_codes SET used=true WHERE email=%s AND code=%s",
                     (body.email.lower(), body.code))
    user = await db.fetch_one("SELECT * FROM users WHERE email=%s", (body.email.lower(),))
    if not user:
        user = await db.fetch_one("INSERT INTO users (email) VALUES (%s) RETURNING *",
                                  (body.email.lower(),))
    return {"token": make_token(user["id"]),
            "user": {"id": user["id"], "email": user["email"],
                     "selected_model": user["selected_model"]}}
