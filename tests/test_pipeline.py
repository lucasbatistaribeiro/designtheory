"""Testes do pipeline de curadoria e renderização (sem rede)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from newsletter.config import load_config
from newsletter.curate import curate, dedupe, drop_blocked, group_by_category, within_window
from newsletter.models import Article, FetchReport, canonical_url
from newsletter.render import render_issue
from newsletter.state import State

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def cfg():
    return load_config()


def make_article(title: str, url: str, source: str = "Smashing Magazine", days_ago: float = 1.0) -> Article:
    return Article(
        title=title,
        url=url,
        source_name=source,
        source_category="Web & Front-end",
        published=NOW - timedelta(days=days_ago),
        summary=f"Resumo de {title}.",
    )


def test_canonical_url_remove_tracking():
    assert canonical_url("https://WWW.Exemplo.com/post/?utm_source=x&id=7") == "https://exemplo.com/post?id=7"


def test_canonical_url_normaliza_host_e_barra_final():
    assert canonical_url("https://exemplo.com/post/") == canonical_url("https://www.exemplo.com/post")


def test_fingerprint_estavel_entre_variacoes_de_url():
    a = make_article("Design systems na prática", "https://exemplo.com/a?utm_campaign=news")
    b = make_article("Design systems na prática", "https://www.exemplo.com/a/")
    assert a.fingerprint == b.fingerprint


def test_within_window_descarta_itens_velhos():
    items = [make_article("novo", "https://e.com/1", days_ago=2), make_article("velho", "https://e.com/2", days_ago=30)]
    kept = within_window(items, window_days=7, now=NOW)
    assert [a.title for a in kept] == ["novo"]


def test_item_sem_data_entra_na_janela():
    orphan = make_article("sem data", "https://e.com/3")
    orphan.published = None
    assert within_window([orphan], window_days=7, now=NOW) == [orphan]


def test_blocklist_filtra_por_titulo_e_resumo():
    items = [make_article("Webinar de design", "https://e.com/1"), make_article("Tipografia fluida", "https://e.com/2")]
    kept = drop_blocked(items, ["webinar"])
    assert [a.title for a in kept] == ["Tipografia fluida"]


def test_dedupe_usa_estado(tmp_path):
    state = State(tmp_path / "state.json", retention_days=30)
    repetido = make_article("Já enviado", "https://e.com/antigo")
    state.remember([repetido.fingerprint], when=NOW)

    items = [repetido, make_article("Inédito", "https://e.com/novo")]
    kept = dedupe(items, state)
    assert [a.title for a in kept] == ["Inédito"]


def test_state_prune_remove_fingerprints_antigos(tmp_path):
    state = State(tmp_path / "state.json", retention_days=30)
    state.remember(["antigo"], when=NOW - timedelta(days=200))
    state.remember(["recente"], when=NOW)
    removed = state.prune(now=NOW)
    assert removed == 1
    assert state.knows("recente") and not state.knows("antigo")


def test_state_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    state = State(path, retention_days=30)
    state.remember(["abc"], when=NOW)
    state.record_issue("2026-08-23")
    state.save()

    reloaded = State(path, retention_days=30)
    assert reloaded.knows("abc")
    assert reloaded.issues == ["2026-08-23"]


def test_curate_respeita_max_per_source(cfg):
    cfg.collect["max_per_source"] = 2
    cfg.collect["max_items"] = 50
    items = [make_article(f"Post {i}", f"https://e.com/{i}") for i in range(6)]
    kept = curate(items, cfg)
    assert len(kept) == 2


def test_curate_respeita_max_items(cfg):
    cfg.collect["max_per_source"] = 10
    cfg.collect["max_items"] = 3
    items = [make_article(f"Post {i}", f"https://e.com/{i}", source=f"Fonte {i}") for i in range(8)]
    assert len(curate(items, cfg)) == 3


def test_score_prioriza_palavras_chave(cfg):
    cfg.collect["max_per_source"] = 10
    generico = make_article("Uma nota qualquer", "https://e.com/1")
    relevante = make_article("Acessibilidade em design systems", "https://e.com/2")
    kept = curate([generico, relevante], cfg)
    assert kept[0].title == "Acessibilidade em design systems"
    assert kept[0].score > kept[1].score


def test_group_by_category():
    a = make_article("um", "https://e.com/1")
    b = make_article("dois", "https://e.com/2")
    b.source_category = "UX & Pesquisa"
    groups = group_by_category([a, b])
    assert set(groups) == {"Web & Front-end", "UX & Pesquisa"}


def test_render_issue_gera_markdown_e_html(cfg, tmp_path):
    cfg.raw["output"]["dir"] = str(tmp_path.name)
    groups = group_by_category([make_article("Tipografia fluida", "https://e.com/1")])
    reports = [FetchReport("Smashing Magazine", "https://e.com/feed", True, entries=1)]

    result = render_issue(cfg, groups, reports, now=NOW, write=False)

    assert "Tipografia fluida" in result.markdown
    assert "https://e.com/1" in result.html
    assert result.total == 1
    assert "23 de agosto de 2026" in result.subject


def test_render_lista_fontes_com_falha(cfg):
    groups = group_by_category([make_article("Item", "https://e.com/1")])
    reports = [FetchReport("Fonte Morta", "https://morta.com/feed", False, error="timeout")]
    result = render_issue(cfg, groups, reports, now=NOW, write=False)
    assert "Fonte Morta" in result.markdown
    assert "timeout" in result.markdown


def test_config_carrega_fontes(cfg):
    assert cfg.sources, "sources.yml deve ter fontes"
    assert all(s.url.startswith("http") for s in cfg.sources)
    assert cfg.enabled_sources


def test_recipients_mescla_env(cfg, monkeypatch):
    monkeypatch.setenv("NEWSLETTER_RECIPIENTS", "a@x.com, b@x.com ,a@x.com")
    assert cfg.recipients() == ["a@x.com", "b@x.com"]
