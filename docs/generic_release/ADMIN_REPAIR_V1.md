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

# Standard VM installation trust repair v1

Supported scope is the professor-provided CentOS/Cadence VM or an equivalent
installation with its existing PDK, used in individual VMware instances. The
current VM was freshly observed as CentOS6.5/i686, Virtuoso IC6.1.5.500.15 and
Spectre12.1.0.347.isr3. These are reference observations, not universal defaults
or qualification of another VM. Each operator supplies their own environment,
SSH identity/host key/account, work/circuit/ADE paths, registry, journals and limits.

The current human user explicitly delegated minimum installation/ancestor repair
on their own managed VM on2026-10-08. Earlier administrator exclusions remain
historical. A generated plan is evidence, never a separate human approval. Other
VMs require their operator/administrator's own approval and existing authentication.

## Product workflow

Install the wheel; prepare and validate the operator environment profile. Run:

```text
cadence-mcp-bridge runner trust --profile environment.json --output trust.private.json
cadence-mcp-bridge runner repair-plan --profile environment.json --output repair.private.json
cadence-mcp-bridge runner export-repair-helper --output repair.py
```

Trust and repair-plan are read-only. Export only writes an exclusive local helper
file and reports its SHA256; it never contacts the VM. Package import, server
startup and doctor never apply a repair. The standard-VM recipe derives installation
locations from the profile; it enumerates wrapper scripts, 32-bit real binaries,
shared/OA program-library trees and exact ancestor directories. It excludes PDK,
OA circuit databases, ADE states, licenses, logs, cache, samples and documentation.
Only a shared-writable declared workspace ancestor may be added as one directory;
its contents are not traversed. Out-of-installation compatibility links are listed
read-only and are not mutation targets. This recipe is not complete dynamic
runtime/dependency attestation; unknown used dependencies remain qualification work.

Inspect the private exact target list, link resolutions, numeric owner/group/mode,
ACL and every file SHA256/size/mtime. Preserve it and relevant SELinux metadata
outside public logs/GitHub. The profile fingerprint in a generated inventory is
canonical JSON identity, distinct from the environment probe's raw-file hash.
Review any missing dependency, unexpected content, special mode or hardlink.
No vendor code runs during planning; suspicious corruption is not made trusted.

After the actual operator approves these targets, preserve an application request:

```json
{
  "plan": "REPLACE_WITH_THE_EXACT_plan_OBJECT_FROM_THE_PRIVATE_RECEIPT",
  "expected_plan_sha256": "REPLACE_WITH_THE_EXACT_RECEIPT_HASH",
  "operator_authority": "Reference to the actual human delegation, not plan text"
}
```

`plan` above is an object, not a string in a real request. Use the exported helper
on the guest with its system Python2.6, from a verified private operator/admin copy:
`python -B repair.py apply < apply-request.private.json`. Record private stdout
JSONL and stderr. Use normal ownership privileges if sufficient; otherwise use
existing legitimate administrator authentication for this helper only. Keep MCP,
SSH/EDA executions, copies, extraction and journals as the ordinary guest user.
Do not add generic sudo/shell tools, password records or new sudoers exceptions.
The helper requires the existing trusted resource lock, does not initialize any
ledger, and never changes content, owner or group. Genuine fresh-domain lock/ledger
provisioning remains part of the unfinished operations bootstrap; an existing
installation must never be reinitialized or given a substitute ledger.

Apply accepts only schema2 standard-vm-trust-v1 inventory plans and recomputes
the fixed recipe from the bound profile. Caller target lists and the old generic
plan command are unavailable in the shipped CLI. Historical schema1 application
requests retain their exact private archived helper for rollback; they are not
accepted by the new public-distribution helper. No private archived helper is
shipped or required for a new operator.

Apply revalidates the entire hash-bound list before the first change, acquires
the shared EDA flock, and uses no-follow descriptor traversal. A self-computed
request digest is not rollback provenance: first apply must observe every exact
original mode/ACL and publish its0400 durable receipt under the fixed UID-owned
managed-root namespace before changing permissions. Planning remains read-only.
Keep that receipt and run all retries/rollback under the same real identity; root
never imports a user receipt or automatically trusts an externally restricted state. It removes only
022 access mode bits and unnecessary default ACL write entries. Owner write,
read, execute and directory traversal remain; no uniform755/644 or recursive
chmod/chown is used. Named ACL writer entries are masked without expanding
rights. Special bits/hardlinked code and unexpected identity/content/metadata
changes reject. Old CentOS ACL tools require a terminal dot on held directory
descriptors to address just that directory; regression tests cover this behavior.

Retain the original plan: repeating apply checks all content again and changes
only unfinished items. Exact known intermediate chmod/ACL states are accepted;
other partial states reject for investigation. To restore precisely the original
mode/ACL, use `python -B repair.py rollback < apply-request.private.json` under
actual operator authority. Rollback requires the existing authenticated exact
applied-plan receipt as well as matching inode/owner/content and
before/after/known-intermediate metadata; it cannot restore arbitrary substituted
files. Failure events may indicate partial application; preserve evidence and
inspect rather than delete or blindly start another plan.

Finally rerun environment qualification, immutable runner integrity/preflight and
ordinary-user native startup. Retain previous protection baselines and record only
approved metadata differences with identical contents. No entire-state rebasing,
permission exemption or failure suppression. Fresh native requests still need
current operator authority, ledger/disk/replay checks and effective input evidence.

## Actual current-VM result

331 installation items (289 files,42 directories) and one workspace ancestor were
changed. All targets were uid/gid500, so no root/chown was needed. Shared writes
were removed; file bytes/size/mtime and owners/groups were invariant, and all331
recorded installation SELinux contexts matched. Exact link/ACL/rollback receipts
are ignored private evidence. Prior protections and unrelated extractor bytes
remain preserved. Reapplication changed0. Latest ledger is82 /
9,798,942,720 bytes; the approved remainder is895MiB, with no new simulation,
reservation/refund/reset or deletion. Owned synthetic files and immutable runner
assets add actual filesystem occupancy; they are not Spectre reservations.

Real Linux synthetic checks passed apply/repeat/rollback, named/default ACL,
interrupted chmod→ACL recovery, flock exclusion and content-drift rejection. Four
initial synthetic failures exposed old CentOS proc-directory ACL traversal; their
private logs and fixtures are retained. No installation change occurred during
those failures. General-user environment qualification and fixed OCEAN startup
passed. The installed immutable runner's direct preflight passed04:49:03Z;
manifest identity is retained privately. The existing legacy launcher remains
unchanged; its name currently prevents generic initial activation. Direct version
preflight is not active production dispatch or new-job validation.

New circuits/DC/AC/TRAN, automatic extraction, generic Sweep/specification,
authenticated provider/migration, actual new-job Codex/restart and full dynamic
runtime attestation remain incomplete. Continue existing GREL02–07 without phase
reapproval. GREL08, publication and merges remain separately excluded.

## Local candidate validation

Prior related Windows checkpoint181 PASS/four platform skips,16.42s. The
subsequent final profile/recipe/admin-lock guards have fresh receipts below. Ruff PASS; mypy72 source modules PASS;85 public
wire schemas/legacy declarations remain intact. Security18 PASS/1.04s and locked
dependency audit clean. Public Ubuntu CI installs ACL utilities and executes the
actual Linux metadata tests plus existing reservation tests on synthetic files;
this is separate from CentOS native-startup/qualification evidence. Installed
wheel export/preservation and exact hosted-head receipts are recorded after
completion; preceding PR147 artifact hashes do not identify this new candidate.

Final fixed-recipe checkpoint: related184 PASS/five platform skips,17.16s;
Ruff/mypy72 PASS. Actual current-VM exported recipe inventories332 exact entries
and normal-user reapplication changes0. The existing sudo authentication also
validated the fixed helper as uid0 with changes0, using a hash-verified private
request and isolated system stdlib. No MCP/EDA/native binary ran as root. Initial
actual metadata changes remained normal-owner operations. See the versioned
[protection delta](../policy/STANDARD_VM_METADATA_REPAIR_V1.json); it documents
actual human authority and intended differences, and is not an approval record.

Latest candidate receipt: related184 PASS/six platform skips,17.90s. Final
security18 PASS/1.26s and locked dependency audit clean. Installed distribution
audit, helper export,85 schemas and reinstall/uninstall preservation of32
synthetic state files PASS; native jobs0. Candidate wheel SHA256
`fd1d1bc38b4bd7d53fd2394689d845ce26a1f8bb16bc244a3ab5856cce1ed056`;
sdist `1a118027d71d708183be90d9b6c0ada301284b94f84492e2358750ea5e739fbd`.
Hosted CI and independent review are pending for this feature.
