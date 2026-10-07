# GREL-02 runner/bootstrap checkpoint

The user explicitly authorized continuous GREL-02 through GREL-07, and use of
existing remaining895MiB. This supersedes phase-boundary questions for that range.
GREL-08, publication, budget increase, protected vendor permission changes and
old-result deletion remain excluded. Original checkout/OCN/history are preserved.

Baseline main553276d; parent feature3a1fdaa (PR142 review correction). PR142 is
unmerged. Current branch feat/grel-02-runner-bootstrap is a stacked feature.
The independent automated P2 review of PR142 was addressed by forcing explicit
serve to legacy_reference;40 targeted tests passed/one OS symlink skip. Later
full GREL-02 validation covers the corrected implementation.

## Implementation

The wheel contains original fixed Python2.6-compatible content installer,
launcher, preflight runner and metadata-only trust diagnostic, reusing the old
environment probe. Existing registry/PDK/85 wire schemas remain unchanged.
Installed CLI can export an exclusive private bundle/installer, install immutable
hash directories, verify exact bytes, and request an exact-manifest/fresh-nonce
preflight. Runner commands are identity/preflight only at this phase. No generic
shell/eval/script/host/path MCP is added; generic native execution is still absent.

Standalone activation rejects old launchers, incomplete/drifting versions and
active/unresolved markers. Deactivation appends a revocation while retaining
versions/pointer history. Existing active-pointer replacement is denied pending
reviewed lifecycle migration. Content installation is not environment trust,
license entitlement, analysis qualification, physical ledger provisioning or
execution authority. Install/verify outputs always execution_authorized=false.

The bounded internal transport checks both streams concurrently, deadline and
request bytes, killing only its own SSH/synthetic child on limit or timeout.
CLI failures carry closed codes and next actions; private executable/ancestor
paths only enter an exclusive local operator diagnostic file.

Artifact-only instructions are in README (included in sdist), and every needed
content/preflight/diagnostic asset is package source data. The private profile and
bundle stay operator-owned; public artifacts contain no Cadence/PDK/netlist data.
Generic ADE/native templates are a later GREL-04 requirement, not claimed here.

## Evidence, 2026-10-08 KST

- Final focused runner/transport/context/CLI/onboarding:98 PASS/3 OS symlink SKIP.
- Ruff src/scripts/tests PASS; mypy66 source files PASS.
- Actual VM Python2.6 grammar:four shipped standalone assets PASS after normalizing
  CRLF for ast.parse. This is grammar-only; no asset install or native execution.
  The initial CRLF string-parser failure remains in ignored .tmp evidence.
- Installer faults: wrong/rehashed content, extra/duplicate/linked/hardlinked
  files, incomplete install, active marker, old launcher collision and exact
  repetition/append-only deactivation tested synthetically.
- Transport stdout/stderr flood/deadline cases PASS after correcting readiness
  handling; the two intermediate synthetic failures are retained.
- Interim installed wheel: exact85 schema/2 context1→2→1 restart PASS. Exact final
  candidate package verification and full suite are recorded below when complete.
- Full final source suite: PENDING_FINAL_GREL02_UNIT.
- Final curated wheel/sdist: d0fdab1fc4eed13f7b09f61693618fa01eeaac5c7deecd28316ed14070d8b7ae /
  18764aebd63918a72a6ad9b9eedf8347d015142d5b1c190d4e345bf3b29855eb;
 74/75 members, Apache-2.0/notices/source match, no unexpected/protected patterns.
- Independent review of GREL02 candidate/hosted CI: NOT_RUN at checkpoint.

## Actual native blocker and resources

The registered VM was off. Starting the same VM in the background restored SSH;
VMnet8/NAT/DHCP remained configured. A fresh existing environment qualification
still rejects executable_permissions. Metadata diagnosis finds group/other writes
in5 Virtuoso and6 each OCEAN/Spectre executable/ancestor components (shared paths
count more than once). Modes include777 and775. No wrapper exception or permission
check weakening is applied. The private diagnosis records exact existing paths,
UID/GID/modes; administrator investigation must include dependent code, not just
launchers. Protected/vendor permissions, owner, license and source contents have
not been changed. A verified safe installation/admin action is required for G03.

Fresh bounded storage observation:82 attempts;9,798,942,720 reserved bytes against
10,737,418,240. Remaining938,475,520 =895MiB, allowing six128MiB slots plus127MiB.
User approval permits that existing remainder, not a higher ceiling or refund.
Registered roots18030073 logical/48308224 allocated bytes; filesystem free
25690456064, floor6238251418, statusOK. Registered inventory scope is not all VM
private state. This phase zero native simulations/reservations/deployments,
permission/license changes and result deletion. No approval/ledger was recreated.

## Continuous program status

GREL02: local runner/bootstrap foundation implemented; generic runner assets/
positive native trust gate not fully qualified (REMOTE_BLOCKED). G03 not complete.
GREL03: reusable authority/lifecycle integration next; remote execution depends
on the unchanged native trust gate and actual shared-ledger provisioning.
GREL04/05/06: new-circuit/native measurement/Sweep/clean-app execution NOT_RUN;
not replaced by synthetic fixtures or historical replay.
GREL07: independent synthetic CI/update/preservation work can proceed under the
existing continuous instruction while native prerequisites remain blocked.
GREL08/publication: NOT_AUTHORIZED. General release remains BLOCKED.

No next-phase approval is requested within the authorized02–07 range. Any actual
protected install repair, additional budget or exact deletion is a separate user
choice. The blocker is preserved while independently useful work continues.
