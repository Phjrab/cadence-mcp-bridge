## Python isolation before interpreter startup, 2026-10-11

Independent P1 review4240357276 is addressed by a manifest-bound fixed POSIX
operator launcher. The supported domain transport now invokes /bin/sh with that
fixed bundle entry; it executes only /usr/bin/python -E -s -B and the adjacent
migration.py, with four closed actions and one lowercase64-hex binding. The
caller cannot supply Python flags, an interpreter, script path or shell command.
The launcher is a fifth exact helper asset and participates in strict manifest
and directory inventory. Import, doctor and MCP startup do not invoke migration.

The in-script flag guard remains a direct-invocation diagnostic only: it cannot
prevent usercustomize.py or .pth code already executed during interpreter startup.
A disposable POSIX regression creates both hooks in the interpreter's actual
versioned user site, proves they execute without -s, then checks that the fixed
launcher suppresses both. The hosted fixture substitutes its tested interpreter;
the distributed standard-VM launcher retains literal /usr/bin/python. Trusted
system interpreter/site configuration remains required; no OS or security setting
is changed. Direct python migration.py without isolated flags is unsupported.

Connected Windows domain41 PASS/2 POSIX skips; official Ruff/mypy74 PASS. Exact
hosted POSIX, package/security, fresh independent review and installed standard-VM
validation remain gates. No VM change, simulation or reservation occurred.
Current16GiB/500/same-change20,GREL02-08 and conditional normal merge authority
remain; final exact public posting approval is still separate. Earlier records
and all original ledgers, policy versions, grants and evidence remain preserved.

## Durable next-runtime update binding, 2026-10-11

Independent review4240354827 is corrected: activation and preflight-only update
share the version-directory/runtime-parent durability barrier and a full asset
and target revalidation before launcher, pointer or transition-history writes.
Initial, interrupted and completed exact retries repeat these barriers. Failure
preserves current files and pointer; a substituted next runtime rejects before
publication. Six portable failure/retry cases and one last-barrier replacement
case pass; the POSIX completed-retry fixture checks actual directory fsync order.

Connected Windows bootstrap94 PASS/12 platform skips. Exact hosted Linux,
security/package and refreshed independent review remain gates; no actual VM,
ledger, grant, simulation or reservation changes occur in this correction.
Current directGREL02-08/16GiB/500/same-change20/conditional normal integration
remain authorized. Public tag/Release/assets require the exact final approval.
Earlier source evidence, policy and recovery histories are retained.

## Selected runtime namespace durability, 2026-10-11

Fresh independent finding4240331189 is corrected: activation fsyncs the selected
version and runtime parent before any launcher or active pointer publication,
then validates the exact manifest/assets again. Exact retries repeat both
barriers. Actual POSIX fsync-order coverage is extended; four portable cases
inject repeated version/runtime barrier failure in initial and exact activation,
and another replaces runtime bytes during the last barrier. Pointer/history and
failed evidence remain preserved. Windows87 PASS/12 POSIX skips, Ruff/mypy72 PASS.
Hosted actual POSIX and fresh final review/package remain separate pending gates.
This correction performs no actual VM activation, EDA or accounting mutation.

## Direct migration interpreter isolation, 2026-10-11

Fresh independent finding4240335186 is corrected before filesystem-backed imports:
direct migration startup requires ignore_environment and no_user_site flags,
otherwise a bounded explicit isolated-interpreter error exits without migration.
Memory-loaded authenticated composition retains its existing import boundary.
Two exported-helper child tests omit each flag with absolute PYTHONPATH and
PYTHONUSERBASE shadows; no unreviewed marker executes or request writes occur.
Windows40 PASS/one actual POSIX skip; Ruff/mypy74 PASS. Current exact hosted,
package and final independent review remain gates. No VM/accounting mutation.

## Lexical compatibility ancestors, 2026-10-11

Independent review4240327313 is corrected: external-link observations now retain
all lexical parent identities, modes, owners, timestamps and symlink targets,
then compare them after the final leaf and canonical-parent observations.
Legitimate compatibility directory aliases remain supported. Retargeting an alias
cannot pass merely because the original canonical directory and same leaf inode
still exist. Two owned POSIX fixtures retain both parents and external contents;
the race must reject and the unchanged alias must pass. This remains a final
observation guard, not atomic exclusion of external filesystem operations.

Connected Windows repair/bootstrap120 PASS/206 platform skips and Ruff PASS.
Exact hosted Linux, package/security and refreshed independent review are still
required; no new VM change, simulation or reservation occurred in this fix.
The prior root3ec actual four-directory metadata correction is source-specific
history, not a current helper or release qualification. ContinuousGREL02-08,
16GiB/500/same-change20 and conditional normal integration remain authorized.
Public posting still needs final approval of the exact qualified candidate.
Earlier dated records and all journals, results, receipts and policies remain.

## Fixed stdin inventory and isolated operator invocation, 2026-10-11

The latest independent P1 review4240265879 is addressed in the primary README
and current runbook apply/rollback commands: use /usr/bin/python -E -s -B.
Direct helper startup also rejects missing environment/user-site isolation before
filesystem-backed imports. Two portable tests supply absolute search-hook values;
neither unreviewed marker executes. This cannot repair an already compromised
system startup hook; standard VM/system interpreter trust remains required.

Actual root-installed inventory uncovered host WinError206 before SSH creation:
the package helper now exceeds the Windows command-line limit. Repair-plan uses
a small fixed package bootstrap plus bounded stdin source/request framing. It
hashes exact installed helper bytes before compile/evaluation, keeps the fixed
inventory-only dispatch and16MiB/60s transport limits, and rejects a source over
128KiB or a changed source. No arbitrary-code/path/shell MCP input is introduced;
only the immutable installed resource supplies this internal source. Portable
owned child tests use a >32KiB helper, short command and same-size byte tampering.
All failed harness/line-ending/escaping attempts remain preserved, with no actual
VM/admin/simulation/reservation changes. Updated exact hosted/package/review and
root installed actual inventory are still mandatory; previous receipts are history.
Current16GiB/500/20,GREL02-08 and conditional normal merge continue. Public posting
remains subject to one approval of the identical final qualified candidate.

## External-parent and startup trust correction, 2026-10-11

Fresh8a325b0 review4240230641/4240230643 found two narrower trust gaps. The
external collector now reopens the full named no-follow parent after the final
fixed leaf read, rejecting ancestor detach while a held leaf directory survives.
An external-only nested library now contributes its canonical in-installation
parent chain to the exact repair plan; external target files remain excluded.
A parent that resolves outside the fixed installation rejects instead of expanding
mutation scope. Existing content/owner/read/execute/ACL and rollback protections
remain. Apply/rollback timing and nested-parent recovery have dedicated Linux
regressions; Windows startup shadows are portable separate evidence.

Read-only repair-plan now uses the reference -E -s -B Python flags. The exported
helper removes script/CWD paths using builtin sys before filesystem-backed imports;
retained memory-loaded modules preserve their legitimate stdlib paths. Use
`/usr/bin/python -E -s -B repair.py apply` or `rollback` for explicitly authorized
operator/admin execution. Import, doctor and planning still perform no repair.
Historical -B-only instructions/helper receipts stay historical, not the current
recommended invocation. Current VM16GiB/500/20 and continuousGREL02-08 delegation
persist; package/hosted/fresh review/final actual installed gates are pending.
This correction itself performs no actual VM/admin mutation/reservation/simulation.
Public tag/Release/upload still requires final exact-candidate approval.


## PR151 authenticated setup execution correction, 2026-10-11

Review4239974380 found fresh setup reimported helper paths after complete asset
validation. Standalone setup now executes only the retained authenticated bytes
in fresh fixed module instances, ignores poisoned helper caches and gives its
migration helper the same authenticated accounting/installer/probe instances.
A failed revalidation clears prior authenticated state. Startup removes the script
entry only for direct __main__ launch; memory-loaded helpers preserve legitimate
stdlib entries. Canonical staging aliases are excluded before stdlib imports and
retained compilation. Standalone storage follows the same startup distinction.
Original pre-fix regression logs are retained; exact updated source/package/hosted/
fresh-review gates remain required. This isolated branch changes no actual VM,
admin state, journal, ledger, reservation, simulation or protected circuit content.
Current user16GiB/500/20,GREL02-08 and conditional normal integration delegation
remains; exact public candidate approval is separate. General release stays BLOCKED.
Earlier source receipts and policy records below are preserved as history.

## PR151 current safety-parent refresh, 2026-10-11

Current source normally integrates150206fe0b: initial executable pins, retained
validated helper bytes and reviewed installed-fixture correction, with148 fixed
recipe completion membership. The151 early fresh-policy correction retains all
legacy/scientific protections. Exact3d74b50 isolated installed disposable-ledger
1/2 amplifier/power/SDK consumers PASS; its new Linux parser fixture initially
failed only on host ssh.exe availability and now explicitly stubs that unused
executable lookup. No actual transport or supported platform behavior changed.
Final related/package/hosted/review and pending parent membership corrections are
separate gates. General release stays BLOCKED; current delegated limits/history
remain preserved, and exact public-candidate approval is still required.

## PR151 current standalone correction and parent integration, 2026-10-11

Review4239919242 is fixed by binding the private named resource lock's inode,
ownership/mode/link count/size and at most4096 actual content bytes. Existing
fixed launchers' O_TRUNC of an empty lock can change timestamps without corrupting
it; only lock mtime/ctime are excluded. Same-size content drift and all namespace/
permission/link checks still reject. Artifact metadata protection is unchanged.

Exact8c8389e Ubuntu actual files/flock/standalone463 PASS with zero POSIX skips,
Windows portable consumers119 PASS/17 OS skips, Ruff/mypy78 PASS and exact
isolated installed85-tool43+20-state preservation PASS are source evidence.
Current source additionally merges latest150ca2476, including148 final receipt
namespace and149 independently compiled launcher binding. This integrated source
needs refreshed hosted/security/package/review gates; previous receipts remain
source-specific history. No VM contact/admin/deployment/actual journal/ledger/
reservation/simulation changes occurred. General release and exact RC stay BLOCKED.
Current user16GiB/500/20,GREL02-08 and conditional normal PR integration authority
continues; public tag/Release/assets still require exact-candidate approval.

## Active PR151 standalone deployment correction, 2026-10-11

Fresh review exposed a missing production accounting helper/manifest in the
historical v6 storage deployment. A separate hash-bound v7 deployment and exact
operator-configured pin now provide storage.py/reservations.py plus a canonical
manifest, with no import/startup/doctor provisioning. The shared trusted-root
execute_fixed dispatcher validates activation after held/busy lock decisions;
legacy native_generic=True remains fail-closed pending the qualified consumer.
Windows portable60 PASS/11 skips, Ruff and mypy78 PASS are source evidence;
real standalone Linux/hosted/package/security/review gates are pending.
No VM/deployment/simulation/reservation/actual ledger/admin change occurs.
General release remains BLOCKED. See [exact runtime](generic_release/REFERENCE_STORAGE_RUNTIME_V7.md) for routing, protection
and qualification scope. Current retained16GiB/500/20, GREL02-08 and conditional
normal integration delegation remains; exact publication still needs approval.
Historical source receipts and authority records below remain preserved.

## Active PR151 lock-contended inventory correction, 2026-10-11

The current direct user delegation allows GREL02-08 candidate preparation,
conditional normal integration of reviewed related PRs, and the validation VM's
16 GiB retained reservation ceiling. Existing attempts/corrections/reservations
remain retained. Public tag/Release/assets publication still needs the final
exact-candidate approval. Earlier exclusions and resource observations below
remain historical and do not override that delegation.

PR151 now distinguishes lock-contended read-only storage inventory from a
lock-held conservation audit. Only expected fixed-main inventory flock contention
uses the partial route: authenticate the immutable registered domain/policy and
last committed physical counter, mark coverage incomplete and artifacts active/
protected, and offer no deletion candidates. Cleanup, spending and lock-held
inventory keep the full multi-file audit; unexpected lock failures reject.
This is local synthetic source/package work, with no VM contact, actual journal/
ledger change, reservation, simulation or metadata repair. The native storage
asset changes identity and needs exact new-bundle qualification; prior native
receipts do not qualify this correction. Release and exact candidate remain
BLOCKED. See [consumer correction](generic_release/FRESH_POLICY_CONSUMERS_V1.md)
for source-scoped test/package receipts. Independent final review/CI remain gates.
Historical sections below keep their original source scope.
## Retained migration composition startup boundary, 2026-10-11

A retained migration module can be compiled by the new-install provider with an
empty package name. Only direct __main__ startup now removes the first sys.path
entry; memory-loaded modules retain their legitimate standard-library first
entry. Canonical bundle/current-directory aliases remain excluded in both paths.
A composition regression compiles the exact exported migration bytes under the
fixed module name with legitimate stdlib plus bundle aliases and checks both
preservation and exclusion. Prior083608 package/tests remain source-specific
history; fresh gates apply to this one-condition production change. No native
journal, counter, grant, budget, result or original circuit change occurred.

## Migration transitive import isolation, 2026-10-11

Fresh review P2 identified that direct script launch left the staged helper
bundle on sys.path. The retained-byte loader now removes every bundle path alias
(including an empty/current-directory entry) before any import or compilation.
New same-UID platform/types/subprocess files created after inventory cannot be
resolved as dependencies of reviewed retained helpers. Fixed module names and
complete manifest checks remain mandatory. This does not authenticate arbitrary
caller dependencies or expand the supported standard VM. New regressions and
exact source/installed/CI/review gates are required; prior failures are retained.
No VM, ledger, reservation, replay, results or circuit originals changed.

## GREL03 exact reservation-asset pin integration, 2026-10-11

The new initial-activation pin test correctly rejected the inherited GREL02 pin
against GREL03's already reviewed append-only legacy-seal reservation helper.
The branch-owned compiled reservations pin now binds those exact reviewed bytes
(normalized SHA25661c04f53fb8896c9844581ad3a6b5afec1fb8ac470c8db987e419b53eb66b905).
The helper content and prior anchors/counters are unchanged by this correction;
only the independent source pin follows the branch's reviewed implementation.
Failed exact-head CI/logs are retained. The pin-match regression stays enabled,
and affected bootstrap/combined/installed/hosted gates are rerun for new source.
Source/review identity is not replaced by operator-supplied manifest hashes.
No VM, journal, result, reservation or source-design changes occurred.

## Retained validated migration helpers, 2026-10-11

Fresh review P2 identified a path-import gap after source manifest verification.
The standalone helper now compiles only the exact retained, bounded bytes for
fixed reservations/installer/probe module names after ALL asset hashes pass.
It neither rereads helper paths nor uses cached helper modules. Failed validation
clears retained authority; standalone calls before validation reject. Package
internal synthetic calls keep normal imports and do not attest a native install.
Replacement of each helper after read plus cached-module poisoning:29 PASS/1
Windows POSIX skip; Ruff PASS. Exact installed/hosted/fresh review gates are
pending. Counter, replay, retained job history and the VM have not been changed.


## Initial-pin installed package evidence, 2026-10-11

Exact newly changed bootstrap/fixture source passed curated wheel80/sdist81,
locked clean installation,85 stdio schemas across three templates, two isolated
operator contexts, operation acceptance, bootstrap/update/revocation and43-file
synthetic journal/accounting/replay preservation across reinstall and uninstall.
Wheel SHA256:f80d49af490e3361df846dbe048c062ed9c553e3a35797c31febfb00adb0b0b2.
Sdist SHA256:e2ed47c7fd1dd63c2b33bbab982738155b29ff332375899502295e3d0364253b.
These hashes predate the latest repair-parent integration; new final source
requires its own package receipt. No native/VM qualification is inferred.
Mypy72 PASS. A Windows pip-api locale failure was retained and strict locked
security audit is being rerun with UTF8 enabled; checks are not bypassed.

## Initial activation reviewed executable binding, 2026-10-11

Fresh review P1 identified that initial activation checked a caller-rehashed
manifest without independent executable authentication. Initial operator
activation and preflight updates now bind ALL four executable assets (launcher,
runner, probe and reservation helper) to reviewed package SHA256 pins, normalized
only for checkout line endings. Profile bytes remain per-operator configuration.
Self-rehashed replace/append-code/append-comment attacks for every executable
reject without pointer, launcher, file inode or history mutation. Current bundle
pins match exact package assets:bootstrap82 PASS/12 Windows OS skips; Ruff PASS.
Synthetic update history is now explicitly prepared in disposable test state;
current activation refuses those old modified bytes. Prior installed43-file
preservation passed the fixture correction; exact newly changed shipped-source
package/hosted/fresh review verification is pending. No native job or VM change.

## Installed reviewed-launcher fixture correction, 2026-10-11

The complete installed bootstrap verifier now builds explicitly synthetic prior
launcher history and updates toward the unmodified reviewed package executable,
then repeats and revokes that exact current identity. It asserts installed new
launcher bytes equal the package bundle while legacy activation remains unchanged.
The obsolete arbitrary synthetic NEXT comment is no longer a positive fixture.
This corrects acceptance code for the new pin; all shipped source assets remain
byte-identical to c32d246/ca2476. Exact full installed verification is pending and
must pass before main integration. No native execution or reservation occurs.

## PR149 reviewed executable binding correction, 2026-10-11

Fresh review P1 exposed a self-rehashed arbitrary replacement launcher. Update
now pins new launcher bytes to the independently compiled reviewed package asset
and rejects substitute/append-code/append-comment before state/history mutation.
Windows bootstrap69 PASS/12 OS skips; final parent, related, exact package, hosted
and fresh review remain pending. Earlier82b207 receipts remain source-scoped
history. This correction has0 VM/admin/EDA/ledger side effects and preserves all
existing evidence and delegatedGREL02-08/16GiB normal integration authority.
Public tag/Release/upload still requires exact-candidate user approval.

## PR149 directed update durability correction, 2026-10-11

Fresh review found reverse preflight transitions and missing retry fsync barriers.
The same retained-lock update now rejects completed/partial opposite history,
re-syncs exact retained files/parent directories and already-replaced launcher and
pointer directories before advancing. New Windows bootstrap66 PASS/12 OS skips;
actual POSIX order, relevant/package/hosted/final review remain pending. This is a
local source correction only: VM/admin/EDA/ledger side effects0. Prior receipts,
open PRs, history, grants and cumulative consumption remain preserved. Continue
currentGREL02-08/16GiB conditional integration; public candidate approval remains.
See OPERATOR_RUNNER_COEXISTENCE_V1.md. Earlier dated records remain history.

## Held external-link observation correction, 2026-10-11

Fresh exact c0b4b69 review found separate pathname reads could retain a stale
external-link tuple after a concurrent retarget. The fixed collector now holds
the canonical no-follow parent and observes its proc-fd leaf without opening the
external target for content or metadata changes. It binds the external entry's
identity/metadata and immutable parent identity, and repeats literal target,
resolution, existence, held/named parent and trailing no-follow entry checks.
After internal target hash/ACL reads and serialization bounds, the full inventory
reobserves every external binding. Parent mode is only checked for stability
within each read-only observation so approved code-directory chmod can still
complete; external entry and immutable parent identity remain authenticated.
These are last-observation guards, not atomic exclusion of filesystem tools.

Twenty-four complete owned Linux timing cases inject retarget or parent detach
during literal-target/existence/trailing-resolution reads across apply/rollback
and no-op/processed paths. Eight further cases inject drift during later internal
target hashes. External bytes/metadata and partial/failed evidence are preserved;
no complete event is emitted. Latest connected local checks: 173 PASS / 199
Windows POSIX or symlink skips; Ruff/mypy (72 files) PASS. Updated exact security,
package, hosted CI, fresh review and root final installed-helper actual read-only
inventory remain pending gates. Previous exact c0b4b69 hosted POSIX 314 PASS / 0
skips and installed 32-state preservation remain source-specific historical proof.
No VM contact/admin/simulation/reservation or publication occurred in this fix.
The current 16 GiB / 500 / 20, GREL-02 through GREL-08 and conditional normal merge
authority remains active; public tag/Release/upload requires final candidate approval.

## External compatibility-link membership correction, 2026-10-11

Fresh exact 1e685b1 review found new external .so symlinks were omitted from the
completion plan because their read-only compatibility records lived only in the
response envelope. The standard installation plan now authenticates the ordered
external membership, resolved target, existence and literal symlink target under
its plan digest and apply receipt. Initial apply/rollback and fixed completion
re-enumeration reject missing or changed binding. External resolved targets remain
outside every metadata mutation path. Historical unbound plans/helpers/receipts
are preserved; the updated helper requires a fresh read-only inventory rather
than inventing a historical before-state. The model recipe retains its separate
explicit exact profile/model_include selector.

Two portable pre-lock rejection cases and 36 complete owned Linux cases cover
create, rename and retarget-to-the-same-resolution across IC/Spectre/OA roots,
apply/rollback and no-op/processed states. External target bytes and metadata are
preserved, failed evidence remains, and no complete event is emitted. Latest
connected local checks: 173 PASS / 167 Windows POSIX or symlink skips. Ruff and
mypy (72 files) PASS. Updated security/package/hosted/fresh-review and actual final
installed-helper read-only inventory gates remain pending. Prior exact 1e685b1
hosted POSIX 276 PASS / 0 skips and Windows success remain source-specific history.
No current-VM contact, admin action, simulation or reservation occurred here.
Active 16 GiB / 500 / 20, GREL-02 through GREL-08 and conditional normal PR merge
authority persists. Public tag/Release/upload requires final exact-candidate approval.

## Completion fixed-recipe membership correction, 2026-10-11

Fresh exact169f4a6 review found that completion only reobserved original paths;
new or renamed .so members in a fixed code root could escape that path list. The
final completion check now uses a registered fixed recipe selector to reenumerate
its full scope, requires exact original scope equality, and verifies all content/
identity/mode/ACL records from that fresh inventory. Original path/link validation
is retained. Arbitrary recipe IDs/directories/globs cannot select a new scope.
The standard installation selector is explicit; the separate registered model
recipe in the parent must retain its exact profile/model_include binding.

Three portable selector cases and24 complete owned Linux cases cover create and
rename across IC/Spectre/OA library roots for apply/rollback, no-op and postchange
completion. New shared-writable .so evidence is preserved without mutation, and
no complete event is emitted. The owned recovery fixture now regenerates its
synthetic inventory records honestly after metadata changes. Prior exact169f
hosted Linux249 PASS/0skip and installed32-state preservation remain history.
Updated-source connected171 PASS/131 Windows POSIX/symlink skips; Ruff/mypy72/
security18/strict locked audit/85 schemas and exact wheel/sdist/license/content/
installed32-state preservation PASS. Updated exact hosted/fresh review/current-VM
read-only inventory gates remain pending.0 current-VM/admin/simulation/reservation
activity; prior helpers/artifacts/receipts and cumulative ledgers are preserved.
Current user16GiB/500/20,GREL02-08/conditional normal merge delegation persists;
public tag/Release/upload still needs exact-candidate final approval.

## Final receipt content observation namespace correction, 2026-10-11

Fresh exact0d72108 review found that the final receipt hash ran after its earlier
fixed-directory check. A same-UID rename during that hash left the proc-fd file
entry readable. After the last content hash and file-entry check, read_receipt now
reauthenticates the full fixed parent/directory namespace and repeats held file and
directory metadata stability. No content read or fsync follows that final check.
Four additional complete owned Linux apply/rollback cases detach the directory
during the final hash or final file-entry lookup and retain its original evidence.
The held-target/fixed-lock/resource_guard correction is retained; no new mutation
scope, schemas, authority, platform abstraction or transport allowance is added.

Previous0d72108 exact hosted Linux245 PASS/0skip and isolated installed32-state
preservation PASS remain source-specific history. Updated-source connected local
168 PASS/107 Windows POSIX/symlink skips; Ruff/mypy72/security18/strict locked audit/
85 schemas and exact wheel/sdist/license/content/installed32-state preservation
PASS. Exact updated hosted/fresh independent review and actual read-only332-target
inventory remain pending gates. Current-VM contact/admin actions,
simulations and result reservations remain0 in this correction. The user16GiB/500/
20,GREL02-08 and conditional normal merge delegation persists; exact public tag,
Release/upload requires the separate final approval. Earlier artifacts, failed
review evidence, installed helpers and cumulative ledger are retained unchanged.

## Held target and fixed resource-lock race correction, 2026-10-11

Fresh exact-e169 review found two remaining prechange windows: a new regular-file
hardlink could appear between the earlier nlink check and held snapshot, and a
renamed/replaced run.lock could leave flock protecting a detached inode. Held
snapshots now reject regular nlink !=1 without changing historical plan schema.
After receipt/ancestor/resource-lock checks, the helper repeats the whole target
observation and its immediate link-count check before chmod. The separate setfacl
mutation repeats those guards and authenticates the exact chmod intermediate ACL.

Flock now retains its parent descriptor, verifies the fixed lock/parent named
entries and held metadata after acquisition and receipt admission, before target
mutation, and at completion including no-op/rollback. Fixed names are rechecked
again after all reads. Detached, substituted, relinked or metadata-drifted locks
reject; failed/partial evidence is retained. Six portable and26 complete owned
Linux cases cover both apply/rollback, hardlink timing, real independently acquired
replacement flock, no-op/postchange drift, and drift between chmod and setfacl.
These are last-observation guards, not atomic exclusion of external filesystem
operations. Lock contents, mutation targets, transport limits and authority do not
expand. Administrator/MCP execution separation and authenticated receipts persist.

Updated-source Ruff/mypy72 PASS; connected Windows repair/bootstrap/transport/context
checks168 PASS/103 POSIX/symlink skips. Secret scan/security18, strict locked audit
and85 schemas PASS. Exact wheel/sdist source/license/content and isolated installed
CLI/SDK/context/operation/bootstrap plus reinstall/uninstall32-state preservation
PASS. Hosted Linux/Windows, refreshed independent review and exact current-VM
read-only332-target inventory are separate pending final gates. The initial local audit failed on a CP949 child-process decode and is
rerun under explicit UTF8; this is not a dependency or VM modification. Prior
helper bundles/artifacts and all exact source-specific results remain historical.
No current-VM contact/admin/simulation/reservation has occurred in this correction.
Active16GiB/500/20,GREL02-08 and conditional normal PR merge remain authorized;
public tag/Release/upload still requires exact-candidate approval.

## Whole receipt durability and named-chain correction, 2026-10-11

Fresh review of f4e0084 found a receipt file could be detached or replaced during
fsync after its earlier fixed-name check. After all file/directory fsync and
namespace operations the helper now repeats the held receipt's complete stat,
content hash/stability and fixed filename identity. The held receipt directory's
full metadata must also remain stable. The fixed managed parent is reopened after
its entry read; every named ancestor to/ is checked and reopened for identity,
owner/group/mode drift. Unlisted writable ancestors reject. An exact planned
workspace before/after/known-intermediate state is allowed so authorized workspace
repair and rollback still work; no other shared-write exception is introduced.
Exact8952b7 hosted Linux reached212 PASS with one existing fixture assertion
expecting the later ancestor reason. The new receipt ancestor guard correctly
rejects that recipe-to-lock race earlier, before target validation/mutation. The
fixture now expects that exact earlier reason and retains all protected-state and
no-completion assertions. Production helper/artifact bytes are unchanged; exact
corrected hosted/independent review/current-VM inventory gates remain pending.

First apply still publishes/verifies the full exact receipt before any target
mutation, and every target's immediate prechange and completion reauthenticate it.

Grouped owned Linux fixtures cover31 new file fsync/directory fsync cases: rename,
unlink, identical-byte replacement, restored-mtime content change, receipt-directory
metadata drift, selected/unlisted ancestor drift and detached managed parents, with
apply/rollback and exact planned writable-workspace recovery. Failed evidence is
preserved. This is last-observation validation, not atomic exclusion of external
administrator/user filesystem tools. Previous f4 local179/49skip, hosted Linux182/
no skips and installed32-state package PASS are history. Updated-source local
179 related PASS/80 Windows POSIX skips and Ruff/mypy72 PASS. Final updated-source
package/security/audit/hosted/refreshed review gates are pending.
No VM/admin/simulation/reservation change; prior receipts/helper bundles/ledger and
all existing active16GiB/500/20,GREL02-08,normal merge/publication boundaries persist.

## Fixed receipt namespace read-race correction, 2026-10-11

Fresh review of7fb77b7 found that a directory could be detached during a receipt
read or fsync while its held descriptor still authenticated the old file. The
helper now reopens the fixed managed parent and verifies its exact UID-owned
0700 directory entry after receipt reads and durability operations. Detached or
substituted entries reject before chmod/completion; their evidence is preserved.
Six complete Linux recipe cases race read, file fsync and directory fsync during
both immediate rollback prechange and idempotent apply completion checks.
Previous7fb local179/43skips, hosted Ubuntu176/no skips, all four hosted checks and
installed32-state package preservation PASS remain that source's history.
Updated-source local179 related PASS/49 Windows POSIX skips, Ruff/mypy72 PASS.
Final updated-source security/audit/package/hosted/refreshed review gates are pending.
No VM contact/admin/simulation/reservation, target expansion, authority grant or
protection bypass occurs. Prior exact helper/bundle/ledger records are retained;
updated modeltrust native qualification remains separate. Current16GiB/500/20,
continuous GREL02-08 and conditional normal integration remain authorized;
public tag/Release/upload requires exact-candidate approval.

## Authenticated rollback provenance correction, 2026-10-11

Fresh PR148 review found that a caller could change both the private plan and its
self-computed digest to invent a more permissive pre-apply mode/ACL. The explicit
apply path now requires all first-apply records to match the actual before-state
and durably publishes the exact observed plan before any target mutation. The
fixed managed-root namespace is trust-repair-v1-user-UID or trust-repair-v1-admin-0;
no-follow owner checks,0700 directories and0400 single-link files separate normal
users from administrators. Root never accepts a user-owned receipt. The receipt
records observation, not human approval; the real operator delegation is still
required. Read-only inventory/import/doctor never provision a receipt.

Existing exact receipts permit interruption/retry/no-op/rollback without rewriting
history. Missing receipts reject rollback and externally changed after/intermediate
states; fabricated plans, changed receipts and metadata/content drift reject.
Publication writes/fsyncs a private candidate, verifies its bytes, links exclusively
and fsyncs the directory before mutation. Failed candidates and partial/multi-link
publication evidence are retained. A multi-link interruption requires investigation,
not automatic deletion or promotion. Receipt trust and the fixed directory are
rechecked before each chmod and before completion; external filesystem activity is
not claimed to be atomic. Resume under the same real identity. Historical repair
helpers/plans/receipts remain archived; no automatic provenance import is provided.

Portable provenance cases and complete owned Linux recipe cases cover invented
before states, exact repeat/rollback/no-op, partial apply, forged root receipts,
write/fsync/link/unlink interruptions and detached receipt directories. Final local
179 related tests PASS/43 Windows POSIX skips, Ruff/mypy72/security18/strict locked
audit and85-schema compatibility PASS. Exact package, hosted Linux/Windows and
refreshed independent review checks remain pending.
The helper is shipped as native modeltrust.py, so exact updated native qualification
remains a separate gate; prior eb62/bf6c20 evidence is source-specific and preserved.
No VM contact, administrator change, simulation or reservation occurs in this fix.
Latest root-observed ledger102/12,483,297,280 is historical to this local correction;
active16GiB/500/20,GREL02-08 and conditional normal PR integration remain authorized.
Public tag/Release/upload still requires approval of an exact completed candidate.

## Operator launcher directory durability, 2026-10-11

PR149's further P2 found that initial activation could persist the active pointer
while the launcher entry in its separate bin directory remained uncommitted.
Correction f76c8d5c1000331a772fcd52614bcd9f447ae3d1 now fsyncs that directory
before publishing a pointer and repeats the barrier for exact retries, including
a recreated launcher with a preexisting exact pointer. A directory-sync failure
returns no success, does not publish a new pointer, and preserves exact launcher,
pointer and historical state for recovery under the retained lifetime domain lock.

Exact bootstrap: 58 PASS / 11 Windows platform skips. Five new POSIX cases inspect
actual file/directory descriptors and publication order, inject bin-directory sync
failure for absent, launcher-only, complete and pointer-only states, then verify
exact recovery and inode/history preservation. Ubuntu hosted execution and fresh
review remain pending. Ruff/mypy72, security18/strict locked audit,85 schemas and
installed CLI/SDK/bootstrap/43-state reinstall-uninstall preservation PASS.
Persistent audited wheel80-member SHA256
8dfced4add90877be811b704e369141730e4640c1b27a7f6822356b8c859fc54;
sdist81-member a6d20e6e6c3ccb822e6f216e6de7954cdbd5c2b7ff7f658698dc7bdc3a333854.
Installer SHA256 861581f16ed41ec330d0c038a474da90dbf9f13bac83378341cfd0ca9896ce38.

Parent148's later rollback-receipt-origin correction is still awaiting normal
integration; these receipts apply to f76c8d5 with the prior9c311 repair parent.
Foundation branch metadata1.0.0 is separate from root152's chosen2.0 development
metadata and is not a frozen RC. Current direct user delegation permits reviewed
GREL02-08 integration within the retained16GiB/500-attempt/20-correction limits;
old contrary statements below remain historical. This correction has zero VM
contacts, actual activation/revocation, admin changes, simulations or reservations.
Changed native assets require renewed exact qualification. Generic release BLOCKED;
public tag/Release/artifact upload remains unapproved.

## Atomic operator state and exact parent integration, 2026-10-11

Normal merge f7559262cd4aff87b088db143f2632114848e5bf incorporates the latest
repair parent 9c311b0a6c14d06bb5abc92bb59ec1039497e339 and atomic operator-state
correction 14e7e0c. Initial active-pointer and revocation publication now writes a
private mode-600 exclusive candidate under the existing lifetime resource lock,
handles short writes, fsyncs the file and directory, checks complete bytes and
absence of a conflicting final marker, then renames and fsyncs the directory.
Failed candidates remain evidence; an exact retry uses a new candidate, and
repeating a completed marker preserves its inode. General exclusive export and
historical launcher-collision behavior remain unchanged. This is the existing
trusted-owner/lock contract, not protection against hostile same-UID editing.

Related tests: 273 PASS / 28 Windows platform skips in 40.74s; Ruff/mypy 72 files,
security 18, strict locked audit and 85-schema compatibility PASS. New activation
and deactivation tests interrupt writes, file fsync and publication, preserve
partial candidates and unrelated final collisions, and recover exact requests.
POSIX directory barriers run in the Ubuntu operator suite; Windows synthetic
evidence does not attest native POSIX behavior. Exact installed CLI/SDK/bootstrap,
reinstall and uninstall preserve 43 disposable synthetic state files.

Audited wheel (80 members) SHA256:
80de927e51d66c64978ef85f6dcfc5fde04cf683ac5327c5ee1c25ba27e5c85f;
sdist (81 members):
63afe42904a73c686a02eb6d1a06113301749042546cc7242007c6ff353d4ce1.
Shipped installer SHA256:
1627bf45fd93c738830ea64f33a1fe3eea2a50032151e7b7a33f42f14f1e8425 (20,979 bytes);
repair/modeltrust helper:
8f2723ee210ba244be298b35e0cb1db921d21085beb63f68836502aa01303bb1.
These are test artifacts, not an accepted release candidate. Exact final hosted
checks and fresh review remain pending. A native bundle with these changed assets
requires renewed exact qualification; bf6c20 and all prior evidence are retained.

General private transport remains 256 KiB; repair inventory alone uses 16 MiB.
This integration performs 0 VM contacts, administrator changes, simulations or
reservations. Existing real consumption, journals, replay and protected originals
remain preserved. Direct 16 GiB / 500 / 20, continuous GREL02-08 and conditional
normal related feature-PR merge authority persist. Exact public tag/Release/upload
still requires final user approval. Earlier receipts remain source-scoped history.

## Whole-target completion integrity correction, 2026-10-11

Fresh PR148 review found no-op targets and already processed targets could drift
after their earlier observation without preventing a complete receipt. The helper
now recomputes the whole exact recipe immediately before completion. Every target's
content/hash, identity, owner/group, size/mtime, requested mode and normalized ACL
must match; original links are revalidated by the recipe. Partial receipts remain
preserved on rejection. Omitted-ancestor rechecks, mutation scope, caps and explicit
authority remain unchanged; outside administrator activity is not made atomic.
Twelve portable completion cases cover apply/rollback, protected and metadata drift
and record count. Eight owned Linux cases cover no-op/previously processed mode,
ACL, content and same-resolution link drift, requiring rejection without complete.
Local169 relevant tests PASS/26 Windows POSIX skips; Ruff/mypy72, security18/
strict locked audit and85-schema compatibility PASS. Exact wheel/sdist license/
content audit and installed CLI/SDK/bootstrap/reinstall/uninstall32-state
preservation PASS. Retained wheel SHA256 is68f6e31be5e403237e9ec77f1408fe6f45646a850d487786c8f53b6aac9b4083;
helper SHA256 is8f2723ee210ba244be298b35e0cb1db921d21085beb63f68836502aa01303bb1.
Final hosted Linux/Windows and refreshed independent review remain pending. Prior
installed eb62 current-VM UID500 read-only inventory PASS (332 targets,0 changes,
173064-byte response, historical exact targets/content/metadata preserved) remains
that source's evidence. Updated helper/modeltrust needs exact installed/current-VM
qualification; preserve bf6c20 and all prior bundles/results.
Root's latest actual ledger observation is102 attempts/12,483,297,280 reserved
bytes. Earlier94 and82 snapshots below are history. This fix performs0 VM contacts,
admin changes, simulations or reservations. Active16GiB/500/20, continuous GREL02-08,
conditional normal merge and final exact-publication authorization gate persist.

## Repair application ancestor race correction, 2026-10-11

Fresh PR148 review identified omitted-ancestor permission drift between recipe
inventory and application under the resource lock. The fixed helper now reopens
and checks the no-follow ancestor chain immediately before each held-target chmod
and before completion, including idempotent/no-op apply and rollback. Unsafe
outside-scope paths reject without adding mutation targets; drift after an actual
change retains partial receipts and cannot produce a complete event. This does not
make concurrent administrator filesystem activity atomic; the operator must
stabilize the external ancestor and resume the preserved exact plan.
Portable apply/rollback regressions cover prechange, postchange and no-op drift.
Complete owned Linux fixtures exercise recipe-to-lock and held-target races plus
postchange/no-op rejection without modifying omitted ancestors through the helper.
Local157 relevant checks PASS/18 Windows POSIX skips; Ruff/mypy72, security18/
strict locked audit and85-schema compatibility PASS. Exact wheel/sdist distribution,
installed CLI/SDK/bootstrap and reinstall/uninstall32-state preservation PASS.
Retained wheel SHA256 is54807b0e4d181ed9d6b9e62ac1340b4aa9f014bf332e0b9bdefb1fa5c6de9495;
helper SHA256 is9a6da270a65bdffaa2b50369ea862ec35b6c61f427fbea05e56e24ec036626cf.
Final hosted Linux/Windows, refreshed review and actual standard-VM read-only
inventory remain pending. modeltrust helper bytes change again; preserve
bf6c20 and all earlier evidence until exact updated native qualification. This fix
adds0 VM contacts/admin changes/simulations/reservations. Current16GiB/500/20,
continuous GREL02-08, conditional normal merge and exact-publication gate persist.

## PR148/149 integrated-source receipt, 2026-10-11

Normal merge c649853d5b1a36f41818badda3150b8fcd650650 incorporates parent
3360d0e5c0f1af28140475516f1861b54db9fb68 and operator revocation durability
correction a2fc3d880aafdf845b35ff30ae8e3cc27b3d982e. Both documentation histories
are retained. Integrated related235 checks PASS/16 Windows platform skips;
Ruff/mypy72, security18/locked audit/85-schema compatibility and installed43-state
package/reinstall/uninstall preservation PASS. Audited wheel80 members SHA256
80a40eebc288e8368dec463f6f3baad641a610d7d3e86e5cfd531ac49272fa86;
sdist81 members af5a65792553ec2a7afb5cb5906f06d0abfa625292a699848346b90618585f0c.
These are test artifact identities, not an accepted release candidate. Exact hosted
checks and independent review remain pending. A subsequent parent review identified
another omitted-ancestor race whose correction still needs normal integration and
renewed qualification. Updated installer/modeltrust bytes have no current-VM
qualification in this receipt; prior native bundle/evidence remains preserved.
This integration has0 VM contacts/admin changes/simulations/reservations and does
not grant publication authority. Earlier source-scoped receipts remain history.

## Operator revocation directory durability, 2026-10-11

PR149's final P2 found that an fsynced revocation file could lose its directory
entry after power loss. Operator deactivation now fsyncs the managed directory
before reporting success, including an exact existing marker left by interruption.
A failed directory sync propagates; retry retains the original marker inode,
active pointer, historical versions and resource state, then repeats the barrier.
The existing resource lock, identity/permissions checks and drift rejection remain.

Local related226 tests PASS/15 Windows platform skips, Ruff/mypy72, security18,
locked dependency audit and85-schema compatibility PASS. The three new POSIX
regressions inspect real fsync descriptors/order and inject new/existing-marker
sync failure before success, then verify recovery/repeat without replacement.
They run in the existing Ubuntu operator CI; exact hosted checks and independent
review of this final source remain pending. Matching curated artifacts and isolated
installed protocol/bootstrap/coexistence/reinstall/uninstall preserve43 synthetic
state files. Synthetic/Windows evidence does not attest native POSIX durability.

The shipped installer bytes change; any later native bundle containing this helper
requires its own exact hash/qualification. Worker, launcher, profile and shared
reservation assets are unchanged. This correction performs0 VM contacts, metadata
changes, simulations or reservations; existing real journals/ledger/replay remain.
Direct16GiB/500/20, continuous GREL02-08 and conditional normal feature-PR merge
authority persist. Release is still blocked; exact public tag/Release/upload needs
final user approval. Prior dated boundaries and observations below are history.

## Whole repair protocol and omitted ancestor checks, 2026-10-11

Fresh PR148 review found valid large-ACL plans exceeding the whole16MiB protocol
and unsafe ancestors above the fixed vendor base being omitted. The standalone
helper now bounds aggregate records, the complete inventory response and canonical
apply/rollback envelope (including newline and maximum allowed authority text)
before action. Oversized plans fail closed rather than expanding the private cap.
Unlisted ancestors above vendor/workspace roots are checked read-only through
no-follow descriptors to/. Unsafe ancestors reject; exact repair targets and their
content/owner protection do not expand to user or system ancestor trees.
Local167 relevant checks PASS/10 Windows POSIX skips; Ruff/mypy72 and isolated
package/CLI/bootstrap/reinstall/uninstall32-state preservation PASS. Complete Linux
synthetic recipe coverage checks the omitted writable ancestor without changing it,
then proves healthy ancestors stay outside the target set. Exact current-VM
read-only inventory, hosted checks and final independent review remain pending.
The helper is also shipped as native modeltrust.py, so its bytes change. Preserve
bf6c20 and prior runtime evidence; qualify the exact updated native bundle before
candidate acceptance. This fix performs0 VM contacts/admin changes/simulations/
reservations. Earlier observations remain history; active16GiB/500/20, continuous
GREL02-08 and conditional normal merge authority and exact-publication gate persist.

## Real repair transport boundary correction, 2026-10-11

Final PR148 review found that bootstrap's16MiB request still met the general
transport's256KiB ceiling before SSH. Repair planning now uses a dedicated internal
16MiB/60-second inventory transport. General fixed calls retain their256KiB ceiling
and32KiB default, strict host keys and bounded pipes. No public MCP input or tool
is added; planning remains read-only and exclusive, without approval creation.
The profile-bound small/large inventory tests now run the real transport against
owned synthetic child processes. Exact16MiB output succeeds; oversized input,
stdout and stderr reject. Related71 tests PASS/9 Windows POSIX skips; Ruff/mypy72,
security18/locked dependency audit and85-schema compatibility PASS. Exact isolated
package build/installed CLI/bootstrap/reinstall/uninstall preserves32 synthetic
state files. Exact final hosted checks and refreshed independent review are pending.
This host-only fix changes no native worker/helper bytes and performs0 VM contacts,
admin changes, simulations or reservations. Earlier ledger snapshots remain
historical; admission must read the latest actual ledger. Direct16GiB/GREL02-08/
conditional normal merge authority and exact-publication approval gate remain.

## Repair inventory transport-bound correction, 2026-10-09

Latest review found inventory responses larger than256KiB blocked despite the
fixed helper's16MiB request/plan protocol. The private bounded transport now uses
the same16MiB ceiling; timeout/host-key checks and exclusive output remain. Large
synthetic inventories over256KiB preserve exact plan/profile binding, while the
transport retains a finite cap. This host-only bootstrap change does not modify
native worker/model-trust assets or authorize remote metadata mutation.
Related61 repair/bootstrap checks/9 Windows skips, Ruff/mypy72 and exact installed
32-state preservation pass. Final exact hosted/final review remains pending.
Current direct authority, real94/11,409,555,456 ledger and prior evidence remain;
0 new simulations/reservations/admin changes in this PR qualification.

## Final stable-parent integration, 2026-10-09

This feature normally incorporates latest trust-repair parent49b9906 and keeps
operator/legacy runner coexistence and existing root/ledger/journals unchanged.
Related bootstrap/runtime/environment/repair213 checks pass/12 Windows POSIX
skips; Ruff/mypy72 and exact installed43-state preservation pass. Current parent
49b9906 and this final head still require exact hosted/final review and ordered
normal merge; no code integration is actual native candidate or release PASS.
Existing direct16GiB/GREL02-08/conditional normal merge/minimum VM repair authority
continues. Last observed94/11,409,555,456 ledger remains preserved;0 new EDA/
reservation/admin changes. Exact public-candidate tag/Release/upload gate persists.
Earlier dated checkpoints remain historical evidence.

## Descriptor snapshot stability correction, 2026-10-09

The subsequent review identified content/metadata change during ACL collection.
Held snapshots now check trailing stat including ctime, repeat the content hash
and check final descriptor stability. Same-length content replacement followed
by restored original mtime during ACL observation rejects before chmod. Actual
UID500/Python2.6 synthetic interruption/repeat and4 descriptor races pass; real
ledger94/11,409,555,456 unchanged. Local59 checks/9 Windows POSIX skips plus
Ruff/mypy72 pass. Exact installed32-state package preservation passes; final hosted review/CI
pending for this source; no vendor/admin/simulation change. Existing authority/publication
gate and all prior evidence remain preserved.

## Held-descriptor integrity correction, 2026-10-09

A subsequent independent review found path snapshot/final-open ACL race exposure.
The helper now reobserves all protected content/identity/mtime/mode and normalized
ACL on the held descriptor immediately before chmod. Unreviewed named/default
ACL or content drift rejects before any metadata mutation. Three Linux race
regressions and actual UID500/Python2.6 synthetic races pass; apply/rollback
interruption/repeat still restores original fixture metadata/content. Actual
ledger94/11,409,555,456 remains unchanged; no vendor/admin/simulation changes.
Local59 checks/8 Windows POSIX skips, Ruff/mypy72 and exact installed32-state
preservation pass. Final exact-head hosted review/CI remain pending. Current
direct16GiB/GREL02-08/conditional merge authority and exact-publication gate persist.

## Exact rollback interruption recovery, 2026-10-09

The latest review of3b678d2 found an interrupted rollback metadata state missing
from the fixed helper. Chmod now computes access owner/mask-or-group/other bits
from the exact requested mode while preserving named/default entries. Only
rollback accepts the exact original-mode/restricted-ACL intermediate state;
unexpected metadata and all protected content/identity drift still reject.
The Linux fixture interrupts both apply and rollback, resumes and repeats each,
then checks original contents and metadata. Local59 repair/bootstrap checks pass/
5 Windows skips; Ruff/mypy72 pass. Actual UID500/Python2.6 synthetic apply/rollback
interruption/repeat restores exact contents/ACL/mode/identity, with the real94/
11,409,555,456-byte ledger unchanged. This is not a new vendor metadata repair.
Exact installed32-state package preservation passes; final hosted review/CI
remain pending for this source.

Latest main98710153a167e103c2955b1c5c82612eb2864038 includes normal PR142-147
merges. Existing16GiB/GREL02-08/conditional normal merge/minimum VM repair authority
continues; public exact-candidate approval remains required. Prior receipts and
policies are historical and retained. No new simulation/reservation/admin change.

## Component-aware installation boundary correction, 2026-10-09

The fixed repair recipe now derives the installation base from path components,
so sibling vendor roots whose names share a prefix keep both IC/OCEAN and MMSIM/
Spectre targets in scope. The exact profile/executable hashes, role-specific seed
list, no-follow descriptors, ACL/content/owner checks and bounded mutation remain.
Local58 repair/bootstrap tests pass with5 Windows OS skips; Ruff/mypy72 and exact
installed32-state conservation pass. Current authoritative16GiB/GREL02-08 and
conditional normal merge overlay remains;82-attempt repair evidence is historical.
Final exact-head hosted checks and independent review are pending. No new remote
repair, simulation or reservation; actual generic release acceptance is separate.

## Retained ID serialized-capacity correction, 2026-10-09

Migration inventories retain up to the bounded2048-entry scan capacity, then
reject if the complete canonical anchor exceeds the existing8192-byte accounting
record bound or the complete response exceeds262144 bytes. Legacy classification
validation uses the same serialized bound; no IDs are dropped to fit.129/160-ID
fixtures plan/apply/repeat with unchanged old bytes;240-ID over-capacity planning
rejects without anchor writes. Local94 tests/5 Windows POSIX skips, Ruff/mypy74
pass. Final installed package, latest parent integration, exact hosted checks and
independent review are pending. No current-VM migration or resource reset occurs.

## Cross-version repair metadata correction, 2026-10-09

A final PR148 review found fractional mtime serialization differs between
Python2.6 and Python3. New fixed inventories encode mtimes as round-trip strings;
content, inode, owner, group, mode and ACL checks remain separate and enforced.
Historical numeric private records and their exact helper/digests remain preserved;
comparison supports equivalent historical numeric mtimes without accepting drift.
Local136 tests/5 POSIX skips, Ruff/mypy72 and exact installed32-state preservation
pass. Actual UID500/Python2.6 fractional synthetic inventory hashes identically on
the host; real94-attempt/11,409,555,456-byte ledger is unchanged. Final exact-head
hosted checks and independent review are pending. No administrator change or new
simulation/reservation was performed. This is not general release acceptance.

## Serialized AC grid correction, 2026-10-09

Final review exposed valid ultra-narrow grids whose %.16g displacement exceeds
the quarter-gap cap. Projection now compares the expected grid in the extractor's
serialized representation and normalizes requested frequencies to that same format
before unique sample selection. The quarter-gap bound remains disjoint; missing
boundaries and collapsed serialized grids still reject before execution. Both
reviewer counterexamples pass compile/projection regression, with both endpoints
selected. Local352 tests/4 POSIX skips, Ruff/mypy71 and exact isolated wheel/sdist/
installed32-state preservation pass. Final exact-head hosted checks and independent review are pending.
No new native deployment, simulation or reservation; publication remains blocked.
Earlier receipts below retain their historical source scope.

## Narrow AC grid review correction, 2026-10-09

Latest PR147 review found an additional P2: relative1e-12 endpoint/full-grid
tolerance could consume the entire spacing of a valid ultra-narrow high-frequency
sweep, accepting a missing start/end sample. Both checks now cap tolerance at one
quarter of the nearest declared grid gap. Regressions request only the unchanged
endpoint and demonstrate the other missing boundary still rejects. Exact close
neighbors and normal16-digit serialized endpoints remain supported.
Local350 related tests PASS/4 Windows POSIX skips, Ruff/mypy71 PASS; exact isolated
wheel/sdist/CLI/SDK/bootstrap/reinstall/uninstall32-state preservation PASS.
Current PR152 host reader also reprojects both retained actual AC results identically;
that is prior-bundle result evidence, not fresh candidate simulation/app acceptance.
All ten earlier findings remain implemented with distinct regressions. Final exact
hosted CI and fresh independent review are still required before conditional merge.

PR145 and146 normally merged asbdcba004 and5a85beb; current main5a85beb. Direct
GREL02-08/retained16GiB/conditional related merge authority continues; consumption,
replay and history are retained. No new VM jobs/admin changes/reservations. This
foundation remains native-unqualified, release BLOCKED and exact publication approval
separate. Earlier dated restrictions below are preserved historical checkpoints.

## Closed static-input grammar checkpoint, 2026-10-09

The final control boundary accepts only ordinary port-list component instances,
plain/parenthesized lowercase subckt and inline-subckt declarations, matched ends,
global/save node lists and named options/info assignments as static statements.
Unknown named commands reject before static-hash comparison. Reserved analysis
masters also reject in port-list form, including PSP/QPSP/HBSP/QPSTB and keyword
case variants. Protection pragmas reject before comments are discarded. Unsupported
model/initial-condition dialects fail closed rather than being promoted by a hash.
The standard VM's existing PDK includes and exact source/model fingerprints remain
separately bound; no PDK/vendor/source contents were changed.

Local237 related input/operations/lifecycle tests PASS; Ruff and mypy69 PASS.
Exact isolated package/CLI/SDK/bootstrap/reinstall/uninstall PASS with19 operator
state files preserved. The corresponding common native parser in draftPR152 has
actual UID500/Python2.6 synthetic coverage and preserves all six real registrations;
this parent feature does not itself establish live execution authority. Hosted
final-head CI and independent review remain required. Release BLOCKED, no RC or
publication. Latest direct02–08/16GiB/conditional merge authority remains active;
older historical exclusions below do not override it.

## Extracted-control case and hidden-analysis correction, 2026-10-09

The third independent PR145 P1 exposed PARAMETERS and uppercase DC/AC/TRAN being
misclassified as static despite overrides/extra analyses. The comparator now rejects
case variants of extracted controls plus unsupported noise/periodic/sweep/alter
analysis controls before static fingerprint comparison. Regression explicitly binds
the harmful extra statement into the same approved static hash; equality cannot
prove the control is harmless. Supported lowercase DC/AC/TRAN remains unchanged.
Local238 related tests/Ruff/mypy69 and exact installed CLI/SDK/bootstrap/reinstall/
uninstall19-state preservation PASS. Final hosted CI and independent review remain
required before conditionally authorized normal merge. Earlier667e007 CI successes
remain historical because its review found this blocker. No new execution or quota
reservation occurs; current GREL02-08/retained16GiB authority is unchanged and exact
public release approval remains separate. Equivalent common native correction is
validated on ordinary-user actual Python2.6 in draftPR152; no runtime update yet.

## Reviewed parent integration checkpoint, 2026-10-09

Current direct user authority permits continuous GREL02-08 and conditional normal
related PR integration. Managed-VM16GiB/Spectre500/corrections20 retains all actual
consumption and history; it is not a fresh-user default. Publication of any exact
candidate still needs final public approval. Earlier exclusions below are history.

PR146 normally integrated current main/lifecycle/grant-byte binding and PR145's
closed Spectre scope correction. Both sides of documentation conflicts are preserved.
Existing sealed shared-reservation implementation is unchanged. Four earlier review
issues are covered by post-reservation historical marker floors, exact legacy
count/byte conservation and independent per-operation identity seals; missing jobs/
seals fail closed even for128MiB or cancelling variable deltas. No new ledger,
reservation refund, operator approval or native worker activation is introduced.
Local304 related tests PASS/five POSIX/symlink skips, Ruff/mypy70 PASS. An initial
console-script collection missed the repository script package; rerun under the
repository import path passed without source changes. Exact package/public hosted
checks and refreshed automated review follow. This is still an unqualified provider
foundation; actual terminal/provider/policy confirmation and16GiB managed VM
execution are separately tracked in draftPR152. No new VM execution/reservation.
Latest checked main eda060e; PR145667e007 final review/CI remains pending. Ordered
merge must wait for that parent. Clean actual operator/app and exactRC remain BLOCKED.

## Closed Spectre scope dialect correction, 2026-10-09

The second independent PR145 P1 identified library/section and keyword-case scopes
that could remain opaque while controls were extracted globally. Supported parsing
now permits only lowercase named subckt/inline-subckt scopes, and rejects other
library/section/protected/conditional/braced/language-switch constructs and scope
keyword case variants before comparing fingerprints. DC/AC/TRAN regression covers
all those cases. Existing six actual native baselines remain supported by the same
common parser correction in PR152. No scope is inferred from an opaque static hash.
Earlier limited scope correction receipts below are preserved as superseded evidence.
Current GREL02-08/conditional merge/retained16GiB authority is unchanged; no new
simulation or reservation or publication occurs. Exact corrected gates follow.

## Current GREL04 parameter-scope review correction, 2026-10-09

Current direct user authority allows continuous GREL02-08, normal conditional
related PR merges and the current managed VM retained16GiB ceiling. Spectre500,
corrections20, disk floors, original/vendor contents, results and journals remain
binding. Exact-candidate tag/Release/upload still requires final public approval.
Earlier overlays below are historical and do not cancel that direct authority.

Latest PR145 e90b786 hosted checks passed, but independent review found a P1:
extracting nested parameters as global values could accept moved top-level input.
The corrected local comparator tracks named subckt/inline-subckt scopes, preserves
static structure and rejects nested parameter/include/analysis controls or unbalanced
scope. Top-level parameters with ordinary static subcircuits remain supported.
Regression covers DC/AC/TRAN and inline subcircuits. Related190 PASS, Ruff/mypy69
PASS. Exact corrected installation/hosted checks/review remain pending. This compiler
alone is native-unqualified and never authorizes or dispatches a simulation.

PR142-144 normally merged; latest checked main eda060e1a1a984134e25490839c60ec2c2a93eb4.
Existing changes and evidence are retained. This correction adds0 simulations and0
reservations. Actual standard-VM execution is tracked separately in PR152; actual
Codex new-job acceptance and exact GREL08 candidate remain incomplete. Release BLOCKED.

## Active fresh-policy consumer correction, 2026-10-08

Continue the existing branch and unmerged PR151; latest main remains553276d.
Fresh counter/storage observations now carry and audit the registered schema2
policy and account index rather than inheriting the developer campaign/10GiB.
Historical PowerCounter/study output and85 public MCP schemas remain exact.
The generic provider/public storage route remains incomplete; do not treat this
consumer correction as native dispatch or completed GREL03. Source/package/CI
receipts are tracked in [fresh-policy consumer report](generic_release/FRESH_POLICY_CONSUMERS_V1.md).

Actual ordinary-user retained preflight PASS, existing seven control metadata
unchanged; installed accounting predates current source and cannot attest current
package dispatch. Actual OCEAN17 ADE APIs callable is existence only, not netlisting.
Counter82 /9,798,942,720, remaining895MiB; this continuation simulations/reservations0.
ContinuousGREL02–07 and current minimum administrator delegation persist; no
phase reapproval, merge/GREL08/publication, budget increase/reset/refund or deletion.
Next remains authentic provider/worker, new RC/MOS inputs/jobs/extraction/Sweep/spec
and actual clean Codex retry/restart. Historical overlays below remain evidence.

## Active fresh-policy and retained-domain provisioning, 2026-10-08

Current branch feat/grel-03-fresh-domain-policy continues unmerged PR150 corrected
ancestor a26256a. A fixed normal-user setup CLI separates genuine zero-history
initialization from retained accounting reuse. Account-home index and history
inventory reject alternate-root resets; the same transaction/audit code supports
schema2 initial policy and unchanged historical schema1. Local157 PASS/8 skips,
security18/audit clean, Ruff/mypy76 and installed43+20-state preservation PASS.
Actual current VM installed-wheel staging/repeat and existing-domain index
registration/repeat PASS; fresh initialization correctly DENIED. Existing seven
protected control files' content/uid/gid/mode/inode/mtime unchanged. Counter82 /
9,798,942,720, remaining895MiB; new reservations/simulations0. Setup grant false.

Production authenticated provider/terminal workers, new RC/MOS OA/ADE inputs,
effective netlisting/DC/AC/TRAN/extraction, generic Sweep/specification and actual
clean Codex jobs remain incomplete; release BLOCKED. Existing continuousGREL02–07
and minimum administrator delegation continue; no phase reapproval. See
FRESH_DOMAIN_V1.md for actual/synthetic boundaries and source-scoped receipts.

## Active legacy classification correction, 2026-10-08

PR150 P2 feedback corrected: all retained IDs, including unmarked legacy jobs,
are sealed before generic reservation;256KiB JSON plans no longer use the32KiB
profile limit. Actual normal-user installed-wheel append-only correction/repeat
PASS. Old anchor/receipts remain intact; effective anchorcfd037cd seals3 IDs.
Counter82 /9,798,942,720 and old marker/lock snapshot identical; new attempts0.
Original apply evidence below remains historical. An unrelated hosted PowerShell
cold-start fixture caused one PR-event failure while its push Windows/Ubuntu
checks passed; corrected source CI pending. No execution grant/provider/new jobs.
Continue authorized fresh-domain/provider work without phase reapproval.
See EXISTING_DOMAIN_MIGRATION_V1.md for exact receipts and limits.

## Active existing-domain migration checkpoint, 2026-10-08

Current branch feat/grel-03-operator-domain-provisioning stacks on corrected
PR149/8e7fa306 (Windows/Ubuntu CI PASS, prior P2 lock feedback fixed; no formal
approval or merge). Latest main remains553276d. The installed locked wheel exports
fixed Python2.6 helpers and normal-user actual VM inventory/apply/repeat PASS.
An immutable accounting anchor plus intent/completion records were added; existing
counter, markers and shared lock snapshot remained identical. Counter82 /
9,798,942,720; remaining938,475,520 (895MiB); new simulations/reservations0.
This anchors existing accounting only: execution_authorized=false and no grant.

Local affected140 PASS/8 Windows skips, security18 PASS/audit clean, Ruff/mypy74
and85-schema compatibility PASS. Final package preservation/hosted CI receipts are
tracked in EXISTING_DOMAIN_MIGRATION_V1.md and GREL_03_RESULT.md. Genuine fresh
initialization, authenticated production provider, terminal extraction/recovery,
two new RC/MOS OA/ADE circuits, effective inputs/DC/AC/TRAN, generic Sweep/spec
and actual clean Codex submit/read/retry/restart remain incomplete. Release BLOCKED.
ContinuousGREL02–07 and895MiB stay authorized; do not ask phase approval again.
No GREL08/publication/merge/budget reset or new root to evade existing accounting.
Latest user administrator delegation remains current; older exclusions are history.

## Active operator runner coexistence, 2026-10-08

The standard-VM trust repair is in ready, unmerged PR148; its exact source0870c73
passed hosted Windows and Ubuntu verification. Continuous GREL02–07 and the
895MiB remainder stay authorized. The operator route now uses a separate
cadence-operator-runner and active-operator-runner.json while retaining the legacy
launcher/pointer. Ordinary-user actual activation, repeat, two fresh fixed-Python
preflights and shared run.lock contention rejection passed. No new simulations,
reservations, owner/group changes or journal migration occurred. Existing counter
still82 /9,798,942,720. Failure evidence remains private and retained.

Same-profile preflight-launcher updates retain immutable old versions/history;
only the compiled known preflight runner and unchanged other assets are accepted.
This is not a native worker update gate. Production provider/operator confirmation,
existing-domain migration/fresh provisioning, two new OA/ADE circuits, effective
inputs/DC/AC/TRAN/extraction, generic Sweep/spec and clean actual Codex remain
incomplete. Continue those authorized tasks; no phase approval question.
See [coexistence workflow](docs/generic_release/OPERATOR_RUNNER_COEXISTENCE_V1.md).

## Current standard-VM administrator delegation and repair, 2026-10-08

The user's latest direct instruction fixes release support to the professor-provided
CentOS/Cadence VM (or an equivalent reproduced installation), existing PDK and
individual VMware use. Address/SSH keys/account/workspace/circuit/ADE/results/
registries/journals/limits remain operator data. No developer private checkpoint
is a fresh-install prerequisite; existing installations retain their real ledger.
Other OS/Cadence/PDK/physical-host qualification is deferred.

The user explicitly delegates minimum reversible administrator repair on the
current managed VM. This supersedes earlier administrator/permission exclusions
for this bounded repair only; historical statements below remain prior evidence.
Do not request phase/per-path approval again inside the existing GREL02–07 and
895 MiB delegation. Human authentication input is required only if actually needed.
No GREL08/publication/merge, budget increase/reset/refund, license/content changes,
original OA/ADE/PDK/result/journal deletion, security disabling or root MCP/EDA.

Actual repair removed shared write bits from331 installation-code/ancestor items
and one workspace ancestor (332 total). All289 file contents/owners/groups and
331 recorded installation SELinux contexts were preserved. No chown or root
execution was needed. Exact plans, links, ACLs, hashes, partial/repeat/rollback
receipts are private. Root helper-only verification later changed0;
MCP/EDA remained ordinary-user. Reapplication changed0. General-user OCEAN startup passed.
Environment preflight passed; installed immutable version preflight passed at
04:49:03Z, with the legacy launcher preserved. This is not new circuit execution,
full dependency attestation, license entitlement or production-provider authority.
The old launcher name collides with initial generic activation; coexistence must
be implemented without overwriting it. Latest shared ledger remains82 attempts /
9,798,942,720 reserved bytes; zero new simulation reservations in this repair.

Continue coexisting bootstrap, authentic existing-domain provider/migration,
owned new RC/MOS ADE inputs, DC/AC/TRAN/extraction, generic Sweep/spec facts and
actual clean Codex retry/restart within GREL02–07. Release remains BLOCKED until
those actual gates pass. See [repair boundary](generic_release/ADMIN_REPAIR_V1.md)
and [native continuation](generic_release/NATIVE_RESUME_BOUNDARY.md).

## GREL-05 feasible-reader exact-source receipt, 2026-10-08

Tested source f5a1de2 in ready/unmerged PR147: local247 related PASS/no skips;
hosted Windows2622 PASS/four POSIX skips and Ubuntu73 PASS/no skips. Ruff/mypy71,
security18/audit/85 schemas, matching79/80-member artifacts, installed CLI and
32-state preservation PASS. Ten P2s fixed; automatic bot+1/no new findings is
not formal approval. Complete feasible AC/TRAN reader binding is local only;
native attestation/provider/extraction/Sweep/Spec/clean app remain incomplete.
Generic release BLOCKED. Continuous02–07/895MiB persists; no native side effects,
protected repair/budget reset/merge/GREL08/publication. Native trust/resource
observations remain historical, not refreshed here. Exact receipts and ordered
remaining work: docs/generic_release/GREL_05_RESULT.md and NATIVE_RESUME_BOUNDARY.md.
Later docs-only HEADs are separate from the tested code. Prior overlays are history.

## GREL-05 voltage/current identity correction, 2026-10-08

Second PR147 P2 fixed: voltage/current selector inventories must be disjoint;
known PLUS/MINUS branch spellings cannot be registered as node volts. Physical
PSF quantity/unit attestation remains absent. Corrected193-source receipts below
are historical; final quantity-corrected package/CI/review pending. Native trust/
provider/automatic extraction/Sweep/Spec/clean app remain incomplete; release
BLOCKED.02–07/895MiB persists; no native side effects/protected change/merge/
GREL08/publication. See GREL_05_RESULT.md. Earlier overlays remain history.

## GREL-05 measurement identity correction, 2026-10-08

Independent PR147 P2 fixed: generic reader requires exact existing registry v4+
analysis-specific measurement contract and canonical hash; allowlist-only/unknown/
wrong-analysis/stale binding rejects. Qualified fixed legacy definitions cannot
be rebound. Related193 PASS/no skips/12.64s, Ruff/mypy71 PASS. Final package/hosted/
review pending at corrected source;32906b3 CI/package is historical. Native trust/
provider/automatic extraction/Sweep/Spec/clean actual client remain incomplete;
release BLOCKED,02–07/895MiB persists. No native side effects/protected changes/
budget increase/merge/GREL08/publication. See GREL_05_RESULT.md.

## GREL-05 local generic result reader, 2026-10-08

Continuous02–07/895MiB persists. New stacked feature on unmerged PR146/17cb59a
implements a registered fixed OCEAN reader and bounded DC/AC/TRAN frame projection.
Signed role power reuses exact legacy math; AC uses measured complex input and
selected samples; TRAN reports saved-sample resolution and time-weighted mean.
Local189 PASS/no skips/11.08s, Ruff/mypy71/85 schemas PASS. Initial package32-state
preservation PASS predates final aggregate bound; final receipts pending. No public
MCP execution added. Native trust/authentic provider/automatic extraction/Sweep/
Spec facts/clean actual app remain incomplete. Release BLOCKED; native side effects0,
no protected repair/budget increase/merge/GREL08/publication. See GREL_05_RESULT.md.
Historical overlays below remain source-scoped history.

## GREL-03 sealed accounting source receipt, 2026-10-08

Sourceccd01ab in PR146: hosted Windows2544 PASS/four POSIX skips and Ubuntu73
PASS/no skips. Local230 PASS/five OS skips; Ruff/mypy70/security18/audit/85 schemas,
matching78/79-member artifacts and installed32-state preservation PASS. Actual
Python2.6 is grammar-only. Automatic review no new findings/bot+1, not formal
approval. Existing counter/lock with migration-bound immutable identity seals and
conservation implemented; production provider/operator confirmation/real migration/
terminal workers/native trust/new circuits/extraction/Sweep/clean app incomplete.
Main553276d and unrelated OCN preserved. Generic release BLOCKED;02–07/895MiB
continues. Native side effects0; no protected repairs/merge/GREL08/publication.
Exact source-scoped receipts: docs/generic_release/GREL_03_SHARED_RESERVATIONS_RESULT.md.
Historical overlays below remain history.

## GREL-03 immutable reservation identity correction, 2026-10-08

Second independent P1 corrected with an immutable identity index and mandatory
hash-bound operator migration anchor, under the same existing counter/domain/lock.
No separate mutable budget total, worker, counter initialization/reset or migration
writer. Lost128MiB/cancelling records, missing seals/anchors, class conflicts and
unlisted post-migration increments fail closed. Related230 PASS/five skips/47.04s,
Ruff/mypy70 and actual Python2.6 grammar-only PASS. Final exact-source package/CI/
review pending in PR146; older receipts below remain history. Production provider/
real migration/renewal/native trust/jobs/extraction/Sweep/clean client incomplete.
No native side effects/protected repairs/budget increases/merge/GREL08/publication.
Continuous02–07/895MiB persists. See GREL_03_SHARED_RESERVATIONS_RESULT.md.

## GREL-03 shared-counter conservation correction, 2026-10-08

Independent P1 and two P2 marker findings corrected: retain valid old22–24
markers, reject pre-reservation values, and conserve count/byte pairs against
fixed legacy increments plus immutable generic variable reservations. Duplicate
slots, missing variable records and mixed legacy/new increments are tested.
Related220 PASS/five skips/38.77s, Ruff/mypy70 and five-asset actual Python2.6
grammar-only PASS. Final exact-source package/CI/review pending in PR146;
earlier source/package receipts below remain historical. No native side effects,
protected repairs/budget reset/increase/merge/GREL08/publication. Continuous
02–07/895MiB remains; production provider/trust/jobs/extraction/Sweep/clean client
remain incomplete. See GREL_03_SHARED_RESERVATIONS_RESULT.md.

## GREL-03 shared-reservation source checkpoint, 2026-10-08

Tested source52b5452 in PR146: hosted Windows2527 PASS/four POSIX skips and
Ubuntu56 PASS/no skips. Local related213 PASS/five OS skips; Ruff/mypy70,
security18/audit/85 schemas, matching78/79-member artifacts and installed29-state
preservation PASS. Actual Python2.6 evidence is grammar-only, not module execution.
Existing-domain transaction asset, compiled-input identity and corrected historical
marker compatibility are implemented; schema2 carries it and schema1 remains readable.
Independent P1/P2 marker corrections implemented; source52b5452 receipts
below are historical after the latest22-marker floor correction. Related214
PASS/five skips, Ruff/mypy70/Python2.6 grammar PASS; final package/CI/review pending. PR146 ready/unmerged.
Production provider/operator authenticity/native jobs/extraction/Sweep/clean client
remain incomplete; vendor trust still blocked. Continuous02–07/895MiB persists.
No native side effects, protected repair, budget reset/increase, merge/GREL08/
publication. Exact source-scoped history: GREL_03_SHARED_RESERVATIONS_RESULT.md.
Historical overlays below retain their original source/scope.

## GREL-04 source/package/review checkpoint, 2026-10-08

Sourcea3f5fb8 in PR145 (stacked on unmerged144): hosted2473 PASS/no skips;
local2466 PASS/seven OS symlink skips. Ruff/mypy69/security18/dependency/85 schemas/
curated matching artifacts/installed CLI/bootstrap/19-state preservation PASS.
Independent bot+1/no findings is not formal approval. Operator-only generic ADE L
input compilation/comparison is implemented; native provider/copy/API/jobs/
extraction/Sweep/clean actual client remain incomplete. Latest main553276d and
82/9,798,942,720 shared counters preserved. Native trust still blocked by latest
executable_permissions check, not rerun here. Continuous02–07/895MiB persists;
no protected repairs/simulations/reservations/deployments/deletions/merge/GREL08/
publication. Exact receipts and ordered remaining work: GREL_04_RESULT.md and
NATIVE_RESUME_BOUNDARY.md. Historical overlays below retain their original scope.

## GREL-04 generic-input implementation, 2026-10-08

Continuous02–07/895MiB authorization persists. Latest main553276d unchanged;
GREL03 PR144 remains unmerged. New stacked feat/grel-04-generic-ade-inputs adds
operator-only ADE L input compilation/verification, no native dispatch. Local
checks and exact receipts are recorded in docs/generic_release/GREL_04_RESULT.md.
Native trust/provider/copy/API/new DCACtran/extraction/Sweep/clean app remain
incomplete. General release BLOCKED. No simulations/reservations/deployments/
deletions/protected repairs/merge/GREL08/publication. Historical overlays below
remain scoped evidence; do not promote synthetic inputs to native qualification.

## Final durable lifecycle source checkpoint, 2026-10-08

Tested sourcea7fcf45: hosted2423 PASS/no skips/56 warnings; local153 related PASS/
one OS symlink skip; Ruff/mypy68/security18/dependency/85 schemas/package and
installed19-state preservation PASS. Existing AnalysisStore durable lifecycle,
atomic admission/intent, lookup-only retries/provider tombstones, in-flight floor,
SQLite link guards and cached local journal-status are implemented. Two independent
P2s fixed; bot+1 after corrected ready is not formal APPROVED. PR144 ready/unmerged,
main553276d unchanged. Exact receipts in generic_release reports/continuation.
Native provider/attestation/renewal/extraction recovery/generic ADE/new measurement/
Sweep/clean actual client remain incomplete; latest trust rejects executable_permissions
(not rerun in this chunk). Release BLOCKED. Native side effects0;02–07/895MiB
approval persists. Merge/GREL08/publication/protected repairs remain excluded.
Installation owner must provide a trusted chain before native execution. Prior
source overlays and failures below remain history, not current PASS evidence.

## Combined durable lifecycle corrections, 2026-10-08

Two independent P2 findings fixed: atomic admission/intent and restart-safe
provider tombstones; disk floor includes existing in-flight commitments. Primary
review also closes SQLite sidecar hardlinks/nonregular leaves and junction parents.
Affected153 PASS/one OS symlink skip; Ruff/mypy68 PASS. Final source/package/hosted
receipts pending; previous sources remain historical. Native provider/authority/
trust/generic ADE/new measurements/Sweep/actual clean client remain incomplete.
02–07/895MiB authorization persists; no native side effects/merge/GREL08/publication.
See current generic_release reports/continuation. Prior overlays remain history.

## In-flight floor review correction, 2026-10-08

Independent PR144 disk-floor finding corrected: physical free must cover existing
in-flight commitments plus the new reservation above the configured floor.
Affected149 PASS/one OS symlink skip; Ruff/mypy68 PASS. Final source CI/package/
security receipts pending; previous source receipts remain history. Atomic
admission/intent and safe absent-intent cancellation remain implemented. Production
provider/native trust/generic ADE/new measurements/Sweep/clean client remain
incomplete/blocked; no native side effects.02–07/895MiB authorization persists;
merge/GREL08/publication excluded. See current generic_release reports/continuation.

## Durable lifecycle review correction, 2026-10-08

PR144 independent pre-send crash finding corrected: admission/intent commit
atomically; lookup absence permits only provider-verified atomic tombstone, never
resend. Active/remote-unknown state remains denied. Affected147 PASS/one OS skip,
Ruff/mypy68 PASS; final corrected package/hosted receipts pending. d67df77 full2414
PASS is historical after correction. Native provider/operator attestation/generic
ADE/new measurement/Sweep/actual clean client and trust remain incomplete/blocked.
02–07/895MiB authorization persists; no native side effects, merge/GREL08/publication.
See current generic_release reports/continuation. Prior overlays remain history.

## Durable operator lifecycle checkpoint, 2026-10-08

GREL03 now extends the existing AnalysisStore with immutable plans and bounded
append-only lifecycle events. Provider-coordinated submit/reconcile/pending cancel
are implemented locally and tested synthetically; no production native provider
or public dispatch route is installed. Network ambiguity is committed before send;
retries only look up, and cancellation needs an atomic remote identity tombstone.
Legacy admissions/application identity/version remain intact. No budget DB,
parallel worker, refund, reset, grant writer or termination capability is added.
Fresh affected144 PASS/one local OS symlink skip, Ruff/mypy68 PASS. Final exact
source package/security/full hosted receipts are recorded in generic_release
reports/continuation as they are observed; earlier233e27e receipts are historical.
Main553276d unchanged. Continuous02–07 and existing895MiB approval persist.
Native trust/execution, operator attestation, extraction recovery/renewal,
generic ADE/new results/Sweep/actual clean client remain incomplete. No native
simulations/reservations/deployments/deletions/permission/license changes.
GREL08/merge/publication excluded; no repeated phase approval inside02–07.
Prior overlays below remain dated history.

## Final corrected local/hosted checkpoint, 2026-10-08

Tested source233e27e: independent hosted2373 PASS/no skips/56 warnings; fresh
local analysis/forms65 PASS, Ruff/mypy67/security18/dependency/85 schemas/package/
installed two-design forms/reinstall/uninstall19-state preservation PASS. Three
independent review findings are fixed; bot+1 after corrected ready transitions is
recorded separately from formal approval. PR143/144 ready/unmerged; main553276d.
Native trust blocked/executable_permissions; generic admission/ADE/new results/
Sweep/actual clean client and native operating/migration qualification incomplete.
Program0 simulations/reservations/deployments/deletions/permission/license changes;
895MiB existing-remainder approval and continuous02–07 delegation persist.
GREL08/merge/publication excluded. Exact source/artifact/CI/failure receipts:
docs/generic_release/GREL_03_RESULT.md, GREL_07_RESULT.md, ACCEPTANCE_CURRENT.json.
Installation owner must supply a trusted executable/dependency chain first; ordered
resume is in NATIVE_RESUME_BOUNDARY.md. Prior overlays below remain history.

## GREL-03/GREL-07 independent checkpoint, 2026-10-08

Explicit continuous GREL-02 through GREL-07 and existing895MiB remaining-space
approval are active. Latest main553276d is unchanged. GREL02 fixed assets/local
bootstrap are implemented in stacked PR143; positive native trust is BLOCKED by
actual group/other-writable vendor chains. GREL03 adds local authority/immutable
plan forms only; no grant issuance/remote lifecycle/provider/ledger reset. GREL07
adds hosted synthetic workflow and installed state-preservation tooling. Generic
ADE execution/new measurements/Sweep/actual clean app remain NOT_IMPLEMENTED/
NOT_RUN; do not call these phases complete. Source/test/package evidence and
exact source-scoped CI/review receipts are in docs/generic_release/GREL_03_RESULT.md and GREL_07_RESULT.md.
No simulations/reservations/deployments/deletions/permission/license changes.
Installation-owner trust action is required before native acceptance. No protected
chmod, budget increase, merge, GREL08 or publication is authorized. No phase-boundary
question inside02-through-07. Earlier overlays remain dated historical records.

## GREL-02 through GREL-07 continuous user delegation, 2026-10-07

The user now explicitly authorizes GREL-02,03,04,05,06,07 continuously.
Record each phase result and continue independent authorized work without a
phase-boundary question. GREL-08 and publication are not authorized. Existing
resource ceilings, original/PDK/history protection and external trust gates
remain. Remote installs/experiments must use concrete reviewed plans and real
operator authority; no self-created grants, permission weakening or budget reset.
Budget increase, protected vendor chmod, old-result deletion and license changes
remain excluded. PR142 remains unmerged; use feature branches/stacked PRs and
preserve the original checkout's unrelated OCN edit. Do not silently relax its
recorded merge boundary. Current phase: GREL-02 local runner bootstrap; native
qualification awaits SSH connectivity and unchanged executable trust gates.

## GREL-01 active general-release scope, 2026-10-07

The current user selects GREL-01 only, following an attached release pack and
fresh main revalidation through PR141/553276d. Preserve completed client/storage
qualification, all historical circuit work and unrelated local changes. Implement
immutable operator routing, setup/consistency checks, local context observation,
tests, documentation and one feature PR. No remote writes, new simulation,
installation permission changes, global client changes or publication.
Earlier continuous-phase delegations do not extend to the new program.
Report this phase and ask once before GREL-02; do not auto-merge or start it.
See [runtime contract](generic_release/RUNTIME_CONTEXT_V1.md) and
[phase result](generic_release/GREL_01_RESULT.md).
GREL-01 local foundation is complete in feature PR #142 (unmerged).
The next phase is GREL-02 only after a new user choice; general release remains
BLOCKED pending runner/authority and new-circuit execution gates.
Earlier overlays below remain dated historical records.

# Current Phase Plan — Post-v1 Baseline and Capability Preparation

## CLIENT-LIFECYCLE-QUAL-01 completion gate

Actual app sessions03/04 captured initialize2025-06-18 and all85 normalized full
wire schemas equal to SDK. Installed product OpenAI.Codex26.1002.6548.0 is
supported by its observed executable AppxManifest.61 public source inputs were
fingerprinted at child launch, not imported memory. Actual app graceful EOF/
child_exit NOT_VERIFIED: both traces end at server_response, later PID absence
is not graceful-shutdown proof. Four observer slots exhausted; temporary tool
absence and initial failures preserved. Original direct launch/all other current
config restored;26 reads and preserved runtime/DC/AC Sweep/six no-target facts
match after reconnect. Stable Storage16/18,030,073 logical/48,308,224 allocated/
12288 candidate; no execute.2143 prior hashes/whole live checkpoint/ledger82/
9,798,942,720/local stat-only extractor change exact. Phase0 simulator/reservation/
deployment/simulation deletion; conservative11/20 corrections. Initial local
C: disk exhaustion gates preserved; only current synthetic pytest temp roots
cleaned, private phase and simulation evidence untouched. Fresh full2261 PASS/five OS symlink SKIP/57 warnings; observer16/security18/
static59/contract85/dependency/package67+68/install/three SDK profiles/uninstall
PASS. Exact review/containing PR integration receipts govern completion; see
[phase report](CLIENT_LIFECYCLE_QUAL_01.md). Finish reviewed feature integration,
remote SHA/tree verification, report scoped outcome and ask once before another
phase. Complete client lifecycle/new execution remains unqualified; no publication.
Earlier active overlays remain dated history.


## Active CLIENT-LIFECYCLE-QUAL-01

Explicit user continuation activates actual app protocol/lifecycle investigation.
Preserve the existing amplifier-v2/26-read configuration, results and shared
ledger82/9,798,942,720; no simulation, reservation, deletion, consent or publication.
Prepare a fixed operator-only stdio observer with hash-bound private activation,
bounded initialize/tools/list evidence, hashed call results, EOF/child-exit events
and no payload/env/stderr/path audit copy. The child remains the existing bridge
serve command; no MCP API is added. Preserve every prior private/live checkpoint.
Observe actual app schemas/version and re-read preserved results around a
server-only reconnect; keep SDK/synthetic/source-on-disk evidence distinct.
Only an actual app connection restart can supply actual initialize/tools/list and
manager shutdown evidence. No restart API is available here; request one bounded
human server restart after preparation, then restore direct launch and request
the final reconnect for EOF/termination/replay verification. Do not ask for a
whole-app reboot. Source-at-launch hashes are not loaded-memory attestation.
Finish applicable tests/build/security/reviewed feature PR/permitted merge/remote
verification, report verified and unresolved scope, ask once before next phase.
Earlier overlays and correction histories remain dated evidence.

## CLIENT-STORAGE-QUAL-01 completion gate

Actual Codex reconnect exposes26 configured read names; summary, paginated16
artifacts, A/B plus replay/evidence descriptions, exact plan/repeat and stale/
unknown/path/limit rejection match the preserved SDK/native snapshot.
A empty protected container/B retained12288-byte control/original14 records and
whole live checkpoint/2122 prior private hashes remain exact. SDK full85 schemas
are separate from actual app schema/build/version/lifecycle qualification.
Fresh127 scoped PASS/one OS skip, security18/static59/contract85/dependency/
package67+68/isolated CLI/three SDK profiles/uninstall PASS. Full2245 PASS/five OS
skips/57 warnings reused only with exact tested-source/toolchain/policy equality.
Phase0 simulation/reservation/deployment/deletion; ledger82/9,798,942,720 retained.
Five conservative corrections/20; external non-Cadence transport config change
preserved after investigation. Bridge config retains existing catalogs/journals
and22 reads plus four Storage reads; cleanup execute remains excluded.
Finish exact candidate review/feature PR/permitted merge/remote SHA-tree receipt,
report scoped completion, then ask once before CLIENT-LIFECYCLE-QUAL-01.
See docs/CLIENT_STORAGE_QUAL_01.md. No next phase or publication activated.
Earlier overlays remain dated history.


## STORAGE-REAL-QUAL-01 native completion gate

Separate direct human A selection and operator approval bind exact plan/request/
operation. Native A-only payload deletion COMPLETE:8192 logical/unlinked bytes,
observed free delta4096/actual attributable reclaim null; no reservation refund.
B12288 bytes/original14 artifact records/whole original live checkpoint/2094 prior
private hashes exact. A empty container/metadata retained, quarantine empty.
Same-ID replay and fresh SDK server restart return identical durable COMPLETE;
direct bounded native intent/item/result/consent/registration audit PASS.
Storage5/MCP85/v1-v8/old engines unchanged. SDK evidence is not actual Codex-app
Storage E2E; native fault/concurrency injection NOT_RUN. Source/test/toolchain/
policy exact full2245 PASS/five OS skips/57 warnings reuse; fresh scoped/security/
static/contract/package and exact review gates govern completion integration.
Fresh123 scoped PASS/one OS symlink SKIP, security18/dependency/static59/contract85/
package67+68/isolated install/three SDK stdio/uninstall PASS.
Conservative10/20 corrections, initial failures preserved; phase0 simulator/0
reservation/one8192-byte payload delete. Ledger82/9,798,942,720 preserved.
Finish normal reviewed continuation PR/permitted merge/remote SHA-tree receipt;
then report complete and ask once before CLIENT-STORAGE-QUAL-01 read-only actual
app verification. No next phase/extra deletion/compaction/publication activated.
Earlier overlays and preparation evidence remain dated history.


## STORAGE-REAL-QUAL-01 preparation checkpoint — deletion gate pending

Native Linux two fixed synthetic leaves8192/12288 bytes created/inspected; existing
Storage inventory14 protected ->16 protected before registration ->two reviewed
candidates/20480 bytes. Exact plan, both/A-only dry-run, SDK restart and bounded
stale/hash/substitution/path rejection PASS. Storage5/MCP85 full schemas unchanged;
SDK evidence is not actual Codex-app Storage E2E (current app22 filter excludes it).
Fresh full2245 PASS/five OS symlink skips/57 warnings; fixture11/static59/security18/
contract85/dependency/package67+68/install/three SDK profiles/uninstall PASS.
Initial console collection/text-mode failures and external model/reasoning config
change retained; MCP entries unchanged. Eight conservative corrections/20.
2042 prior private hashes/whole original live checkpoint/original14 artifact records/
ledger82/9,798,942,720/local stat-only change exact. New simulation/reservation/delete0;
one helper deployed,20KiB new synthetic payload. No destructive consent produced.
Complete exact-head review/normal checkpoint PR/remote verification, then request
precise user item selection plus independent operator consent under Storage policy.
Native deletion/audit/destructive replay/restart NOT_RUN; this phase is incomplete.
No next major phase/publication/compaction is activated. Earlier overlays history.


## Active STORAGE-REAL-QUAL-01 preparation

User continuation after PR137/main971defcc activates bounded native Storage
qualification preparation: two new disposable synthetic payloads8192/12288 bytes,
one immutable closed fixture helper, existing registration/inventory/plan/dry-run.
No simulator/reservation/historical deletion/config change/publication. Actual
delete remains NOT_AUTHORIZED until exact user selection plus independent operator
consent. Current app22 read-only amplifier tools exclude Storage; use SDK stdio
and label it separately. Preserve2042 prior private hashes, whole live checkpoint,
ledger82/9,798,942,720 and local stat-only extractor change. Complete concrete
plan and applicable gates/reviewed feature PR checkpoint before requesting selection.
Native deletion/replay/audit qualification remains pending; earlier overlays history.


## CLIENT-REAL-QUAL-CODEX-03 completion gate

Scoped actual reads are verified: operator measurement-v8 Gain/Power/native
DC/AC/TRAN/no-target goal and pinned amplifier-v2 runtime/two complete Sweep
payloads/six no-target facts match preserved data.22 filtered names in each
context; final installed context amplifier. Initial reconnect propagation,
external config change, three concurrent read failures and schema-projection
verification failure are retained. Sequential shared-EDA-lock reads/repeats
and stale/malformed rejection PASS. Nine conservative corrections/20.
Fresh19/security18/static59/contract85/package PASS; full2234/five OS skips/56
warnings reused by exact source/tests/toolchain/policy equality. Preserve1987
private hashes/whole live checkpoint/ledger82/9,798,942,720/local stat-only change.
No simulation/reservation/deployment/deletion/target/publication. Overall complete
app schema/build/version/new lifecycle remains unverified. Finish exact gates,
reviewed feature PR/permitted merge/remote verification; report and stop.
Earlier active overlays remain dated history.


## CLIENT-REAL-QUAL-CODEX-03 active operator read qualification

Checkpoint: actual operator-v8 runtime/22 filtered names and preserved
Gain/Power/DC/AC/TRAN/catalog/no-target goal/repeats match historical payloads;
unknown/stale requests reject. Measurement context is verified. Grid profile is
now applied with current unrelated settings byte-exact; a post-reboot external
config change was observed and preserved after a correct stale guard failure.
User reported Sweep reconnect, but first runtime observation remains v8.
Actual grid reads pending correct runtime. Fresh19/security18/static59/contract85
and SDK both profiles PASS; five conservative corrections, initial failures kept.
Current phase remains active, no simulator/reservation/deletion/publication.

User continuation after merged PR136/main15bcd9c authorizes applying the prepared
read-only operator profiles and actual Codex preserved Gain/Power/Sweep/Specification
reads. Measurement v8 and reviewed finite-grid v2 remain distinct contexts; use
only existing PDK metadata/admission/sweep journals, with22 client-filtered read
tools. Preserve all unrelated global settings with byte-exact backup/review;
human reconnect may be necessary because this agent cannot restart its connection.
No simulation/reservation/deployment/deletion/target/optimization/publication.
Freeze prior private/live evidence, preserve82/9,798,942,720 shared counters and
local stat-only change. Actual app observations are separate from SDK/source
schema checks, and config application alone is not measurement qualification.
Complete applicable gates, documentation/state, reviewed feature PR/permitted
merge/remote verification; report and stop, ask once before another major phase.
Earlier overlays are preserved dated history.


## CLIENT-REAL-QUAL-CODEX-02 completion gate

Actual current85 names/native DC reads/repeated reads and bounded rejections
PASS in loaded builtin4/default journals; operator-bound qualification remains
incomplete. Fresh61 client/runtime/contract tests, static59/security18/contract85
PASS; exact unchanged full2234 PASS/five OS skips/56 warnings reused. Current
README package rebuild and exact review/remote integration receipts are required.
Whole live checkpoint,1,955 prior private hashes and global registration match.
Five conservative corrections/20; zero simulator/reservation/deployment/deletion.
Prepared read-only contexts are not installed. After normal reviewed checkpoint
PR integration, report and ask once before operator-bound qualification.

## CLIENT-REAL-QUAL-CODEX-02 active checkpoint

User continuation from PR135/main815321e activates actual Codex read-only
qualification. User-reported restart refreshes host names77 to85; runtime stays
builtin designv4/PDKv2/default journals. Existing native DC repeat/frame evidence
PASS; generic admission and new amplifier catalog correctly deny missing operator
bindings. No full schema/build/app-version/lifecycle qualification is claimed.
Prepare private existing-registry/journal read-only handoff, do not install it.
No simulation/reservation/deployment/config change/deletion/target/publication.
Preserve ledger82/9,798,942,720,1,955 baseline private hashes, original/ADE/PDK/
all results/replay and local stat-only change. Verify current contract/client/
security/package/doc gates and unchanged full-unit reuse, reviewed normal PR,
remote SHA/tree; report partial qualification and ask once before next scope.
Actual Claude Code-tab reads/restart via PR127 remain verified in that scope.


## RELEASE-READINESS-03 completion gate

Current assessment/result v3 records scope-specific conditional/blocked states.
Full 2,234 PASS / 5 OS skips / 56 warnings, static/security/contract85/package
gates PASS; exact candidate archive/install/review/remote integration receipts
are required before completion. No simulation/reservation/deployment/deletion
or publication; shared ledger and protected evidence remain exact. Report and
stop after normal reviewed PR integration; ask once before the next phase.

## Active RELEASE-READINESS-03

User continuation after reviewed SPEC PR134 activates one scoped release
reassessment from61e7b1f. Audit current85 schemas/v1–v8/version/scientific/client/
license boundaries, actual curated builds/install and exact local/hosted archives.
Runtime/MCP/remote code and all historical policy/ledger/protected evidence stay
identical. No new simulation/reservation/deployment/deletion/app config/target,
version bump/tag/release/index/MCPB or old release-body edit. Claude/other hosts/
versions/PDKs deferred. Scope-specific CONDITIONAL/BLOCKED states, imported rights
LEGAL_REVIEW_REQUIRED and PUBLICATION_NOT_AUTHORIZED remain explicit. Preserve
whole live checkpoint82/9,798,942,720,1920 prior private hashes and local changes.
Complete canonical gates, exact candidate review/normal feature PR merge/remote
verification, report and stop; ask once before another major phase. Prior phase
completion/activation overlays below are preserved history.


## SPEC-REAL-EVAL-01 completion gate

Actual six admitted finite-grid gain/power facts now bind to the reused exact
specification comparator through versioned companion contracts. No real target:
NOT_EVALUATED.85 tools preserve all old83 full schemas/v1–v8/RC/native definitions.
Final2234 full PASS/five OS skips/56 warnings, static/security/package and SDK
six facts/restart/nine preserved reads PASS. Initial full timeout-test failure
retained; test-only budget/reserve correction, product10s checker unchanged.
Conservative8/20 corrections; phase0 simulation/reservation/deployment/deletion,
ledger82/9,798,942,720/1880 prior hashes/whole protected checkpoint exact.
Exact candidate/review/containing PR/remote integration receipts govern final
completion. Current85 live app NOT_RUN, full Claude UNVERIFIED, imported rights
LEGAL_REVIEW_REQUIRED/publication unauthorized. Stop after normal reviewed PR
integration: this completes the expressly approved four-phase sequence. Recommend
release readiness reassessment; no further phase, target, experiment or release
is activated. The prior active overlays below are preserved phase history.


## SPEC-REAL-EVAL-01 active plan

Start f6206ce after reviewed Sweep PR133 under explicit continuous delegation.
Reuse existing specification condition/comparator with a typed versioned fact
protocol, not fake old NativeSettings or relabeled preserved PowerDefinition.
Bound actual gain/power point facts, source result/definition/unit/conditions/
plan/catalog digests. Operator-owned companion catalog is empty by default;
no user numerical targets, actual design status NOT_EVALUATED. Read-only bounded
catalog/evaluation only; caller cannot provide target, value, script or path.
Verify missing/unqualified/errors/condition/hash/revision/stale/unit distinctions
and old83 full schemas/v1-v8. Zero new simulation/reservation/deployment/deletion.
Ledger82/9,798,942,720 and existing protected results/private hashes remain exact.
Complete full/static/security/package/actual-source SDK gates, reviewed feature PR,
permitted merge and remote check. Stop after this last continuously approved phase.

## REAL-AMPLIFIER-SWEEP-01 qualification checkpoint

Six actual fixed-grid DC/AC point runs and gain/signed-rail-power facts PASS.
SDK same-ID/restart/old78 schema/read/admission regression PASS; active pending
cancel/crash/partial-failure semantics remain synthetic evidence only. Full2194
PASS/four OS skips/56 warnings/static/security PASS. Ledger82/9,798,942,720;
six jobs1,105,799 logical/1,511,424 allocated bytes,10/20 corrections retained.
Original/ADE/PDK/prior jobs/replay/1810 private hashes preserved. Complete final
package/exact reviewed feature PR/remote, then continue already approved
SPEC-REAL-EVAL-01 without a question. No target/new simulation/deletion/release.

## REAL-AMPLIFIER-SWEEP-01 active plan

Start from reviewed Bias PR132/main a809b5e under continuous user delegation.
Reuse the existing SweepStore/SweepSupervisor lifecycle via explicitly versioned
compiled plan/point codecs and one closed amplifier adapter, preserving every
old78 MCP schema/v1–v8/RC plan identity. Operator-owned finite-grid contract only:
VBIASN319/320/321mV, VBIASP702mV/VDD1V/VCM0.5V,NN27C,no added external load.
One1D DC then one1D AC actual three-point sweep; at most six128MiB reservations
under the same ledger/EDA/disk/replay guards, baseline76/8,993,636,352.
Signed-power point definition is separately versioned; gain is differential at10Hz.
No caller script/path/rawPSF/netlist, optimization/expansion/deletion/publication.
Cancellation can stop unstarted points only; active simulator termination remains
unqualified and must not be claimed. Freeze typed policy/delegation before deploy/
actual execution; prove effective input, exact receipts, restart/same-ID/resume,
partial failure, budgets and protected Bias/Offset/history. No invented target.
Finish current gates/reviewed feature PR/remote, report and continue the next
already approved SPEC-REAL-EVAL-01 without a transition question.

## BIAS-RANGE-QUAL-01 activation

Qualification checkpoint: four actual endpoint DC/AC runs and reused center
PASS; finite grid only.2,127 full PASS/four OS skips, current static/security/
contract/package/SDK gates PASS,8/20 conservative corrections. Ledger76/
8,993,636,352, four jobs732,166 logical/958,464 allocated bytes; old78/v1-v8 and
all original/ADE/PDK/prior jobs/replay/1,746 private hashes preserved. Reviewed
containing-PR integration is recorded privately. Continue the next already
approved REAL-AMPLIFIER-SWEEP-01; no transition question inside this sequence.

From merged Offset5e89fd0; branch feat/bias-range-qual-01, user continuous delegation.
Finite one-axis VBIASN319/320/321mV; fixed VBIASP702mV/VDD1V/VCM0.5V/NN27C,
original topology/no added load. Reuse exact admitted center DC/AC/power; four
new owned endpoint DC/AC jobs maximum. Stop first unexpected guard, identity,
effective input, simulation or missing-extraction failure; no expansion.
Shared ledger72/8,456,765,440,500/10GiB/20 corrections, no elapsed ceiling.
Preserve original/ADE/PDK, all prior jobs/Offset/private evidence and78/v1-v8.
Before registering numeric grid require complete signed sources, DC rail/common
mode/bias, valid bounded10Hz gain and exact reversed source hashes/receipts.
This qualifies only the finite nominal simulation grid, not continuum, MOS-region
proof, electrical ratings, reliability, performance targets or optimization.
Parameterized submission remains denied until the next reviewed adapter phase.
Finish gates/reviewed feature PR/remote; continue next already approved phase.

## Final Offset gate

2,073 PASS/four OS symlink skips; static/security/package/SDK and strict composed
protection pass. Reviewed containing-PR/main verification recorded privately.
Continue approved BIAS-RANGE-QUAL-01 at this boundary, without another question.

## ANALOG-OFFSET-01 qualification checkpoint

Selected input-nulling five-case actual study complete; supplemental
PARTIALLY_QUALIFIED, numerical zero residual without physical precision. Generic
offset remains UNQUALIFIED/null, goals absent. Read-only78-tool addition preserves
old77/v1-v8. Ledger72/8,456,765,440; phase4/536,870,912. Preserve strict historical
verifiers/protected evidence and finish current full gates/reviewed PR integration.
Then continue the separately approved three phases without another question.

## Four-phase continuous delegation, 2026-10-06

The user explicitly authorizes ANALOG-OFFSET-01 followed by BIAS-RANGE-QUAL-01,
REAL-AMPLIFIER-SWEEP-01 and SPEC-REAL-EVAL-01 continuously in this chat, without
another phase-transition question inside that sequence. Report and verify each
phase and its reviewed feature PR; preserve all security/resource/scientific
selection gates. This supersedes older transition-confirmation text for these
four phases only. No release, deletion, optimization, original mutation or
unbounded execution is authorized. Stop and report after SPEC-REAL-EVAL-01.

The user separately selects nominal open-loop input nulling for Offset: applied
Vp−Vm where Vop−Vom=0, fixed VCM0.5V/NN27C/VDD1V/bias320/702mV. Existing admitted
DC reports zero differential output, but is insufficient alone to qualify input
offset. Fix four new DC points at−1,+1,−0.5,+0.5microV before observing results,
plus high-precision extraction from existing zero-input PSF. At most four new
128MiB reservations under the shared ledger; no range expansion or new zero
simulation. Require effective input/common mode/rails, unique bracket, local
output window and pair-refinement diagnostics. This limited nominal study is
separate from mismatch statistics, electrical ratings, the generic offset-v1
definition and goals. Keep unavailable/uncertain results fail closed.

## Historical ANALOG-OFFSET-01 initial activation, 2026-10-06

User confirmation after merged Claude PR127 activates feat/analog-offset-01
from09339c48c692f6e00e53b36adc725516b54b4daf. Preserve original77 MCP schemas,
registry v1-v8, native readers, source/ADE/PDK/jobs/replay and all prior evidence.
Investigate current nominal open-loop reference and existing DC conditions.
Prepare bounded input-nulling/output candidate definitions and extraction/tests;
do not choose the user's scientific definition or register a target implicitly.
Ask once at the necessary selection point, continue independent preparation,
and keep actual experiments/readers gated until an answer. Baseline68 attempts /
7,919,894,528 reserved bytes;500/10GiB/20 corrections, no elapsed ceiling.
No range/point/reservation has been activated. Preserve failures and use existing
engines/ledger/lock/disk protections for any later justified fixed experiment.
No deletion/optimization/source edit/release or other-environment request.
See [preparation checkpoint](ANALOG_OFFSET_V1.md). Phase is active and incomplete;
no next phase is activated. Report only the scientific blocker if it requires
user input; complete normal reviewed PR/main integration when the phase is done.

## Claude PR127 review and integration, 2026-10-06

The user explicitly requests review and merge of the completed Claude-authored
read/restart report on its existing branch. Preserve its historical observations
and unknown tested source identity. Integrate latest main without rewriting the
branch; review public JSON, evidence references, links and secret boundaries.
Record Code-tab existing reads/restart separately from Desktop chat, full
schema/protocol, new lifecycle and the blocked sweep journal. No blanket
CLAUDE_REAL_CLIENT_UNVERIFIED clearance, new simulation, deployment, configuration
change, deletion or release. Reuse exact unchanged runtime/test evidence; run
current contract/security/client and updated distribution/documentation checks.
Complete reviewed PR127 integration and verify remote SHA/tree privately.
ANALOG-SLEW-01 is already merged as PR130; this review activates no next analog
phase. ANALOG-OFFSET-01 still requires one user confirmation. See the
[Claude run report](validation/claude-desktop/20261006T0407Z/REPORT.md).

## ANALOG-SLEW-01 activation, 2026-10-06

User confirmation after merged PM PR129 at b49d826448c1ddab2a2b3d4e176d07db3462412d
activates feat/analog-slew-01. Fixed discovery pins native TRAN and installed
pulse/TRAN controls. See [step study](ANALOG_SLEW_V1.md). Four owned copies only:
10/5/2.5 ns maxstep at1 ns input edge, then2.5 ns/0.5 ns. Stop10 us, differential
input -0.1 to+0.1 V at2 us then back at6 us; VCM0.5 V. Fixed NN27C/VDD1V/bias
320/702mV, original topology/no added load. Preserve source/ADE/PDK/all prior
evidence/replay/contracts/76 schemas. Maximum four128MiB reservations, shared
500 attempts/10GiB/20 correction limits; no elapsed limit. Evaluate fixed plateau
windows,20--80% secants, bracket density, ringing, subwindow linearity and1%
empirical timestep/edge agreement before any qualification. Original analog
slew stays UNQUALIFIED; supplemental versioned study cannot evaluate goals.
Complete applicable gates/real study/SDK/protection and reviewed PR integration.
No deletion/publication/optimization/other-environment request. Report and ask
once before ANALOG-OFFSET-01.

Qualification checkpoint: four actual owned step runs and bounded summary extraction
complete; supplemental20--80% rise/fall is PARTIALLY_QUALIFIED and nonlinear,
conventional generic slew stays UNQUALIFIED/null. Initial coarse bracket is
insufficient; remaining controls fixed to200/100/100 ps before new observations,
within max4 attempts. Original5/2.5ns plan remains NOT_RUN. Two-resolution and
faster-edge differences <1%, no absolute error bound or three-level convergence.
Current-source SDK77/v8 preserves old76 schemas/DC/AC/TRAN/power/bandwidth/sweep
and restart; live Codex69 analog catalog remains empty/new tool NOT_EXPOSED.
Ledger68/7,919,894,528; phase4/536,870,912, no refund/reset/deletion. Nine of20
corrections and all initial failures/immutable deployments retained; strict
composed conservation protects original/ADE/PDK/jobs/replay/1,487 old private
hashes. Final full2,002 PASS/four OS skips/static/security/package gates PASS;
containing reviewed PR integration recorded privately and
in [result](ANALOG_SLEW_01_RESULT_V1.md). Report and ask once before
ANALOG-OFFSET-01; no next phase is activated.

## ANALOG-PM-01 activation, 2026-10-06

User confirmation after merged BANDWIDTH-QUAL-02 (#128) activates this phase only.
Starting main854bc0c44b23efc6e4296579e7948e83f9cd9bbb, branch feat/analog-pm-01.
Inspect the exact admitted reference circuit/analysis and available installed
Spectre STB/probes through bounded fixed operator reads. Identify differential
and common-mode feedback, return paths and any candidate probe point before
deciding applicability. No arbitrary expressions, files, scripts or waveforms
are exposed. The first discovery step consumes no simulator attempt/reservation.
No loop-gain measurement is assumed from AC output phase or a help entry.

Only a scientifically defined loop in an authorized owned copy may justify a
later fixed simulation: establish DC and loading preservation, sign, unity-loop
crossing selection, multiple crossings, conditions and provenance first. If no
applicable/qualified loop exists, preserve UNQUALIFIED/null and report the exact
reason and a future qualification path; do not invent an application feedback
network to obtain a number. Preserve all76 schemas/v1-v8 contracts and protected
material/replay/budgets;500 attempts/10 GiB cumulative reservation/20 same-change
corrections, no elapsed ceiling. Current baseline64/7,383,023,616 remains history.
Complete applicable gates, actual discovery and unchanged MCP regression, docs/
state, reviewed feature PR/permitted merge/remote SHA-tree verification. No
deletion, optimization, target, version/tag/release or other-environment request.
Report and ask once before ANALOG-SLEW-01.

Final qualification checkpoint: actual pinned reference audit finds no defined
application feedback loop; numeric PM remains UNQUALIFIED/null. STB/iprobe help
documented only; diffstbprobe unknown-topic warning despite exit0. No licensed
STB/probe/sign/crossing run. Operator35/combined99, full1,929 PASS/four OS symlink
SKIP/56 warnings519.73s, canonical Ruff/mypy52/contracts76/v1-v8/security18/locked
audit/886-file scan/package wheel60-sdist61/isolated76-tool three SDK formats/CLI/
uninstall PASS. Current-source v8 SDK PM null/restart is equal. Actual Codex
69-name surface returns an empty analog list and denied PM description; global
configuration stays exact. Three of20 conservative corrections; zero new
simulation/reservation/deployment/result/deletion. Ledger64/7,383,023,616 and
source/ADE/PDK/jobs/replay/1,452 prior private hashes remain unchanged. Exact
containing-PR review and remote SHA/tree integration are recorded privately.
See [result](ANALOG_PM_01_RESULT_V1.md). Ask once before independent ANALOG-SLEW-01;
no next phase is activated. Numerical PM needs a separately defined loop fixture.

## BANDWIDTH-QUAL-02 activation, 2026-10-06

User confirmation after merged MEAS-CONTRACT-02 (#126) activates this phase only.
Starting main `d97d9934341d382c1131ee1f5d61ab8cc75ace38`, branch
`feat/bandwidth-qual-02`. The prior 71-point AC evidence is 10 Hz–100 MHz,
10 points/decade, first -3.0 dB crossing relative to 10 Hz differential gain.
Preserve its definition, schema, result and PARTIALLY_QUALIFIED status.

Before new results are observed, fix two refinements: 10 Hz–1 MHz at 50 and 100
points/decade (251/501 samples), same circuit/model/options/stimulus/conditions.
No new netlister or state mutation: reconstruct the exact pinned native input
from each owned copy by reversing its single AC-line change. Installed Spectre
AC decimal-grid control and prior input/result identity must be checked first.
Maximum two new attempts, two 128 MiB cumulative reservations; no refund/reset.
Use the same EDA lock, ledger, native protection guards, disk floor, exact private
delegation, durable exclusive admissions, result fingerprints and no blind retry.
New raw PSF/jobs are phase evidence, protected/unknown to cleanup.

Report sampled 10–1,000 Hz span, observed peaking, downward-crossing count,
containing bracket and first-crossing interpolation. Empirical convergence uses
successive relative change <=0.1%, decreasing change and brackets, reference gain
agreement <=0.001 dB, sampled span/peaking <=0.05 dB. These are study diagnostics,
not user specifications or electrical limits. Record nonconvergence, missing or
multiple crossings explicitly. No absolute error bound or continuum flatness is
established. Even an observed grid convergence remains PARTIALLY_QUALIFIED.

Add one bounded read-only supplementary study tool through existing registered
bandwidth/source/PDK/admission checks. No caller frequency/grid/formula/path,
raw vector, execution route or goal evaluation. Preserve old 75 full schemas,
v1-v8 registry versions and all protected/private/replay material. Limits500/10GiB/
20 corrections, no elapsed ceiling. Complete focused/full/static/security/
dependency/contract/build/install/SDK and justified real reference verification,
docs/state and one reviewed feature PR/permitted merge/remote SHA/tree check.
Actual new app tool calls are separate from SDK stdio. Claude/other versions/PDKs/
hosts remain deferred. No optimization, deletion, version/tag/release or numerical
target. Apache original-code/export boundaries, LEGAL_REVIEW_REQUIRED and
PUBLICATION_NOT_AUTHORIZED remain. Report and ask once before ANALOG-PM-01.

Final qualification:1,894 full unit PASS/four OS symlink SKIP/56 warnings in539.63s;
focused112 and server/SSH/science/operator121 PASS, Ruff/mypy52 and exact76-tool/
old75/v1-v8 contract audit PASS. Security18 PASS, locked audit no known vulnerabilities,
881-file secret scan and wheel60/sdist61 isolated76-tool/three SDK formats/CLI/uninstall
PASS. Real two-grid AC and current-source SDK preserved reads/restart PASS; new actual
app calls NOT_RUN. Both prior failed full runs and historical sizing-domain FAIL
are preserved alongside the strict composed verification PASS. Twelve of20 corrections;
64/500 attempts and7,383,023,616/10,737,418,240 cumulative reservation, no refund/reset.
Protected source/ADE/PDK, prior jobs/replay/admission and1,370 prior private hashes
remain exact. Containing reviewed feature-PR integration/remote SHA/tree are recorded
privately. See [result](BANDWIDTH_QUAL_02_RESULT_V1.md). No next phase is activated.

MEAS-CONTRACT-02 is complete at merged #126 main d97d993; its prior qualification
and resource counts below remain historical evidence, not active restrictions on
this separately user-approved study.

## MEAS-CONTRACT-02 activation, 2026-10-06

User continuation after merged #124 selects one power-contract integration phase.
Starting main `0e85a12804d550279a9da0c5ebe9f92acabcc62e`; branch
`feat/power-measurement-contract-binding`. Reuse qualified `dc-supply-power-v1`
and its exact admitted reference DC operation. Add bounded combined discovery,
operator registry v8 with version-2 power goals, and evaluation through existing
signed-current reader and shared condition/comparison engine. All old 72 tool
schemas and v1-v7 registries remain exact; old analog power stays UNQUALIFIED.
A version-2 runtime observation describes v8 honestly; the old version remains
exact for v1-v7 and rejects v8 with a versioned-tool handoff. No numerical reference
goal exists: NOT_EVALUATED. No new simulation/reservation, remote deployment,
source/ADE/PDK change, deletion, optimization or publication. Preserve counters,
replay identity, private evidence and Apache/export/legal boundaries. Limits:
500 attempts,10 GiB cumulative reservation,20 corrections; no elapsed ceiling.
Run full/static/security/dependency/contract/build/install/stdio and justified
preserved-power read regression, then reviewed feature PR/permitted merge/remote
verification. Report and ask once before BANDWIDTH-QUAL-02. Claude/other
Cadence/PDK/host qualification stays deferred.

Final qualification:1,813 full unit passes/four OS symlink skips/56 warnings
in481.33s; focused147, Ruff/mypy50, exact old72/v1-v7 and new75/v8 schema audit,
18 security tests/dependency audit and wheel58/sdist59 isolated75-tool CLI/stdio
acceptance pass. New v8 preserved-power/DC/AC/TRAN/sweep/restart SDK regression
equals earlier real evidence; power82.42816 microW and targetless NOT_EVALUATED.
New actual-app tools are NOT_RUN. Five conservative correction events retained;
all1,342 prior private records and source/ADE/PDK/jobs/counters/admissions equal.
Zero new simulation/reservation/deployment/deletion/owned remote bytes. Integrate
one containing reviewed PR with exact remote SHA/tree recorded privately, report
and ask once before BANDWIDTH-QUAL-02. See
[result](MEAS_CONTRACT_02_RESULT_V1.md). No next phase is activated.


## AGENT-PLAN-EXPORT-BOUNDARY-01 activation, 2026-10-06

Starting main `20726ead871ffda18a937938fed7c4a6426d5b5d`, completed #125.
The user selects existing draft #124 on `chore/agent-plan-export-boundary-01`.
Merge current main into that branch without rewriting history. Preserve all
181 currently tracked imported/integration files, source/remote bytes, contracts,
private evidence and cumulative resources. Audit external references/copies,
run current local gates and inspect exact candidate local ZIP/TAR plus actual
GitHub ZIP/tar.gz. Compare every retained member with its candidate Git blob.
Document installation without the omitted historical planning helper, whose
missing inputs must still fail. Imported rights and publication remain separate.
Correction ceiling20; no remote contact, simulation/reservation/deletion/release.
Finish one reviewed PR, verify remote SHA/tree and report once. See
[export boundary](AGENT_PLAN_EXPORT_BOUNDARY_V1.md). Power extraction is complete;
its generic measurement/specification binding remains pending. Recommend a
bounded MEAS-CONTRACT-02 continuation to finish that part of the expanded
ANALOG-POWER-01 objective, then BANDWIDTH-QUAL-02, ANALOG-PM-01, ANALOG-SLEW-01,
ANALOG-OFFSET-01, BIAS-RANGE-QUAL-01, REAL-AMPLIFIER-SWEEP-01 and SPEC-REAL-EVAL-01
at separately confirmed phase boundaries. This sequence is future program scope,
not continuous execution authority. Preserve old measurement definitions; do not
invent numerical goals or reinterpret point observations as qualified ranges.
Other Cadence/PDK/host and Claude actual-app qualification remain deferred.
Storage actual deletion requires separately selected disposable plan/items and
independent operator consent; raw-result compaction remains a separate phase.


Final full gate: 1,783 passed, four OS symlink skips, 56 warnings in616.85s.
Initial console-script collection failed on a project-root import; corrected
`uv run python -m pytest` runs every test. Ruff/mypy48, contract72/legacy22/v1-v7,
861-file secret preflight, 18 security tests and locked dependency audit pass.
Both checkout and actual hosted ZIP build/install gates pass: wheel56/sdist57,
three installed SDK stdio formats/72 tools, local doctor/CLI and uninstall.
Actual hosted snapshot additionally passes64 archive/distribution/contract tests.
Four inspected archives exclude181 import/integration files and retain680 exact
candidate blobs. Windows auto-CRLF first caused243 text mismatches; canonical
Git export resolves them without changing the verifier or original data. Two
bounded verification corrections of20; first failures remain private. Historical
imported helper is NOT_PASS because its original ZIP is absent; no waiver/skip.
No runtime/API/remote/source/import/evidence/budget change or new simulation,
reservation, deployment, result deletion, version/tag/release. Rights review and
publication remain distinct; prior private1304 records are rechecked before merge.
Continue existing reviewed PR124; exact final-head hosted/local archives,
installation, review and remote SHA/tree outcomes remain private. Report once
and ask before MEAS-CONTRACT-02; do not restart completed power extraction.

## ANALOG-POWER-01 activation, 2026-10-06

User continuation activates one power extraction phase from
`8009060edc076ccacb371c45d8f8fb3a335b150f` after #123. Inspect the preserved
admitted native DC result before considering simulation. Its exact native netlist
has six ideal voltage sources: two supply rails, two bias sources and two inputs.
Require complete inventory, effective voltage, signed positive-terminal current,
units, conditions and source/frame provenance. Keep supply-rail power distinct
from bias/input-source contribution and total delivered source power.

Use an immutable fixed operator extraction stage with an owned bounded output;
never modify the preserved job/PSF/source/ADE/PDK. Fit at most 8 MiB of extraction
overhead within the existing source-job 128 MiB reservation after checking unused
capacity and disk floor. No new Spectre attempt or result reservation. A missing
current, ambiguous sign/unit or incomplete inventory is UNQUALIFIED, never zero.
Preserve old analog definitions, v1-v7 registries, replay identities and 70 schemas.
Any new power API is additive and read-only, references registered IDs only, and
cannot initiate extraction. Complete applicable tests/security/package/protocol
and preserved-result regressions, one reviewed PR and remote SHA/tree verification.
Claude real app remains deferred. No deletion, optimization, release or new target.
Correction ceiling 20 with failures and prior histories retained. Report at this
phase boundary and ask once before further work.

Final gates: **1,772 passes/four OS symlink skips/56 warnings/739.32 seconds**;
79 focused passes; Ruff/mypy48, final secret preflight857, 18 security tests and
locked dependency audit pass. Final wheel56/sdist57 includes canonical Apache
notices with no unexpected/protected findings; isolated 72-tool/three-format
CLI/stdio/uninstall passes. Exported Codex SDK stdio qualifies signed reference
power and preserves all 70 schemas/native DC/AC/TRAN/sweep/restart results.
Independent OP current/power, installed sign/unit help and actual guest Python2.6
exhausted-read budget boundaries pass. Original analog v1 power/goals stay exact.
Nine corrections of20; prior failures retained. Zero new Spectre/reservation/
deletion. New owned extraction/crosscheck/v1-v2 deployment footprint **39,314 B**
fits the existing source-job reservation. Source/ADE/PDK/jobs/counters/admission
and1,224 prior private records unchanged. See [result](ANALOG_POWER_01_RESULT_V1.md).
Integration uses containing reviewed [PR #125](https://github.com/Phjrab/cadence-mcp-bridge/pull/125),
with resulting remote SHA/tree verified privately,
then report. Recommend MEAS-CONTRACT-02; no next phase is automatically activated.

## RUNTIME-CONFIG-01 activation, 2026-10-06

Starting main `b015b7151239e5613f8960fa896b8422b0b680aa`, merged #122.
The latest user instruction defers Claude actual-client qualification and selects
next development. Existing Sweep/Storage/Analog/Specification and release reassessment
are complete. Real Codex has five verified reads; complete app lifecycle remains
unverified. No phase history is restarted or promoted.

Select a small onboarding foundation: clients cannot presently identify the
running server's loaded registry version or whether journals use default/operator
selection. `cadence_health` is remote health; CLI `doctor` checks a different local
process. Add `cadence_runtime_info`, a local no-input observation of actual service
startup snapshots. Do not reread paths/files or change settings. Preserve all 69
prior schemas and add a separate reviewed schema snapshot. Verify defaults,
v1-v7 loading, explicit/mixed journal choices, rejected arguments, bounded privacy,
repeated/concurrent/restarted stdio reads and isolated installed-wheel behavior.
Run static/full-unit/security/dependency/package and justified preserved-result
regression. No simulation/deployment/deletion or version/tag/release. Claude
adapter remains present; its actual-app gate is DEFERRED_BY_USER and
CLAUDE_REAL_CLIENT_UNVERIFIED. Report and ask once before another phase.
See [runtime observation](RUNTIME_CONFIGURATION_V1.md).

Final gates: 1,731 full unit passes/four OS symlink skips/56 warnings; focused
49 passes; Ruff/mypy 46 modules; security/dependency and final wheel54/sdist55,
isolated installed 70-tool stdio/CLI/uninstall pass. Old 69 schemas and 74
service methods remain exact. Preserved native DC/AC/TRAN and RC sweep/restart
are equal; fresh fixed postflight verifies source/ADE/PDK/jobs/counters unchanged.
All 1,191 prior private records equal. Three corrections of 20 consumed; failed
and environment-misconfigured runs are retained as NOT_PASS. Zero new simulation,
reservation, deployment, deletion or publication. Integrate one containing reviewed
feature PR with exact remote SHA/tree recorded privately. Recommend ANALOG-POWER-01
at the normal boundary; no automatic next phase. See
[phase result](RUNTIME_CONFIG_01_RESULT_V1.md).

## CLIENT-REAL-QUAL-01 actual Codex read evidence, 2026-10-06

Starting main `434e5efd7fc8ad940d921d5e82c5cd25bd818d7f`, after #121.
The active Codex host now exposes the bridge's 69 names, matching the reviewed
names. Actual design list/describe/PDK and preserved native DC status/result
calls succeed through its MCP tools; no SDK substitute or new simulation.
The preserved DC frame hash matches prior evidence. Record
[partial actual-app qualification](CLIENT_REAL_QUAL_CODEX_READS_V1.md) through
a reviewed documentation PR. No runtime/API/profile/journal changes. Earlier
missing-tool blocker is superseded for Codex; UI control restriction remains.
Full app schema/version/lifecycle and Claude are still NOT_TESTED/unverified;
phase incomplete. No automatic next phase or release.

## CLIENT-REAL-QUAL-01 activation/checkpoint, 2026-10-06

User continuation activates actual app qualification after #120 at
`3432d580994bd825e5d650dd284d110342ac01e3`. Fresh Windows helper inventory is
callable, superseding the earlier native-unavailable assessment. Current Codex
is returned as ChatGPT; the applicable Computer Use skill prohibits that UI.
No targetable Claude app is returned, and current global Codex config has no
bridge entry. Actual app inventory/calls remain NOT_TESTED; phase is BLOCKED,
not complete. Add [concrete human handoff/evidence rubric](CLIENT_REAL_QUAL_01_CHECKPOINT_V1.md)
through a reviewed checkpoint PR. Do not install immutable replay-test configs
as live app configs or reset historical journals. Runtime/API/configs/budgets
remain unchanged; no new remote/simulation/deletion/release action. Resume this
same phase with direct app evidence; no automatic next development phase.

## RELEASE-READINESS-02 activation, 2026-10-06

Starting main `4ea17e2641f316ec0899c9c91f8bea97c6b4086f`, merged #119.
Preserve completed foundations. Reassess 69 tools/22 legacy declarations,
v1-v7 schemas, current package/license/client evidence and public scope. Add a
repeatable local contract gate and updated readiness v2; run existing applicable
static/security/full/package/installed/protocol gates. Reuse exact prior native
E2E because no runtime/remote source changes. No release candidate/version/tag/
publication, actual Desktop claim, deletion or optimization. Complete one reviewed
PR and report open gates at the normal boundary; no automatic next phase.

Final gates: 1,717 unit passes/four OS symlink skips/57 warnings; focused 56
passes; Ruff/mypy 45 modules; security/dependency and final distribution/isolated
install acceptance pass. Audit preserves 69 full schemas, 22 legacy declarations,
two models and seven registry schemas; API/runtime/remote unchanged. Prior exact
native E2E reused with fresh protected postflight; 1,088 prior private records equal.
Zero simulation/reservation/deployment/deletion; one correction of 20 consumed.
Curated package CONDITIONALLY_READY; new GitHub release NOT_READY; whole-tree
rights LEGAL_REVIEW_REQUIRED. No version/tag/release/body edit or app PASS.
Integration uses containing reviewed [PR #120](https://github.com/Phjrab/cadence-mcp-bridge/pull/120), with resulting remote SHA/tree
recorded privately. Recommend CLIENT-REAL-QUAL-01; ask once at this phase boundary.

## SPEC-CONTRACT-01 activation, 2026-10-06

Starting main: `e3a3fb41d48a391a8c9667237a076dabeea3dda1`, merged #118.
Activate one operator-owned specification phase with registry v7 and three
read-only APIs. Exact measurement/unit/conditions binding; no invented reference
targets. Strict QUALIFIED only for PASS/FAIL, inclusive range and bounded decimal
comparators. Empty reference specifications remain NOT_EVALUATED. Preserve
old schemas, source admission, sweep identity, resources and evidence. Reuse
preserved results; no simulation, deployment, deletion, optimization or release.
Run static/full/security/package/stdio and provenance regression, integrate one
reviewed PR, verify remote main, then report and ask once before Release Readiness.

Final gates: 1,693 full unit passes/four OS skips/57 warnings; 79 focused passes;
Ruff/mypy 45 modules; security/dependency and final distribution/isolated installed
acceptance pass. Exported Codex/Claude SDK stdio verifies old 66 schemas and native/
analog/sweep/storage/restart equality with zero new simulation/reservation/deletion.
Reference has no goals and remains NOT_EVALUATED. One correction of 20 used;
1,063 prior private records and protected jobs/counters remain equal. Integration
uses containing reviewed [PR #119](https://github.com/Phjrab/cadence-mcp-bridge/pull/119);
final remote SHA/tree preserved privately.
This completes one phase and does not activate Release Readiness or publication.

## ANALOG-MEAS-01 activation, 2026-10-06

User continuation selects this one phase after merged #117 at
`e3fcfad30f35c68b1a90160d4d5f3a364436ab12`. STORAGE-MGMT-01 is complete;
actual Linux deletion remains NOT_RUN. Implement registry v6 derived contracts
around unchanged v5 source/analysis/sweep identities, with three read-only tools.
Use preserved admitted native AC evidence for differential gain at 10 Hz and
first downward 3.0 dB crossing relative to that measured reference. Bandwidth
is a bracketed log-frequency interpolation estimate; no DC plateau/error bound,
unity-gain or closed-loop claim. Phase margin, power, offset and slew rate retain
explicit UNQUALIFIED reasons and future scientific/extraction requirements.

No new simulation, extraction, remote deployment, deletion, reservation, target
registration, optimization or release. Keep 62/500 attempts, 7,114,588,160 / 10 GiB
reservations, removed elapsed ceiling and all protection/replay rules. Local
static/full/security/dependency/distribution and exported-client stdio regression
are required; real Desktop app evidence remains distinct. Preserve failures and
active correction ceiling 20. Integrate one reviewed feature PR and verify remote
main. Report and ask once before SPEC-CONTRACT-01. See [workflow](ANALOG_MEASUREMENTS_V1.md).

Final qualification: full unit 1,651 passes/four OS skips/57 warnings, static
42 source modules, focused 94 passes and corrected server/analog 33 passes,
security/dependency/distribution/install gates pass. Actual exported SDK stdio
verifies all 63 old schemas, source provenance, native/sweep/storage regression
and restart without simulation. Gain is qualified at 10 Hz only; bandwidth is
partially qualified as a sampled-reference estimate; four other physical metrics
remain UNQUALIFIED. Five corrections used of 20 with failures preserved.
Integration uses containing reviewed [PR #118](https://github.com/Phjrab/cadence-mcp-bridge/pull/118),
with exact remote SHA/tree verification retained privately after permitted merge.
This completes one phase and does not activate SPEC-CONTRACT-01.

## STORAGE-MGMT-01 final qualification overlay, 2026-10-06

The user explicitly sets the repository same-change correction ceiling to 20;
PHASE_CORRECTION_LIMIT_V5.json binds that overlay without resetting usage.
Nine corrections are consumed. Immutable v6 retains old deployments, failed v1
stage and the original control/spool/replay domain. Protected-group aggregation
and bounded per-root traversal resolve the old coverage gap: all six registered
roots SCANNED, 446 job identities, 14 protected groups and 9,470 observed nodes.
Every fixed historical group's orphan active marker also blocks cleanup.
Current [phase result](STORAGE_MGMT_01_RESULT_V1.md) supersedes the checkpoint
below; earlier approvals/failures are preserved history. Final full unit
(1,629 passed, four skipped, 57 warnings), security and distribution gates pass.
Integration uses containing reviewed PR #117 with exact remote SHA verification
retained privately after permitted merge; no state-sync-only PR is created.
There is no actual user-selected deletion; remote delete remains NOT_RUN.
Complete this phase, report exact qualification and ask once before ANALOG-MEAS-01.

## STORAGE-MGMT-01 activation, 2026-10-06

The user says continue after planning PR #116. Starting main is
`2797d60cbd4c254cd753527b8542cdae27c1b10a`. Activate this one implementation phase;
the scheduling-only language below is preserved history. Implement registered
inventory/classification, summary/pagination, exact cleanup plan, dry-run and
independently user-selected operator consent for one isolated intermediate leaf.
All historical results default to replay/evidence protection; source/ADE/PDK,
ledgers/admissions/journals and prior evidence remain protected. No actual historical
or synthetic reference-host deletion is currently selected by the user.

Reuse locks, budgets and transport; keep 10 GiB/500 counters and removed elapsed
ceiling. Verify static/full/security/dependency/distribution/protocol gates and
bounded real-host inventory/plan/dry-run, preserving old schemas/results and
fingerprints. Record absent deletion E2E honestly. Integrate one feature PR under
existing delegation and ask once before ANALOG-MEAS-01. Workflow:
[simulation storage](SIMULATION_STORAGE_V1.md). Advanced compaction stays deferred.

Current checkpoint: [STORAGE_MGMT_01_CHECKPOINT_V1.md](STORAGE_MGMT_01_CHECKPOINT_V1.md).
Later fourth-correction qualification supersedes the pending-deployment checkpoint
below: immutable v2 deploy, actual SDK inventory/plan/dry-run, prior-result and
protection regression pass. Final full-unit gate has 1,622 passes/four OS skips;
static/security/dependency/distribution gates pass. Actual inventory reaches the
64-artifact limit before later registered groups: coverage is PARTIAL and all
bytes are lower bounds. A fifth correction for bounded group aggregation is
requested and pending. Draft PR #117 preserves the reviewed checkpoint; do not
merge until that acceptance gap is resolved. Actual deletion remains NOT_RUN.

Earlier pre-fourth-correction observations, retained for failure provenance:
Local full-unit verification completed with 1,621 passes and one existing backend
method-inventory expectation needing the two new typed methods. Initial curated
distribution/install verification passed. Exact old schemas/results and protected
evidence regression passed. Deployment stopped before activation because guest
worker/shell bytes had CRLF; the failed stage and transcripts remain preserved.
The original three corrections are consumed. A separately requested fourth
correction is pending explicit user approval; general continuation does not reset
that limit. No completed-phase, real inventory or real deletion PASS is claimed.


## Storage-management scheduling directive, 2026-10-05

GENERIC-SWEEP-INTEGRATION-01 is complete and merged as #115 at main
`3f7bd81131e40f7781351b18e7ec824f362a5ef7`. Preserve that completed phase.
The user's new directive schedules **STORAGE-MGMT-01 before ANALOG-MEAS-01**,
then SPEC-CONTRACT-01. See [audited implementation plan](STORAGE_MANAGEMENT_PLAN_V1.md).
This overlay records program authority and concrete dependencies; storage MCP
implementation remains PLANNED, with one major-phase activation choice at this
boundary. The earlier ANALOG-MEAS-01 recommendation below is historical.

Existing operator cleanup is fixed/dry-run-only and is not dependency-aware.
Implement inventory/classification/summary and exact hash-bound cleanup plans;
selected deletion additionally requires explicit user intent and an operator-owned
approval record for exact plan/items. General development autonomy never grants
historical-result deletion. Unknown, active, replay/evidence-required artifacts,
ledgers/journals and protected objects fail closed. Do not make legacy 30-day
candidates deletable by age. Do not refund consumed reservations after deletion.

Keep 10 GiB/500 attempts, existing locks/disk floor and removed elapsed ceiling.
No new simulation, deployment, data deletion or compaction occurs in this planning
change. STORAGE-COMPACT-01 remains separate. Complete the planning feature PR,
report the proposed implementation boundary, and ask once before implementation.


## GENERIC-SWEEP-INTEGRATION-01 overlay, 2026-10-05

The user selects lifecycle integration after merged #114, starting main
`e8e5ebdf4628844c8726d8d38b051d5ccd890efc`. Preserve completed planning.
Registry v5 adds an exact compiled passive RC fixture analysis/completion reader;
reuse all v4 native validations and all existing sweep lifecycle/identity/guards.
Add prepare/submit/status/result/cancel around the existing engine and persist
hash-bound registered admission in the same operator sweep journal. No second
engine, arbitrary bindings or physical amplifier ranges. Bias ranges remain
unqualified; VDD=1 V is fixed. Reuse preserved fixture/native results, no new
simulation. Three corrections for this integration; prior histories remain.
The user's subsequent explicit result-budget instruction raises cumulative
reservation to 10 GiB through PHASE_RESULT_LIMIT_V4.json, retaining 62 attempts
and 7,114,588,160 reserved bytes. Deploy new immutable native-v3/sweep-v2
adapters with the same replay/ledger domains, 500 attempts, unchanged disk floor,
EDA lock and absent elapsed ceiling. Historical versioned policies/bytes remain.
Complete local/security/distribution/protocol and bounded read-only remote
qualification, reviewed feature PR and exact remote verification. Next phase:
ANALOG-MEAS-01, then SPEC-CONTRACT-01; ask once at phase completion. Other
Cadence versions/PDK execution are deferred and are not prerequisites here.
Claude desktop/rights review remain separate release prerequisites; no release.

The initial three corrections and all failed transcripts are preserved. The user
subsequently explicitly adds one correction for this phase: standard submit/cancel
MCP annotations and canonical JSON UUID handling discovered by full/protocol
verification. The four-correction bound is private hash-bound; it does not reset
old histories or automatically carry into future phases. Focused 51 and actual
SDK preserved fixture/native/restart equality pass after that correction.
Final full unit gate: 1,574 passes / three OS symlink skips / 57 warnings;
Ruff, mypy (37 modules), security/dependency and audited installed-package
gates pass. Integration uses feature PR #115; exact remote main verification is
retained in the private completion checkpoint, without an extra state-sync PR.

## GENERIC-SWEEP-01 preparation overlay, 2026-10-05

The user selects the recommended registered 1D contract/planning phase after
merged #113, starting main `13e17f8f8604737a901aeaa5c6d907efc1996a63`.
Reuse registry v4 variable reviews/analyses/measurements and the 16-point bound.
Add two closed read-only tools for description and hash-bound exact decimal
plans. Require every non-axis fixed value; no defaults or guessed range.
Report local numeric eligibility separately from execution; all points remain
NOT_RUN. Fixed native analysis compatibility is not a parameterized adapter.
No generic submission, reservation, durable admission/cancellation, new simulation,
remote deployment or FS circuit work is activated. Legacy fixture lifecycle is
preserved. Three corrections for this change; prior correction histories,
counters, protected objects and removed elapsed ceiling remain. Verify canonical
local/security/dependency/package gates, full old schemas and preserved native
measurement/restart regression with fresh protection/accounting. Integrate one
reviewed feature PR, report scope/limitations and ask once before another phase.

Final gates: 1,534 unit passes / three OS skips / 56 historical warnings and one
cache warning; focused 76 / one cache warning; security 18 / one cache warning;
Ruff/mypy 34 modules, strict dependency and isolated package gates pass. Actual
exported-config stdio preserves 51 full schemas, three native measurements and
restart identity, while new plans stay NOT_RUN. All four registry schemas,
protected/accounting objects and journal bytes are unchanged. Two corrections:
typing/JSON arrays, then Windows temporary-package DLL isolation. Failed/partial
transcripts are retained. The initial shared-DLL temporary folder was removed
after source tests ended; final build also used UV_LINK_MODE=copy. Recommend
GENERIC-EXEC-PREP-01 physical binding preparation, subject to one user choice;
no next phase or unqualified physical sweep execution is activated.

## GENERIC-MEAS-01 overlay, 2026-10-05

The user proceeds after RELEASE-LICENSE-01 merged as #112. Starting main:
`a776ec0230ac32f8a2eee2fb99ebd1884c2f1726`. Complete one phase: operator design
registry v4 hash-bound measurement definitions, three closed read-only MCP tools
and projections of already validated native DC scalars/AC transfer spectrum/TRAN
summary. Preserve v1/v2/v3 registry schemas and existing analysis plan/admission
identities. No arbitrary formula/signal/path, new reader execution, broader PDK,
electrical range or invented scientific target. PDK/native admission remains
required; spec_evaluation is not_evaluated. No new simulation, reservation,
deployment, FS circuit work, release or rights remediation. Keep every old
ledger, evidence/correction history and the removed elapsed ceiling.
This change has three corrections. Verify local/security/dependency/package
gates, actual stdio measurement/result/restart equality against completed jobs,
unchanged legacy schemas and fresh protected/accounting checks. Complete the
dedicated reviewed feature PR, report results/limits and ask once before another
major phase. Imported planning rights and desktop qualification remain separate
public-release prerequisites.

## RELEASE-LICENSE-01 overlay, 2026-10-05

The user selected Apache License 2.0 for original bridge code after merged #111.
Starting main: `19f8bfb95661f30fd2458d019b3cc9fe6857ea75`. Audit tracked contents,
local reachable history, external material/dependencies and actual distributions;
add canonical LICENSE, conservative project-owner NOTICE, scope/third-party
notice, modern SPDX metadata and an exact curated package-content gate. Preserve
imported `docs/agent_plan/` and history; its rights remain LEGAL_REVIEW_REQUIRED
and it is excluded from wheel/sdist. Do not extend the Apache grant to external
Cadence, PDK, clients or dependencies. No simulation, reservation, deployment,
release/tag publication, destructive remediation or new scientific target.
Retain existing ledgers, correction histories, elapsed-limit removal and safety.
Complete local/security/dependency/package gates, reuse sealed native evidence
with fresh protected/accounting checks, review and integrate the feature PR.
Report CONDITIONALLY_READY scope/limits, then ask once before another phase.
See [audit](LICENSING_AUDIT_V1.md) and [result](RELEASE_LICENSE_01_RESULT_V1.md).

## CLIENT-COMPAT-01 overlay, 2026-10-05

The user's multi-client directive extends the same onboarding program. PR #110
is merged; starting main is `28d5313cbacbde2cdc3aba1389548d4c2e1115bb`.
Environment/design/variable/analysis/PDK/onboarding foundations permit selecting
one client compatibility phase now. Licensing/publication remains pending and
is independent of this implementation. Audit client references and all 48 tool
contracts, preserve Codex registration, reuse the JSON exporter for Claude,
make sweep journal location operator configurable without moving/resetting
existing state, verify stdio using an independent JSON-RPC client and installed
SDK clients, and reuse completed native results with fresh integrity checks.
Desktop application execution is separately qualified only when observable.
Do not equate exported configuration or SDK tests with actual desktop E2E.
Investigate MCPB only; no bundle/publication/remote endpoint. No new simulation,
result reservation, remote deployment or FS work. Existing cumulative limits,
removed elapsed ceiling and old histories remain binding; three corrections
for this change. Complete reviewed feature PR integration, report precise
matrix/evidence/limitations, then ask once before another major phase.
See [compatibility](CLIENT_COMPATIBILITY_V1.md).
Local full regression passes: 1,458 passes / three OS skips / 56 existing
warnings; focused 51 / one OS skip; security 18, Ruff/mypy and installed-wheel
stdio pass. Preserved native DC/AC/TRAN and restart lookup are equal through
both exported settings, with fresh protected/accounting checks. Real desktop
qualification remains unverified and is documented separately. Recommend
GENERIC-MEAS-01 around existing extraction evidence while actual desktop
qualification remains a public-candidate prerequisite; no next phase is activated.

## PUBLIC-RELEASE-01 overlay, 2026-10-05

The user explicitly proceeds with readiness review after merged PR #109.
Starting main: `fff725cdf64d084d7c55ab30d5a38da15f33fb49`. Audit actual tag/release,
version, 22-tool legacy compatibility, 48-tool current inventory, installation
and licensing. Extend the existing package gate to installed-wheel local CLI
and actual stdio for both exported formats, preventing source-import false passes.
Keep source/runtime/lock version 1.0.0, historical v1 notes and published release
unchanged. A proposed semver and candidate notes are not a publication grant.
Owner licensing is a meaningful unresolved decision; ordinary inspection, local
fixes/tests and feature PR integration continue autonomously within this phase.
Reuse native E2E evidence only after exact production-byte identity checks;
record fresh protection/accounting. No new simulation/reservation/deployment,
FS work or scientific target is needed. Existing ledgers, correction histories
and absent elapsed ceiling remain binding; this new code change has three
corrections. Finish assessment, implementation/gates and reviewed feature PR,
report residual publication gates and ask once before another major phase.
See [readiness](RELEASE_READINESS_V1.md) and [result](PUBLIC_RELEASE_01_RESULT_V1.md).
Final local gates pass: 1,453 unit passes / three OS skips / 56 existing
warnings, 43 focused passes / one OS skip, Ruff/mypy/security/dependency and
actual installed-package stdio. One correction of three used. Protected objects,
job trees/counter, runtime bytes/prior hashes and old tag/release are unchanged.
Licensing choice remains pending; finish preparation PR and stop for that choice.

## ONBOARD-CLI-01 overlay, 2026-10-05

The user explicitly proceeds after completed PDK-ADAPTER-01 (merged PR #108).
Starting main: `730e5bcc7bcb718433d04db00658cef65fadfcbd`. Complete one phase:
join existing environment/design/PDK contracts in operator `verify`, optional
explicit existing bounded remote preflight, and private reviewable client-config
export with persisted registry/journal settings and retained platform approvals.
Improve local doctor registry validation; provide coherent fictional examples
without changing historical examples/schemas. MCP tool count remains 48.
No new execution routing, simulation/reservation/deployment or FS work is needed.
Preserve cumulative ledgers, prior correction histories and absent elapsed ceiling.
This new code change has the usual three-correction limit; the prior PDK extra
allowance does not carry forward. Run local/security/package gates, actual stdio
from exported configuration and preserved-result regression with fresh guards.
Complete dedicated feature PR review/integration, report and ask once before
another major phase. See [workflow](ONBOARDING_CLI_V1.md) and
[result](ONBOARD_CLI_01_RESULT_V1.md).
Final gates pass: 1,453 unit passes, three OS symlink skips and 56 existing
warnings; 136 focused passes, Ruff/mypy, security/dependency and package gates.
Actual exported-config stdio preserves three native results/restarts; fresh
guards/accounting are unchanged. Corrections used: 3/3; failures remain private.
Complete containing feature PR integration and ask once before another phase.

## PDK-ADAPTER-01 overlay, 2026-10-05

The user explicitly proceeds after the PDK adapter proposal. Start from main
`e8c451b6c64fba264a50979bc25563e865f432e2` (PR #107). Implement one phase:
versioned logical PDK runtime contracts, operator registry, closed inspection
and registered-analysis capability resolution. Preserve historical WP-15 files,
reference native behavior and admission identities. No proprietary mappings,
arbitrary execution, FS change, new simulation/reservation or deployment is needed.
Run local/security/package gates and sealed actual stdio preserved-result replay
with fresh integrity/accounting checks. Preserve all budgets/correction histories;
elapsed ceiling remains absent. Complete feature PR integration, report and ask
once before another phase. See [workflow](PDK_ADAPTER_RUNTIME_V2.md) and
[result](PDK_ADAPTER_01_RESULT_V1.md).

The first checkpoint stopped after three corrections with two stale test counts.
The user then explicitly allowed one additional correction for this phase: both
counts 45 → 48 and required validation/review/integration. Keep the original
three-correction audit, failed transcripts and blocked checkpoint immutable; the
new private delegation binds this extra allowance. General policy and prior
phase budgets are not changed. Final gates pass: 1,416 unit passes, two OS
symlink skips and 56 existing warnings; resumed focused gate has 290 passes.
Preserved sealed stdio E2E uses identical production bytes; fresh postflight
verifies protected objects, job trees and accounting unchanged.
Complete exact feature review/integration, report, then ask once before ONBOARD-CLI-01.

## GENERIC-SIM-01 overlay, 2026-10-05

The user explicitly proceeds after the registered analysis API proposal.
Starting main is `962f6ca3db9381cbab3174f4ed8fbd3974a4efcd` (merged PR #106).
Implement one bounded phase: registry v3 compiled analysis adapters, six closed
MCP lifecycle interfaces and durable local admission identity, preserving v1/v2
and legacy execution. The first adapter reuses fixed native reference DC/AC/
trap TRAN; unqualified designs and parameterized inputs stay blocked. Generic
environment preflight and PDK/scientific qualification are not bypassed.
Native active cancellation lacks a qualified route and is reported unsupported.

Verify code/security/package gates and actual stdio with completed DC/AC/TRAN
IDs only, durable restart lookup and fresh protection/accounting checks. No new
simulation, reservation, remote deployment, FS change or numerical target is
needed. Preserve candidate/constraint semantics, private evidence, all budgets
and correction histories; removed elapsed ceiling stays absent. See
[workflow](GENERIC_ANALYSIS_V1.md) and [result](GENERIC_SIM_01_RESULT_V1.md).
Complete feature PR review/integration, report and ask once before another
major phase. This overlay does not automatically activate a next phase.

## GENERIC-VAR-01 overlay, 2026-10-05

The user explicitly proceeds after the variable-phase proposal. Starting main
is `cf541f4e7fa42f3c2329f58401161b571de92309` (merged PR #105).
Implement one bounded phase: operator registry v2 variable contracts, separate
hash-bound numeric reviews, local MCP inspection/checking, v1 compatibility,
tests/documentation and permitted feature PR integration. Existing settings and
execution routes are retained; no simulation, result reservation, deployment or
FS modification is needed. Reference bias ranges stay unqualified; 320/702 mV
are candidates and VDD=1 V is a fixed constraint. No target is invented.

See [workflow](GENERIC_VARIABLES_V1.md) and
[result](GENERIC_VAR_01_RESULT_V1.md). Preserve private source/PDK/history and
all cumulative counters/correction histories; elapsed remains unbounded.
Report this complete phase and ask once before GENERIC-SIM-01 or another phase.
This overlay does not automatically activate the next major phase.

## GENERIC-DESIGN-01 overlay, 2026-10-05

The user explicitly selects registered design profiles as the next one major
phase, starting from main `3d41404096a894d2fac0f9fe829a31af12ff4623`,
merged PR #104. Implement a versioned bounded local operator registry and
two read-only MCP introspection tools. Represent the reference amplifier,
preserve existing execution routes, and separate registration from environment,
PDK, variable-range and generic execution qualification. No scientific range,
target or new simulation is needed. Keep private bindings and all prior FS
evidence protected; do not restart FS circuit changes.

Complete local/security/package gates, actual subprocess introspection and
preserved native result/replay regression, documentation and the dedicated
feature PR under the existing autonomy policy. Report and ask once before
GENERIC-VAR-01 or another major phase. See
[contract/workflow](GENERIC_DESIGN_V1.md) and
[result](GENERIC_DESIGN_01_RESULT_V1.md). Existing elapsed-limit removal,
cumulative budgets, correction histories and protection boundaries remain.

## GENERIC-ENV-01 overlay, 2026-10-05

The user's NEXT PHASE MASTER PROMPT selects one foundational phase of
GENERIC-USER-ONBOARDING. The fresh starting main is
`407cc401e5027070a54da190537e1b7d91e80a11` (PR #103). Implement operator-owned
environment contracts and fixed preflight around the existing execution layer.
This phase does not restart completed WP/circuit work or activate another FS
circuit modification. [The bounded program plan](GENERIC_USER_ONBOARDING_PLAN_V1.md)
records the decomposition; [the result](GENERIC_ENV_01_RESULT_V1.md) records
verification and limits.

Complete local gates, permitted bounded deployment/E2E and dedicated feature PR
integration under the existing autonomous policy, then report and ask once
before GENERIC-DESIGN-01. No chained next phase is authorized by this overlay.
Elapsed remains unbounded; all existing cumulative resource/correction histories
and original/PDK/evidence protections remain. Environment descriptions and
qualification never reset or activate runtime ledgers or grant analysis authority.

## AUTO-PHASE-01 active overlay, 2026-09-29

The user's explicit bounded delegation replaces this plan's project-level STOP,
per-read and per-PR approval gates for future in-scope operations. See
`policy/PHASE_AUTONOMY_V1.md` and `policy/PHASE_CAMPAIGN_V1.json`. The older
restrictions below describe the pre-transition phase and remain historical for
legacy records. A new implementation or remote operation still needs actual
capability, fresh evidence, integrity, budget, replay, and environmental checks.
WP-14 is the current circuit task; PR #57 and WP-15/WP-16 are complete and are
not repeated. The 2026-09-30 WP14-CLOSEOUT records completed work-copy
characterization with no numerical specification evaluation in
`WP14_CLOSEOUT_RESULT_V1.md`. The original source/ADE scientific baseline and
historical snapshot equivalence remain unverified. Stop after this closeout's
report and ask once before beginning the proposed `SIM-MCP-01` implementation.
The user subsequently selected SIM-MCP-01. Its fixed work-copy DC/AC MCP
implementation and real client E2E are recorded in `SIM_MCP_01_RESULT_V1.md`.
The user selected SWEEP-MCP-01. Its registered-fixture 1D implementation and
real three-point MCP E2E are recorded in `SWEEP_MCP_01_RESULT_V1.md`. The
historical circuit bias pairs are a coupled path; no one-axis actual-circuit
bias range or binding was approved or executed. Ask once before the next
ADE-QUAL-01 or narrow DESIGN-OPT-01 preparation phase.
The user selected ADE-QUAL-01 current source/ADE state netlist and analysis
validation. After the user's explicit three-correction renewal, its first native
DC bundle completed at observed 300/650 mV, NN, 27 C and VDD=1.0 V. Native
netlist conditions, one simulation and PSF scalar extraction were verified;
specification evaluation remains `not_evaluated`. Five of six corrections and
15 of 100 cumulative Spectre attempts are consumed. See `ADE_QUAL_01_RESULT_V1.md`.
Earlier failures and the private checkpoint remain preserved. Ask once before
another major phase; no subsequent phase is active.
The user subsequently selected native AC/TRAN qualification. Native AC, default
TRAN and a simulator-recommended trap TRAN comparison completed at the same
observed 300/650 mV conditions. The default ringing notice is preserved; the trap
run has zero notices. See `ADE_QUAL_NATIVE_AC_TRAN_RESULT_V1.md`. Three new
Spectre attempts bring cumulative use to 18 of 100. This new change consumed its
three corrections; the earlier DC change remains at five of six. Ask once before
the next major phase; no subsequent phase is active.
The user subsequently selected native comparison of the fixed 320/702 mV
candidate. `NATIVE-CANDIDATE-01` copies the original ADE state separately for DC,
AC and trap TRAN, changes only the two owned variable expressions, and verifies
the effective native input before each simulation. It reuses the completed
300/650 mV native results without rerunning them. VDD=1.0 V, NN, 27 C, the circuit,
stimulus, load, original/PDK/history protection and all cumulative budgets remain
bound. No numeric specification target or additional bias range is introduced.
The candidate native DC/AC/trap TRAN comparison is complete; see
`NATIVE_CANDIDATE_01_RESULT_V1.md`. Actual owned-state biases are 320/702 mV;
the original saved state remains 300/650 mV. The v1 AC simulation succeeded but
extraction failed; v2 reused its preserved PSF for extraction only and completed
TRAN. One of three candidate corrections is consumed. Previous native AC/TRAN
retains three-of-three consumed corrections and prior DC retains five of six.
Cumulative Spectre use is 21 of 100; specification remains `not_evaluated`.
The user selected NATIVE-MCP-01: integrate reusable fixed native DC/AC/trap TRAN
MCP submission, status, bounded result and contract listing. Reuse qualified guards,
protect prior evidence, enforce caller UUID4 replay identity and shared cumulative
budgets. Complete implementation, tests, bounded deployment, real MCP E2E and feature
PR review/merge without intermediate approval. No new voltage range, source promotion
or numerical target is introduced. Prior correction counters remain unchanged; this
new capability permits an initial deployment and at most three corrections. Ask once
before another major phase after reporting completion.
Its fixed DC/AC/trap TRAN tools passed actual subprocess stdio E2E; see
`NATIVE_MCP_01_RESULT_V1.md`. Same-ID replay consumes no extra attempt and wrong
analysis is rejected. Cumulative Spectre use is 24/100; one local transport
correction is consumed, with remote v1 assets unchanged. Protected references
remain intact, active EDA is zero, and specification remains `not_evaluated`.
Ask once before another major phase after reviewed feature PR integration.
The user selected `ADE-PVT-PREP-01` on 2026-10-04: protected reads of the actual
PDK corner/statistics definitions and installed execution support, fixed-code
tests and owned deployment, followed by reviewed feature PR integration. This
preparation includes no new circuit execution. The inventory is complete in
`ADE_PVT_PREP_01_RESULT_V1.md`: ten actual sections, MOS definition binding for
8/6 instances, mismatch declarations present, process declarations absent in the
inventoried graph, and installed help/API support observed. Effective statistical
variation, non-NN runtime corner behavior and statistical/corner license entitlement
remain unqualified. Three preparation corrections are consumed; all failed/partial
versions and prior counters remain preserved. Shared Spectre use is still 24/100.
Report this phase and ask once before the proposed `ADE-PVT-QUAL-01`; it is not active.
The user subsequently selected `ADE-PVT-QUAL-01`: reuse preserved NN evidence,
qualify FF/SS/FS/SF through native owned-state DC and AC at fixed 320/702 mV,
VDD=1.0 V and 27 C, with at most eight new Spectre attempts. Existing circuit,
VCM, load, stimulus and revision guards remain binding. No highPerf selection,
temperature/supply sweep, statistical execution or optimization is included.
Implementation, tests, managed deployment and reviewed feature PR integration
are delegated without intermediate approval. Preserve all prior correction
histories and cumulative limits; the removed elapsed ceiling remains absent.
Report this phase and ask once before another major phase, then stop.
All eight fixed FF/SS/FS/SF native DC/AC jobs completed; see
`ADE_PVT_QUAL_01_RESULT_V1.md`. Cumulative Spectre use is 32/100 and specification
evaluation remains `not_evaluated`. FF/FS gain reduction is an observed result,
not a simulator failure or an established device-level cause. Original/PDK and
prior NN evidence are unchanged. Ask once before `ADE-PVT-DIAG-01` or another
major phase; no subsequent phase is activated by this characterization.
The user selected `ADE-PVT-DIAG-01`: read preserved MOS operating points to
investigate FF/FS gain loss without new simulation, bias change or optimization.
All 700 fields across five corners were read and source/PDK/prior-job integrity
verified. Saved input and output PMOS headroom and conductance changes explain
the two-stage gain collapse; independent local MOS linearizations corroborate
the prior 10-Hz AC gains. See `ADE_PVT_DIAG_01_RESULT_V1.md` for the numerical
evidence and approximation limits. One of three diagnostic corrections is
consumed with the failed v1 preserved. Shared Spectre use remains 32/100;
specification evaluation remains `not_evaluated`. Complete reviewed feature
integration, report and ask once before a new bias/headroom planning phase.
No new range, circuit run or subsequent phase is activated here.
The user subsequently selected a bounded bias/headroom improvement phase and
raised cumulative Spectre attempts to 500. `PHASE_SPECTRE_LIMIT_V3.json` and
`NATIVE_MCP_V2.json` bind the active budget implementation. Preserve prior usage,
the 5 GiB results ceiling, all correction histories and the removed elapsed limit.
The private bound `BIAS_HEADROOM_PLAN_V1` record proposes only 300/702, 320/650, 300/650 and
310/676 mV, using observed saved/qualified endpoints rather than a PDK rating.
`BIAS_HEADROOM_RUN_V2.json` activates the selected finite validation: eight FF/FS
DC screens, then three remaining-corner DC and five AC jobs only for the measured
eligible candidate, at most sixteen new Spectre attempts. VDD=1 V, 27 C, VCM,
topology, stimulus and load remain verified at execution; no numeric spec target,
automatic range expansion or original-state promotion is introduced. The first
v1 computation is reused after a preserved reader failure and exact extraction
script reconstruction; v1 submissions are retired. The v2 adapter adds write
containment and avoids guard-module reloads during extraction. Record actual
results and residual limitations in `BIAS_HEADROOM_01_RESULT_V1.md`, complete
reviewed feature PR integration, then ask once before another major phase.
The transition was integrated through PR #58. Subsequent bounded observations
and copied-revision tests are reconciled in the closeout report. Candidate
biases remain 320/702 mV; VDD=1.0 V is a hard constraint. The observed VCM,
load scope, revision, and applied values are specific to the cited evidence,
not assumed for a future live design.

## Authority and boundary

This is the only active phase plan after the `v1.0.0` release baseline. The complete long-term
direction is recorded in `docs/AUTONOMOUS_CADENCE_MCP_FULL_ROADMAP.md`, but that roadmap is not an
execution instruction. An execution reads only the roadmap sections needed for its active WP.

The Git, security, approval, testing, completion-report, and STOP rules in
`CODEX_MASTER_PROMPT.md` remain binding. WP-00 through WP-11 are completed v1 history and must not
be reopened or treated as incomplete. Existing evidence from later exploratory branches remains
historical evidence and is not authority to perform a new mutation.

## Agent-plan integration overlay

The reviewed prompt package is available under `docs/agent_plan/` as a planning reference. Its
work-package IDs use the independent `ICF-*` namespace and do not renumber, reopen, or supersede
the repository's existing `WP-*` history. `docs/agent_plan/WORK_ID_MAP.md` is the required
crosswalk; mappings are evidence references, not automatic completion claims or execution
authority. The imported package templates and archive references are inactive by default.

The user explicitly selected **WP-16 — ADE and Sweep Capability Inventory** after PR #54
integrated the repository-only WP-15 design as
`239b1fc7e4fd0d59e1e17d089d2a16d16856dc13`. WP-13's audit was merged through PR #19 as
`b12cff904fe31a1d68490836c1fe6765734b9bf0`. WP-16's repository-only inventory
was merged through PR #55 as `b2239f5743034aa019d33dd29f6c1e4da230d17e`;
the active intent/fact/approval interaction rule was merged through PR #56 as
`85706385cfb82b60d829f44c1ac197339eebbafd`. WP-14 remains blocked: its
scientific baseline and fresh remote evidence are unconfirmed. A separately
approved one-time renewal local preflight returned `LOCAL_PREFLIGHT_READY` on
2026-09-29; it established only local prerequisites at that instant, not remote
or circuit facts. See `docs/WP16_ADE_SWEEP_CAPABILITY_INVENTORY_V1.md` and
`docs/interaction/GOALS_FACTS_AND_APPROVALS.md`. No unscoped remote probe,
parameterized execution, sweep, or WP-14 baseline promotion follows from these
merges or the local result. Other `ICF-*` tasks remain planning references, not
execution instructions.

## Phase objective

Reconcile the post-release repository and security truth, establish an authoritative read-only
actual ADE baseline, resolve the `VBIASN`/`VBIASP` source of truth, design a technology-neutral PDK
abstraction, and inventory legacy ADE/sweep capabilities before any parameterized implementation.

## Work packages

| WP | Scope | Required outcome | Mutation boundary |
|---|---|---|---|
| WP-12 — Roadmap Integration | Preserve the v1 contract, integrate the long-term roadmap, reconcile governance metadata, and establish this bounded phase. | Documentation authority is unambiguous and repository/security state is recorded. | Repository documentation only. |
| WP-13 — Actual ADE Profile Baseline and Capability Audit | Audit the approved actual profile, ADE state, source snapshot, fingerprints, freshness, and available read-only introspection paths. | A bounded evidence report identifies facts, drift, and unknowns without choosing values by inference. | Read-only; no runner deployment, simulation, OA save, ADE state change, or PDK/work-library write without a new explicit contract. |
| WP-14 — VBIASN/VBIASP Source-of-Truth Confirmation | Reconcile repository defaults, ADE state, source snapshot, prior evidence, and explicit user choice. | One versioned, user-approved baseline contract or a documented blocker. | No parameterized execution or sweep. |
| WP-15 — PDK Abstraction Design | Define a technology-adapter schema for devices, parameters, models, corners, layers, verification backends, and protected source-of-truth metadata. | Repository-only design and threat model with gpdk090 as a regression adapter and no proprietary PDK content. | Documentation/schema design only unless a later WP explicitly authorizes code. |
| WP-16 — ADE and Sweep Capability Inventory | Inventory IC6.1.5/ADE L/Spectre capabilities, fixed APIs, extraction paths, budgets, and fail-closed gaps required before implementation. | A capability matrix and implementation prerequisites for a later phase. | Read-only probes only when separately scoped and approved; no sweep or mutation. |

## Phase acceptance gates

The 2026-09-17 user-approved visibility policy is PUBLIC. WP-14 version-2 request
packages supersede only the active private-visibility prerequisite and related hash
bindings; version-1 packages and v1 release history remain preserved. Public operation
does not authorize transport or publication of fresh evidence. Exact evidence fields
require local publication review. Deployment remains disabled and existing operation,
data-protection, single-use, testing and Git approval controls remain mandatory.

- Repository visibility, release baseline, branch policy, and protected-data policy agree across
  GitHub metadata and repository documents.
- The actual ADE profile baseline is supported by bounded, reproducible evidence.
- `VBIASN` and `VBIASP` are never selected from conflicting evidence without explicit user
  confirmation.
- The PDK abstraction contains no proprietary model, rule deck, raw netlist, or guessed MyChip
  identifiers.
- ADE/sweep implementation remains disabled until the capability inventory and input contracts are
  complete.
- Each WP uses a dedicated feature branch from the latest approved `origin/main`, passes its
  acceptance checks, updates `PROJECT_STATE.md`, pushes only that feature branch, verifies its
  remote SHA, and stops.

## Explicit exclusions

This phase does not authorize arbitrary shell, SSH, SKILL, OCEAN, file-path, netlist, or PDK access.
It does not authorize remote runner deployment, Cadence execution, OA/database writes, ADE-state
changes, schematic/layout changes, work-library mutation, sweep execution, repository visibility
changes, direct `main` pushes, force-push, or automatic merge. Any such action needs a later exact
WP contract and any required separate user approval.

## Phase exit

The phase may advance to ADE/sweep implementation only after WP-13 through WP-16 are integrated and
all unresolved baseline, capability, approval, and proprietary-data questions are recorded. The
WP-14 blocker remains recorded even though the user explicitly selected the
repository-only WP-15 and WP-16 checkpoints. Neither selection authorizes WP-14
execution or satisfies phase exit. WP-16 must not start automatically after WP-15
is pushed or merged; this inventory follows a new explicit user request.
The older numbered implementation sequence in
`docs/NEXT_VERSION_SCOPE.md` is historical and cannot override this plan.
