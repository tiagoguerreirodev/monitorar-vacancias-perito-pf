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

## Actual pre-stage classification and protected-parent follow-up (#30)

The earlier run **43614843495** did not classify its pre-stage refusal. Subsequent
trusted manual-main run **43617881100**, code
**6deb2f2b8ef0d7717f3b29bf69bfdcd2fa4e7137**, now independently verifies
`experiment_failed`, `tree_sha256: null`, empty phases, all cleanup booleans true,
matching before/after runtime receipts, seven matching code resources and unchanged
supporting host facts. Its owner failure is exactly `stage/ancestor_unprotected`.
Actual fixed `lstat` facts show `/`, `/opt`, `/usr`, `/usr/lib` are root-owned,
non-symlink directories; **only `/opt` is group/world writable**. The old first
stage guard correctly refused `/opt`. No browser phase ran: this identifies the
pre-stage refusal, **not AppArmor startup causality or Gov qualification**.

The matching official runner-image source at immutable commit
`fb099341ddaf44a428fb17495341cb7c2300faf2`,
[`configure-system.sh:12–15`](https://github.com/actions/runner-images/blob/fb099341ddaf44a428fb17495341cb7c2300faf2/images/ubuntu/scripts/build/configure-system.sh#L12-L15),
explicitly makes `/opt` writable. Its
[`install-java-tools.sh:70–71`](https://github.com/actions/runner-images/blob/fb099341ddaf44a428fb17495341cb7c2300faf2/images/ubuntu/scripts/build/install-java-tools.sh#L70-L71)
also makes `/usr/lib/jvm` writable. The temporary capsule therefore uses only a
dedicated `/usr/lib/perito-uf-sandbox-<128-bit-random>` child, outside `jvm`.
**Every job freshly checks all ancestors `/usr/lib`, `/usr`, `/` before exclusive
creation**; recorded facts from a prior job are never authorization. If any fails,
staging refuses with the existing fixed classification. No fallback, caller-picked
path, existing-parent chmod/chown or protection relaxation is permitted. Actual
browser reversals still require the coordinator's separately reviewed CI run.
Offline fixtures below do not establish actual Linux/root behavior or causation.

## Actual protected-parent B abort and temporary classification (#31)

Trusted no-Gov run **43619280568**, code
**7dd6b5f6e4c213263fddc509f0bb5c7665459af3**, independently verified in
`protected-parent-experiment-verified.json` (outside the artifact directory),
successfully staged the protected copy. All three A1 and all three A2 observations
were `early_exit` / `SIGABRT`, `sandbox_refusal` + `crash`; all three B observations
were `early_exit` / `SIGABRT`, **only `crash`**. No phase reached a port or readiness.
Runtime receipts and supporting host facts matched before/after; all browser,
profile, runtime and process cleanup flags were true. Status was
`no_reversible_effect`, qualification false. **B's cause remains UNKNOWN.** The
missing-verified-file remark in the primary research was a directory-location
mistake, not absent independent verification.

The next discriminator ranks (not concludes): helper configuration; later
namespace/credentials/seccomp failure; other crashpad/profile/resource startup
failure. Only temporary `stderr_classes` instrumentation changes. No remedy,
helper mode/removal, copy/policy/path change, launch argument change or production
change is authorized. A known public helper literal is not evidence of B's actual
cause until a separately authorized actual CI observation matches it.

All mappings below use immutable Chromium **157.0.8103.78**, commit
**4b3d0dabb8250b6f152d2d85d79e7706e309d087**. A case-sensitive `FATAL:` source
header must contain an exact allowlisted basename followed by a numeric line
(`:123]` or `(123)]`); optional relative directory components are ignored privately.
No matched basename, line, message, path, PID, URL or secret is emitted. Each
allowlisted site emits its fixed category even for an unlisted CHECK. Site labels
identify the reporting site, **not the ultimate cause**:

| Public source (pinned) | Fixed site category | Public fatal fragment (fixture coverage; site category does not require this fragment) |
|---|---|---|
| [`setuid_sandbox_host.cc:134–175`](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/sandbox/linux/suid/client/setuid_sandbox_host.cc#134) | `suid_helper_fatal` | helper literals below |
| [`zygote_host_impl_linux.cc:129–145,196–208`](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/content/browser/zygote_host/zygote_host_impl_linux.cc#129) | `zygote_host_fatal` | `No usable sandbox!` |
| [`sandbox_linux.cc:227–228`](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/sandbox/policy/linux/sandbox_linux.cc#227) | `namespace_fatal` | `EngageNamespaceSandboxInternal(from_zygote)` |
| [`credentials.cc:320–340`](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/sandbox/linux/services/credentials.cc#320) | `credentials_fatal` | `SetGidAndUidMaps(gid, uid)` |
| [`sandbox_bpf.cc:245–277`](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/sandbox/linux/seccomp-bpf/sandbox_bpf.cc#245) | `seccomp_fatal` | `Kernel refuses to enable no-new-privs`; `Kernel refuses to turn on BPF filters` |
| [`crashpad_linux.cc:266–268`](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/components/crash/core/app/crashpad_linux.cc#266) | `crashpad_fatal` | `client.StartHandler(` |
| [`process_singleton_posix.cc:315,1052–1054`](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/chrome/browser/process_singleton_posix.cc#315) | `profile_fatal` | `Socket path too long:`; `Temp directory mode is not 700:` |
| [`resource_bundle.cc:333–334`](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/ui/base/resource/resource_bundle.cc#333) | `resource_fatal` | `failed to load pak file` |

Three additional labels require the **same FATAL line's** exact basename and
case-sensitive literal fragment:

- `suid_bad_configuration`: `setuid_sandbox_host.cc` +
  `The SUID sandbox helper binary was found, but is not configured correctly.`
- `suid_missing`: `setuid_sandbox_host.cc` +
  `The SUID sandbox helper binary is missing:`
- `no_usable_sandbox`: `zygote_host_impl_linux.cc` + `No usable sandbox!`.

The eleven new labels above extend only the existing fixed list field; schema
version/report shape remain unchanged. Existing four pattern classes keep their
semantics and order, followed by site categories in table order, then the three
literal labels in the order above. Repeated matches deduplicate. Unknown sites
and messages remain generic `crash`/`other` (or existing legacy matches); no raw
fallback exists. Only the existing private 64 KiB stderr prefix is examined;
anything beyond it cannot produce a class. Nothing raw is persisted or uploaded.
The receiver accepts exactly the six legacy plus eleven new strings, unique,
nonempty, at most seventeen labels, retaining its 16 KiB whole-report bound.

`python3 -m unittest tests.test_linux_diagnosis -v` exercises real public
`observeStartup` through Node and an external executable printing controlled
fragments, plus the public Python `observations` receiver with an external helper.
It covers exact paired literals, allowlisted-site unknown CHECK fallback,
unknown/secret-bearing and unpaired text, order/deduplication, stderr bounds,
strict receiver vocabulary, unchanged readiness, seven arguments and cleanup.
These are **instrumentation contracts, not Chrome/Linux/root/Gov cause proof**;
no private classifier is patched. Existing four-signal/protected-parent/typed
receipt/recovery/positive-readiness guards remain required.

Coordinator sequence: fresh local integration and review of code, update only the
external verifier's identical fixed vocabulary, then **one actual no-Gov A/B/A
classifying job before any remedy**. No branch dispatch or Gov qualification is
part of this change.

## Actual profile fatal and fixed discriminator (#32)

Trusted no-Gov run **43621480712**, code
**6ba766c29a8a6ff479d2cc375e99e4e0b6dc6bc6**, independently verified from the
artifact and API receipt, records all three A1/A2 observations as
`SIGABRT`, `sandbox_refusal`, `zygote_host_fatal`, `no_usable_sandbox`; all
three B observations are `SIGABRT`, `crash`, `profile_fatal`. No observation
reached a port or readiness. The protected runtime tree remained
`c5c9b1ad6abb3093160dbf0ef030191a071fc0596f92202b4d908e10c4abf260`,
receipts/host facts matched, and all cleanup flags were true. Status remains
`no_reversible_effect`, qualification false. **The actual profile fatal cause
is UNKNOWN until the next separately authorized real no-Gov CI observation.**

Ranked hypotheses, not conclusions: (1) singleton Unix socket path length under
the current staged `TMPDIR`; (2) socket-directory permission lookup/mode check;
(3) socket creation, listen or peer-reply failure. Chromium allocates its own
socket directory beneath `TMPDIR`; the fresh profile's `0700` mode does not
establish the socket-directory check. No path shortening or other remedy is
included or authorized here.

Five additive fixed labels follow the existing seventeen-label vocabulary.
Each requires the same case-sensitive `FATAL` record and exact
`process_singleton_posix.cc` basename. Prefer the exact public literal below;
only when **no known literal matches that record**, use its pinned numeric
source line. Both existing `:line]` and `(line)]` headers are supported.
Mappings refer only to immutable Chromium commit
**4b3d0dabb8250b6f152d2d85d79e7706e309d087**:

| Fixed label (append order) | Exact public literal | Pinned fallback lines |
|---|---|---|
| `profile_socket_create` | `socket() failed` | [297](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/chrome/browser/process_singleton_posix.cc#297) |
| `profile_socket_path_length` | `Socket path too long: ` | [314–315](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/chrome/browser/process_singleton_posix.cc#314) |
| `profile_socket_dir_check` | `Temp directory mode is not 700: ` | [1052–1054](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/chrome/browser/process_singleton_posix.cc#1052) |
| `profile_listen` | `listen failed: ` | [1088–1089](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/chrome/browser/process_singleton_posix.cc#1088) |
| `profile_peer_reply` | `The other process returned unknown message: ` | [936–937](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/chrome/browser/process_singleton_posix.cc#936) |

Trailing spaces shown inside the literal code spans are significant. Official
builds can strip CHECK/NOTREACHED streaming; see pinned
[`base/check.h:248–288`](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/base/check.h#248)
and [`base/notreached.h:15–36`](https://chromium.googlesource.com/chromium/src/+/4b3d0dabb8250b6f152d2d85d79e7706e309d087/base/notreached.h#15).
Fallback therefore classifies a reporting site, not a syscall cause or build
configuration. Unknown singleton lines/fragments retain `profile_fatal`; no
`profile_other` or free field exists. Only fixed labels leave private memory:
no filename, source line, message, errno, path, mode, peer reply or raw output.
The 64 KiB private prefix, 16 KiB receiver bound, exact unique nonempty vocabulary
(now 22), existing label order, cleanup, readiness and seven arguments remain
unchanged.

Public external-executable → Node `observeStartup` tests cover all five literals,
both fallback header forms, wrong site/case, cross-line text, unknown secrets,
literal-before-line precedence per record, deduplication/order and out-of-bound
text. The strict Python receiver is exercised with an external helper, including
all 22 labels and rejection of unknown/duplicate/non-string/empty/oversize labels
and extra fields. Genuine pre-implementation failures were missing new classes;
these fixtures establish **instrumentation contracts only**, not the actual
Chromium/Linux/root/Gov cause. All prior ownership, four-signal, exclusive staging,
final-drain, runtime pin and root guards remain untouched.

Coordinator must freshly integrate and review this code and update the independent
verifier's identical fixed vocabulary, then classify **one actual no-Gov CI run
before choosing any fix**. This local change does not dispatch, close #32 or its
parents, authorize Gov access, or establish the original A/B/A readiness proof.

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
`/usr/lib/perito-uf-sandbox-<128-bit-random>/runtime` subtree. It refuses collisions,
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

Success schemas remain unchanged. On an owner failure only, its final protocol
receipt has exactly `ok`, `profile_removed`, `runtime_removed`,
`processes_stopped`, `failure`, `candidate_ancestors`. `ok: true` means this is a
cleanup receipt, **not successful staging**; each cleanup boolean is independently
checked. `failure` has exactly `action` and `reason`. Actions are `stage`, `load`,
`unload`, `cleanup`, `protocol`; the driver requires the requested action or
`protocol`. The exact reason whitelist is:

`ancestor_unprotected`, `source_ownership`, `collision`, `inventory_refused`,
`copy_integrity`, `executable_integrity`, `policy_refused`, `parser_untrusted`,
`not_staged`, `runtime_changed`, `process_visibility`, `browser_running`,
`policy_removal`, `policy_absent`, `invalid_request`, `interrupted`,
`unexpected_error`.

Only explicit typed owner refusals use known literal codes; all other exceptions
become `unexpected_error` without stringification. Signals become `interrupted`.
Inventory and policy refusals deliberately group multiple literal checks; they
are discriminators, not causal diagnoses. No exception text, stderr, path, PID or
profile list is emitted. A failed cleanup is retained as false flags even if the
owner has already exited; receipt retention never converts refusal to success.

`candidate_ancestors` has exactly fixed labels `root`, `opt`, `usr`, `usr_lib`
for `/`, `/opt`, `/usr`, `/usr/lib`. Each has exactly `directory`, `non_symlink`,
`root_owned`, `group_or_world_writable`, each boolean or null on inaccessible
metadata. These remain read-only `lstat` facts, not arbitrary paths, scans, or a
complete protection proof. The fixed staging destination is checked separately on
every job. No ancestor is repaired.

After strict whole-receipt validation the artifact's `experiment` additionally
retains `owner_failure` (the same `failure` object) and `candidate_ancestors`.
Malformed/oversize/duplicate-key/unknown-code/extra-field/wrong-type receipts
retain neither classification nor cleanup claims. Owner responses remain bounded
to 4096 bytes; protocol input is bounded to 128 characters. An independent valid
cleanup receipt remains admissible. Old successful and cleanup-only schemas are
still accepted; existing top-level schema version 1 is unchanged. The external
verifier must explicitly allow these two optional failure-only experiment fields
before collecting the next reviewed run.

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

`python3 -m unittest tests.test_sandbox_stage_diagnosis -v` additionally exercises
the actual owner main/protocol with temporary unprivileged paths and host trust
metadata adaptations. Real staging refusal, exclusive creation, copy and cleanup
logic are not replaced. Injected chmod/unlink syscall failures test generic secret
redaction and actual incomplete removal. External malformed-receipt stand-ins test
the driver's whole-receipt validation; actual four-signal ownership and collision
regressions remain in `tests/test_sandbox_owner_signals.py`.

`python3 -m unittest tests.test_sandbox_protected_parent -v` exercises real owner
main/protocol, path selection, inventory/copy, tiny fixture executable pins, exact
policy text creation and cleanup with filesystem/syscall adapters only. It
reproduces the actual writable `/opt` / protected `/usr/lib` pattern (including a
writable `jvm` sibling); the old owner refuses, the new owner stages and cleans.
Each unsafe executable ancestor still refuses before creation, and competitor
sentinel bytes/modes and shared-parent modes survive. This is unprivileged
contract evidence, not installed Chrome, root, Linux or AppArmor execution proof.

After the reviewed experiment, remove this workflow, the two sandbox scripts,
their two test modules and this temporary note (or retain a separately reviewed
sanitized findings summary). Existing diagnostic infrastructure is not part of
that deletion. Artifact expires after seven days; the coordinator should inspect
all cleanup booleans immediately and stop on unknown/failed cleanup. Do not
retry with global relaxation or broaden this profile when support is absent.
