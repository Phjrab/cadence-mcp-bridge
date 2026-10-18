# Explicit registered voltage/current candidates — unreleased development

This separate follow-up is not in published2.1.0. Version2.2.0.dev0 marks a
development build with additive operator CLI/API work. It is not a release
candidate or a claim of new actual VM qualification. Support stays limited to
the professor-provided standard VM and its existing PDK.

## Input and authority

`operator-candidates schema` shows the closed request/observation formats. Supply
2–16 explicit candidates, stable UUID4 batch/child identities, user labels and
every registered variable. Preserve the original numeric spelling and unit; the
plan also includes the existing canonical complete OperationRequest for each
child. Partial overrides, duplicate vectors, undeclared differences, arbitrary
expressions and missing values reject. There is no candidate generator/search.

Each changing dimension must be a registered, numerically reviewed, qualified
owned-copy V/A variable. This is a software contract check, not a new electrical
range qualification. Fixed source/testbench revision/baseline references, exact
ADE/source-instance/master/property bindings and evidence hashes, profile/analysis
hashes, reader/measurement identity, model/analysis/static/ADE conditions are
included prospectively. Supplied evidence references are explicitly not an
independent source attestation. Descriptive labels do not certify conditions.

Every child passes the existing `prepare_plan`, scoped v1/v2 grant and numeric
checks. Aggregate executions/reservations must fit the grant. Live remaining
budget, qualification, OS-operator confirmation, original/native/model guards,
disk floors and replay remain independent admission checks. No grant is minted,
no journal is replaced, and no spent allowance is refunded by planning.

## Explicit operator workflow

Use your own runtime settings and a valid bounded grant. These commands contain
placeholders, not a circuit registration or execution approval.

```powershell
python -m cadence_mcp_bridge operator-candidates schema
python -m cadence_mcp_bridge operator-candidates plan --settings RUNTIME.json --context CONTEXT --request REQUEST.json --output NEW_PLAN.json
python -m cadence_mcp_bridge operator-candidates submit --settings RUNTIME.json --context CONTEXT --plan NEW_PLAN.json --expected-plan-sha256 PLAN_HASH --experimental-candidates
python -m cadence_mcp_bridge operator-candidates advance --settings RUNTIME.json --context CONTEXT --plan NEW_PLAN.json --expected-plan-sha256 PLAN_HASH --experimental-candidates
python -m cadence_mcp_bridge operator-candidates status --settings RUNTIME.json --context CONTEXT --plan NEW_PLAN.json --expected-plan-sha256 PLAN_HASH
python -m cadence_mcp_bridge operator-candidates result --settings RUNTIME.json --context CONTEXT --plan NEW_PLAN.json --expected-plan-sha256 PLAN_HASH
python -m cadence_mcp_bridge operator-candidates capture --settings RUNTIME.json --context CONTEXT --plan NEW_PLAN.json --expected-plan-sha256 PLAN_HASH --output NEW_OBSERVATIONS.json
python -m cadence_mcp_bridge operator-candidates compare --plan NEW_PLAN.json --expected-plan-sha256 PLAN_HASH --observations NEW_OBSERVATIONS.json --output NEW_COMPARISON.json
python -m cadence_mcp_bridge operator-candidates csv --comparison NEW_COMPARISON.json --output NEW_COMPARISON.csv
```

Inspect the full expanded plan before admission. `submit` reserves the immutable
local batch/child identities only; it dispatches no child. `advance` submits at
most one untouched child, after all predecessors have succeeded. It never loops
through a whole batch automatically. Unknown/running/extraction-failed/failed/
cancelled work stops advancement. Generic failure is not relabeled as convergence.
The only policy in this first implementation is `halt_all`.

Retries/restarts with the same manifest use existing identities; submit/status/
result/capture do not become a simulator retry. Changed inputs/authority reject
fresh admission. Parent/child claims share the existing AnalysisStore transaction
with direct operations and native Sweep. Extraction recovery uses a distinct
durable admission marker before its remote request; a lost reply is lookup-only,
including when lookup returns no result. No force-unlock/termination is added.
Recovery status/result inspect the same local namespace before and after remote
reads, so an existing remote result cannot adopt a direct operation or a batch/
Sweep parent or child ID. An exact recovery marker still permits lookup after
grant expiry/exhaustion; an absent remote result never causes a resend.

## Reporting and evidence limits

Partial results retain every declared candidate and its status/reason. Capture
uses the registered provider's existing-result reader for succeeded children,
preserving failed/nonterminal/not-run rows. A report read failure remains
`RESULT_UNAVAILABLE` with `retained_report_read_failed`; it does not re-extract
or simulate. Captured observation files connect directly to local comparison.

Comparison is separate from unchanged `result_reports.compare`. Only declared
input values and per-candidate effective-input digests may differ in the common
condition calculation. Each original digest remains in its own full record.
Source/ADE/static/model/analysis/grid/reader/measurement conditions are retained;
a mismatch produces a visible row with no measured values. Missing values remain
null with a reason. Relative change is `(value-baseline)/abs(baseline)`; a zero
baseline yields null rather than infinity. Exact plans, operation IDs, provider/
input/frame/extraction identities and unit-bearing metric definitions remain.

Reimported files receive `LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION`.
Local hashes are not fresh remote authenticity proofs. Scalar reports lack a
separate physical readback-value field, so effective values remain unavailable;
requested values are never copied into a field labeled verified effective values.
CSV is UTF-8 with BOM, standard quoting and formula-prefix escaping including
whitespace/control prefixes. Original labels remain in JSON. Scalar data does
not fabricate time/frequency waveforms; waveform export is unsupported here.

## Qualification and next actual scope

Synthetic complete-vector/grant/comparison/CSV tests and disposable real SQLite/
separate-process restart/concurrency tests establish software behavior only.
Installed package/CI evidence is recorded with the final feature commit. No
fresh native candidate run, current grant approval, effective new candidate
readback, actual client connection or electrical performance PASS is implied.

W/L and geometry-mixed candidates remain unsupported. The observed inverter CDF
defaults do not establish legal ranges/grid/callbacks, w/fw/nf/m behavior or derived
geometry. Unknown units/properties and unregistered dimensions reject. Implement
a dimension-changing writer only after the exact device family has a reviewed
binding and legal finite choices, original protection/owned revision recovery,
independent CDF reopen/readback and effective netlist/topology/model verification.

Before any new real trial, present one finite decision binding the exact circuit/
revision, full bias-only/geometry-only/mixed candidate list, analyses, missing
bounded observations, maximum runs/reservations, change/restore boundaries and
stop policy. Re-read current original accounting immediately before execution.
Global capacity, the source60 limit and expired/spent M2 grants do not approve it.
Do not request a new PC, another Cadence version/PDK or an optimizer as a prerequisite.
