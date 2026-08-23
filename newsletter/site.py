"""Geração do site estático (GitHub Pages) a partir das edições publicadas."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

from newsletter.config import Config, Source
from newsletter.render import _date_label, build_env

log = logging.getLogger(__name__)

EXCERPT_CHARS = 180


@dataclass
class IssuePage:
    slug: str
    date_label: str
    date_iso: str
    total: int
    subject: str
    groups: dict[str, list[dict]]

    @property
    def path(self) -> str:
        return f"edicoes/{self.slug}.html"

    @property
    def categories(self) -> list[str]:
        return list(self.groups.keys())

    @property
    def lead(self) -> dict | None:
        """O primeiro item da primeira categoria — o mais bem pontuado da edição."""
        for items in self.groups.values():
            if items:
                return items[0]
        return None

    @property
    def headline(self) -> str:
        """Título da edição no arquivo: o destaque + quantos links vêm com ele."""
        lead = self.lead
        if not lead:
            return f"Edição de {self.date_label}"
        rest = self.total - 1
        if rest <= 0:
            return lead["title"]
        return f"{lead['title']} e mais {rest} {'links' if rest != 1 else 'link'}"

    @property
    def excerpt(self) -> str:
        lead = self.lead
        summary = (lead or {}).get("summary") or ""
        if len(summary) > EXCERPT_CHARS:
            summary = summary[:EXCERPT_CHARS].rsplit(" ", 1)[0] + "…"
        return summary


def load_issues(cfg: Config) -> list[IssuePage]:
    """Lê os metadados de issues/*.json, do mais recente para o mais antigo."""
    pages: list[IssuePage] = []
    for meta_path in sorted(cfg.output_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("ignorando %s: %s", meta_path.name, exc)
            continue
        slug = data.get("date")
        if not slug:
            continue
        pages.append(
            IssuePage(
                slug=slug,
                date_label=_date_label(datetime.fromisoformat(slug)),
                date_iso=slug,
                total=int(data.get("total", 0)),
                subject=data.get("subject", ""),
                groups=data.get("groups", {}),
            )
        )
    return pages


def _site_settings(cfg: Config) -> dict:
    site = dict(cfg.raw.get("site") or {})
    site.setdefault("base_url", "")
    site.setdefault("output_dir", "site")
    site.setdefault("repo_url", cfg.newsletter.get("site_url", ""))
    site["base_url"] = site["base_url"].rstrip("/")
    return site


def _sources_by_category(sources: list[Source]) -> dict[str, list[Source]]:
    grouped: dict[str, list[Source]] = {}
    for source in sources:
        grouped.setdefault(source.category, []).append(source)
    for items in grouped.values():
        items.sort(key=lambda s: (not s.enabled, s.name.lower()))
    # ativas primeiro, depois por tamanho do grupo
    return dict(sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])))


def build_site(cfg: Config, now: datetime | None = None) -> Path:
    """Renderiza index, arquivo, fontes, páginas de edição e feed.xml em site/."""
    now = now or datetime.now(timezone.utc)
    site = _site_settings(cfg)
    out = cfg.root / site["output_dir"]
    env = build_env(cfg.root)

    issues = load_issues(cfg)
    if not issues:
        log.warning("nenhuma edição encontrada em %s — o site sairá vazio", cfg.output_dir)

    shutil.rmtree(out, ignore_errors=True)
    (out / "edicoes").mkdir(parents=True, exist_ok=True)

    common = {
        "newsletter": cfg.newsletter,
        "site": site,
        "issues": issues,
        "generated_at": now.strftime("%d/%m/%Y"),
        "year": now.year,
    }

    # home: última edição inteira + as 3 anteriores
    recent = issues[1:4]
    (out / "index.html").write_text(
        env.get_template("site/index.html.j2").render(
            latest=issues[0] if issues else None,
            recent=recent,
            has_more=len(issues) > 4,
            depth="",
            page="index",
            **common,
        ),
        encoding="utf-8",
    )

    # arquivo completo
    (out / "arquivo.html").write_text(
        env.get_template("site/arquivo.html.j2").render(depth="", page="arquivo", **common),
        encoding="utf-8",
    )

    # fontes acompanhadas + como a curadoria funciona
    (out / "fontes.html").write_text(
        env.get_template("site/fontes.html.j2").render(
            sources_by_category=_sources_by_category(cfg.sources),
            sources_active=len(cfg.enabled_sources),
            sources_total=len(cfg.sources),
            window_days=int(cfg.collect.get("window_days", 7)),
            max_per_source=int(cfg.collect.get("max_per_source", 3)),
            depth="",
            page="fontes",
            **common,
        ),
        encoding="utf-8",
    )

    # uma página por edição, com navegação anterior/seguinte
    template = env.get_template("site/issue.html.j2")
    for index, issue in enumerate(issues):
        newer = issues[index - 1] if index > 0 else None
        older = issues[index + 1] if index + 1 < len(issues) else None
        (out / "edicoes" / f"{issue.slug}.html").write_text(
            template.render(
                issue=issue, newer=newer, older=older, depth="../", page="edicao", **common
            ),
            encoding="utf-8",
        )

    # feed RSS das edições (não dos artigos)
    (out / "feed.xml").write_text(
        env.get_template("site/feed.xml.j2").render(
            build_date=format_datetime(now),
            pub_dates={
                i.slug: format_datetime(datetime.fromisoformat(i.slug).replace(tzinfo=timezone.utc)) for i in issues
            },
            depth="",
            page="feed",
            **common,
        ),
        encoding="utf-8",
    )

    (out / "404.html").write_text(
        env.get_template("site/404.html.j2").render(depth="", page="404", **common),
        encoding="utf-8",
    )

    # estáticos + desliga o Jekyll do Pages
    for asset in ("style.css", "theme.js"):
        shutil.copyfile(cfg.root / "web" / asset, out / asset)
    (out / ".nojekyll").write_text("", encoding="utf-8")

    log.info("site gerado em %s (%d edições)", out, len(issues))
    return out
