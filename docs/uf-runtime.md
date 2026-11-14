# UF runtime and trusted read-only observation (#15)

**Actual trusted Ubuntu acquisition proof: ACCEPTED (#15 closed).** On
14 November 2026, trusted run **43633428483**, attempt **1**, qualified code
`631f35c9c34d3f6bc90f0ad0d584fd94c79b4fe4` using the ordinary two-export
production path. See [receipts, artifact digest and acceptance limits](composed-acceptance.md).
Offline tests and the preceding no-Gov diagnostic alone are not source proof.
Qualification did not publish UF or close the composed/public acceptance gates.

The [source contract](uf-source.md) and [document seam](uf-seam.md) still apply.
UF geography is a project assumption, not an official verified definition. UF
source totals are never reconciled against the separate national total.

## Production behavior (no qualification flag)

`pages.yml` keeps its existing manual/monthly cadence, trusted repository/main
restriction, serialized `pages-main` group, explicit accepted-data artifact,
superseded-main guard and deployment dependency. Only the refresh runner changes
to `ubuntu-24.04`; the deploy job is unchanged except immutable action pinning.
PR/push validation is still offline and never installs/launches the Gov collector.

Both production refresh and manual observation use `OfficialUF.latest_export()`.
It always obtains **two** fresh sequential exports, each from a separate owned
Node process group and Chrome profile with zero initial cookies. The existing
central parser validates each export's exact population, latest period, 27-UF
coverage, actual row count, own-source total, ordinary WS 101, GUID, size and
chronology. Both periods and canonical scope-aware semantic hashes must agree;
the GUIDs must differ and the second isolation must follow the first completion.
ZIP byte hashes need not match. There is no single-export acceptance fallback or
qualification switch. First/second-run denial, runtime/setup/checksum/version,
cleanup or agreement failures are **inside the UF candidate**: healthy national
acceptance can still advance while both previous UF files remain byte-for-byte.

`PERITO_RUNTIME_ROOT` selects the owned managed-runtime directory in the two
trusted workflow collection steps only (not their offline test steps). Node and
Chrome install/verify there *inside* the UF call. The packaged capsule then stages
one exclusive root-owned `/usr/lib/perito-uf-sandbox-<32hex>/runtime` copy,
validates protected ancestors, inventory and executable pins, and loads only its
exact Chrome-path AppArmor userns exception. Node and Chrome remain the caller's
unprivileged processes. The non-executable caller-owned `0700` sibling `p` is
both their actual `TMPDIR` and the parent of two fresh run/profile directories.
The complete UTF-8 singleton paths are preflighted against Linux's 107-byte
limit (pinned Chrome suffixes: 106/102 bytes; profile layout independently tested).
No setuid/helper mode, global policy/sysctl or seven-argument launch change occurs.

`runtime.runtime_capsule()` owns both exports and agreement. It hashes and runs
`--version` on the **protected executables actually used**, before and after,
then asks the owner to verify the protected tree before deletion. Only after
complete policy/process/profile/runtime cleanup, whole bounded typed final
receipt and owner exit zero may `OfficialUF` publish exports, proof or
`runtime_receipt`. The receipt binds protected-tree before/after and final cleanup;
qualification consumes it directly and hashes both new packaged resources
(`_capsule.py`, `collector/runtime-owner.py`), not just a checkout wrapper/cache.
All setup, privilege, policy, integrity and cleanup failures remain UF-local;
shared publication failures still roll back both feeds. Four handled signals
request cooperative cleanup/reaping, never forcibly kill a privileged cleaner.

Managed elevation is refused outside the exact repository/main hosted Ubuntu
workflow identities (`qualify-uf.yml` manual; `pages.yml` manual/schedule), or
when the application is root. Environment checks prevent accidental use, not
forged-environment authorization: sudo remains the OS privilege boundary.
Python is needed by both feeds,
so its verified installation necessarily precedes the application. Local explicit
`PERITO_NODE` / `PERITO_CHROME` discovery remains available; it is not trusted
Ubuntu qualification, and does not bypass repeat/export checks.

Only `data/history.json`, `data/status.json`, `data/uf.json`, `data/uf-status.json`
may be staged by the serialized persistence script. Missing files on first partial
success are allowed. Proof/XLSX/browser material never enters that allowlist.

## Exact runtime lock

Reviewable source: `perito_dashboard/collector/runtime.json` (URLs, lengths,
archive and executable SHA256, publisher provenance). Runner label:
`ubuntu-24.04`, x86_64; it is **not** an immutable OS-image digest. Actual
`ImageOS`, `ImageVersion`, Python/Node/Chrome versions and executable hashes are
recorded in proof. No pip/npm/package manager, unbounded install, system Chrome
fallback, `--no-sandbox`, global AppArmor disable or browser/header/auth bypass.
The ordinary Chrome sandbox is preserved. Ubuntu AppArmor/user-namespace and
shared-library **source-flow** compatibility were established for the exact
qualified code/runtime in the accepted trusted observation, not for future drift. Trusted no-Gov run 43624804937 established reversible
same-path A-red/B-ready/A-red startup with a real port and complete cleanup;
this authorizes the exact-path capsule adoption, not Gov-source qualification.
If that exact exception fails, stop; never disable global policy or sandbox.

| Asset | Version | SHA256 of downloaded archive |
| --- | --- | --- |
| Official actions/python-versions Ubuntu 24.04 x64 | 3.13.18, release `3.13.18-40336726450`, asset `678421609` | `683005a1465d94d40045f6a1a6eb316885b5f08d3360f7922b44ef58a14a9eed` |
| Official Node linux-x64 | v26.13.1 | `5c063e46bab0fbc1c17cc445d7ff129cbdcd0471be6ed83b6ab864f8143bc864` |
| Official Chrome for Testing linux64 | 157.0.8103.78, revision 1717349 | `9223832977a13db3646201b1341c1f9cf08afa3ceae92540116d7b0c062364fb` |

Python's SHA is the official GitHub release-asset digest; Node's is in its
publisher `SHASUMS256.txt`. CfT does not publish a SHA256 in the queried metadata:
the committed SHA was **locally computed**, not a publisher signature. Before
downloading, known-good metadata confirmed version/revision/linux64 URL, and
object headers confirmed generation `1794360528414332`, size `203266906`,
CRC32C `XCtEmw==`, MD5 `n3ml73xVw0ZMdH0ruvsZVg==`. The exact-generation HTTPS
download matched size/CRC32C/MD5 before SHA256 pinning. No Linux binary was run
on the implementing Darwin host. URLs and executable hashes are in the manifest.

`.github/scripts/setup-python.sh` checks Ubuntu/version/architecture, downloads
with HTTPS/180-second bound, verifies length/archive SHA/executable SHA/version,
and exposes the private runtime with `PYTHONHOME`, `LD_LIBRARY_PATH`, Actions PATH.
It deliberately does **not** execute the publisher's pip-upgrading `setup.sh`.
Node/Chrome downloads have a shared 300-second deadline (30-second bounded
reads), length/SHA checks before extraction, executable SHA/version checks before
atomic installation. Failed staging is removed. No fallback selects runner Chrome.

Immutable action pins (the existing Pages major versions are unchanged):

- checkout v7: `3d3c42e5aac5ba805825da76410c181273ba90b1`
- upload-pages-artifact v5: `fc324d3547104276b827a68afc52ff2a11cc49c9`
- deploy-pages v5: `368f82528645a54fb793d4d04e342629a3f51346`
- upload-artifact v7 (read-only proof): `cf430e030ddbb5b0abf93d22962f4752f3646cd9`

## Coordinator-only dispatch, after reviewed main

Do not dispatch a branch/PR or the publication workflow to obtain qualification.
Wait for any Pages activity to finish. This is one bounded manual observation,
not a schedule, site deployment, issue closure or authorization for outreach.

```bash
repo=tiagoguerreirodev/monitorar-vacancias-perito-pf
gh workflow run qualify-uf.yml --repo "$repo" --ref main
gh run list --repo "$repo" --workflow qualify-uf.yml --event workflow_dispatch --limit 5
# Select the actual new RUN_ID; do not mistake an older success for this run.
gh run watch RUN_ID --repo "$repo" --exit-status
gh run view RUN_ID --repo "$repo" --json headSha,attempt,conclusion,url,jobs
# Match SHA, RUN_ID and ATTEMPT from that run:
gh run download RUN_ID --repo "$repo" \
  --name uf-qualification-SHA-RUN_ID-ATTEMPT --dir /tmp/uf-proof-RUN_ID
```

Workflow ID/path: `.github/workflows/qualify-uf.yml`. `workflow_dispatch` only,
exact repository + `refs/heads/main` guard, checkout `${{ github.sha }}` with no
persisted credentials, `contents: read` only, no Pages environment/token/deploy,
no Git commit/push or accepted-data/site write, 20-minute bound, success-only aggregate artifact upload.
No input can enable/skip collection or supply source documents. Its offline tests
run first; then the same packaged self-validating production source runs once.

Artifact `uf-qualification-SHA-RUN_ID-ATTEMPT` (14 days):

- `export-1.xlsx`, `export-2.xlsx`: the two actual fresh aggregate downloads,
  unchanged bytes; no old fixture substituted.
- `proof.json`: both centrally accepted aggregate snapshots (actual month, rows,
  27 UFs, counts, own source total, raw SHA, canonical semantic SHA, selections,
  native DPF mapping), safe isolation/WS/download receipts, owner-observed Node/run
  cleanup plus browser/profile cleanup, protected-tree/final-owner cleanup,
  actual versions/executable SHA, manifest
  pins and unchanged collector-resource hashes. `runtime_verification.before` and
  `.after` contain matching SHA/version observations of the exact resolved
  Python/Node/Chrome executables used by the collector; the qualifier does not
  resolve them again. Unrecognized version output is a fixed non-qualification
  marker, never raw process output. No executable paths are published.
- `workflow.json`: checked-out code revision, workflow run ID and attempt.

No temporary download URLs, selection trace dumps, raw browser/control logs,
DevTools/control endpoints/tokens, cookies, profiles or individual records are
uploaded. A failed observation does not create/upload a success proof directory.
No proof enters accepted data or a Pages artifact. Review run provenance and both
exports, **not merely the green job**. A failure leaves #15 open; do not retry
raw denied WS, change auth/headers/network, or proceed to #16.

## Local checks, cleanup and limits

```bash
python3 -m unittest discover -v
python3 -m compileall -q perito_dashboard tests
node --check perito_dashboard/collector/browser-probe.mjs
node --check perito_dashboard/collector/collect-flow.js
node --check perito_dashboard/assets/inspection.js
bash -n .github/scripts/setup-python.sh .github/scripts/persist-data.sh
git diff --check
# On the trusted runner, only after the normal application step installed pins:
python3 --version
"$RUNNER_TEMP/perito-uf-runtime/node/bin/node" --version
"$RUNNER_TEMP/perito-uf-runtime/chrome-linux64/chrome" --version
sha256sum "$RUNNER_TEMP/perito-uf-runtime/node/bin/node" \
  "$RUNNER_TEMP/perito-uf-runtime/chrome-linux64/chrome"
```

Each collector call closes the owned Chrome, waits/kills only its new process
group, and removes its owned profile/run/download/log directory before returning
bytes. The proof records successful owner-observed cleanup; failure never advances
UF acceptance. Failed proof staging is also deleted. Verified runtime assets live
in the unprivileged ephemeral runner cache; the protected execution copy and its
policy/private sibling are deleted before any UF result is accepted. GitHub
removes the runner cache after the job. For deliberate cleanup **after** use, remove only the known owned
`$RUNNER_TEMP/perito-uf-runtime` and the exact Python install parent exposed in
`PYTHONHOME` (check it is `$RUNNER_TEMP/perito-python-*/runtime` first); never glob
unrelated profiles/processes. Retained proof is intentionally removed separately
by its operator/14-day artifact expiry, not by collector cleanup.

Offline external-process documents cover semantic disagreement, denial, reused
GUID, overlapping sessions, cleanup failure, setup failure and raw-ZIP-noise
identity. They do not establish Linux sandbox, live frontend, WS or download
compatibility. The actual trusted-run SHA/attempt, artifact and XLSX digests are
now recorded in [composed acceptance](composed-acceptance.md). A change to any of
the nine attested collector/runtime resources requires requalification before
publication; docs-only/local acceptance changes do not. Publication remains a
separate coordinator gate.
