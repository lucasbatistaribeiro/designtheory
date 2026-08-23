"""Coleta de itens dos feeds RSS/Atom."""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone

import feedparser
import requests

from newsletter.config import Config, Source
from newsletter.models import Article, FetchReport

log = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Rodapés que os feeds grudam no fim do resumo e não dizem nada ao leitor.
_BOILERPLATE = [
    re.compile(r"\s*The post .{0,200}? appeared first on .{0,80}?\s*\.?\s*$", re.IGNORECASE),
    re.compile(r"\s*Continue reading on .{0,80}?\s*»?\s*$", re.IGNORECASE),
    re.compile(r"\s*(Read|Leia) (more|mais)( on| em| at)?[: ].{0,80}?\s*$", re.IGNORECASE),
    re.compile(r"\s*(Keep reading|Continue lendo).{0,80}?$", re.IGNORECASE),
    re.compile(r"\s*\[…\]\s*$"),
]


def strip_boilerplate(text: str) -> str:
    for pattern in _BOILERPLATE:
        text = pattern.sub("", text)
    return text.strip(" .·—-").strip()


def clean_text(value: str, limit: int | None = None, drop_boilerplate: bool = False) -> str:
    text = html.unescape(_TAG_RE.sub(" ", value or ""))
    text = _WS_RE.sub(" ", text).strip()
    if drop_boilerplate:
        text = strip_boilerplate(text)
    if limit and len(text) > limit:
        cut = text[:limit].rsplit(" ", 1)[0]
        text = f"{cut}…"
    return text


def _entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _entry_summary(entry, limit: int) -> str:
    for key in ("summary", "description"):
        if entry.get(key):
            return clean_text(entry[key], limit, drop_boilerplate=True)
    content = entry.get("content") or []
    if content and isinstance(content, list):
        return clean_text(content[0].get("value", ""), limit, drop_boilerplate=True)
    return ""


def fetch_source(source: Source, cfg: Config) -> tuple[list[Article], FetchReport]:
    """Baixa e converte um feed em artigos. Nunca levanta exceção."""
    timeout = int(cfg.collect.get("timeout", 15))
    user_agent = cfg.collect.get("user_agent", "DesignTheoryNewsletterBot/1.0")
    summary_chars = int(cfg.collect.get("summary_chars", 320))

    if source.type != "rss":
        return [], FetchReport(source.name, source.url, False, error=f"tipo não suportado: {source.type}")

    try:
        response = requests.get(
            source.url,
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "application/rss+xml, application/xml, text/xml, */*"},
        )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except Exception as exc:  # rede, DNS, TLS, HTTP…
        log.warning("falha ao buscar %s: %s", source.name, exc)
        return [], FetchReport(source.name, source.url, False, error=str(exc)[:200])

    if parsed.bozo and not parsed.entries:
        error = str(getattr(parsed, "bozo_exception", "feed inválido"))
        return [], FetchReport(source.name, source.url, False, error=error[:200])

    articles: list[Article] = []
    for entry in parsed.entries:
        link = (entry.get("link") or "").strip()
        title = clean_text(entry.get("title", ""))
        if not link or not title:
            continue
        articles.append(
            Article(
                title=title,
                url=link,
                source_name=source.name,
                source_category=source.category,
                published=_entry_datetime(entry),
                summary=_entry_summary(entry, summary_chars),
                author=clean_text(entry.get("author", "")),
            )
        )

    return articles, FetchReport(source.name, source.url, True, entries=len(articles))


def fetch_all(cfg: Config) -> tuple[list[Article], list[FetchReport]]:
    articles: list[Article] = []
    reports: list[FetchReport] = []
    for source in cfg.enabled_sources:
        items, report = fetch_source(source, cfg)
        articles.extend(items)
        reports.append(report)
        status = f"ok ({report.entries} itens)" if report.ok else f"erro ({report.error})"
        log.info("%s: %s", source.name, status)
    return articles, reports
