"""API Key 存储层，管理访问鉴权密钥。"""

from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ApiKeyMeta:
    id: str
    key: str
    name: str
    created_at: str
    last_used: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApiKeyMeta":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def masked_key(self) -> str:
        if len(self.key) <= 8:
            return self.key[:2] + "****"
        return self.key[:6] + "****" + self.key[-4:]


def _resolve_keys_path() -> Path:
    env = os.getenv("AISTUDIO_API_KEYS_FILE")
    if env:
        return Path(env).resolve()
    roots = [
        Path.cwd(),
        Path(__file__).resolve().parents[4],
    ]
    for root in roots:
        candidate = root / "data"
        if candidate.is_dir():
            return candidate / "api_keys.json"
    return (roots[0] / "data" / "api_keys.json").resolve()


def _generate_key_id() -> str:
    return f"k_{secrets.token_hex(4)}"


class ApiKeyStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _resolve_keys_path()
        self._lock = threading.Lock()
        self._keys: dict[str, ApiKeyMeta] | None = None
        self._key_set: set[str] | None = None

    def _load_unlocked(self) -> dict[str, ApiKeyMeta]:
        if self._keys is not None:
            return self._keys
        if not self._path.exists():
            self._keys = {}
            self._key_set = set()
            return self._keys
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            keys_list = data.get("keys", [])
            self._keys = {k["id"]: ApiKeyMeta.from_dict(k) for k in keys_list}
            self._key_set = {meta.key for meta in self._keys.values()}
        except (json.JSONDecodeError, OSError, KeyError):
            self._keys = {}
            self._key_set = set()
        return self._keys

    def _save_unlocked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"keys": [meta.to_dict() for meta in (self._keys or {}).values()]}
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._key_set = {meta.key for meta in (self._keys or {}).values()}

    def is_enabled(self) -> bool:
        with self._lock:
            keys = self._load_unlocked()
            return len(keys) > 0

    def verify(self, key: str) -> bool:
        with self._lock:
            self._load_unlocked()
            if not self._key_set:
                return True
            valid = key in self._key_set
            if valid:
                for meta in self._keys.values():
                    if meta.key == key:
                        meta.last_used = datetime.now(timezone.utc).isoformat()
                        break
                self._save_unlocked()
            return valid

    def list_keys(self) -> list[ApiKeyMeta]:
        with self._lock:
            return list(self._load_unlocked().values())

    def create_key(self, name: str, key_value: str | None = None) -> ApiKeyMeta:
        with self._lock:
            keys = self._load_unlocked()
            key_id = _generate_key_id()
            if key_value is None or len(key_value.strip()) < 8:
                key_value = f"sk-aip-{secrets.token_hex(16)}"
            else:
                key_value = key_value.strip()
            now = datetime.now(timezone.utc).isoformat()
            meta = ApiKeyMeta(id=key_id, key=key_value, name=name, created_at=now)
            keys[key_id] = meta
            self._save_unlocked()
            return meta

    def delete_key(self, key_id: str) -> bool:
        with self._lock:
            keys = self._load_unlocked()
            if key_id not in keys:
                return False
            del keys[key_id]
            self._save_unlocked()
            return True

    def update_key(self, key_id: str, name: str) -> ApiKeyMeta | None:
        with self._lock:
            keys = self._load_unlocked()
            if key_id not in keys:
                return None
            keys[key_id].name = name
            self._save_unlocked()
            return keys[key_id]


_store: ApiKeyStore | None = None


def get_api_key_store() -> ApiKeyStore:
    global _store
    if _store is None:
        _store = ApiKeyStore()
    return _store
