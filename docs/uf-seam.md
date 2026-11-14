# UF core seam — native #13

Successors: #14 owns UF bars/ranking and presentation; #15 owns workflow wiring,
pins, trusted Ubuntu/Python 3.13 anonymous acquisition proof. #9 owns any UF time
series. This core adds neither that UI/history nor a runtime qualification claim.
Existing national ODS history/status schemas, guards, byte-sensitive national
correction rules and vacancy-first/real-mouse UI are unchanged.

## Public composition boundary

```python
from perito_dashboard import refresh_and_build, UFExport

refresh_and_build(data_dir, site_dir, *, source=None, uf_source=None, clock=None)
# -> {"national": outcome, "uf": outcome, "publication": publication}
```

- `source` retains the national `archive_index()`, `year_index(year)` and
  `spreadsheet(url)` boundary. `uf_source.latest_export() -> UFExport` is
  independent. `UFExport(content: bytes, evidence: dict)` is frozen. No parser,
  renderer or orchestration collaborator needs to be mocked.
- Omitted boundaries use the real official collectors, **even if the other
  boundary is supplied**. Tests explicitly supply both independent external
  sources or replace the external runtime. There is no fixture/URL/session
  qualification override in production.
- `clock() -> aware datetime` is optional. The UF successful check is sampled
  after acquisition so the real download cannot postdate its check. Backward
  clocks/stale saved checks invalidate the composed transaction.
- Outcomes: `updated`, `unchanged`, `failed`; UF can additionally be `blocked`
  when its required executable is absent. `publication` is `complete` when both
  feeds succeed, `partial` when exactly one succeeds. Partial success returns
  normally. No healthy feed, invalid saved state, stale/concurrent writer or
  publication failure raises `ValueError`/`OSError` and preserves accepted output.
- `python -m perito_dashboard --data-dir data --site-dir site` uses both real
  boundaries. CLI prints the three outcomes; complete/partial exit 0, total or
  transaction failure exits nonzero. No workflow modification is included here.

### Concrete offline public-flow example (tests only)

```python
import json
from datetime import datetime, timezone
from pathlib import Path
from perito_dashboard import refresh_and_build, UFExport
from tests.sources import ControlledArchive

class ControlledUF:
    def latest_export(self):
        fixtures = Path('tests/fixtures/uf')
        return UFExport((fixtures / 'run-6.xlsx').read_bytes(),
                        json.loads((fixtures / 'run-6.json').read_text()))

result = refresh_and_build('/tmp/example-perito/data', '/tmp/example-perito/site',
                           source=ControlledArchive(), uf_source=ControlledUF(),
                           clock=lambda: datetime(2026, 11, 14, 12, tzinfo=timezone.utc))
assert result == {'national': 'updated', 'uf': 'updated', 'publication': 'complete'}
# Assert data/uf.json, site/data/uf.json and site/index.html, not private helpers.
```

For an outage, supply a source whose external method raises `ValueError`/`OSError`;
never omit that boundary expecting it to be disabled. See the public acceptance
cases for healthy/failing national and UF pairs and exact byte-preservation checks.

### Renderer integration for #14

The existing **private** rendering boundary is now
`render_site(history, status, destination, *, uf=None, uf_status=None)`.
`history`/`status` may both be `None` for first national absence; `uf`/`uf_status`
are a paired accepted `uf.json`/`uf-status.json` mapping or both `None`.
The orchestrator invokes it once against the staging site with the independently
selected new/last-good bundles; rendering must not collect, accept or advance checks.
#14 can replace the minimal `uf_content` summary using
`uf['current']['counts_by_uf']`, `uf['current']['reference_month']` and
`uf_status['last_successful_check']`. Keep missing bundles distinct from explicit
zero and preserve the national markup/assets/inspection behavior. This is not a
new public renderer/parser API; tests still enter `refresh_and_build`.

## Acceptance and atomic publication

National and UF candidates are built independently, then one site is rendered
and data/site directories are promoted under the existing locks/signature checks
and rollback. A failed feed retains **both** accepted dataset and successful-check
file byte-for-byte in data and `site/data`. It cannot advance its check, block a
healthy feed, fabricate zeros, force national/UF equality or delete last-good data.
On first-run absence the missing pair is not written; the composed page says the
feed/check is unavailable and does not link nonexistent national JSON files.
A shared storage/build/promotion error is never treated as source partial success.

Only `history.json`, `status.json`, `uf.json`, `uf-status.json` are accepted in the
saved data directory. Saved UF documents must be a paired valid schema; identities,
scope, sums, coverage, provenance, correction references and checks are validated
before collection. Unknown schema or corruption is not silently reset/migrated.

## Exact version-1 files

All JSON is UTF-8 (`ensure_ascii=False`), indent 2 plus final newline. `site/data`
contains byte-identical accepted files. Nothing is written to the working data
folder unless publication succeeds. No XLSX/profile/cookies/control tokens/raw
frontend trace is persisted in it.

`uf.json` has exactly:

```text
{
  "schema_version": 1,
  "current": Snapshot,
  "corrections": [{"superseded": Snapshot, "corrected_at": aware-ISO-timestamp}, ...]
}
```

`uf-status.json` has exactly:

```text
{
  "schema_version": 1,
  "last_successful_check": aware-ISO-timestamp,
  "last_export": Snapshot
}
```

`Snapshot` has exactly these fields:

- `reference_month`: `YYYY-MM` from the returned workbook and actual selected
  latest eligible native month; its numeric Qlik/Excel serial must agree.
- `rows`: lexically sorted seven-string rows in exact column order
  `[Ano, Mês, Grupo Situação do Vínculo, Nome do Cargo, Orgão, UF, Servidores]`.
  Original explicit zero rows remain present; absent class/UF groups stay absent.
- `counts_by_uf`: object with all 27 uppercase UF keys and nonnegative integer
  sums. `total`: their integer sum, reconciled **only** to the UF table's own total.
- `scope`: exactly
  `{"organization":"DPF","native_organization":"Departamento De Policia Federal","status":"Ativo","classes":["Perito Criminal Federal 1a Cla","Perito Criminal Federal 2a Cla","Perito Criminal Federal 3a Cla","Perito Criminal Federal Classe"],"metric":"Servidores"}`.
- `geography`: exactly
  `{"source_field":"UF Servidores","meaning":"UF de lotação","basis":"project_assumption","officially_verified":false}`.
- `coverage`: `{"ufs": [all 27 UF codes sorted lexically], "absent_class_uf_pairs":"not_asserted_zero"}`.
- `semantic_identity`: `{"version":1,"sha256":64-lowercase-hex}`.
- `source`: exactly the following keys:
  - `url`: `https://pep.paineis.gov.br/extensions/pep/index.html`
  - `app_id`: `aec332a1-406b-4fec-a776-b1ed66735961`
  - `table`: `Dwnkq`
  - `retrieved_at`: the completed fresh download's aware ISO timestamp
  - `download_guid`: same-run correlated browser download identity
  - `own_source_total`: reconciled integer table total
  - `sha256`: raw XLSX SHA-256
  - `evidence_sha256`: SHA-256 of the accepted evidence dictionary serialized
    with `ensure_ascii=False, sort_keys=True, separators=(',', ':')`
  - `filters`: actual final selection-label → string-list map, with exactly
    `Seção:[Servidores]`, `Mês/Ano:[native month label]`,
    `Grupo Situação do Vinculo:[Ativo]`,
    `Orgão:[Departamento De Policia Federal]`, `Cargo:[four exact classes above]`,
    `Dimensão:[Grupo Situação do Vínculo,Nome do Cargo,Orgão,UF]`, `Métricas:[Servidores]`
  - `organization_mapping`: `{"nativeOrgaoField":"Órgão (Servidores)","nativePfLabel":"Departamento De Policia Federal","physicalFields":["Sigla Orgão Vinculado (Servidores)"],"availableAbbreviations":["DPF"]}`
  - `anonymous_session`: `{"cookie_count_before_navigation":0,"websocket_status":101}`

The identity's **exact** preimage is UTF-8 JSON with `ensure_ascii=False`,
`sort_keys=True`, `separators=(',', ':')` of:
`{"version":1,"rows":sorted_rows,"scope":scope,"geography":geography,"coverage":coverage}`.
Thus ZIP timestamp/metadata/raw hash noise does not change business identity.
A semantically identical export leaves `uf.json` byte-identical, advances only its
successful-check/provenance file (`last_export` records the new raw hash/retrieval).
A same-period semantic change appends the superseded snapshot plus correction
time. A newer period replaces current and clears same-period correction audit:
this is latest-only, **not** UF history. Older candidate periods are rejected.

For the authentic fixture: September 2026, 88 explicit rows, all 27 UFs, DF 324,
total 1,108; national controlled acceptance remains 1,195. See fixture provenance
and independent literal assertions in `tests/fixtures/uf/README.md`, `tests/test_uf.py`.

## Collector / document contract

Implementation resources (ordinary code; no harness runtime):

- `perito_dashboard/_collector.py`: every live call obtains two sequential fresh
  exports, each with its own process group and absolute temporary run, bounded
  controller, new GUID-named download, size check and mandatory cleanup. Both
  exports pass the same central parser, agree on period/semantic identity, have
  different GUIDs and non-overlapping sessions. No qualification/single-run flag.
- `perito_dashboard/runtime.py` and `collector/runtime.json`: checksum/version
  verified private Linux Node/Chrome installation, inside the UF candidate.
  Setup failure cannot suppress healthy national advancement.
- `perito_dashboard/collector/browser-probe.mjs`: isolated clean Chrome profile,
  dynamic loopback DevTools/control ports, random authenticated loopback control,
  ordinary anonymous frontend bootstrap, trace, denial stop, bounded cleanup.
- `perito_dashboard/collector/collect-flow.js`: installed native filters, metadata
  mapping from exact native PF name to the returned DPF abbreviation, actual final
  selection rereads, aggregate table dimensions/measure/total. The controller then
  invokes the **installed public download button**, not a reconstructed export URL.
- `perito_dashboard/_uf.py`: bounded strict OOXML parser and document/evidence
  acceptance; it never requests an employee field/table or individual data.

`PERITO_NODE` and `PERITO_CHROME` optionally select explicit executable paths
(including paths with spaces); otherwise system discovery uses `node` and common
Chrome/Chromium names, including macOS Chrome. Node needs built-in WebSocket,
fetch and AbortSignal timeout; use a modern Node (22+). Trusted workflows use
`PERITO_RUNTIME_ROOT` with the [exact runtime lock](uf-runtime.md), not CI browser
discovery. Actual Ubuntu acquisition remains pending. Resources are read only
in place. Outputs/profile/download/logs are in a fresh owned temporary directory;
no existing browser/tab/profile or private session is attached/reused.
No runtime qualification flag, cookie injection, Gov outreach, alternate network,
proxy/identity change, WAF bypass or retry-after-denial mechanism is provided.
HTTP 401/403/429, denied WebSocket/Qlik or authentication/CAPTCHA/UI denial stop
collection. The overall controller and browser each have a 180-second bound.
Cleanup closes/kills only owned processes and removes only the owned profile/run.

`UFExport.evidence` has three required top-level keys (the live adapter also
returns cleanup receipts and browser version for the read-only proof):

- `snapshot`: final public frontend result: `entry` (`...index.html#fvm`), `appId`,
  `table`, `latest` (`qText`, numeric `qNum`), `availablePeriodCount`,
  `finalSelections` (`label`, `selected`), `mapping` (four organization mapping
  keys above), `qSize` (`qcx:7`, `qcy:explicit row count`), `dimensions` (first six
  headers), `qGrandTotalRow` (one numeric integer `qNum`), `measure` (`title:Servidores`),
  `utc`. Collector diagnostic extras (`availablePeriods`, trace/title/etc.) are
  allowed and included in the evidence fingerprint.
- `available_periods`: native month-list cells (`qText`, numeric `qNum`, `qState`).
  Only eligible O/A/S states participate in latest selection and count validation.
- `trace`: same-run `isolation` (zero cookies, `utc`), successful `ws_handshake`,
  one `Browser.downloadWillBegin` (`guid`, official `tempcontent` URL, `utc`), and
  one completed `Browser.downloadProgress` (same GUID, matching positive
  `receivedBytes`/`totalBytes` equal to the actual workbook byte length, `utc`). Isolation ≤ snapshot ≤ download start ≤
  completion ≤ check. Intermediate progress events are allowed, denials rejected.

Workbook acceptance bounds: ≤2 MB raw, ≤8 MB expanded, ≤40 unique unencrypted
members, one declared worksheet resolving to `xl/worksheets/sheet1.xml`, known
package parts only, no external relationships/path traversal/DTD/entities,
≤109 ordered rows including header and exactly seven explicit ordered cells.
Shared-string, inline-string and numeric cells are supported, not formulas/errors.
Exact headers, one period, four literal classes, Ativo, DPF and all 27 actual UFs
are required. Blank/masked/negative/fractional counts, duplicate groups, mixed
periods/populations, unexpected columns/rows/coverage or source-total mismatch fail
closed. No absent-pair-to-zero conversion or national-total reconciliation exists.

## Verification / limits

`python3 -m unittest discover -v` is network-free. Tests call the public complete
refresh/build boundary and compare independent literal persisted and rendered
outputs. They cover both partial directions/first absences, checks and preserved
bytes, genuine noisy XLSX identity, corrections, explicit zeros, malformed source,
latest selection, corrupt saved state, stale clocks and real filesystem failures.
`tests/uf_runtime.py` is an **offline external process stand-in**, only installed
by a test; it exercises the production controller's process/control/download/
cleanup boundary with genuine saved evidence, not the real Chrome/frontend runtime.
It is neither runtime qualification nor a production fixture fallback.

Trusted Ubuntu/Python 3.13 + pinned Node/Chrome clean anonymous first-and-repeat
acquisition remains **PENDING** for #15. The [manual trusted-main workflow and
operator runbook](uf-runtime.md) exercise that same two-export production path,
retain both raw aggregate XLSX and sanitized evidence/provenance, and never
publish a site. #15 stays open until the coordinator reviews its actual proof;
offline tests are not trusted runtime proof.
