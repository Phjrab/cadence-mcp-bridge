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
- Exact final installed wheel: three SDK configuration formats/all85 schemas,
  two operator contexts1→2→1 and setup-required/default isolation PASS. Fixed
  bundle/export/install/repeat/verify/activate/deactivate/staging/fault acceptance
  PASS using only installed assets. Same-version reinstall and uninstall retained
  exact19 synthetic operator-state file hashes; package import absent afterward.
  Bootstrap preservation verifier is subsequent GREL07 independent test tooling,
  not an additional GREL02 runtime dependency. This is not semver/native upgrade.
- Security18 PASS and strict locked dependency audit: no known vulnerabilities.
- Interim suite:2317 PASS/7 OS skips/56 warnings, before exact preflight additions.
- Exact suite initially2317 PASS/2 FAIL/7 OS skips; long explicit pytest base
  caused per-item synthetic audit path271 characters (Windows file-open rejection).
  A separate renamed-handle fixture improvement passed25 tests/one OS skip, but
  did not resolve this long-path invocation. Both failures and diagnostic retained.
  Final short exclusive system-temp full invocation:2319 PASS/7 OS symlink
  SKIP/56 warnings in790.75s. Exact source/unit input hashes unchanged before/after.
  No production storage protection was weakened.
- Final curated wheel/sdist: d0fdab1fc4eed13f7b09f61693618fa01eeaac5c7deecd28316ed14070d8b7ae /
  18764aebd63918a72a6ad9b9eedf8347d015142d5b1c190d4e345bf3b29855eb;
 74/75 members, Apache-2.0/notices/source match, no unexpected/protected patterns.
- Primary code/diff review completed; this is not independent review.
  Independent automatic review pending at PR143 ready transition. GREL02 branch
  has no hosted workflow; GREL07 subsequent branch supplies actual CI separately.

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

GREL02: local runner/bootstrap foundation implemented and locally verified; generic runner assets/
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

PR143 https://github.com/Phjrab/cadence-mcp-bridge/pull/143 is stacked on
feat/grel-01-runtime-context/PR142; neither merged. Tested source+test commit142e1b4
and later documentation receipts have equal source/test input snapshots.
Candidate wheel/sdist retain the exact SHA256 values above. Fresh storage read
again matches82/9,798,942,720 and snapshot1ff1794c7ff2d75b3aeed475d587a68e2d39bc5157a8704107397cc7610b09e2;
filesystem free25690324992/floorOK, registered logical/allocated totals unchanged.
The original checkout still contains only the preserved unrelated OCN edit.
Generic positive-native bootstrap gate remains BLOCKED; local PASS does not close it.

## Independent PR143 review correction

Automated review of ad63410 found P1 installation-target binding: standalone
install could accept a different owned TARGET. Native install now compares the
normalized target with the hash-verified profile managed_root before any write;
wrong-target tests prove an empty target stays empty. Windows CLI install is
explicit LOCAL_CONTENT_STAGING_ONLY, not a Linux installation, and the standalone
remote command offers no staging entry point. Staging helper refuses Linux.
Primary additional review hardens launcher/preflight runner directory ancestors
before reading/importing assets: directory type, current/root ownership and no
group/other write. No permission is changed. Both assets check the full chain.

Corrected focused runner/transport/context73 PASS/2 OS skips; Ruff/mypy66 PASS;
actual Python2.6 grammar4 assets PASS. The prior2319 full and d0fdab/18764a
artifacts above are historical tested candidates, not corrected-head receipts.
Corrected full/artifact/installed acceptance: PENDING_GREL02_REVIEW_FINAL.
Independent review of the corrected code remains pending. The initial P1 remains
visible in PR143; no approval or merge is inferred from our own fix.

Selected original private/history/local-change baseline:99964 files rehashed,
changed0. Original unrelated OCN edit retains its exact baseline bytes. This is
selected local preservation, not a complete scan of protected OA/PDK/remote VM.
