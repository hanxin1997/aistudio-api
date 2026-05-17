"""API Key 管理路由（管理面板使用，自身不鉴权）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aistudio_api.infrastructure.auth.api_key_store import ApiKeyMeta, get_api_key_store

router = APIRouter(prefix="/api/keys")


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    masked_key: str
    created_at: str
    last_used: str | None = None


class ApiKeyCreatedResponse(ApiKeyResponse):
    key: str  # 仅创建时返回完整 key


class CreateKeyRequest(BaseModel):
    name: str
    key: str | None = None  # 可选自定义；不传则自动生成


class UpdateKeyRequest(BaseModel):
    name: str


def _to_response(meta: ApiKeyMeta) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=meta.id,
        name=meta.name,
        masked_key=meta.masked_key(),
        created_at=meta.created_at,
        last_used=meta.last_used,
    )


@router.get("", response_model=list[ApiKeyResponse])
async def list_keys():
    return [_to_response(m) for m in get_api_key_store().list_keys()]


@router.post("", response_model=ApiKeyCreatedResponse)
async def create_key(req: CreateKeyRequest):
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, detail="名称不能为空")
    if req.key is not None and len(req.key.strip()) < 8:
        raise HTTPException(400, detail="自定义 key 至少 8 个字符")
    meta = get_api_key_store().create_key(name=name, key_value=req.key)
    return ApiKeyCreatedResponse(
        id=meta.id,
        name=meta.name,
        masked_key=meta.masked_key(),
        created_at=meta.created_at,
        last_used=meta.last_used,
        key=meta.key,
    )


@router.put("/{key_id}", response_model=ApiKeyResponse)
async def update_key(key_id: str, req: UpdateKeyRequest):
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, detail="名称不能为空")
    meta = get_api_key_store().update_key(key_id, name)
    if meta is None:
        raise HTTPException(404, detail="密钥不存在")
    return _to_response(meta)


@router.delete("/{key_id}")
async def delete_key(key_id: str):
    if not get_api_key_store().delete_key(key_id):
        raise HTTPException(404, detail="密钥不存在")
    return {"ok": True}
