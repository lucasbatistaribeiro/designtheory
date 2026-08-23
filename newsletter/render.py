"""Renderização da edição em Markdown e HTML."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from newsletter.config import Config
from newsletter.models import Article, FetchReport

_MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


@dataclass
class RenderResult:
    slug: str
    markdown_path: Path | None
    html_path: Path | None
    markdown: str
    html: str
    subject: str
    total: int


def _tz(cfg: Config) -> ZoneInfo:
    try:
        return ZoneInfo(cfg.newsletter.get("timezone", "UTC"))
    except Exception:
        return ZoneInfo("UTC")


def _date_label(moment: datetime) -> str:
    return f"{moment.day} de {_MONTHS_PT[moment.month - 1]} de {moment.year}"


def _article_view(article: Article, tz: ZoneInfo) -> dict:
    published_label = ""
    if article.published:
        published_label = article.published.astimezone(tz).strftime("%d/%m")
    meta_parts = [f"`{article.source_name}`"]
    if published_label:
        meta_parts.append(published_label)
    if article.author:
        meta_parts.append(article.author)
    return {
        "title": article.title,
        "url": article.clean_url,
        "meta_line": " · ".join(meta_parts),
        "source_name": article.source_name,
        "source_category": article.source_category,
        "summary": article.summary,
        "author": article.author,
        "score": article.score,
        "published": article.published.isoformat() if article.published else None,
        "published_label": published_label,
    }


def build_env(root: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=select_autoescape(["html", "xml"], default_for_string=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_issue(
    cfg: Config,
    groups: dict[str, list[Article]],
    reports: list[FetchReport],
    now: datetime | None = None,
    write: bool = True,
) -> RenderResult:
    tz = _tz(cfg)
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    env = build_env(cfg.root)

    total = sum(len(items) for items in groups.values())
    context = {
        "newsletter": cfg.newsletter,
        "issue": {
            "date_label": _date_label(now),
            "date_iso": now.date().isoformat(),
            "generated_at": now.strftime("%d/%m/%Y %H:%M"),
            "total": total,
            "source_count": len([r for r in reports if r.ok]),
            "window_days": int(cfg.collect.get("window_days", 7)),
        },
        "groups": {cat: [_article_view(a, tz) for a in items] for cat, items in groups.items()},
        "failures": [{"source_name": r.source_name, "error": r.error} for r in reports if not r.ok],
    }

    markdown = env.get_template("issue.md.j2").render(**context)
    html = env.get_template("issue.html.j2").render(**context)

    subject_tpl = cfg.delivery.get("subject_template", "{name} — {date}")
    subject = subject_tpl.format(
        name=cfg.newsletter.get("name", "Newsletter"),
        date=context["issue"]["date_label"],
    )

    slug = now.date().isoformat()
    md_path = None
    html_path = None
    formats = cfg.output.get("formats", ["markdown", "html"])

    if write:
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        if "markdown" in formats:
            md_path = cfg.output_dir / f"{slug}.md"
            md_path.write_text(markdown, encoding="utf-8")
        if "html" in formats:
            html_path = cfg.output_dir / f"{slug}.html"
            html_path.write_text(html, encoding="utf-8")

        meta = {"date": slug, "subject": subject, "total": total, "groups": context["groups"]}
        meta_path = cfg.output_dir / f"{slug}.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        if cfg.output.get("write_index", True):
            write_index(cfg)

    return RenderResult(slug, md_path, html_path, markdown, html, subject, total)


def write_index(cfg: Config) -> Path:
    """Regera issues/README.md a partir dos metadados das edições."""
    env = build_env(cfg.root)
    issues = []
    for meta_path in sorted(cfg.output_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        stamp = datetime.fromisoformat(data["date"])
        issues.append(
            {
                "date_label": _date_label(stamp),
                "filename": f"{data['date']}.md",
                "total": data.get("total", 0),
            }
        )
    path = cfg.output_dir / "README.md"
    path.write_text(env.get_template("index.md.j2").render(issues=issues), encoding="utf-8")
    return path
