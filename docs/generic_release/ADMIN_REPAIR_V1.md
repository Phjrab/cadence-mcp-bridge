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
the shared EDA flock, and uses no-follow descriptor traversal. It removes only
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
actual operator authority. Rollback requires matching inode/owner/content and
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
