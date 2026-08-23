"""Estruturas de dados compartilhadas."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

_TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|mc_cid|mc_eid|ref|source$)")


def strip_tracking(url: str) -> str:
    """Remove parâmetros de tracking sem mexer em host, caminho ou barra final."""
    parts = urlsplit(url.strip())
    query = "&".join(
        piece
        for piece in parts.query.split("&")
        if piece and not _TRACKING_PARAMS.match(piece.split("=", 1)[0].lower())
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def canonical_url(url: str) -> str:
    """Remove parâmetros de tracking e normaliza a URL para deduplicação."""
    parts = urlsplit(url.strip())
    query = "&".join(
        piece
        for piece in parts.query.split("&")
        if piece and not _TRACKING_PARAMS.match(piece.split("=", 1)[0].lower())
    )
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


@dataclass
class Article:
    title: str
    url: str
    source_name: str
    source_category: str = "Geral"
    published: datetime | None = None
    summary: str = ""
    author: str = ""
    score: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)

    @property
    def canonical(self) -> str:
        return canonical_url(self.url)

    @property
    def clean_url(self) -> str:
        """URL para exibir: sem tracking, mas com host e caminho intactos."""
        return strip_tracking(self.url)

    @property
    def fingerprint(self) -> str:
        """Chave estável usada no arquivo de estado."""
        base = f"{self.canonical}|{self.title.strip().lower()}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]

    @property
    def domain(self) -> str:
        return urlsplit(self.url).netloc.lower().removeprefix("www.")


@dataclass
class FetchReport:
    source_name: str
    url: str
    ok: bool
    entries: int = 0
    error: str = ""
