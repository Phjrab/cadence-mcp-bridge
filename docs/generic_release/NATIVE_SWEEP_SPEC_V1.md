# Native registered1D Sweep and specification

Current standard-VM feature evidence, 2026-10-09. General release BLOCKED;
exact installed onboarding, actual Codex and final candidate remain separate gates.
The professor standard CentOS/Cadence/PDK VM in personal VMware is the supported
scope. Other hosts/versions/PDKs remain deferred.

## Same native execution and retained accounting

`native-sweep` and conditional MCP tools coordinate up to16 explicitly registered
values on one qualified mutable axis. Every point uses NativeOperationService,
OperatorLifecycle, the existing guarded AnalysisStore, confirmed operator scope,
normal-user native worker and authoritative remote ledger. No additional worker,
budget/journal reset, reservation refund or circuit-specific Python helper exists.
The original reference SweepStore and its UUID5 codecs remain untouched. An
additive native parent table in AnalysisStore persists fresh UUID4 child identities
atomically before any dispatch; existing native child plans/events remain the
source of execution truth. This avoids treating the incompatible reference sweep
schema as a native operation journal.

Plan and submit do not execute or reserve. Submit fixes the parent/children and
same-ID retries only reconcile. Explicit advance admits at most one untouched
point after preceding points succeed. Running, unknown outcome, failed simulation,
failed extraction or cancellation stops subsequent admission. The current grant,
runner, registry and requested inputs must still reproduce the saved plan before
a new point starts. Completed/previously admitted children are never blindly resent.
A changed policy cannot silently resume untouched points under new authority.

MCP inputs contain logical IDs, canonical decimal strings, bounded explicit arrays
and UUID/hash queries. No model-selected file paths, commands, raw PSF selector,
OCEAN expression, targets, authority writer or optimizer is added. Old85 tools and
five native operation declarations remain unchanged. Six additional declarations
are conditional on the explicit existing native provider/grant configuration.
The fresh/unconfigured launch remains SETUP_REQUIRED with no remote contact.

## Operator CLI

Obtain `native-sweep schema`. Write a private JSON request containing a complete
`template` OperationRequest, one `variable_id`, and an explicit `values` array.
All registered fixed/non-axis values must remain present, with their exact units.
Each point's result reservation comes from the template. Numeric qualification
and the actual operator grant must both permit every value; no implicit defaults,
linear range expansion or electrical-rating assumption is used.

```text
cadence-mcp-bridge native-sweep plan --settings RUNTIME --context CONTEXT --request REQUEST
cadence-mcp-bridge native-sweep submit --settings RUNTIME --context CONTEXT --request REQUEST --sweep-id UUID4 --expected-plan-sha256 PLAN_SHA
cadence-mcp-bridge native-sweep advance --settings RUNTIME --context CONTEXT --sweep-id UUID4 --expected-plan-sha256 PLAN_SHA
cadence-mcp-bridge native-sweep status --settings RUNTIME --context CONTEXT --sweep-id UUID4 --expected-plan-sha256 PLAN_SHA
cadence-mcp-bridge native-sweep result --settings RUNTIME --context CONTEXT --sweep-id UUID4 --expected-plan-sha256 PLAN_SHA
```

Keep the original UUID/plan hash across process restart. Observe the active child;
only advance another point after it succeeds. Parent submit/retry never progresses
the next untouched point. Aggregate results are limited to1MiB; larger valid
campaigns use the existing individual child result queries. No raw file download.

## Operator-owned specifications

`native-specification schema` describes a private catalog with up to32 targets.
Bind its absolute path and exact raw SHA256 through the optional paired runtime
fields `native_specifications` and `native_specifications_sha256`. Restart with
that reviewed immutable runtime snapshot; package import/server start never writes
or selects goals. Export protects this catalog path like the other runtime inputs.
`native-specification list --settings RUNTIME --context CONTEXT` returns registered
contracts and canonical contract digests. Evaluation accepts only a registered
specification ID/hash and an optional existing operation ID/plan hash:

```text
cadence-mcp-bridge native-specification evaluate --settings RUNTIME --context CONTEXT --spec-id SPEC_ID --expected-contract-sha256 CONTRACT_SHA --operation-id UUID4 --expected-plan-sha256 POINT_PLAN_SHA
```

The contract binds exact operation plan, design, measurement and reader registration.
The plan/runtime binds all explicit values, analysis, model section/closure,
temperature, topology/stimulus/load and confirmed authority. Supported closed
projections are registered DC node voltage, signed delivered supply power, sampled
AC gain at an exact registered frequency, and TRAN last/time-weighted mean voltage.
Logical signal IDs and units must match; no conversion, expression or optimization.
The existing exact Decimal comparator is shared after native condition validation.
Missing target is NOT_EVALUATED without querying a job; missing selected operation
is MISSING_MEASUREMENT. Changed plan/reader/design/measurement is CONDITION_MISMATCH.
Missing/null/inapplicable scalar is UNQUALIFIED. Failed simulator/extraction and
stale target errors remain errors, never specification FAIL.

## Actual current-VM observations

The new QA inverter completed DC at0.55/0.60/0.65V, then a distinct parent request
completed AC at0.55/0.65V. Both use the already registered0.5–0.7V/0.05V numeric
region and common immutable bundle. Five new native simulations passed owned
OA/ADE copy, netlisting, effective inputs, protected library/model checks, Spectre,
automatic extraction and terminal/PSF integrity result retrieval. There was no
manual circuit-specific extraction or receipt construction. These are new runs,
including a fresh0.60V point, separate from the earlier single-job results.

New processes retried completed parent submit and advance; all original child
identities/states returned and there were0 additional attempts/reservations.
The second AC parent was admitted under the same remaining grant, demonstrating
continued use after a completed first batch. Actual UID500; latest read-only
native preflight passed after both campaigns.

QA-only output-voltage rail sanity0–1.2V produced PASS on the fresh0.60V result
(0.5953729581442881V). A deliberately impossible negative-range test produced FAIL;
a targetless contract produced NOT_EVALUATED/null. Applying the0.60V condition
contract to the0.55V point produced CONDITION_MISMATCH/null. These targets are
test namespace expectations, not a real amplifier goal or optimized circuit claim.
The evaluation and parent retries added no simulations or reservations.

This continuation5 attempts/671,088,640 bytes (640MiB). All generic validation
including the prior retained extraction failure12 attempts/1,610,612,736 bytes.
Latest actual cumulative94 attempts/11,409,555,456 reserved bytes; remaining
5,770,313,728 of approved16GiB. Current replacement grant spends11 of19jobs;
8jobs/1,073,741,824bytes remain inside the original20job/2.5GiB validation scope
after accounting for the failed1job/128MiB. Spectre500/corrections20, disk floors,
per-job size/process/time bounds and all historic reservations remain enforced.
This is the current managed VM policy, not a new user's installation default.

## Interruption repair review

Independent PR152 review identified that an interrupted direct final-path record
write could leave an unrecoverable partial update receipt/history. The fixed helper
now fsyncs a complete private candidate before atomic publication under the same
existing lifetime flock. Interrupted candidates remain evidence; retries create
another complete candidate without deleting them. Pending pointer, immutable
update receipt, activation history and initial pointer all use this path. Known
records/pointer metadata/history remain checked; no broad baseline replacement.

Actual UID500/Python2.6/POSIX synthetic validation passed9 scenarios: normal,
lost replies after pending/receipt/history/final pointer rename, held-lock rejection,
and interruption inside each of pending/receipt/history writes. Existing actual
ledger preserved,0 simulations/reservations. This synthetic OS/helper validation
is separate from the five actual Cadence jobs and actual Codex app acceptance.
Final hosted checks/review of this corrected feature are still required.

Remaining gates: public artifact-only enrollment/provenance preparation, fresh
operator installation/client lifecycle, actual Codex new submission/query/restart,
remaining ordered normal PR integration, GREL07 matrix and exact GREL08 candidate.
Public tag/Release/upload remains subject to final approval of exact candidate.

## Final local checkpoint

Related source tests113 PASS/25 OS skips, Ruff and mypy92 files PASS.
Security18 PASS and locked dependency audit clean after explicit UTF8 Windows
path retry; initial encoding failure is retained. Installed wheel protocol96 native
schemas, setup/update/reinstall/uninstall preserved43 state files and20 migration
files. These remain local/synthetic installed checks, not hosted final CI or app
acceptance. Active resource object now records94 attempts/11,409,555,456 bytes;
the former89-attempt observation and next-work list are retained in history.
