# POST-04 extraction-only recovery (unpublished experimental development)

The installed operator CLI `operator-recovery` links a separately identified
extraction attempt to an original EXTRACTION_FAILED job. The original operation,
failure events, effective input, PSF and files remain read-only. The fixed worker
runs only OCEAN's registered reader and writes to a new job area. It has no netlist
or Spectre invocation. Existing operation/tool contracts remain unchanged; no new
public MCP tool or automatic recovery is installed.

## Qualification boundary

Host tests/static checks are preliminary evidence. Actual standard-VM extraction
from retained failed PSF, installed qualification and hosted POSIX tests remain
required. Do not call this feature generally qualified or part of the published
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
