"""Internal renderer. Consumes aggregate history and operational status only."""
from html import escape
import json
from pathlib import Path


def _number(value):
    return f"{value:,}".replace(",", ".")


def render_site(history, status, destination):
    """Build a complete local-only artifact in destination (no persistence)."""
    destination = Path(destination)
    (destination / "data").mkdir(parents=True, exist_ok=True)
    for name, value in (("history", history), ("status", status)):
        (destination / "data" / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    observations = history["observations"]
    current = max(observations, key=lambda row: row["reference_month"])
    rows = "".join(
        f'<tr><th scope="row">{escape(row["reference_month"])}</th>'
        f'<td>{_number(row["occupied"])}</td><td>{_number(row["vacant"])}</td>'
        f'<td><a href="{escape(row["source"]["url"], quote=True)}">Planilha oficial</a></td></tr>'
        for row in observations
    )
    html = f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Perito Criminal Federal — Polícia Federal</title></head>
<body><main><h1>Perito Criminal Federal — Polícia Federal</h1>
<p>Totais nacionais, todas as classes da carreira.</p>
<h2>Referência oficial: {escape(current["reference_month"])}</h2>
<p>Ocupados: <strong>{_number(current["occupied"])}</strong></p>
<p>Vagos: <strong>{_number(current["vacant"])}</strong></p>
<p>Total de cargos aprovados: <strong>{_number(current["authorized"])}</strong></p>
<p>Última verificação bem-sucedida: {escape(status["last_successful_check"])}</p>
<p>Retratos oficiais mensais, não dados em tempo real nem vagas de concurso.</p>
<h2>Histórico</h2><table><caption>Cargos por mês de referência</caption>
<thead><tr><th>Mês</th><th>Ocupados</th><th>Vagos</th><th>Fonte</th></tr></thead>
<tbody>{rows}</tbody></table>
</main></body></html>
'''
    (destination / "index.html").write_text(html, encoding="utf-8")
