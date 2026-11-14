# Genuine aggregate export fixtures (#13)

These are **unmodified public aggregate workbooks**, not reconstructed spreadsheets.
They were supplied by the earlier anonymous ordinary-frontend feasibility runs,
not fetched during this implementation. They contain counts, not employee records.
Neither these captures nor their tests qualify the future trusted CI runtime.

Source: `https://pep.paineis.gov.br/extensions/pep/index.html#fvm`, public app
`aec332a1-406b-4fec-a776-b1ed66735961`, table `Dwnkq`.

Original evidence root (local, not a portable dependency):
`/var/folders/6d/xn0p45kd3td2pb8zhw4zvvbh0000gn/T/perito-collector-qualification-a4fr56fh`.

| Fixture | Original relative path | Raw SHA-256 |
| --- | --- | --- |
| `run-6.xlsx` | `run-6/downloads/f763006f-5265-47a3-835b-05b67f92526d.xlsx` | `5f88f93738b41b035a4bf58450292366afd2aa28b66019c8103e079c0aa6fb55` |
| `run-7.xlsx` | `run-7/downloads/83cde208-3893-4671-a091-266c8ea3ed07.xlsx` | `fbffe323c3485bed0024afe6133f450dc20f51ab8c7aba65a1079be6476e345c` |

Both files are 7,915 bytes. Their September 2026 business rows are identical:
88 explicit class/UF groups, all 27 UFs represented, DF 324, total 1,108. Their
ZIP document metadata differ; that is **not** a business correction. The earlier
researcher's row-only canonical fingerprint was
`9d05ce428f7b51a03718958176a00d49a370a66927282f4b0a65cf86ce3f851d`;
production uses the separately versioned, scope-aware identity in `docs/uf-seam.md`.

Each JSON sidecar is a mechanical extraction of that same run's existing evidence:

- `snapshot`: `export-request.json` → `result.value` (actual final selections,
  native organization mapping, returned dimensions/row count/measure/source total).
- `trace`: `trace.jsonl` entries with kinds `isolation`, `ws_handshake`,
  `Browser.downloadWillBegin`, `Browser.downloadProgress` only.
- `available_periods`: `selection-diagnostics.json` → the `filterCandidates`
  entry labeled `Mês/Ano` → `values`.

Sidecar raw SHA-256 values:

- `run-6.json`: `40f614895cf8b16f70ca8d3126519f2a3b4459a506757f3f2723c9f85ed7d43b`
- `run-7.json`: `5a98e338cc87827c556391294a8507f34b92549d61f97912a158c571a8ee03bc`

The source's `UF Servidores` is used as UF de lotação **by project assumption**,
not independent official verification. The UF total must not be forced to match
national ODS counts. Missing class/UF groups are not zero observations. Controlled
negative/correction/zero cases modify these source bytes/evidence in memory;
`run-6.xlsx` and `run-7.xlsx` themselves stay authentic.
