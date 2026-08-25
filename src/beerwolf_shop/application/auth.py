"""Telegram initData validation and customer JWT helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, unquote

import jwt

from beerwolf_shop.config import Settings
from beerwolf_shop.domain.exceptions import AuthError


def validate_telegram_init_data(init_data: str, bot_token: str, *, max_age_seconds: int = 86400) -> dict[str, Any]:
    """Validate Telegram Mini App initData as documented by Telegram.

    secret_key = HMAC_SHA256(key=b"WebAppData", msg=bot_token)
    hash = HMAC_SHA256(secret_key, data_check_string)
    """
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise AuthError("missing_hash")
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise AuthError("invalid_hash")
    auth_date = int(pairs.get("auth_date") or 0)
    if auth_date and time.time() - auth_date > max_age_seconds:
        raise AuthError("expired")
    user_raw = pairs.get("user")
    if not user_raw:
        raise AuthError("missing_user")
    try:
        user = json.loads(unquote(user_raw))
    except json.JSONDecodeError as exc:
        raise AuthError("invalid_user") from exc
    return user


def create_access_token(settings: Settings, telegram_id: int, is_admin: bool = False) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(telegram_id), "adm": is_admin, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(settings: Settings, token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AuthError("invalid_token") from exc
