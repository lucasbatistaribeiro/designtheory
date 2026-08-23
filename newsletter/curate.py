"""Filtragem, pontuação e agrupamento dos itens coletados."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from newsletter.config import Config
from newsletter.models import Article
from newsletter.state import State


def within_window(articles: list[Article], window_days: int, now: datetime | None = None) -> list[Article]:
    """Mantém itens publicados na janela. Itens sem data entram (feed sem timestamp)."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    return [a for a in articles if a.published is None or a.published >= cutoff]


def drop_blocked(articles: list[Article], blocklist: list[str]) -> list[Article]:
    terms = [t.lower() for t in blocklist or []]
    if not terms:
        return articles
    kept = []
    for article in articles:
        haystack = f"{article.title} {article.summary}".lower()
        if not any(term in haystack for term in terms):
            kept.append(article)
    return kept


def dedupe(articles: list[Article], state: State | None = None) -> list[Article]:
    """Remove repetições dentro da edição e itens já enviados em edições passadas."""
    seen: set[str] = set()
    kept: list[Article] = []
    for article in articles:
        fp = article.fingerprint
        if fp in seen:
            continue
        if state is not None and state.knows(fp):
            continue
        seen.add(fp)
        kept.append(article)
    return kept


def score(articles: list[Article], cfg: Config) -> list[Article]:
    keywords = {k.lower(): float(v) for k, v in (cfg.ranking.get("keywords") or {}).items()}
    weights = {s.name: s.weight for s in cfg.sources}
    now = datetime.now(timezone.utc)

    for article in articles:
        haystack = f"{article.title} {article.summary}".lower()
        matched = [kw for kw in keywords if kw in haystack]
        base = sum(keywords[kw] for kw in matched)
        # frescor: itens mais recentes ganham um leve empurrão
        if article.published:
            age_days = max((now - article.published).total_seconds() / 86400, 0)
            base += max(0.0, 2.0 - age_days * 0.25)
        article.matched_keywords = sorted(matched)
        article.score = round(base * weights.get(article.source_name, 1.0), 3)
    return articles


def cap_per_source(articles: list[Article], max_per_source: int) -> list[Article]:
    if max_per_source <= 0:
        return articles
    counts: dict[str, int] = {}
    kept: list[Article] = []
    for article in articles:
        used = counts.get(article.source_name, 0)
        if used >= max_per_source:
            continue
        counts[article.source_name] = used + 1
        kept.append(article)
    return kept


def curate(articles: list[Article], cfg: Config, state: State | None = None) -> list[Article]:
    """Pipeline completo de curadoria: janela -> blocklist -> dedup -> score -> limites."""
    items = within_window(articles, int(cfg.collect.get("window_days", 7)))
    items = drop_blocked(items, cfg.ranking.get("blocklist") or [])
    items = dedupe(items, state)
    items = score(items, cfg)
    items.sort(key=lambda a: (-a.score, -(a.published.timestamp() if a.published else 0.0)))
    items = cap_per_source(items, int(cfg.collect.get("max_per_source", 3)))
    return items[: int(cfg.collect.get("max_items", 24))]


def group_by_category(articles: list[Article]) -> dict[str, list[Article]]:
    groups: dict[str, list[Article]] = {}
    for article in articles:
        groups.setdefault(article.source_category, []).append(article)
    return dict(sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])))
