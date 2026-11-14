# [DEBUG-uf-linux] Temporary sandbox A/B/A preparation (#26)

**Not executed; not a production fix, AppArmor attribution, Linux compatibility
claim, or Gov-source qualification.** #15, #16 and whole #8→#9 remain open. The
owner's UF de lotação assumption remains unchanged. Remove this temporary probe
after the coordinator has reviewed its evidence; do not wire it into production.

## Measured evidence versus hypotheses

The independently sanitized `linux-diagnosis-verified.json` from trusted run
**43610510498**, code **38f2c2abdd52c1a597a84de4e00624bd90803d81**, records three
fresh blank startups: `early_exit`, `SIGABRT`, `sandbox_refusal` + `crash`, no
DevTools port, and successful process-group/profile cleanup. Python 3.13.18,
Node v26.13.1 and Chrome 157.0.8103.78 executable hashes match before/after.
This establishes a reproducible startup sandbox refusal, **not its cause**.
Qualification run 43607769377 remains opaque/unqualified. No government requests
are authorized by this experiment.

Ranked falsifiable hypotheses, retained from the primary-source investigation:

1. **Executable-specific AppArmor userns restriction:** an exact-path allowance
   changes red startup to ready, and its removal restores red startup.
2. **Kernel/host namespace availability or quota:** the allowance does not restore
   startup when the namespace capability or quota is unavailable.
3. **Helper packaging/configuration:** if scoped policy has no reversible effect,
   helper configuration remains possible; do not guess setuid/chmod remedies.

## Primary-source findings (conditional)

- [Ubuntu 24.04 release notes](https://discourse.ubuntu.com/t/noble-numbat-release-notes/39890)
  document restricted unprivileged user namespaces and application-specific
  profiles. They do not establish the policy of the measured GitHub runner.
- [Chromium's AppArmor guidance](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md)
  explains pathname attachment: `/opt/google/chrome/chrome` does not automatically
  cover a custom CfT extraction. It documents ABI 4.0, global tunables,
  `flags=(unconfined)` and `userns,`. This is an application-specific **exception**,
  not restrictive AppArmor confinement; Chrome's internal sandbox stays enabled.
  Its wildcard example is deliberately narrowed here to one protected executable.
- [AppArmor ABI 4.0](https://gitlab.com/apparmor/apparmor/-/blob/master/profiles/apparmor.d/abi/4.0)
  names the `namespaces/mask` feature `userns_create`. The probe reads only that
  bounded feature mask, emitting a boolean/null, not the mask.
- [Kernel namespace-limit documentation](https://docs.kernel.org/admin-guide/sysctl/user.html#max-user-namespaces)
  describes per-user/per-namespace limits with ancestor accounting. A positive
  `max_user_namespaces` is supporting evidence, **not remaining capacity**.
- Pinned Chromium [credentials.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.78/sandbox/linux/services/credentials.cc)
  (`CanCreateProcessInNewUserNS`) probes creation/nesting and accepts failures
  including `EPERM`, `EUSERS`, `EINVAL`, `ENOSPC`. Generic refusal/EPERM alone
  cannot attribute the failure to AppArmor.
- Pinned [setuid_sandbox_host.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.78/sandbox/linux/suid/client/setuid_sandbox_host.cc)
  prefers adjacent `chrome-sandbox`; an environment helper is not necessarily an
  override. [Ubuntu execve(2)](https://manpages.ubuntu.com/manpages/noble/en/man2/execve.2.html)
  documents `nosuid`/`NoNewPrivs` suppressing setuid elevation. No helper elevation,
  helper override, `--no-sandbox` or sandbox-disabling argument is used here.
- [apparmor_parser(8)](https://manpages.ubuntu.com/manpages/noble/en/man8/apparmor_parser.8.html)
  defines `--add` (collision fails), `--remove` and `-K` (no caching). The probe
  never replaces a profile, reloads a service/directory, or changes global policy.

## Prepared experiment and safety boundaries

Workflow `.github/workflows/sandbox-experiment.yml` is manual-only, exact-repo,
main-only, `contents: read`, pinned checkout of the dispatch SHA with credentials
unpersisted. No inputs, source overrides, Gov/frontend calls, ordinary collector
retries, publication, accepted-data writes, Git mutations, packages or global
policy changes. Only the coordinator may dispatch **after fresh review and main
staging**. Do not dispatch from this branch or run privileged operations locally.
The job runs the full offline suite first, with the same pinned Python setup.
Production workflows, installer, runtime manifest, diagnostic driver/startup helper
and collector recipe remain unchanged.

`ensure_runtime` verifies the original managed runtime. It intentionally rejects
another owner's runtime directory, so it is **not** called as nonroot on the
root-owned copy. Instead a separate, minimal privileged owner creates an exclusive
`/opt/perito-uf-sandbox-<128-bit-random>/runtime` subtree. It refuses collisions,
symlink/writable/non-root ancestor chains and special/setuid/setgid files. It
compares bounded full-tree SHA256 inventories before/after copying and rechecks
Node/Chrome against the existing executable pins. Relative internal symlinks are
preserved; escaping/absolute symlinks are rejected. Copied directories/files are
root-owned, nonwritable to the runner; shared ancestors are never repaired.
A separate `profiles` sibling is exclusively created and assigned to the runner
for Chrome's temporary directories via `TMPDIR` in all phases. It is never an
executable ancestor and is removed with the owned subtree, including leftover
profiles after interruption. No Node/Chrome executable is executed as root.

All phases use that **same** protected path and the existing diagnostic driver's
`observations`, `receipt` and strict report validator. Each phase verifies the
same pinned Python/Node/Chrome receipts before/after and uses the existing three
fresh launches with the identical seven Chrome arguments and `about:blank`.
Moving the runtime is not the A→B variable: it occurs **before A1**. The original
runtime location is never used as A1 or A2.

1. Read supporting numeric/boolean host facts; unknown/inaccessible means null,
   never a diagnosis. Missing required support stops without privileged staging.
   No journal, environment dump, namespace enumeration or active namespace probe.
2. **A1:** no owned profile. Require 3/3 launched `early_exit`/`SIGABRT`/
   `sandbox_refusal`, no port/readiness, and complete cleanup. Otherwise stop as
   non-reproduction; never load a profile to manufacture the desired result.
3. **B:** after checking no owned processes/policy collision and unchanged copied
   tree, load one uniquely named exact-executable profile. Its root-owned file
   lives inside the owned subtree; `apparmor_parser --add -K` loads only it,
   using no cache or system parser configuration. Same three observations.
4. **A2:** verify browser cleanup, unload **only** the owned policy, verify its
   absence, and rerun unchanged. `reversible_effect` requires B 3/3 ready AND
   A2 3/3 matching red. Other outcomes are non-reproduction, no reversible effect,
   unsupported/failure/interruption; none authorizes a production change.

The privileged owner accepts only stage/load/unload/cleanup actions, with no
caller-selected policy/base/parser/executable. Root-only process inspection is
limited to detecting executables inside its own unique runtime tree, not unrelated
namespace enumeration. Normal observations must finish Chrome group/profile
cleanup before policy/root removal. On EOF/graceful interruption the owner's
`finally` stops any surviving processes executing that exact runtime, verifies
absence, removes only its own policy, verifies absence, then removes only its
exclusively created subtree. Unknown process visibility/removal failure fails
closed and is explicit, never success. No root subtree deletion under a browser
known still live. Repeated interruption does not skip cleanup. Parser subprocesses
are bounded (20 seconds per parser operation; 150-second staging/transition alarm);
no raw output is retained. PID descriptors prevent fallback cleanup from signalling
a recycled PID. Hard SIGKILL, runner loss or an unavailable
kernel cannot promise a final artifact/cleanup receipt: the ephemeral VM's
destruction is the final boundary, not evidence of in-job cleanup.

## Artifact and interpretation

Only `uf-sandbox-experiment.json` is uploaded, artifact name
`uf-sandbox-experiment-SHA-RUN_ID-ATTEMPT`, 7-day retention, including on step
failure when the sanitized file exists. No raw stderr/journal/profile lists,
paths, URLs, PIDs, environment, tokens or logs are uploaded.

Fixed schema version 1:

- tag/scope/`qualification: false`, fixed-vocabulary status;
- provenance: exact code revision, run ID, attempt (validated formats);
- runtime before/after: only expected versions and verified executable SHA256;
- resources SHA256: experiment/owner/diagnostic/startup/manifest/installer/recipe;
- host before/after: root boolean, AppArmor enabled, restriction sysctl, clone
  sysctl, max-user-namespace integer, ABI/parser/userns-feature boolean/null;
- `global_facts_unchanged`: equality of those read-only facts, **not proof that
  all host policy was unchanged**;
- experiment: copied-tree SHA256, A1/B/A2 existing sanitized observations,
  fixed status, and explicit profile/runtime/process cleanup booleans.

A green workflow is not a green B and is not source qualification. Even a
reversible effect is evidence only for this scoped allowance on this runner/path,
not universal AppArmor attribution. Actual B-green/A-red reversal must be reviewed
before considering any production fix; then #15 still needs separate authorized
Gov qualification and #16 acceptance remains separate.

## Offline validation and temporary cleanup plan

`python3 -m unittest tests.test_sandbox_experiment tests.test_sandbox_boundaries -v`
uses external privileged-command/observer stand-ins and temporary files. It covers
A/B/A sequencing and identical paths, non-reproduction, collisions/refused loads,
invalid/private output, browser-cleanup failure, owner-cleanup failure, nonzero
observer status, symlink/ownership/mode/integrity boundaries and repeated SIGTERM.
These are orchestration/privacy checks, **not Linux/AppArmor execution proof**.

After the reviewed experiment, remove this workflow, the two sandbox scripts,
their two test modules and this temporary note (or retain a separately reviewed
sanitized findings summary). Existing diagnostic infrastructure is not part of
that deletion. Artifact expires after seven days; the coordinator should inspect
all cleanup booleans immediately and stop on unknown/failed cleanup. Do not
retry with global relaxation or broaden this profile when support is absent.
