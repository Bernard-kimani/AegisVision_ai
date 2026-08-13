"""
PromptStore - versioned storage for strategy/agent prompts.

Local-file implementation for v1 (one JSON file per strategy, holding a list of
versions). Swapping to a Supabase-backed implementation later means writing a
second class against the same PromptStore interface - callers never change.
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class PromptVersion:
    strategy_name: str
    version: int
    text: str
    created_at: str
    notes: str = ""


class PromptStore(ABC):
    @abstractmethod
    def save_prompt(self, strategy_name: str, text: str, notes: str = "") -> PromptVersion:
        """Save a new version of a prompt. Never overwrites prior versions."""

    @abstractmethod
    def get_latest(self, strategy_name: str) -> Optional[PromptVersion]:
        """Get the most recent version of a prompt, or None if it doesn't exist yet."""

    @abstractmethod
    def get_version(self, strategy_name: str, version: int) -> Optional[PromptVersion]:
        """Get a specific historical version."""

    @abstractmethod
    def list_versions(self, strategy_name: str) -> List[PromptVersion]:
        """List all versions of a prompt, oldest first."""

    @abstractmethod
    def list_strategies(self) -> List[str]:
        """List all strategy names that have at least one stored prompt version."""


class LocalFilePromptStore(PromptStore):
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def _path(self, strategy_name: str) -> str:
        safe_name = "".join(c for c in strategy_name if c.isalnum() or c in ("-", "_")) or "default"
        return os.path.join(self.storage_dir, f"{safe_name}.json")

    def _load_all(self, strategy_name: str) -> List[PromptVersion]:
        path = self._path(strategy_name)
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [PromptVersion(**item) for item in raw]

    def _write_all(self, strategy_name: str, versions: List[PromptVersion]) -> None:
        path = self._path(strategy_name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump([asdict(v) for v in versions], f, indent=2, ensure_ascii=False)

    def save_prompt(self, strategy_name: str, text: str, notes: str = "") -> PromptVersion:
        versions = self._load_all(strategy_name)
        next_version = (versions[-1].version + 1) if versions else 1
        record = PromptVersion(
            strategy_name=strategy_name,
            version=next_version,
            text=text,
            created_at=datetime.now().isoformat(),
            notes=notes,
        )
        versions.append(record)
        self._write_all(strategy_name, versions)
        return record

    def get_latest(self, strategy_name: str) -> Optional[PromptVersion]:
        versions = self._load_all(strategy_name)
        return versions[-1] if versions else None

    def get_version(self, strategy_name: str, version: int) -> Optional[PromptVersion]:
        for v in self._load_all(strategy_name):
            if v.version == version:
                return v
        return None

    def list_versions(self, strategy_name: str) -> List[PromptVersion]:
        return self._load_all(strategy_name)

    def list_strategies(self) -> List[str]:
        if not os.path.exists(self.storage_dir):
            return []
        return [
            os.path.splitext(f)[0]
            for f in os.listdir(self.storage_dir)
            if f.endswith(".json")
        ]
