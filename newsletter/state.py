"""Estado entre edições: lembra o que já foi enviado."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


class State:
    def __init__(self, path: Path, retention_days: int = 180) -> None:
        self.path = path
        self.retention_days = retention_days
        self.seen: dict[str, str] = {}
        self.issues: list[str] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self.seen = dict(data.get("seen", {}))
        self.issues = list(data.get("issues", []))

    def knows(self, fingerprint: str) -> bool:
        return fingerprint in self.seen

    def remember(self, fingerprints: list[str], when: datetime | None = None) -> None:
        stamp = (when or datetime.now(timezone.utc)).date().isoformat()
        for fp in fingerprints:
            self.seen.setdefault(fp, stamp)

    def record_issue(self, slug: str) -> None:
        if slug not in self.issues:
            self.issues.append(slug)

    def prune(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=self.retention_days)).date().isoformat()
        stale = [fp for fp, day in self.seen.items() if day < cutoff]
        for fp in stale:
            del self.seen[fp]
        return len(stale)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "issues": self.issues,
            "seen": self.seen,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
