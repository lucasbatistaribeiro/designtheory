"""Interface de linha de comando da newsletter.

    python -m newsletter build          # coleta, curadoria, render (e envio, se configurado)
    python -m newsletter build --dry-run
    python -m newsletter validate       # checa se todos os feeds respondem
    python -m newsletter sources        # lista as fontes cadastradas
    python -m newsletter index          # regera issues/README.md
    python -m newsletter site           # gera o site estático em site/
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from newsletter import __version__
from newsletter.config import load_config
from newsletter.curate import curate, group_by_category
from newsletter.deliver import send
from newsletter.fetch import fetch_all, fetch_source
from newsletter.render import render_issue, write_index
from newsletter.site import build_site
from newsletter.state import State

log = logging.getLogger("newsletter")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
        stream=sys.stderr,
    )


def _github_output(key: str, value: str) -> None:
    """Expõe resultados para os steps seguintes do GitHub Actions."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{key}={value}\n")


def cmd_build(args: argparse.Namespace) -> int:
    cfg = load_config()
    if args.window_days:
        cfg.collect["window_days"] = args.window_days
    if args.max_items:
        cfg.collect["max_items"] = args.max_items

    log.info("coletando %d fontes ativas", len(cfg.enabled_sources))
    articles, reports = fetch_all(cfg)
    ok = [r for r in reports if r.ok]
    log.info("%d/%d fontes responderam, %d itens brutos", len(ok), len(reports), len(articles))

    state = State(cfg.state_path, cfg.retention_days)
    selected = curate(articles, cfg, None if args.ignore_state else state)
    log.info("%d itens selecionados para a edição", len(selected))

    if not selected and not args.allow_empty:
        log.warning("nenhum item novo na janela — nada a publicar")
        _github_output("published", "false")
        _github_output("items", "0")
        return 0

    groups = group_by_category(selected)
    result = render_issue(cfg, groups, reports, write=not args.dry_run)

    if args.dry_run:
        print(result.markdown)
        log.info("dry-run: nada foi gravado nem enviado")
        return 0

    log.info("edição gravada: %s", result.markdown_path or result.html_path)

    state.remember([a.fingerprint for a in selected])
    state.record_issue(result.slug)
    removed = state.prune()
    state.save()
    if removed:
        log.debug("%d fingerprints antigos removidos do estado", removed)

    if not args.no_site:
        build_site(cfg)

    if args.no_send:
        log.info("envio ignorado (--no-send)")
    else:
        delivery = send(cfg, result.subject, result.html, result.markdown)
        log.info("envio: %s", delivery.detail)

    _github_output("published", "true")
    _github_output("items", str(result.total))
    _github_output("slug", result.slug)
    return 0


def cmd_site(_: argparse.Namespace) -> int:
    cfg = load_config()
    out = build_site(cfg)
    print(f"site gerado em {out}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    cfg = load_config()
    failures = 0
    for source in cfg.sources:
        if not source.enabled:
            print(f"  -   {source.name}: desativada")
            continue
        _, report = fetch_source(source, cfg)
        if report.ok:
            print(f"  ok  {source.name}: {report.entries} itens")
        else:
            failures += 1
            print(f"  ERRO {source.name}: {report.error}")
    print(f"\n{len(cfg.enabled_sources) - failures}/{len(cfg.enabled_sources)} fontes ativas responderam")
    return 1 if failures and args.strict else 0


def cmd_sources(_: argparse.Namespace) -> int:
    cfg = load_config()
    by_category: dict[str, list] = {}
    for source in cfg.sources:
        by_category.setdefault(source.category, []).append(source)
    for category, items in sorted(by_category.items()):
        print(f"\n{category}")
        for source in items:
            flag = " " if source.enabled else "x"
            print(f"  [{flag}] {source.name}  (peso {source.weight})  {source.url}")
    print(f"\n{len(cfg.enabled_sources)} ativas de {len(cfg.sources)} cadastradas")
    return 0


def cmd_index(_: argparse.Namespace) -> int:
    cfg = load_config()
    path = write_index(cfg)
    print(f"índice regerado: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="newsletter", description="Gerador da newsletter Design Theory")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="log detalhado")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="gera (e opcionalmente envia) uma edição")
    build.add_argument("--dry-run", action="store_true", help="imprime a edição sem gravar nem enviar")
    build.add_argument("--no-send", action="store_true", help="grava a edição mas não envia e-mail")
    build.add_argument("--no-site", action="store_true", help="não regera o site estático")
    build.add_argument("--ignore-state", action="store_true", help="não filtra itens de edições anteriores")
    build.add_argument("--allow-empty", action="store_true", help="gera edição mesmo sem itens novos")
    build.add_argument("--window-days", type=int, help="sobrescreve collect.window_days")
    build.add_argument("--max-items", type=int, help="sobrescreve collect.max_items")
    build.set_defaults(func=cmd_build)

    validate = sub.add_parser("validate", help="testa todos os feeds cadastrados")
    validate.add_argument("--strict", action="store_true", help="sai com código 1 se alguma fonte falhar")
    validate.set_defaults(func=cmd_validate)

    sources = sub.add_parser("sources", help="lista as fontes")
    sources.set_defaults(func=cmd_sources)

    index = sub.add_parser("index", help="regera issues/README.md")
    index.set_defaults(func=cmd_index)

    site = sub.add_parser("site", help="gera o site estático em site/")
    site.set_defaults(func=cmd_site)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
