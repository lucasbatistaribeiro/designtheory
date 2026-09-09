"""Testes do gerador do site estático."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from newsletter.config import load_config
from newsletter.fetch import strip_boilerplate
from newsletter.site import MIN_CHIP_ITEMS, build_site, load_issues, slugify

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
    write_issue(cfg, "2026-08-16", total=3)
    write_issue(cfg, "2026-08-23", total=3)
    out = build_site(cfg, now=NOW)
    index = (out / "index.html").read_text(encoding="utf-8")

    assert "23 de agosto de 2026" in index
    # a última edição vem inteira
    for i in range(3):
        assert f"Artigo {i} de 2026-08-23" in index
    # a anterior aparece resumida: só o destaque, com link para a página dela
    assert "edicoes/2026-08-16.html" in index
    assert "Artigo 0 de 2026-08-16" in index
    assert "Artigo 1 de 2026-08-16" not in index


def test_paginas_de_edicao_navegam_entre_si(cfg):
    write_issue(cfg, "2026-08-16")
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)

    recente = (out / "edicoes" / "2026-08-23.html").read_text(encoding="utf-8")
    antiga = (out / "edicoes" / "2026-08-16.html").read_text(encoding="utf-8")

    assert "2026-08-16.html" in recente and "Anterior" in recente
    assert "2026-08-23.html" in antiga and "Seguinte" in antiga
    # a mais antiga não tem link para anterior
    assert "Anterior" not in antiga


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


def test_nenhuma_pagina_tem_bloco_de_assinatura(cfg):
    """O projeto não envia e-mail: nenhuma página pede cadastro."""
    write_issue(cfg, "2026-08-16")
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)

    for nome in ("index.html", "arquivo.html", "fontes.html", "404.html", "edicoes/2026-08-23.html"):
        html = (out / nome).read_text(encoding="utf-8")
        assert "subscribe" not in html.lower(), nome
        assert "<form" not in html, nome
        assert "Assinar" not in html, nome


def test_rss_segue_acessivel_como_navegacao(cfg):
    """Sem e-mail, o feed é o único jeito de acompanhar — não pode desaparecer."""
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)
    assert (out / "feed.xml").exists()

    index = (out / "index.html").read_text(encoding="utf-8")
    assert 'href="feed.xml"' in index
    edicao = (out / "edicoes" / "2026-08-23.html").read_text(encoding="utf-8")
    assert 'href="../feed.xml"' in edicao


def test_paginas_de_arquivo_e_fontes(cfg):
    write_issue(cfg, "2026-08-16")
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)

    arquivo = (out / "arquivo.html").read_text(encoding="utf-8")
    assert "Todas as edições" in arquivo
    assert "edicoes/2026-08-23.html" in arquivo and "edicoes/2026-08-16.html" in arquivo

    fontes = (out / "fontes.html").read_text(encoding="utf-8")
    # toda fonte cadastrada aparece, com a URL do feed
    for source in cfg.sources:
        assert source.name in fontes
        assert source.url in fontes


def test_theme_js_e_copiado_e_carregado_sem_defer(cfg):
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)

    assert (out / "theme.js").exists()
    index = (out / "index.html").read_text(encoding="utf-8")
    # sem defer/async: o tema precisa ser aplicado antes da primeira pintura
    assert '<script src="theme.js"></script>' in index
    assert (out / "edicoes" / "2026-08-23.html").read_text(encoding="utf-8").count('"../theme.js"') == 1


def test_botao_de_tema_em_todas_as_paginas(cfg):
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)
    paginas = ["index.html", "arquivo.html", "fontes.html", "404.html", "edicoes/2026-08-23.html"]
    for nome in paginas:
        html = (out / nome).read_text(encoding="utf-8")
        assert "data-theme-toggle" in html, nome
        assert "icon-sun" in html and "icon-moon" in html, nome


def test_css_cobre_os_tres_estados_de_tema(cfg):
    """Sistema, escolha explícita clara e escolha explícita escura."""
    write_issue(cfg, "2026-08-23")
    css = (build_site(cfg, now=NOW) / "style.css").read_text(encoding="utf-8")
    assert "@media (prefers-color-scheme: dark)" in css
    assert ':root:not([data-theme="light"])' in css
    assert ':root[data-theme="dark"]' in css


def test_nav_marca_a_pagina_atual(cfg):
    write_issue(cfg, "2026-08-23")
    out = build_site(cfg, now=NOW)
    index = (out / "index.html").read_text(encoding="utf-8")
    arquivo = (out / "arquivo.html").read_text(encoding="utf-8")
    assert 'href="index.html" aria-current="page"' in index
    assert 'href="arquivo.html" aria-current="page"' in arquivo


def test_titulo_com_html_e_escapado(cfg):
    write_issue(cfg, "2026-08-23", total=1)
    meta = json.loads((cfg.output_dir / "2026-08-23.json").read_text(encoding="utf-8"))
    meta["groups"]["UX & Pesquisa"][0]["title"] = "Tags <script>alert(1)</script> & cia"
    (cfg.output_dir / "2026-08-23.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    index = (build_site(cfg, now=NOW) / "index.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in index
    assert "&lt;script&gt;" in index


def test_headline_usa_o_destaque_e_conta_o_resto(cfg):
    write_issue(cfg, "2026-08-23", total=3)
    issue = load_issues(cfg)[0]
    assert issue.headline == "Artigo 0 de 2026-08-23 e mais 2 links"
    assert issue.excerpt == "Um resumo curto."


def test_headline_com_um_item_nao_diz_e_mais(cfg):
    write_issue(cfg, "2026-08-23", total=1)
    assert load_issues(cfg)[0].headline == "Artigo 0 de 2026-08-23"


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


# ---------------------------------------------------------------- fase 1: dados


def write_multi(cfg, slug: str, spec: dict) -> None:
    """Escreve uma edição com várias categorias: {categoria: quantidade}."""
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    groups = {
        cat: [
            {
                "title": f"{cat} {i}",
                "url": f"https://exemplo.com/{i}",
                "source_name": "Fonte",
                "source_category": cat,
                "summary": "Resumo.",
                "author": "Autor",
                "score": 1.0,
                "published": f"{slug}T10:00:00+00:00",
                "published_label": "21/08",
            }
            for i in range(n)
        ]
        for cat, n in spec.items()
    }
    payload = {"date": slug, "subject": "", "total": sum(spec.values()), "groups": groups}
    (cfg.output_dir / f"{slug}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("UX & Pesquisa", "ux-pesquisa"),
        ("Web & Front-end", "web-front-end"),
        ("Arquitetura & Ambiente", "arquitetura-ambiente"),
        ("Teoria & Crítica", "teoria-critica"),
        ("Design de Produto", "design-de-produto"),
    ],
)
def test_slugify(entrada, esperado):
    assert slugify(entrada) == esperado


def test_items_achata_a_edicao_preservando_a_ordem(cfg):
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 2, "Visual & Branding": 3})
    issue = load_issues(cfg)[0]

    assert len(issue.items) == 5
    assert [i["title"] for i in issue.items[:2]] == ["UX & Pesquisa 0", "UX & Pesquisa 1"]
    # a ordem dos grupos sobrevive: o mais bem pontuado continua no topo
    assert issue.items[0]["category"] == "UX & Pesquisa"
    assert issue.items[-1]["category"] == "Visual & Branding"


def test_items_carimba_categoria_e_slug_sem_perder_campos(cfg):
    write_multi(cfg, "2026-08-23", {"Web & Front-end": 1})
    item = load_issues(cfg)[0].items[0]

    assert item["category"] == "Web & Front-end"
    assert item["category_slug"] == "web-front-end"
    # os campos originais continuam lá
    for campo in ("title", "url", "source_name", "summary", "author", "published_label"):
        assert campo in item


def test_filters_ignora_categoria_pequena_demais(cfg):
    """Um chip que filtra para um tile só numa grade de 3 colunas parece defeito."""
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 5, "Curadoria": 2, "Ferramentas": 1})
    issue = load_issues(cfg)[0]

    rotulos = [f["label"] for f in issue.filters]
    assert rotulos == ["UX & Pesquisa", "Curadoria"]
    assert "Ferramentas" not in rotulos
    # mas o item sem chip continua na grade
    assert any(i["category"] == "Ferramentas" for i in issue.items)


def test_filters_conta_e_slug(cfg):
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 4})
    assert load_issues(cfg)[0].filters == [{"label": "UX & Pesquisa", "slug": "ux-pesquisa", "count": 4}]


def test_min_chip_items_e_o_limite_documentado(cfg):
    write_multi(cfg, "2026-08-23", {"Exata": MIN_CHIP_ITEMS, "Abaixo": MIN_CHIP_ITEMS - 1})
    rotulos = [f["label"] for f in load_issues(cfg)[0].filters]
    assert rotulos == ["Exata"]


def test_edicao_vazia_nao_tem_itens_nem_chips(cfg):
    write_multi(cfg, "2026-08-23", {})
    issue = load_issues(cfg)[0]
    assert issue.items == [] and issue.filters == []


# ------------------------------------------------------- fase 2: grade da home


def test_home_renderiza_um_tile_por_item(cfg):
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 5, "Visual & Branding": 3, "Ferramentas": 1})
    index = (build_site(cfg, now=NOW) / "index.html").read_text(encoding="utf-8")

    assert index.count('class="tile"') == 9
    assert 'class="gallery"' in index
    # inclusive o item da categoria que nao ganhou chip
    assert "Ferramentas 0" in index


def test_tile_carrega_categoria_titulo_e_fonte_sem_resumo(cfg):
    write_multi(cfg, "2026-08-23", {"Web & Front-end": 1})
    index = (build_site(cfg, now=NOW) / "index.html").read_text(encoding="utf-8")

    assert 'data-category="web-front-end"' in index
    assert "Web &amp; Front-end 0" in index
    assert 'class="tile__source"' in index
    # o resumo fica de fora do tile: em tres colunas vira paragrafo apertado
    assert 'class="tile__summary"' not in index
    assert "Resumo." not in index


def test_so_a_home_sai_da_coluna_de_leitura(cfg):
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 2})
    out = build_site(cfg, now=NOW)

    assert '<main class="wrap wrap--full">' in (out / "index.html").read_text(encoding="utf-8")
    for nome in ("arquivo.html", "fontes.html", "404.html", "edicoes/2026-08-23.html"):
        assert '<main class="wrap">' in (out / nome).read_text(encoding="utf-8"), nome


def test_home_mantem_edicoes_anteriores_na_coluna_estreita(cfg):
    write_multi(cfg, "2026-08-16", {"UX & Pesquisa": 2})
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 2})
    index = (build_site(cfg, now=NOW) / "index.html").read_text(encoding="utf-8")

    assert "Edições anteriores" in index
    assert 'class="entry"' in index
    # a grade vem antes do arquivo
    assert index.index('class="gallery"') < index.index('class="entry"')


def test_pagina_da_edicao_continua_em_lista_agrupada(cfg):
    """A galeria e da home; a pagina da edicao mantem secoes e resumos."""
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 2})
    edicao = (build_site(cfg, now=NOW) / "edicoes" / "2026-08-23.html").read_text(encoding="utf-8")

    assert 'class="tile"' not in edicao
    assert 'class="item"' in edicao and 'class="item__summary"' in edicao


def test_css_da_galeria_tem_os_tres_pontos_de_quebra(cfg):
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 2})
    css = (build_site(cfg, now=NOW) / "style.css").read_text(encoding="utf-8")

    assert ".gallery" in css and ".tile" in css
    assert "repeat(3, minmax(0, 1fr))" in css
    assert "repeat(2, minmax(0, 1fr))" in css


def test_laranja_de_texto_tem_token_proprio(cfg):
    """O laranja da marca reprova no AA sobre fundo claro; texto usa o escurecido."""
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 2})
    css = (build_site(cfg, now=NOW) / "style.css").read_text(encoding="utf-8")

    assert "--accent-text: #c2410c" in css
    # nenhum uso de laranja como primeiro plano escapou para o token decorativo
    for regra in (".tile__source", ".item__source"):
        bloco = css[css.index(regra) : css.index(regra) + 120]
        assert "var(--accent-text)" in bloco, regra


# ------------------------------------------------------- fase 4: chips e filtro


def test_chips_saem_do_filters_mais_o_todos(cfg):
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 5, "Curadoria": 2, "Ferramentas": 1})
    index = (build_site(cfg, now=NOW) / "index.html").read_text(encoding="utf-8")

    assert 'data-filter="all"' in index
    assert 'data-filter="ux-pesquisa"' in index
    assert 'data-filter="curadoria"' in index
    # categoria pequena demais nao vira chip, mas o tile continua na grade
    assert 'data-filter="ferramentas"' not in index
    assert 'data-category="ferramentas"' in index


def test_chip_todos_conta_a_edicao_inteira(cfg):
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 5, "Ferramentas": 1})
    index = (build_site(cfg, now=NOW) / "index.html").read_text(encoding="utf-8")
    # 6 itens no total, ainda que so 5 tenham chip proprio
    bloco = index[index.index('data-filter="all"') : index.index('data-filter="all"') + 120]
    assert 'aria-pressed="true"' in bloco
    assert "Todos" in bloco
    assert '<span class="filter__count">6</span>' in bloco


def test_so_um_chip_comeca_pressionado(cfg):
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 3, "Curadoria": 2})
    index = (build_site(cfg, now=NOW) / "index.html").read_text(encoding="utf-8")
    # só a barra de filtros: o botão de tema também usa aria-pressed
    barra = index[index.index("data-filters") : index.index("data-filter-status")]
    assert barra.count('aria-pressed="true"') == 1
    assert barra.count('aria-pressed="false"') == 2


def test_edicao_sem_chip_nenhum_nao_renderiza_a_barra(cfg):
    write_multi(cfg, "2026-08-23", {"Ferramentas": 1})
    index = (build_site(cfg, now=NOW) / "index.html").read_text(encoding="utf-8")
    assert "data-filters" not in index
    assert 'data-category="ferramentas"' in index


def test_filtro_e_progressive_enhancement(cfg):
    """Sem JS os chips somem e a grade vem inteira, em vez de um controle morto."""
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 3})
    out = build_site(cfg, now=NOW)
    css = (out / "style.css").read_text(encoding="utf-8")

    bloco = css[css.index(".filters {") : css.index(".filters {") + 40]
    assert "display: none" in bloco
    assert ".js .filters {" in css
    # o theme.js roda no <head> sem defer e marca <html class="js"> antes de pintar
    assert 'root.classList.add("js")' in (out / "theme.js").read_text(encoding="utf-8")


def test_guarda_do_hidden_no_tile(cfg):
    """.tile e display:flex, que vence o [hidden] do navegador: sem esta regra
    o filtro esconde os tiles e eles continuam na tela."""
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 3})
    css = (build_site(cfg, now=NOW) / "style.css").read_text(encoding="utf-8")
    bloco = css[css.index(".gallery .tile[hidden] {") :][:60]
    assert "display: none" in bloco


def test_filter_js_so_na_home_e_com_defer(cfg):
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 3})
    out = build_site(cfg, now=NOW)

    assert (out / "filter.js").exists()
    assert '<script src="filter.js" defer></script>' in (out / "index.html").read_text(encoding="utf-8")
    for nome in ("arquivo.html", "fontes.html", "404.html", "edicoes/2026-08-23.html"):
        assert "filter.js" not in (out / nome).read_text(encoding="utf-8"), nome


def test_barra_tem_regiao_de_status_para_leitor_de_tela(cfg):
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 3})
    out = build_site(cfg, now=NOW)
    index = (out / "index.html").read_text(encoding="utf-8")

    assert 'role="status"' in index and 'aria-live="polite"' in index
    assert 'data-filter-status' in index
    assert ".visually-hidden {" in (out / "style.css").read_text(encoding="utf-8")


def test_estado_ativo_nao_depende_so_de_cor(cfg):
    """WCAG 1.4.1: o chip ativo tem peso e sublinhado, nao apenas cor."""
    write_multi(cfg, "2026-08-23", {"UX & Pesquisa": 3})
    css = (build_site(cfg, now=NOW) / "style.css").read_text(encoding="utf-8")
    bloco = css[css.index(".filter.is-active {") : css.index(".filter.is-active {") + 200]
    assert "font-weight: 700" in bloco
    assert "border-bottom-color" in bloco
