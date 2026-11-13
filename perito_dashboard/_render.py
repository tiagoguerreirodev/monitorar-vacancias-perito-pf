"""Internal, local-only dashboard renderer for accepted aggregate observations."""
from datetime import datetime, timedelta, timezone
from html import escape
import json
import math
from pathlib import Path
import shutil


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


def _pie(current):
    total = current["authorized"]
    if not total:
        return '<p class="unavailable">Proporção indisponível: total aprovado igual a zero. Nenhum setor de pizza é desenhado.</p>'
    occupied = _percent(current["occupied"], total)
    vacant = _percent(current["vacant"], total)
    sectors = []
    angle = -math.pi / 2
    for key, label, fill in (("occupied", "Ocupados", "#145b79"),
                             ("vacant", "Vagos", "url(#vacancy-hatch)")):
        fraction = current[key] / total
        if not fraction:
            continue
        title = (f'<title>{label}: {_number(current[key])} '
                 f'({_percent(current[key], total)})</title>')
        if fraction == 1:
            sectors.append(f'<circle cx="120" cy="120" r="100" fill="{fill}">{title}</circle>')
            continue
        end = angle + fraction * 2 * math.pi
        x1, y1 = 120 + 100 * math.cos(angle), 120 + 100 * math.sin(angle)
        x2, y2 = 120 + 100 * math.cos(end), 120 + 100 * math.sin(end)
        path = (f"M 120 120 L {x1:.4f} {y1:.4f} "
                f"A 100 100 0 {int(fraction > .5)} 1 {x2:.4f} {y2:.4f} Z")
        sectors.append(f'<path d="{path}" fill="{fill}" stroke="#fff" stroke-width="2">{title}</path>')
        angle = end
    return f'''<svg id="current-pie" viewBox="0 0 240 240" role="img"
aria-labelledby="current-pie-title current-pie-description">
<title id="current-pie-title">Distribuição de cargos em {_month(current["reference_month"])}</title>
<desc id="current-pie-description">Ocupados: {_number(current["occupied"])} ({occupied}).
Vagos: {_number(current["vacant"])} ({vacant}). Total: {_number(total)} cargos aprovados.
Vagos têm hachuras; ocupados têm preenchimento sólido.</desc>
<defs><pattern id="vacancy-hatch" width="8" height="8" patternUnits="userSpaceOnUse">
<rect width="8" height="8" fill="#fff2ca"/>
<path d="M-2 2 L2 -2 M0 8 L8 0 M6 10 L10 6" stroke="#795517" stroke-width="2"/>
</pattern></defs>{"".join(sectors)}</svg>'''


def _current(current):
    rows = "".join(
        f'<tr><th scope="row">{label}</th><td>{_number(current[key])}</td>'
        f'<td>{_percent(current[key], current["authorized"])}</td></tr>'
        for key, label in (("occupied", "Ocupados"), ("vacant", "Vagos"))
    )
    return f'''<section aria-labelledby="current-title" class="panel">
<h2 id="current-title">Situação atual</h2>
<p class="reference">Referência oficial: <strong><time datetime="{current["reference_month"]}">{_month(current["reference_month"])}</time></strong></p>
<div class="current-layout"><figure class="pie">{_pie(current)}
<figcaption><span class="legend-item"><span class="swatch occupied" aria-hidden="true"></span>Ocupados (sólido)</span>
<span class="legend-item"><span class="swatch vacant" aria-hidden="true"></span>Vagos (hachuras)</span></figcaption></figure>
<div><table id="current-values"><caption>Valores da referência atual</caption>
<thead><tr><th scope="col">Situação</th><th scope="col">Cargos</th><th scope="col">Proporção</th></tr></thead>
<tbody>{rows}<tr class="total"><th scope="row">Total de cargos aprovados</th><td>{_number(current["authorized"])}</td><td>{_percent(current["authorized"], current["authorized"])}</td></tr></tbody></table>
<p><a href="{escape(current["source"]["url"], quote=True)}">Planilha oficial da referência atual (ODS)</a></p></div></div></section>'''


def _history(observations):
    maximum = max(1, *(row[key] for row in observations for key in ("occupied", "vacant")))
    magnitude = 10 ** math.floor(math.log10(maximum / 4))
    step = max(1, math.ceil(maximum / 4 / magnitude) * magnitude)
    ceiling = step * 4
    by_month = {row["reference_month"]: row for row in observations}
    year, month = map(int, observations[-1]["reference_month"].split("-"))
    months = [f"{index // 12:04d}-{index % 12 + 1:02d}"
              for index in range(2026 * 12 + 8, year * 12 + month)]
    width = max(940, len(months) * 80 + 170)
    right = width - 85
    graphics, points, rows, missing = [], [], [], []
    runs = {"occupied": [[]], "vacant": [[]]}
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
            for key in runs:
                runs[key].append([])
            continue
        rows.append(f'<tr><th scope="row">{label}</th><td>{_number(row["occupied"])}</td>'
                    f'<td>{_number(row["vacant"])}</td><td>{_number(row["authorized"])}</td>'
                    f'<td><a href="{escape(row["source"]["url"], quote=True)}">Planilha oficial (ODS) — {label}</a></td></tr>')
        for key, name in (("occupied", "Ocupados"), ("vacant", "Vagos")):
            y = 270 - row[key] / ceiling * 240
            runs[key][-1].append(f"{x},{y}")
            title = f'<title>{name}: {_number(row[key])} — {label}</title>'
            if key == "occupied":
                points.append(f'<circle cx="{x}" cy="{y}" r="7" class="occupied-point">{title}</circle>')
            else:
                points.append(f'<rect x="{x - 4}" y="{y - 4}" width="8" height="8" class="vacant-point">{title}</rect>')
    for key, name, color in (("occupied", "Ocupados", "#145b79"), ("vacant", "Vagos", "#795517")):
        dash = ' stroke-dasharray="8 6"' if key == "vacant" else ""
        for run in runs[key]:
            if len(run) > 1:
                graphics.append(f'<polyline aria-label="{name}" points="{" ".join(run)}" '
                                f'fill="none" stroke="{color}" stroke-width="3"{dash}/>')
    graphics.extend(points)
    note = ("Apenas um mês disponível: cada série tem um único ponto, sem tendência. "
            "Novos pontos aparecerão quando novas referências oficiais estiverem disponíveis."
            if len(observations) == 1 else "")
    gaps = "Meses indisponíveis não são zeros. As linhas são interrompidas nessas lacunas, sem interpolação."
    return f'''<section class="panel" aria-labelledby="history-title"><h2 id="history-title">Histórico</h2>
<p>Cargos ocupados e vagos em cada mês de referência oficial, em valores absolutos.</p>
<p>{note}</p><p>{gaps}</p><figure>
<div class="chart-scroll" tabindex="0" role="region" aria-label="Gráfico histórico; role horizontalmente em telas pequenas">
<svg id="history-chart" viewBox="0 0 {width} 360" style="min-width: {max(760, len(months) * 64)}px" role="img" aria-labelledby="history-chart-title history-description">
<title id="history-chart-title">Histórico de cargos ocupados e vagos</title>
<desc id="history-description">{note} {gaps} {" ".join(missing)} Ocupados: círculos e linha sólida. Vagos: quadrados e linha tracejada. Os valores exatos estão na tabela abaixo.</desc>
<text x="85" y="18">Cargos (quantidade)</text>{"".join(graphics)}
<text x="{width / 2}" y="343" text-anchor="middle">Mês de referência oficial</text></svg></div>
<figcaption><span class="legend-item">● ━ Ocupados (linha sólida)</span>
<span class="legend-item">■ ┄ Vagos (linha tracejada)</span></figcaption></figure>
<div class="table-scroll" tabindex="0" role="region" aria-label="Tabela histórica; role horizontalmente em telas pequenas">
<table id="history-values"><caption>Cargos por mês de referência</caption>
<thead><tr><th scope="col">Mês</th><th scope="col">Ocupados</th><th scope="col">Vagos</th><th scope="col">Aprovados</th><th scope="col">Fonte</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div></section>'''


def render_site(history, status, destination):
    """Build a complete artifact; never fetch sources, read a clock or mutate inputs."""
    destination = Path(destination)
    (destination / "data").mkdir(parents=True, exist_ok=True)
    for name, value in (("history", history), ("status", status)):
        (destination / "data" / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
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
<link rel="stylesheet" href="assets/dashboard.css"></head>
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
<p>Somente Polícia Federal (órgão 20115), cargo Perito Criminal Federal, somando Classe Especial, 1ª, 2ª e 3ª classes. Outras carreiras e organizações não estão incluídas.</p>
<p>Histórico a partir de setembro de 2026. Dados agregados, sem registros pessoais.</p>
<p>Dados para consulta: <a href="data/history.json">histórico em JSON</a> e <a href="data/status.json">última verificação em JSON</a>.</p></section>
</main><footer class="wrap"><p>Fonte mensal oficial. Sem estimativas de efetivo ou previsões de concurso.</p></footer></body></html>
'''
    (destination / "index.html").write_text(html, encoding="utf-8")
