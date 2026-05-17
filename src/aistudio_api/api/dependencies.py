"""Shared FastAPI dependencies."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Header, HTTPException, Request

from aistudio_api.infrastructure.auth.api_key_store import get_api_key_store
from aistudio_api.infrastructure.gateway.client import AIStudioClient

from .state import runtime_state


def get_client() -> AIStudioClient:
    if runtime_state.client is None:
        raise HTTPException(503, detail={"message": "Client not initialized", "type": "service_unavailable"})
    return runtime_state.client


def get_busy_lock():
    if runtime_state.busy_lock is None:
        raise HTTPException(503, detail={"message": "Server not ready", "type": "service_unavailable"})
    return runtime_state.busy_lock


def get_account_service():
    if runtime_state.account_service is None:
        raise HTTPException(503, detail={"message": "Account service not initialized", "type": "service_unavailable"})
    return runtime_state.account_service


def get_runtime_state():
    return runtime_state


def _is_playground_request(request: Request) -> bool:
    """判断请求是否来自本地 Playground UI（同源 Referer + 标记头）。

    浏览器 fetch 自动带 Referer 且无法被脚本伪造跨源 Referer；
    再叠加自定义头 X-Aistudio-UI 双重确认，避免 Referer 被外部伪造的小概率问题。
    """
    referer = request.headers.get("referer", "")
    if not referer:
        return False
    try:
        ref = urlparse(referer)
    except ValueError:
        return False
    host = request.headers.get("host", "")
    if not host or ref.netloc != host:
        return False
    return request.headers.get("x-aistudio-ui") == "1"


def verify_api_key(
    request: Request,
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="x-api-key"),
) -> None:
    store = get_api_key_store()
    if not store.is_enabled():
        return
    if _is_playground_request(request):
        return
    key = None
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            key = parts[1].strip()
    if not key and x_api_key:
        key = x_api_key.strip()
    if not key:
        raise HTTPException(
            401,
            detail={"message": "Missing API key. Provide via Authorization: Bearer <key> or x-api-key header.", "type": "invalid_api_key"},
        )
    if not store.verify(key):
        raise HTTPException(
            401,
            detail={"message": "Invalid API key.", "type": "invalid_api_key"},
        )

