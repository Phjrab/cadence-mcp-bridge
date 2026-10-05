# Registered analysis lifecycle v1

GENERIC-SIM-01 adds a registered analysis API around the proven native execution
layer. The first compiled adapter covers only the reviewed reference design's
fixed native DC, AC and trap TRAN candidate. Another design may declare these
analysis types, but remains blocked until its adapter and environment/PDK/input
conditions are qualified. No arbitrary command, path, script, netlist, model
selector or execution flag is accepted.

## Operator registration

Registry v3 extends the same `design schema/validate/register` workflow and
`CADENCE_MCP_DESIGN_REGISTRY_PATH`. It preserves v1/v2 schema/projection behavior.
Configured v1/v2 files have no analysis contracts and do not inherit reference
execution. The server default, when no registry is configured, represents the
existing reference compatibility adapter. Legacy tools retain their own routes.

```powershell
uv run cadence-mcp-bridge design schema --schema-version 3
uv run cadence-mcp-bridge design validate --registry C:\private\proposed-v3.json
uv run cadence-mcp-bridge design register --registry C:\private\proposed-v3.json --output C:\private\registered-v3.json
$env:CADENCE_MCP_DESIGN_REGISTRY_PATH='C:\private\registered-v3.json'
$env:CADENCE_MCP_ANALYSIS_JOURNAL_PATH='C:\private\analysis-admissions.sqlite3'
uv run cadence-mcp-bridge config-check
uv run cadence-mcp-bridge serve
```

Use a stable absolute operator journal path and protect its directory/account
ACL. Without that optional setting, Windows uses
`%LOCALAPPDATA%\cadence-mcp-bridge\analyses-v1.sqlite3`; other local hosts use
`$XDG_STATE_HOME/cadence-mcp-bridge/analyses-v1.sqlite3` or the user's
`.local/state` fallback. This is local state, not a remote execution path. The
analysis layer creates it only on first admission; planning does not create it.
Configuration inspection does not prove the journal is writable or qualify an
analysis. Installed packages do not need a writable source directory for this
new journal. Existing lifecycle/sweep storage mechanisms remain unchanged.

See [v3 schema](schemas/design-registry-v3.schema.json) and
[fictional blocked example](examples/design-registry-v3.fictional.json).
The operator can serialize the built-in `designs.reference_analysis_registry()`
locally to describe the reference adapter; this does not create runtime authority
or qualify another installation.

## Analysis contract and qualification

Each contract records logical design/analysis IDs, DC/AC/TRAN type, exact canonical
design-profile and optional variable-set digests, compiled adapter kind/digest
and input policy. Up to 48 contracts across 16 designs are permitted; one of each
analysis type per design, with unique analysis IDs. An analysis must be in the
design's declared allowlist. Stale/substituted digests and extra fields fail
closed. Registration remains outside MCP and exclusively creates a local file.

The compiled `native-fixed-reference-v1` adapter requires the exact reviewed
reference design profile and reference variable set, plus the compiled native
contract digest. Recomputing hashes cannot redirect this adapter to another
library, ADE state, environment, PDK, variable policy or design ID. All other
contracts use `adapter_kind=unqualified` and cannot dispatch.

`qualification_scope=fixed_native_compatibility` explicitly describes reuse of
the existing guarded reference route. It does not claim successful generic
environment preflight, a second installation, arbitrary design support or a
qualified continuous voltage range. The reference installation's generic
executable-permission blocker remains unchanged. Legacy design/variable
projections retain their conservative unqualified/no-generic-execution states.

`dispatch_eligible=true` is local adapter eligibility. A plan does not reserve
resources, prove current license availability or bypass a remote guard. The
existing native worker independently enforces private delegation, source/ADE/
PDK fingerprints, effective input, EDA locking, disk floors, current shared
budgets and durable UUID replay. Existing dated public budget metadata is not
new accounting authority. A live submission may still be rejected by these
checks. No ledger or resource ceiling is reset or replaced.

The input policy is fixed and has **no variable/analysis parameter fields**.
320/702 mV remain the bounded candidate, VDD=1 V remains the constraint and
the listed settings describe that native contract. They are not a new source
observation, a safe continuous range, an optimum or a specification PASS.

## MCP interface

| Tool | Input and behavior |
| --- | --- |
| `cadence_list_analyses` | `design_id`; local declared modes and registered plans |
| `cadence_plan_analysis` | `request={design_id, analysis_id}`; deterministic contract hash, eligibility, fixed settings and limitations; no reservation |
| `cadence_submit_analysis` | `submission={design_id, analysis_id, operation_id, expected_plan_hash}`; durable local admission, then compiled guarded adapter |
| `cadence_analysis_status` | `request={design_id, analysis_id, operation_id}`; exact admitted identity and native lifecycle |
| `cadence_analysis_result` | Same admitted query; bounded native scalar/spectrum/transient result, settings and provenance |
| `cadence_cancel_analysis` | Same admitted query; explicit cancellation capability and current state; terminal no-op or unsupported active cancellation |

The reference IDs are `native-dc`, `native-ac` and `native-tran` under
`reference-differential-amplifier-tb2`. Operation IDs are lowercase UUID4 text.
Get the current plan hash before admission. Unknown designs/analyses, stale
plans, extra fields and mismatched operation bindings fail before transport.
MCP results omit private registry bindings/review data. Results retain
`spec_evaluation=not_evaluated` and the native bounded validation/evidence model.

## Durable admission and recovery

The local SQLite journal binds operation UUID to design ID, analysis ID and
plan hash. Full-synchronous transactions serialize admission across server
instances. The first caller commits before invoking the existing native submit;
subsequent callers can only query the same remote ID. Status/results require
an admitted matching identity and current contract. Contract changes cannot
rebind preserved operation IDs. Existing legacy jobs can be admitted using
their existing IDs: the native replay domain returns their status, without a
new simulation or reservation.

A crash, timeout, cancelled coroutine, failed response or missing remote state
does not permit automatic resend. The local admission is retained and retries
look up only. If a crash occurred before sending, an absent remote job remains
uncertain rather than being started silently. Preserve the journal and reconcile
under the operator policy; do not delete/recreate it, change the plan to reuse
an ID, or create a new ID merely to work around an uncertain outcome.

The journal is bounded to 10,000 records and 16 MiB. Wrong application/version,
corruption, symlink paths/sidecars, capacity and file errors fail closed without
reset. It stores logical identities/hashes, not raw results, proprietary bindings
or secrets. The trusted operator account/ACL is the boundary; it is not isolation
from someone who controls that account and can edit code/configuration.

## Cancellation and remaining limits

The native infrastructure has no qualified live process-cancellation operation.
`cancellation_supported=false` remains visible in plans and cancellation results.
The cancellation endpoint reads status only: a succeeded/failed job returns
`terminal_noop`; an active/unknown job returns
`unsupported_active_cancellation`. `cancelled=false` always remains. No process
is signalled and the API never claims a cancellation it did not perform.
This endpoint has a read-only annotation for this contract version.

Another user can configure registered analysis descriptions and inspect/plan
their qualification state. The validated reference operator can use the common
API to admit, inspect and recover fixed native jobs without raw legacy selectors.
Other projects/PDKs still need qualified adapters, environment capability and
effective-input proofs. Parameterized execution, generic real-design sweeps,
live native cancellation and full public onboarding are not qualified here.
