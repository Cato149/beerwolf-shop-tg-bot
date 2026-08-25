import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from beerwolf_shop.application.auth import create_access_token, validate_telegram_init_data
from beerwolf_shop.domain.exceptions import AuthError

from tests.fakes import make_test_settings


def make_init_data(bot_token: str, user_id: int = 99) -> str:
    user = json.dumps({"id": user_id, "first_name": "Ann", "username": "ann"}, separators=(",", ":"))
    pairs = {"auth_date": str(int(time.time())), "query_id": "AA", "user": user}
    data_check = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**pairs, "hash": digest})


def test_init_data_ok() -> None:
    token = "123:test"
    user = validate_telegram_init_data(make_init_data(token), token)
    assert user["id"] == 99
    assert user["username"] == "ann"


def test_init_data_bad_hash() -> None:
    with pytest.raises(AuthError):
        validate_telegram_init_data("auth_date=1&hash=dead&user={}", "123:test")


def test_init_data_missing_auth_date() -> None:
    token = "123:test"
    user = json.dumps({"id": 1, "first_name": "A"}, separators=(",", ":"))
    pairs = {"query_id": "AA", "user": user}
    data_check = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(AuthError, match="missing_auth_date"):
        validate_telegram_init_data(urlencode({**pairs, "hash": digest}), token)


def test_jwt_roundtrip() -> None:
    settings = make_test_settings()
    token = create_access_token(settings, 42)
    from beerwolf_shop.application.auth import decode_access_token

    payload = decode_access_token(settings, token)
    assert payload["sub"] == "42"
