# Registered sweep lifecycle v2

This continues merged #114 preparation, using the existing sweep engine.
Operator design registry **v5** adds one compiled passive RC fixture analysis and
completion reader. All v1-v4 schemas and native contracts remain unchanged.
It does not qualify an amplifier bias range or add another execution engine.

## Operator configuration

Use the existing `design schema --schema-version 5`, `design validate/register`,
`pdk validate/register`, environment configuration and client exporter. Example
registries are in `docs/examples/sweep-v2/`; they contain only the registered
reference RC fixture and a path-free no-PDK applicability entry. They grant no
Cadence license or environment qualification. Explicitly configured registries
replace defaults; include existing reference entries to preserve native tools.
Use a stable `CADENCE_MCP_SWEEP_JOURNAL_PATH` with both MCP clients. Never reset
an existing ledger, change UUID to evade uncertainty, or use a new journal to
bypass consumed resources. Runtime calls accept registered IDs, never paths.

The compiled fixture profile pins design/environment/template, three logical
variables, TRAN analysis, nominal corner and completion definition. Numeric
reviews may narrow existing passive bounds but cannot broaden or redirect them.
`builtin-rc-no-pdk` means no model/device PDK is used; it grants no physical-PDK
capability. Recomputed hashes cannot redirect this adapter to another design.

## Calls

1. `cadence_describe_design_sweep(request)` obtains the current v1 local contract.
2. `cadence_prepare_design_sweep(request)` takes that hash, registered IDs, decimal
   strings/units and every non-axis fixed value. Explicit/linear 1D sequences
   have at most 16 unique points and must land exactly on the requested endpoint.
   The v2 response separately reports execution eligibility and plan hash.
3. `cadence_submit_design_sweep(submission)` takes the same request, v2 plan hash
   and stable experiment UUID. Reusing it resumes the exact registered contract.
4. `cadence_design_sweep_status`, `cadence_design_sweep_result` and
   `cadence_cancel_design_sweep` take only admitted design ID and sweep UUID.

Example IDs: design `registered-rc-fixture`, analysis `fixture-tran`, variable
`resistance`, measurement `completion`; unit `ohm`, values 900/1000/1100,
fixed `capacitance` = 1e-12 F and `stop-time` = 1e-9 s. These are previously
reviewed passive fixture inputs, not amplifier voltage ranges or design targets.

The old v1 describe/plan tools remain preparation-only and always report
execution false/NOT_RUN. Their fixed-native analysis/measurement interfaces
cannot run a parameterized fixture; v2 resolves the explicit compiled sweep
adapter. No eligibility result bypasses remote runtime admission or budgets.

## Durable ownership and results

`registered_sweep_admissions` in the existing SQLite sweep journal binds
experiment UUID, complete registry/PDK/analysis/variable/measurement hashes,
canonical request and legacy engine identity. Admission precedes engine dispatch.
An admission-only crash resumes safely. Engine reservation/sending uncertainty
remains lookup-only; no blind replay. Existing deterministic child IDs, durable
phases, terminal-point skip and cancellation are reused. Only admitted identities
can read/cancel. Changed/corrupt admission or engine checkpoints fail closed.
Terminal cancellation is a no-op; uncertain active cancellation stays UNKNOWN.

Results expose bounded engine points, requested/exact applied values and the
hash-bound completion definition. Successful stored points must still match
requested float-represented inputs and fixed sets. Completion is not gain or
another analog scalar. `spec_evaluation=not_evaluated` always remains.

## Active resources and scope

The explicit result-limit change is bound by `PHASE_RESULT_LIMIT_V4.json`.
New immutable native-v3/sweep-v2 guards retain the existing shared ledger and
native-v1/sweep-v1 replay identities: 500 Spectre attempts, 10 GiB cumulative
reservation, 128 MiB per job, one EDA execution, and free-space floor of the
greater of 2 GiB or 10 percent after reservation. No elapsed ceiling returns.
Old deployments, manifests, approvals and historical profile metadata (including
its old 5 GiB field) stay immutable for compatibility; that field is not a live
meter. The active policy and deployed guards enforce 10 GiB. Attempt and
reservation counters never reset. Paid-resource allowance remains zero.

No raw netlist/PSF, expression/script, arbitrary signal/path/command, schematic
mutation, multidimensional sweep, range expansion or optimization is exposed.
Amplifier bias ranges remain unqualified; 320/702 mV remain candidate conditions,
VDD=1 V remains fixed. Other Cadence versions and PDK qualification are deferred.
Claude Desktop real-client E2E and imported-planning rights review remain release
prerequisites; they do not block this registered reference continuation.
