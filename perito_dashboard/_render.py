"""Internal, local-only dashboard renderer for accepted aggregate observations."""
from datetime import datetime, timedelta, timezone
from html import escape
import math
from pathlib import Path
import shutil

from ._shared import CUTOFF, PF_ORGANIZATION, write_json


MONTHS = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro")
DATASET_URL = ("https://www.gov.br/servidor/pt-br/observatorio-de-pessoal-govbr/"
               "gestao-de-pessoas-executivo-federal-cargos-vagos")


def _number(value):
    return f"{value:,}".replace(",", ".")


def _month(value):
    year, month = value.split("-")
    return f"{MONTHS[int(month) - 1]} de {year}"


def _check_time(value):
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    brasilia = instant.astimezone(timezone(timedelta(hours=-3)))
    return brasilia.strftime("%d/%m/%Y às %H:%M") + " (Brasília, UTC−03:00)"


def _percent(count, total):
    return f"{count / total * 100:.1f}".replace(".", ",") + "%" if total else "—"


def _current(current):
    rate_note = ("" if current["authorized"] else
                 '<p>Taxa indisponível: total aprovado igual a zero.</p>')
    return f'''<section aria-labelledby="current-title" class="panel">
<h2 id="current-title">Cargos vagos</h2>
<p class="reference">Referência oficial: <strong><time datetime="{current["reference_month"]}">{_month(current["reference_month"])}</time></strong></p>
<div class="current-layout"><div>
<dl class="vacancy-summary"><div><dt>Cargos vagos</dt><dd id="vacant-count">{_number(current["vacant"])}</dd></div>
<div><dt>Taxa de vacância</dt><dd id="vacancy-rate">{_percent(current["vacant"], current["authorized"])}</dd></div></dl>
<p>Postos aprovados em lei e não ocupados.</p>{rate_note}</div>
<div><table id="current-values"><caption>Contexto da mesma referência</caption>
<thead><tr><th scope="col">Situação</th><th scope="col">Cargos</th></tr></thead>
<tbody><tr><th scope="row">Ocupados</th><td>{_number(current["occupied"])}</td></tr>
<tr><th scope="row">Total de cargos aprovados</th><td>{_number(current["authorized"])}</td></tr></tbody></table>
<p><a href="{escape(current["source"]["url"], quote=True)}">Planilha oficial da referência atual (ODS)</a></p></div></div></section>'''


def _history(observations):
    maximum = max(1, *(row["vacant"] for row in observations))
    magnitude = 10 ** math.floor(math.log10(maximum / 4))
    step = max(1, math.ceil(maximum / 4 / magnitude) * magnitude)
    ceiling = step * 4
    by_month = {row["reference_month"]: row for row in observations}
    year, month = map(int, observations[-1]["reference_month"].split("-"))
    start_year, start_month = map(int, CUTOFF.split("-"))
    months = [f"{index // 12:04d}-{index % 12 + 1:02d}"
              for index in range(start_year * 12 + start_month - 1, year * 12 + month)]
    width = max(940, len(months) * 80 + 170)
    right = width - 85
    graphics, points, rows, missing = [], [], [], []
    runs = [[]]
    for tick in range(5):
        y = 270 - tick * 60
        graphics.append(f'<line x1="85" y1="{y}" x2="{right}" y2="{y}" class="grid-line"/>'
                        f'<text x="73" y="{y + 5}" text-anchor="end">{_number(round(tick * step))}</text>')
    for index, reference in enumerate(months):
        x = width / 2 if len(months) == 1 else 85 + (right - 85) * index / (len(months) - 1)
        label = _month(reference)
        year, month = reference.split("-")
        graphics.append(f'<text x="{x}" y="299" text-anchor="middle">{MONTHS[int(month) - 1][:3]}/{year}</text>')
        row = by_month.get(reference)
        if row is None:
            missing.append(f"{label}: indisponível.")
            graphics.append(f'<text x="{x}" y="319" text-anchor="middle" class="gap-label">indisponível</text>')
            rows.append(f'<tr><th scope="row">{label}</th><td colspan="4">Indisponível — sem observação oficial aceita.</td></tr>')
            runs.append([])
            continue
        rows.append(f'<tr><th scope="row">{label}</th><td>{_number(row["occupied"])}</td>'
                    f'<td>{_number(row["vacant"])}</td><td>{_number(row["authorized"])}</td>'
                    f'<td><a href="{escape(row["source"]["url"], quote=True)}">Planilha oficial (ODS) — {label}</a></td></tr>')
        y = 270 - row["vacant"] / ceiling * 240
        runs[-1].append(f"{x},{y}")
        title = f'<title>Vagos: {_number(row["vacant"])} — {label}</title>'
        points.append(f'<rect x="{x - 4}" y="{y - 4}" width="8" height="8" class="vacant-point">{title}</rect>')
    for run in runs:
        if len(run) > 1:
            graphics.append(f'<polyline aria-label="Vagos" points="{" ".join(run)}" '
                            f'fill="none" stroke="#795517" stroke-width="3" stroke-dasharray="8 6"/>')
    graphics.extend(points)
    note = ("Apenas um mês disponível: um único ponto de cargos vagos, sem tendência. "
            "Novos pontos aparecerão quando novas referências oficiais estiverem disponíveis."
            if len(observations) == 1 else "")
    gaps = "Meses indisponíveis não são zeros. As linhas são interrompidas nessas lacunas, sem interpolação."
    return f'''<section class="panel" aria-labelledby="history-title"><h2 id="history-title">Histórico</h2>
<p>Cargos vagos em cada mês de referência oficial, em valores absolutos. Estoque de postos não ocupados, não saídas no período.</p>
<p>{note}</p><p>{gaps}</p><figure>
<div class="chart-scroll" tabindex="0" role="region" aria-label="Gráfico histórico; role horizontalmente em telas pequenas">
<svg id="history-chart" viewBox="0 0 {width} 360" style="min-width: {width}px" role="img" aria-labelledby="history-chart-title history-description">
<title id="history-chart-title">Histórico de cargos vagos</title>
<desc id="history-description">{note} {gaps} {" ".join(missing)} Vagos: quadrados e linha tracejada. Os valores exatos estão na tabela abaixo.</desc>
<text x="85" y="18">Cargos vagos (quantidade)</text>{"".join(graphics)}
<text x="{width / 2}" y="343" text-anchor="middle">Mês de referência oficial</text>
<path id="history-plot" d="M85 30H{right}V270H85Z" fill="transparent" pointer-events="none"/></svg></div>
<figcaption><span class="legend-item">■ ┄ Cargos vagos (quadrados e linha tracejada)</span></figcaption></figure>
<div class="table-scroll" tabindex="0" role="region" aria-label="Tabela histórica; role horizontalmente em telas pequenas">
<table id="history-values"><caption>Cargos por mês de referência</caption>
<thead><tr><th scope="col">Mês</th><th scope="col">Ocupados</th><th scope="col">Vagos</th><th scope="col">Aprovados</th><th scope="col">Fonte</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div></section>'''


def render_site(history, status, destination):
    """Build a complete artifact; never fetch sources, read a clock or mutate inputs."""
    destination = Path(destination)
    (destination / "data").mkdir(parents=True, exist_ok=True)
    for name, value in (("history", history), ("status", status)):
        write_json(destination / "data" / f"{name}.json", value)
    shutil.copytree(Path(__file__).with_name("assets"), destination / "assets", dirs_exist_ok=True)
    observations = sorted(history["observations"], key=lambda row: row["reference_month"])
    current_content = (_current(observations[-1]) if observations else
                       '<section class="panel"><h2>Dados indisponíveis</h2>'
                       '<p>Nenhuma observação oficial válida está disponível. '
                       'Não há números ou proporções a exibir.</p></section>')
    history_content = _history(observations) if observations else ""
    checked_at = escape(status["last_successful_check"], quote=True)
    html = f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Cargos aprovados, ocupados e vagos de Perito Criminal Federal na Polícia Federal. Dados oficiais mensais, em totais nacionais.">
<title>Perito Criminal Federal — Polícia Federal</title>
<link rel="stylesheet" href="assets/dashboard.css">
<script src="assets/inspection.js" defer></script></head>
<body><a class="skip-link" href="#conteudo">Ir para o conteúdo</a>
<header class="site-header"><div class="wrap"><p class="eyebrow">Quadro da carreira · Dados oficiais</p>
<h1>Perito Criminal Federal — Polícia Federal</h1>
<p>Totais nacionais, todas as classes da carreira combinadas, sem divisão por especialidade ou localização.</p></div></header>
<main id="conteudo" class="wrap" tabindex="-1">
{current_content}
<aside class="context" aria-label="Como interpretar os dados">
<p>Última verificação bem-sucedida: <strong><time datetime="{checked_at}">{_check_time(status["last_successful_check"])}</time></strong>.</p>
<p>Retratos oficiais mensais, não dados em tempo real. Cargos vagos são postos aprovados em lei e não ocupados; <strong>não representam vagas de concurso</strong>.</p>
<p>A data da verificação não é a referência dos cargos. Uma verificação recente pode não encontrar um novo mês publicado.</p></aside>
{history_content}
<section class="sources" aria-labelledby="sources-title"><h2 id="sources-title">Fontes e escopo</h2>
<p><a href="{DATASET_URL}">Cargos Vagos e Vacâncias — conjunto de dados oficial</a>.</p>
<p>Somente Polícia Federal (órgão {PF_ORGANIZATION["code"]}), cargo Perito Criminal Federal, somando Classe Especial, 1ª, 2ª e 3ª classes. Outras carreiras e organizações não estão incluídas.</p>
<p>Histórico a partir de {_month(CUTOFF)}. Dados agregados, sem registros pessoais.</p>
<p>Dados para consulta: <a href="data/history.json">histórico em JSON</a> e <a href="data/status.json">última verificação em JSON</a>.</p></section>
</main><footer class="wrap"><p>Fonte mensal oficial. Sem estimativas de efetivo ou previsões de concurso.</p></footer></body></html>
'''
    (destination / "index.html").write_text(html, encoding="utf-8")
