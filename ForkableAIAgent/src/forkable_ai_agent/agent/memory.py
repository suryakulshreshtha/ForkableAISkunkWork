"""Agent memory: what worked, where, and how often.

Self-healing is only useful if the repair is remembered. Every successful
resolution is scored and written to a JSON file keyed by *(page scope,
element description)*, so the next run tries the proven locator first and the
expensive healing path stays cold. The same file is the audit trail that
answers "which selectors has the app broken lately?".
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

MEMORY_VERSION = 2


def scope_for(url: str, namespace: str = "") -> str:
    """Page scope for a URL.

    Path only, so ports and query strings do not fragment the cache, optionally
    prefixed by a namespace so distinct environments keep distinct memories.
    """
    if not url:
        return f"{namespace}:*" if namespace else "*"
    parsed = urlparse(url)
    path = (parsed.path or "/").rstrip("/") or "/"
    return f"{namespace}:{path}" if namespace else path


@dataclass
class LocatorRecord:
    key: str
    strategy: str = ""
    hits: int = 0
    misses: int = 0
    healed: bool = False
    last_seen: float = field(default_factory=time.time)

    @property
    def confidence(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total) if total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Memory:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.locators: dict[str, list[LocatorRecord]] = {}
        self.runs: list[dict[str, Any]] = []
        self.load()

    # ------------------------------------------------------------------
    @staticmethod
    def _entry_key(description: str, scope: str) -> str:
        return f"{scope}::{description.strip().lower()}"

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for key, records in (data.get("locators") or {}).items():
            self.locators[key] = [
                LocatorRecord(**{k: v for k, v in r.items() if k in LocatorRecord.__dataclass_fields__})
                for r in records
            ]
        self.runs = list(data.get("runs") or [])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": MEMORY_VERSION,
            "updated_at": time.time(),
            "locators": {k: [r.to_dict() for r in v] for k, v in self.locators.items()},
            "runs": self.runs[-100:],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    def known_keys(self, description: str, scope: str = "*", min_confidence: float = 0.34) -> list[str]:
        """Proven locator keys for this description, best first."""
        records = list(self.locators.get(self._entry_key(description, scope), []))
        if scope != "*":
            records += list(self.locators.get(self._entry_key(description, "*"), []))
        good = [r for r in records if r.confidence >= min_confidence or r.hits > 0]
        good.sort(key=lambda r: (r.confidence, r.hits, r.last_seen), reverse=True)
        seen: set[str] = set()
        out: list[str] = []
        for record in good:
            if record.key not in seen:
                seen.add(record.key)
                out.append(record.key)
        return out

    def _find(self, entry: str, key: str) -> LocatorRecord | None:
        for record in self.locators.setdefault(entry, []):
            if record.key == key:
                return record
        return None

    def record_success(
        self, description: str, scope: str, key: str, strategy: str = "", healed: bool = False
    ) -> None:
        entry = self._entry_key(description, scope)
        record = self._find(entry, key)
        if record is None:
            record = LocatorRecord(key=key, strategy=strategy, healed=healed)
            self.locators[entry].append(record)
        record.hits += 1
        record.strategy = strategy or record.strategy
        record.healed = record.healed or healed
        record.last_seen = time.time()

    def record_failure(self, description: str, scope: str, key: str) -> None:
        entry = self._entry_key(description, scope)
        record = self._find(entry, key)
        if record is None:
            return  # never proven, nothing to demote
        record.misses += 1
        record.last_seen = time.time()

    def record_run(self, summary: dict[str, Any]) -> None:
        self.runs.append(summary)

    # ------------------------------------------------------------------
    def healing_report(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for entry, records in sorted(self.locators.items()):
            scope, _, description = entry.partition("::")
            for record in records:
                rows.append({
                    "scope": scope,
                    "description": description,
                    "locator": record.key,
                    "strategy": record.strategy,
                    "hits": record.hits,
                    "misses": record.misses,
                    "confidence": round(record.confidence, 3),
                    "healed": record.healed,
                })
        rows.sort(key=lambda r: (not r["healed"], -r["hits"]))
        return rows
