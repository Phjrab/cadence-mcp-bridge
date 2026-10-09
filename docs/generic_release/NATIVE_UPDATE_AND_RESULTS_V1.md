# Standard VM native update and new-result validation

Current feature validation, 2026-10-09. General release remains BLOCKED.
The target is the professor standard CentOS/Cadence/PDK VM in each user's VMware.
Other hosts, Cadence versions and PDKs remain deferred.

Two distinct newly registered QA circuits completed fresh DC/AC/TRAN through one
unchanged owned-copy/netlist/worker/reader implementation. Each job's effective
parameters, analysis and model inputs were checked before Spectre. Automatic
extraction and subsequent bounded terminal/PSF-integrity result retrieval passed
for all six. This is actual UID500 VM execution, separate from synthetic tests and
actual Codex app qualification. Source/state/library/model content was preserved
at worker boundaries. Existing regular OA lock/recovery evidence stayed intact.

The initial inverter DC succeeded in Spectre but failed extraction because the
standard VM stores top nodes without a leading slash and positive source current
as `:p`. The common closed renderer now tries the registered selector then the
verified compiled alias. Callers still cannot supply raw PSF names, expressions,
scripts or paths. The failed128MiB job remains failed and retained; no refund,
ID reuse for simulation, result replacement or cleanup occurred.

## Operator update and read-only recheck

Prepare an immutable bundle from the installed package and reviewed user settings
using `native-runtime bundle`. Keep the original bundle, settings, grants and
journals. The installed registration schema is `native-runtime schema`; example
private identities and hashes are not approval or reusable developer state.
Stage the new bundle explicitly, then use its exact SHA and the current predecessor:

```text
cadence-mcp-bridge native-runtime stage --bundle NEW_BUNDLE --expected-manifest-sha256 NEW_SHA --operator-authority ACTUAL_AUTHORITY_REFERENCE
cadence-mcp-bridge native-runtime update --bundle NEW_BUNDLE --expected-manifest-sha256 NEW_SHA --previous-manifest-sha256 OLD_SHA --operator-authority ACTUAL_AUTHORITY_REFERENCE
cadence-mcp-bridge native-runtime preflight --bundle NEW_BUNDLE --expected-manifest-sha256 NEW_SHA
```

Update requires a known prior schema3 runtime with the fixed asset inventory,
unchanged content hashes/history/identity and no revocation, plus current package
assets and existing domain/ledger/lock. The same lifetime EDA flock rejects a live
worker. It writes an immutable exact-predecessor receipt and activation history,
fsyncs a private pending pointer, then atomically renames only that pointer.
The receipt records both previous and replacement pointer inode/owner/group/mode/
size/mtime. The pointer's content/inode/mtime changes intentionally; unchanged
legacy controls are independently checked. Old binaries/assets, grants, receipts,
results and journals are preserved. Partial application resumes from matching
records; an identical repeat changes zero files. Unknown predecessor, content,
identity, revocation, pending-pointer or metadata drift rejects without guessing.
A conflicting active runtime cannot be replaced through ordinary `activate`.

Retain the earlier private settings for historical lookup. Both runtime settings
can reference the same existing local journals and resource lock. Old admitted
IDs remain lookup-only, even after grant expiry or runtime replacement; they are
never silently submitted through a new runner/grant. A new runner-bound grant
must reflect the remaining actual approved validation scope and existing global
consumption. Updating is not a phase-budget reset or a fresh-domain initialization.

`native-runtime preflight` performs only fixed package/runtime/domain/accounting
reads and a fresh package-bound environment probe. The host validates nonce,
profile/package hashes, executable versions, timestamp and disk floors. It
requires no operator execution authority and must report zero changed files,
reservations and simulations. Import/server start does not stage or update.
The legacy `environment qualify` uses the immutable profile beside its original
probe; a later policy/profile correctly fails that old binding. Keep that evidence
and recheck the exact new native bundle rather than overwriting the old probe.

Current actual immutable update passed:15 staged files,3 new update/history/
pointer changes,repeat0. Normal UID500; old and new local journals/lock reused.
The20job/2.5GiB validation scope was reduced by the spent failed1job/128MiB before
binding the replacement grant. Actual Py26 POSIX synthetic tests separately passed
normal, pending/receipt/history/rename interruption recovery and live-lock rejection.
They did not authorize or execute Cadence. Product read-only native preflight PASS.

## Actual execution receipts

| Design | Analysis | Extraction receipt SHA256 |
| --- | --- | --- |
| qa-inverter | dc | e5acf8d17e8d66f2dc1e4c469f7820814d8f5e6abebbc0fad194e18fc4035f9f |
| qa-inverter | ac | eb6c5cd70bb328055826af515ce81b6d40f767138b3b9010700719115d52707f |
| qa-inverter | tran | 7c7a4612adc0742a35f023d5cd02b4a346c02f54e7d86ed9bf18d863b3f6c53a |
| qa-comparator | dc | 52a5143c03f19f29d5bbf476236770987915fdcbd24735270625aa8704146848 |
| qa-comparator | ac | 80472293c261a6deeb0f67628ae22692d5981b393cb74112b68ce746a80f2f40 |
| qa-comparator | tran | 586c387606fe80916666cc7aa584d25f51e20ffc034f39163b44b07864710f65 |

Active runtime manifest SHA256:
`eb6d638a0b905ddf0ff455d4998d52f3bcadb2977bd01479e9ad8063f06da175`.
Earlier failed runtime and its immutable receipts remain preserved.

This continuation:6 successful new runs/805,306,368 reserved bytes. Including the
preceding failed extraction:7 runs/939,524,096 bytes. Actual cumulative ledger:
89 attempts/10,738,466,816 reserved bytes.16GiB remaining6,441,402,368 bytes.
Spectre500/same-change20 and disk/process/per-job limits remain binding. Physical
available space is distinct from cumulative reservations; no reset or refund.
Latest post-execution retained preflight/9-source actual Py26 grammar and seven
legacy controls plus home-index content/metadata equality passed. Both successful
and failed same-ID requests in new local processes returned their original state
without additional execution/reservation. This is service/VM restart evidence;
actual Codex app registration/submission/restart remains pending.

Remaining whole release gates:generic native1D Sweep/Specification connection,
second job batch, actual Codex workflow, full new-operator runbook, reviewed normal
PR integration, GREL07 operational matrix and exact GREL08 candidate. Current
code/version1.0.0 is not a ready candidate. Public tag/Release/upload still needs
one final approval of exact version/commit/artifacts/hashes. Current directGREL02–08
and conditional merge authority remains active; previous dated restrictions are
history. No PDK/vendor content, original design/state, license or historical result
was changed by this continuation.

PR142 final `a032a0f17326b29d810937e908b5ddaf00f8c25f` passed both hosted checks and final bot review with no major findings. All review threads resolved; no required branch rules or formal human-approval gate were present. Normal expected-head merge produced `239a1949923fdae210d50e1232b6b7b41e60c7de`. Bot review is not formal APPROVED; this is GREL01 code integration, not whole native release acceptance.
