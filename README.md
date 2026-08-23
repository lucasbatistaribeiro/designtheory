# Design Theory

Newsletter semanal de design, montada automaticamente a partir de feeds RSS/Atom.
Toda segunda-feira o GitHub Actions coleta o que saiu na semana, faz a curadoria,
grava a edição em [`issues/`](issues/) e — se você configurar o envio — manda o
e-mail para a lista.

## Como funciona

```
sources.yml  ──▶  fetch  ──▶  curadoria  ──▶  render  ──▶  issues/*.md + *.html + *.json
 (16 feeds)      (RSS)     janela de 7 dias    Jinja2      │
                           blocklist                       ├─▶  e-mail (opcional)
                           dedup vs data/state.json        └─▶  site/ ──▶ GitHub Pages
                           score por palavra-chave
                           limite por fonte / por edição
```

| Arquivo | Papel |
| --- | --- |
| [`sources.yml`](sources.yml) | lista de feeds, categoria e peso de cada um |
| [`config.yml`](config.yml) | janela de coleta, limites, palavras-chave, blocklist, envio |
| [`newsletter/`](newsletter/) | o pipeline em Python |
| [`templates/`](templates/) | templates Jinja2 da edição (Markdown, e-mail) e do site |
| [`web/`](web/) | CSS e JS do site (tema claro/escuro), sem dependências externas |
| [`issues/`](issues/) | edições publicadas (`.md` para ler no GitHub, `.html` para o e-mail, `.json` de metadados) |
| [`data/state.json`](data/) | o que já foi enviado, para não repetir item entre edições |
| [`.github/workflows/newsletter.yml`](.github/workflows/newsletter.yml) | o cron semanal |
| [`.github/workflows/pages.yml`](.github/workflows/pages.yml) | build e deploy do site no GitHub Pages |

## Rodando localmente

```bash
pip install -r requirements-dev.txt
```

```bash
python -m newsletter build --dry-run
```

Outros comandos:

```bash
python -m newsletter validate
```

| Comando | O que faz |
| --- | --- |
| `python -m newsletter build` | gera a edição, grava em `issues/` e envia (se configurado) |
| `python -m newsletter build --dry-run` | imprime a edição no terminal, sem gravar nem enviar |
| `python -m newsletter build --no-send` | grava a edição mas não envia e-mail |
| `python -m newsletter build --no-site` | não regera o site |
| `python -m newsletter build --ignore-state` | ignora o histórico e reconsidera itens já enviados |
| `python -m newsletter build --window-days 14` | amplia a janela de coleta |
| `python -m newsletter validate` | testa se todos os feeds respondem |
| `python -m newsletter sources` | lista as fontes cadastradas |
| `python -m newsletter index` | regera `issues/README.md` |
| `python -m newsletter site` | gera o site estático em `site/` |

Testes: `pytest`

## Adicionando uma fonte

Cole o feed em `sources.yml` e valide:

```yaml
  - name: Nome da Fonte
    category: UX & Pesquisa      # vira o agrupamento na edição
    type: rss
    url: https://exemplo.com/feed/
    weight: 1.0                  # >1 sobe os itens dessa fonte, <1 desce
    enabled: true
```

```bash
python -m newsletter validate --strict
```

Categorias em uso hoje: `Web & Front-end`, `UX & Pesquisa`, `Design de Produto`,
`Arquitetura & Ambiente`, `Visual & Branding`, `Teoria & Crítica`, `Ferramentas`,
`Curadoria`. Criar uma nova é só escrever um nome diferente.

## Curadoria

Cada item recebe uma pontuação e a edição leva os melhores:

- **palavras-chave** (`ranking.keywords`) somam pontos quando aparecem no título ou resumo;
- **frescor** dá um empurrão pequeno para o que saiu nos últimos dias;
- **peso da fonte** multiplica o total;
- **blocklist** (`ranking.blocklist`) descarta o item de vez — é onde ficam os termos
  de conteúdo patrocinado e promoção;
- **limites** `max_per_source` (padrão 3) e `max_items` (padrão 24) evitam que uma
  fonte prolífica domine a edição.

A deduplicação usa a URL sem parâmetros de tracking + o título, então o mesmo
artigo republicado ou saído em dois feeds entra uma vez só. `data/state.json`
guarda essas chaves por 180 dias.

## Envio por e-mail

Sem credenciais o pipeline gera a edição e simplesmente não envia — nada quebra.
Para ligar o envio, cadastre os secrets em **Settings → Secrets and variables →
Actions**:

**Resend** (padrão em `config.yml`):

| Secret | Exemplo |
| --- | --- |
| `RESEND_API_KEY` | `re_...` |
| `NEWSLETTER_FROM` | `Design Theory <news@seudominio.com>` |
| `NEWSLETTER_RECIPIENTS` | `voce@email.com,outro@email.com` |

**SMTP** (troque `delivery.provider` para `smtp` no `config.yml`):
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, mais `NEWSLETTER_FROM` e
`NEWSLETTER_RECIPIENTS`.

Para uma lista de verdade, o campo `recipients` puxando de secret resolve só o
começo — a partir de algumas dezenas de assinantes vale trocar o passo de envio
por uma audiência gerenciada no provedor (Resend Audiences, Buttondown, Listmonk),
já com opt-in e descadastro.

## Site (GitHub Pages)

**No ar: https://lucasbatistaribeiro.github.io/designtheory/**

Visual inspirado no Substack — wordmark serifada centralizada, laranja `#ff6719`,
nav com borda fina, botão de assinatura em pílula, corpo em serifada. `python -m
newsletter site` lê os `issues/*.json` e gera:

```
site/
├── index.html              assinatura + última edição inteira + 3 anteriores
├── arquivo.html            todas as edições
├── fontes.html             as 16 publicações acompanhadas e como a curadoria funciona
├── edicoes/2026-08-23.html uma página por edição, com navegação anterior/seguinte
├── feed.xml                RSS das edições
├── 404.html
├── style.css
└── theme.js
```

O `build` já regera o site junto (use `--no-site` para pular). Para ver localmente:

```bash
python -m newsletter site && python -m http.server 8765 --directory site
```

### Tema claro e escuro

O botão no canto superior direito alterna entre os dois. São **três estados**: sem
escolha o site segue o sistema operacional; escolhendo claro ou escuro, a
preferência grava no `localStorage` e passa a vencer o sistema.

Isso exige que o CSS defina o escuro **duas vezes** — dentro de
`@media (prefers-color-scheme: dark)` com a guarda `:root:not([data-theme="light"])`,
e de novo em `:root[data-theme="dark"]`. Sem a guarda, quem está no sistema escuro
não conseguiria escolher o tema claro. O [`theme.js`](web/theme.js) é carregado no
`<head>` **sem `defer`** de propósito: aplica o atributo antes da primeira pintura,
senão a página pisca no tema errado. Sem JavaScript, o site continua funcionando —
só segue o sistema.

Os contrastes de texto atendem WCAG AA (mínimo 4.5:1) nos dois temas.

### Assinatura

Com `site.subscribe_url` vazio, o site mostra "Assinar por RSS". Preenchendo a URL
do seu provedor (Buttondown, Listmonk, Tally...), o bloco vira um formulário de
e-mail de verdade, com `POST` para essa URL. Se o provedor espera um campo com
outro nome, ajuste `site.subscribe_field`.

### Deploy

[`pages.yml`](.github/workflows/pages.yml) roda a cada push que toque o gerador, os
templates, o CSS ou as edições, e também logo depois da newsletter semanal terminar
— via `workflow_run`, porque push feito pelo `GITHUB_TOKEN` não dispara outro
workflow por conta própria. Fonte configurada em **Settings → Pages → GitHub
Actions**.

Ajuste `site.base_url` no `config.yml` se trocar de domínio — é o que alimenta o
`feed.xml` e as meta tags Open Graph.

> Pages em repositório privado exige GitHub Pro/Team. Este repositório é público,
> então funciona no plano Free.

Zero dependência externa no front: nenhuma fonte de CDN, nenhum script de terceiro.
A tipografia usa a pilha de serifadas do sistema (Charter, Georgia). Para trocar por
uma webfont, é uma linha em `--serif` no [`web/style.css`](web/style.css).

## Agendamento

`.github/workflows/newsletter.yml` roda `0 12 * * 1` — segunda-feira, 12:00 UTC
(09:00 em Brasília). O cron do GitHub usa sempre UTC, então lembre de ajustar em
troca de horário de verão. Dá para rodar na mão em **Actions → Newsletter semanal
→ Run workflow**, com opção de `dry_run`, `no_send` e janela customizada.

O workflow commita a edição e o `data/state.json` de volta no repositório, então
precisa de `contents: write` — já declarado no arquivo.

## Limitações conhecidas

- Só feeds RSS/Atom. Site sem feed exigiria um coletor novo (`type: html` +
  scraping) — o `fetch.py` já está estruturado para receber outro tipo.
- Os resumos vêm do próprio feed; não há geração de texto. Se quiser resumo
  editorial, é um passo a mais entre a curadoria e o render.
- Feeds mudam de endereço sem avisar. Rode `validate` de vez em quando; as falhas
  de coleta também aparecem no fim de cada edição.
- O site não tem busca nem paginação. Com dezenas de edições no arquivo vale
  paginar o `arquivo.html` ou adicionar um índice por fonte.
- O formulário de assinatura depende de um provedor externo — não há backend
  próprio para guardar e-mails.
