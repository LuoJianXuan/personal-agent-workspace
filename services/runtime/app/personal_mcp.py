"""Credential material stays within the Runtime transport boundary."""

import base64
from urllib.parse import quote

import httpx

from contracts.validate import validate
from .errors import RunError


def authentication_failed(error):
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in (401, 403)
    if isinstance(error, BaseExceptionGroup):
        return any(authentication_failed(item) for item in error.exceptions)
    return False


def sensitive_forms(token):
    return {token, quote(token, safe=""), base64.b64encode(token.encode()).decode()}


def contains_secret(value, token):
    if isinstance(value, str):
        return any(secret in value for secret in sensitive_forms(token))
    if isinstance(value, dict):
        return any(contains_secret(k, token) or contains_secret(v, token) for k, v in value.items())
    if isinstance(value, list):
        return any(contains_secret(item, token) for item in value)
    return False


def safe_result(text, token):
    for secret in sorted(sensitive_forms(token), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return text


async def material(engine, purpose, payload):
    try:
        response = await engine.backend.post(f"/internal/personal-mcp/{purpose}-material", json=payload)
        if len(response.content) > 8192:
            raise RunError("CONNECTION_SECRET_UNAVAILABLE")
        if response.status_code == 204 and payload.get("auth_failed"):
            return None
        result = response.json()
        if response.status_code != 200:
            code = result.get("code")
            known = {"CAPABILITY_CHANGED", "CONNECTION_REVOKED", "APPROVAL_REQUIRED", "APPROVAL_CONFLICT", "OUTCOME_UNKNOWN"}
            raise RunError(code if code in known else "CONNECTION_SECRET_UNAVAILABLE")
        validate("PersonalSecretMaterial", result)
        return result
    except RunError:
        raise
    except Exception:
        raise RunError("CONNECTION_SECRET_UNAVAILABLE") from None
