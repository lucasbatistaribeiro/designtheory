"""Testes do gerador do site estático."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from newsletter.config import load_config
from newsletter.fetch import strip_boilerplate
from newsletter.site import build_site, load_issues

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def write_issue(cfg, slug: str, total: int = 2) -> None:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": slug,
        "subject": f"Design Theory — {slug}",
        "total": total,
        "groups": {
            "UX & Pesquisa": [
                {
                    "title": f"Artigo {i} de {slug}",
                    "url": f"https://exemplo.com/{slug}/{i}",
                    "source_name": "Nielsen Norman Group",
                    "source_category": "UX & Pesquisa",
                    "summary": "Um resumo curto.",
                    "author": "Autor",
                    "score": 1.0,
                    "published": f"{slug}T10:00:00+00:00",
                    "published_label": "21/08",
                }
                for i in range(total)
            ]
        },
    }
    (cfg.output_dir / f"{slug}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def cfg(tmp_path):
    """Config real, mas com issues/ e site/ apontando para um tmp_path."""
    conf = load_config()
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    conf.raw["output"]["dir"] = str(issues_dir)
    conf.raw.setdefault("site", {})
    conf.raw["site"]["output_dir"] = str(tmp_path / "site")
    conf.raw["site"]["base_url"] = "https://exemplo.github.io/designtheory"
    return conf


def test_load_issues_ordena_do_mais_recente(cfg):
    for slug in ("2026-08-09", "2026-08-23", "2026-08-16"):
        write_issue(cfg, slug)
    issues = load_issues(cfg)
    assert [i.slug for i in issues] == ["2026-08-23", "2026-08-16", "2026-08-09"]
    assert issues[0].date_label == "23 de agosto de 2026"
    assert issues[0].path == "edicoes/2026-08-23.html"


def test_load_issues_ignora_json_corrompido(cfg):
    write_issue(cfg, "2026-08-23")
    (cfg.output_dir / "quebrado.json").write_text("{nao é json", encoding="utf-8")
    assert [i.slug for i in load_issues(cfg)] == ["2026-08-23"]


def test_build_site_gera_todas_as_paginas(cfg):
    write_issue(cfg, "2026-08-16")
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)

    assert (out / "index.html").exists()
    assert (out / "edicoes" / "2026-08-23.html").exists()
    assert (out / "edicoes" / "2026-08-16.html").exists()
    assert (out / "feed.xml").exists()
    assert (out / "404.html").exists()
    assert (out / "style.css").exists()
    assert (out / ".nojekyll").exists()


def test_index_mostra_ultima_edicao_e_arquivo(cfg):
    write_issue(cfg, "2026-08-16")
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)
    index = (out / "index.html").read_text(encoding="utf-8")

    assert "23 de agosto de 2026" in index
    assert "Artigo 0 de 2026-08-23" in index
    # a edição antiga aparece só como link no arquivo, não com os itens
    assert "edicoes/2026-08-16.html" in index
    assert "Artigo 0 de 2026-08-16" not in index


def test_paginas_de_edicao_navegam_entre_si(cfg):
    write_issue(cfg, "2026-08-16")
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)

    recente = (out / "edicoes" / "2026-08-23.html").read_text(encoding="utf-8")
    antiga = (out / "edicoes" / "2026-08-16.html").read_text(encoding="utf-8")

    assert "2026-08-16.html" in recente and "Edição anterior" in recente
    assert "2026-08-23.html" in antiga and "Edição seguinte" in antiga
    # a mais antiga não tem link para anterior
    assert "Edição anterior" not in antiga


def test_paginas_internas_referenciam_css_com_caminho_relativo(cfg):
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)
    assert 'href="style.css"' in (out / "index.html").read_text(encoding="utf-8")
    assert 'href="../style.css"' in (out / "edicoes" / "2026-08-23.html").read_text(encoding="utf-8")


def test_feed_lista_edicoes_com_url_absoluta(cfg):
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)
    feed = (out / "feed.xml").read_text(encoding="utf-8")
    assert "https://exemplo.github.io/designtheory/edicoes/2026-08-23.html" in feed
    assert "<pubDate>" in feed


def test_build_site_sem_edicoes_nao_quebra(cfg):
    out = build_site(cfg, now=NOW)
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Nenhuma edição ainda" in index


def test_build_site_limpa_saida_antiga(cfg):
    write_issue(cfg, "2026-08-16")
    out = build_site(cfg, now=NOW)
    assert (out / "edicoes" / "2026-08-16.html").exists()

    (cfg.output_dir / "2026-08-16.json").unlink()
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)
    assert not (out / "edicoes" / "2026-08-16.html").exists()


def test_bloco_assine_aparece_so_com_url(cfg):
    write_issue(cfg, "2026-08-23")
    cfg.raw["site"]["subscribe_url"] = ""
    assert "Quero assinar" not in (build_site(cfg, now=NOW) / "index.html").read_text(encoding="utf-8")

    cfg.raw["site"]["subscribe_url"] = "https://assinar.exemplo.com"
    index = (build_site(cfg, now=NOW) / "index.html").read_text(encoding="utf-8")
    assert "Quero assinar" in index and "https://assinar.exemplo.com" in index


def test_titulo_com_html_e_escapado(cfg):
    write_issue(cfg, "2026-08-23", total=1)
    meta = json.loads((cfg.output_dir / "2026-08-23.json").read_text(encoding="utf-8"))
    meta["groups"]["UX & Pesquisa"][0]["title"] = "Tags <script>alert(1)</script> & cia"
    (cfg.output_dir / "2026-08-23.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    index = (build_site(cfg, now=NOW) / "index.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in index
    assert "&lt;script&gt;" in index


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("Ideia boa. The post Titulo do Artigo appeared first on PRINT Magazine .", "Ideia boa"),
        ("Texto qualquer. Continue reading on UX Collective »", "Texto qualquer"),
        ("Resumo intacto sobre tipografia.", "Resumo intacto sobre tipografia"),
        ("Cortado no meio […]", "Cortado no meio"),
    ],
)
def test_strip_boilerplate(entrada, esperado):
    assert strip_boilerplate(entrada) == esperado
