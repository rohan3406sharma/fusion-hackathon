"""Process-wide application state: dataset, run caches."""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Any, Callable

from ..config import get_settings
from ..domain.dataset import FnbDataset
from ..schemas.scenario import ScenarioSpec


class LRU:
    def __init__(self, size: int):
        self.size, self.d = size, OrderedDict()

    def get_or_set(self, key: str, fn: Callable[[], Any]) -> Any:
        if key in self.d:
            self.d.move_to_end(key)
            return self.d[key]
        val = fn()
        self.d[key] = val
        while len(self.d) > self.size:
            self.d.popitem(last=False)
        return val

    def clear(self) -> None:
        self.d.clear()


class AppState:
    def __init__(self, dataset: FnbDataset):
        self.dataset = dataset
        self.cache = LRU(get_settings().run_cache_size)


_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState(FnbDataset.load(get_settings().data_dir))
    return _state


def reset_state() -> None:
    global _state
    _state = None


def spec_key(spec: ScenarioSpec, *extra) -> str:
    raw = json.dumps([spec.model_dump(mode="json"), extra], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()
