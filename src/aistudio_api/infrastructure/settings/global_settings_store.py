"""全局下游设置存储。"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

_VALID_SEARCH_MODES = {"auto", "always_on", "always_off"}
_VALID_THINKING = {"off", "low", "medium", "high"}
_VALID_SAFETY = {"on", "off"}


@dataclass
class GlobalSettings:
    google_search_mode: str = "auto"
    safety: str = "on"
    default_thinking: str = "off"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GlobalSettings":
        result = cls()
        mode = data.get("google_search_mode")
        if mode in _VALID_SEARCH_MODES:
            result.google_search_mode = mode
        safety = data.get("safety")
        if safety in _VALID_SAFETY:
            result.safety = safety
        thinking = data.get("default_thinking")
        if thinking in _VALID_THINKING:
            result.default_thinking = thinking
        return result


def _resolve_settings_path() -> Path:
    env = os.getenv("AISTUDIO_GLOBAL_SETTINGS_FILE")
    if env:
        return Path(env).resolve()
    roots = [
        Path.cwd(),
        Path(__file__).resolve().parents[4],
    ]
    for root in roots:
        candidate = root / "data"
        if candidate.is_dir():
            return candidate / "global_settings.json"
    return (roots[0] / "data" / "global_settings.json").resolve()


class GlobalSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _resolve_settings_path()
        self._lock = threading.Lock()
        self._cache: GlobalSettings | None = None

    def _load_unlocked(self) -> GlobalSettings:
        if self._cache is not None:
            return self._cache
        if not self._path.exists():
            self._cache = GlobalSettings()
            return self._cache
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._cache = GlobalSettings.from_dict(data)
        except (json.JSONDecodeError, OSError):
            self._cache = GlobalSettings()
        return self._cache

    def get(self) -> GlobalSettings:
        with self._lock:
            settings = self._load_unlocked()
            return GlobalSettings(
                google_search_mode=settings.google_search_mode,
                safety=settings.safety,
                default_thinking=settings.default_thinking,
            )

    def update(
        self,
        *,
        google_search_mode: str | None = None,
        safety: str | None = None,
        default_thinking: str | None = None,
    ) -> GlobalSettings:
        with self._lock:
            settings = self._load_unlocked()
            if google_search_mode is not None:
                if google_search_mode not in _VALID_SEARCH_MODES:
                    raise ValueError(f"google_search_mode 必须是 {sorted(_VALID_SEARCH_MODES)}")
                settings.google_search_mode = google_search_mode
            if safety is not None:
                if safety not in _VALID_SAFETY:
                    raise ValueError(f"safety 必须是 {sorted(_VALID_SAFETY)}")
                settings.safety = safety
            if default_thinking is not None:
                if default_thinking not in _VALID_THINKING:
                    raise ValueError(f"default_thinking 必须是 {sorted(_VALID_THINKING)}")
                settings.default_thinking = default_thinking
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._cache = settings
            return GlobalSettings(
                google_search_mode=settings.google_search_mode,
                safety=settings.safety,
                default_thinking=settings.default_thinking,
            )


_store: GlobalSettingsStore | None = None


def get_global_settings_store() -> GlobalSettingsStore:
    global _store
    if _store is None:
        _store = GlobalSettingsStore()
    return _store
