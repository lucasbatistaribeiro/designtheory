"""Carregamento de configuração (config.yml + sources.yml)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    category: str = "Geral"
    type: str = "rss"
    weight: float = 1.0
    enabled: bool = True


@dataclass
class Config:
    raw: dict[str, Any]
    sources: list[Source]
    root: Path = ROOT

    # --- atalhos de leitura -------------------------------------------------
    @property
    def newsletter(self) -> dict[str, Any]:
        return self.raw.get("newsletter", {})

    @property
    def collect(self) -> dict[str, Any]:
        return self.raw.get("collect", {})

    @property
    def ranking(self) -> dict[str, Any]:
        return self.raw.get("ranking", {})

    @property
    def output(self) -> dict[str, Any]:
        return self.raw.get("output", {})

    @property
    def delivery(self) -> dict[str, Any]:
        return self.raw.get("delivery", {})

    @property
    def state_path(self) -> Path:
        rel = self.raw.get("state", {}).get("path", "data/state.json")
        return self.root / rel

    @property
    def retention_days(self) -> int:
        return int(self.raw.get("state", {}).get("retention_days", 180))

    @property
    def output_dir(self) -> Path:
        return self.root / self.output.get("dir", "issues")

    @property
    def enabled_sources(self) -> list[Source]:
        return [s for s in self.sources if s.enabled]

    def recipients(self) -> list[str]:
        """Destinatários do config.yml mesclados com NEWSLETTER_RECIPIENTS."""
        listed = list(self.delivery.get("recipients") or [])
        env = os.environ.get("NEWSLETTER_RECIPIENTS", "")
        listed += [e.strip() for e in env.split(",") if e.strip()]
        # dedup preservando ordem
        seen: set[str] = set()
        out: list[str] = []
        for email in listed:
            if email.lower() not in seen:
                seen.add(email.lower())
                out.append(email)
        return out


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(
    config_path: Path | None = None,
    sources_path: Path | None = None,
    root: Path | None = None,
) -> Config:
    root = root or ROOT
    raw = _read_yaml(config_path or root / "config.yml")
    src_raw = _read_yaml(sources_path or root / "sources.yml")

    sources: list[Source] = []
    for item in src_raw.get("sources", []):
        if not item.get("name") or not item.get("url"):
            continue
        sources.append(
            Source(
                name=item["name"],
                url=item["url"],
                category=item.get("category", "Geral"),
                type=item.get("type", "rss"),
                weight=float(item.get("weight", 1.0)),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return Config(raw=raw, sources=sources, root=root)
