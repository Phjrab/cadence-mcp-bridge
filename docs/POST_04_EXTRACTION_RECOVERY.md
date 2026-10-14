# POST-04 extraction-only recovery (unpublished experimental development)

The installed operator CLI `operator-recovery` links a separately identified
extraction attempt to an original EXTRACTION_FAILED job. The original operation,
failure events, effective input, PSF and files remain read-only. The fixed worker
runs only OCEAN's registered reader and writes to a new job area. It has no netlist
or Spectre invocation. Existing operation/tool contracts remain unchanged; no new
public MCP tool or automatic recovery is installed.

## Qualification boundary

Host, isolated installed CLI and actual standard-VM extraction have distinct
evidence. Updated final hosted checks and independent review remain required. Do not call this feature generally qualified or part of the published
2.0.0 release. Submit requires `--experimental-recovery`, a hash-bound installed
runtime and an OS-operator-confirmed grant with `recover_extraction`. Import,
server startup, result lookup and ordinary retry never perform recovery.

The source must retain successful Spectre completion evidence: its EXTRACTING
event must match a newly verified effective input. Domain, environment, design,
PDK, analysis and all explicit values must match. Input overrides and static
statements are verified with the common renderer. Original metadata and contents
are pinned, including PSF; current sources/model/installation trust and scope are
rechecked under the shared EDA lock before admission. The fixed source-content
scan is bounded to64MiB/4096 entries; larger sources reject rather than weakening
the check. This is an explicit recovery limitation, not a simulation-size limit.

## Accounting and restart

Recovery uses the existing shared reservation ledger/domain and ordinary-user
flock. It reserves a declared bounded output amount and conservatively charges
one existing accounting attempt, even though Spectre starts0 times. This retains
the existing ledger's fixed +1 semantics; it does not refund the original failed
job, invent an extraction budget or reset a grant. Fresh disk-floor, cumulative
and grant ceilings still apply. Record purpose, original identity, expected output
reservation and stop criteria before a real recovery.

A new recovery ID is separate from the original. Admission and dispatch intent
are durable before fork. Identical-ID retries first look up the exact plan and
never redispatch after accepted, partial, failed or unknown outcomes. Uncertain
transport is not resent automatically. Restart/status/result do not reserve,
extract, netlist or simulate. Interrupted partial entries are retained and fail
closed. A later independent recovery requires its own explicit ID/plan/scope and
reservation; it cannot overwrite the old failure.

## Operator flow

Use your existing configured operator context, current registered analysis and
confirmed extraction-only grant. Preserve older spent grants and the shared
resource-state directory. Do not use a new journal to evade consumption. First
install/qualify the exact reviewed development runtime using the existing native
setup CLI. Historical pre-recovery bundles can be retained as an authenticated
update predecessor; every predecessor asset hash is still checked.

1. Prepare the same original design/analysis/explicit-values request with a small
   bounded recovery output reservation (for example8MiB when justified).
2. Run `operator-recovery plan --settings <private settings> --context <id>
   --request <private request> --original-operation-id <failed UUID>
   --original-plan-sha256 <retained digest> --output <new private plan>`.
   This reads source evidence but creates no remote admission or reservation.
   Keep the returned plan digest and exact plan file.
3. Submit using `operator-recovery submit --settings <private settings> --context
   <id> --plan <private plan> --expected-plan-sha256 <returned digest>
   --operation-id <new UUID> --experimental-recovery`.
4. Use `operator-recovery status` or `result` with the same settings, context,
   plan, digest and new UUID. Repeat submit with the exact identity only to
   reconcile acceptance; it does not rerun the worker.

The returned projected result retains operation/plan IDs and links the original
operation/plan. The original remains EXTRACTION_FAILED even if recovery succeeds.
OCEAN failures create a new linked EXTRACTION_FAILED history. Neither query nor
report generation turns failure into a fresh simulation.

Before deployment run `scripts/verify-post-native-corrections.py --reconciliation
<retained private20-change reconciliation>`. The currentV7 overlay retains20
consumed and raises only the managed-VM source ceiling to24. The guard counts
subsequent native source commits and a pending source change, preserving historical
policy hashes. The guard is not human consent. Other users' install defaults,
published assets, original OA/ADE/PDK/license contents and all past evidence remain
outside this change.

## Windows package line endings

Native bundle source is projected to LF before manifest hashing, because the
standard VM's Python2.6 memory compiler rejects CRLF source strings. The setup
CLI validates the identical package-only projection. No remote file is normalized
after its manifest check. Retained predecessor bundles and failure evidence remain
unchanged. The exact37c84c9 package passed hosted/installed checks but its actual
recovery plan rejected before reservation on this issue; it is not actual recovery
qualification. The corrected installed VM path remains a separate acceptance gate.

## Actual standard VM validation, 2026-10-14

Runtime source0fe7dee at immutable4c288204 passes actual UID500 update/repeat,
preflight and all13 Python2.6 asset compilations. The first accepted extraction
created a complete frame but OCEAN32 aborted during shutdown with glibc double
free/corruption. It remains EXTRACTION_FAILED; no nonzero exit is accepted. A
separately pre-recorded one-attempt/8MiB revalidation on the same runtime succeeds.
No Cadence binary, library, model, license or administrator metadata was changed.
This is observed intermittent vendor shutdown behavior, not a diagnosed vendor fix.

Successful CLI result, identical-ID submission and separate-process restart
queries preserve original EXTRACTION_FAILED/PSF/content and host journal. Failed
ID restart/submit also remains lookup-only, adding0 dispatch/reservations. Two
OCEAN readers,0 Spectre/netlisting starts:2 accounting attempts/16MiB total.
Retained cumulative ledger114/13,842,251,776 bytes;16GiB remaining3,337,617,408.
Native source changes22/24. The updated package verifier passes isolated build,
rights/content, SDK/CLI and63-file reinstall/uninstall preservation. Initial
CRLF verifier mismatch and Linux-only unstubbed ssh.exe fixture failures remain
recorded; test-only fixes are27e83d4, with native source equal to0fe7dee.

This qualifies the tested registered inverter DC recovery route on the current
standard VM only. It does not qualify AC/TRAN recovery, another Cadence/PDK/PC,
actual Claude, or change the immutable published2.0.0 artifacts. Recovery stays
experimental and operator-CLI-only while broader qualification/review is pending.
