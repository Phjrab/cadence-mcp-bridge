# Development layout interface

The existing `serve-operator` launch advertises six additional tools:
`cadence_layout_inspect`, `cadence_layout_fork`, `cadence_layout_plan`,
`cadence_layout_apply`, `cadence_layout_diff`, and `cadence_layout_select`.
Each accepts one `request` object. Discovery works without native layout setup;
execution requires an explicitly configured development context and C1's registered provider.
The legacy launch cannot enable layout writes.

The same operations are available from the installed CLI:

```powershell
cadence-mcp-bridge layout schema
cadence-mcp-bridge layout schema --action plan
cadence-mcp-bridge layout inspect --settings settings.json --context development --request inspect.json
cadence-mcp-bridge layout fork --settings settings.json --context development --request fork.json
cadence-mcp-bridge layout plan --settings settings.json --context development --request edits.json
cadence-mcp-bridge layout apply --settings settings.json --context development --request approved-plan.json
cadence-mcp-bridge layout diff --settings settings.json --context development --request diff.json
cadence-mcp-bridge layout select --settings settings.json --context development --request previous.json
```

Names above are operator-supplied local files/context, not a measured VM example.
Use the registered logical binding returned by inspection. Files hold the typed
request itself; MCP wraps that same content in `{"request": ...}`. Local file paths
are never remote execution inputs. Environment settings may supply the existing
`CADENCE_MCP_RUNTIME_SETTINGS_PATH` and `CADENCE_MCP_RUNTIME_CONTEXT_ID` instead.

Fork to a new owned revision before planning edits. Plan accepts bounded `move`,
`add_rect`, and `add_pin` operations, with decimal text in micrometres. Observed
DBU/grid/layer-purpose determine validity; unsupported or off-grid edits reject.
Pin creation supports no optional text label yet: omit `label` or set it to `null`.
Apply takes `{"plan": <the complete returned plan>, "expected_plan_sha256": <its hash>}`.
Retain the same operation ID and exact content for retries. An uncertain write
requires read-back/reconciliation through the provider; changing the ID is not recovery.
Repeat the same `apply` request to retrieve its retained receipt. `replayed: true`
means `executed: false`; `OUTCOME_UNKNOWN` remains unresolved and never triggers
an automatic new write. Use inspect/diff for read-back and preserve the original request.
An apply seals that working revision after its first edit. Fork another revision
from the preserved result for the next edit; a different operation ID cannot re-edit a sealed target.
Diff retrieves changes/evidence. Select chooses a preserved revision without deleting history.

Inspect returns observed layout data. Results retain `executed`, `new_revision`,
`diff`, `saved`, `reopened`, `source_unchanged`, `replayed`, and separate
`physical_verification` states. `EDIT_VERIFIED` requires native reopen evidence;
DRC/LVS/PEX `NOT_RUN` or `UNAVAILABLE` is not physical or circuit qualification.
Fixture tests establish adapter behavior only. Actual VM verification is performed
by C1 and recorded separately in the integration acceptance evidence.

## Qualified instance-terminal connections

The existing `layout plan` command and `cadence_layout_plan` tool accept
`connect_terminal` edits for an operator-qualified owned child. The edit fields
are `kind`, `object_id` (existing instance), `expected_master_id`, `terminal`
(case-sensitive master terminal), and `pin_object_id` (existing top-level pin
whose net anchors the association). Submit the qualified eight-edit batch by
itself. Qualification is configured by the operator; unqualified requests are
rejected with `layout_instance_terminal_qualification_required`.

The installed build `d4b0136ec9ff83bd32783d6f924aca16074290c1` verified this
sequence for one operator-registered child. C1 supplies the exact registration
and runs the native stages.

1. Run `layout fork` with the registered child binding and preserved parent's
   baseline hash. Keep the first `FORK_VERIFIED` result and its reopened child
   `snapshot`. In `snapshot.instance_terminals`, require the eight qualified
   rows with `present: false`. An omitted field or missing row leaves that
   terminal unobserved. An existing instTerm, including an unbound one,
   prevents the create-only edit.
2. Use the reopened child's `semantic_sha256` as the plan request's
   `expected_baseline_sha256`, with its exact binding, the eight registered
   edits and a distinct apply operation ID. C1 compiled the plan locally from
   that snapshot. Save the complete plan as `plan` and its `plan_sha256` as
   `expected_plan_sha256` in the apply request file.
3. On the registered `serve-operator` stdio session, call
   `cadence_layout_apply` once with the apply file's JSON object as `request`.
   Check the structured result for `EDIT_VERIFIED`, `executed=true`,
   `replayed=false`, `saved=true`, `reopened=true` and `source_unchanged=true`.
   The reopened snapshot has eight present rows, and
   `diff.instance_terminal_changes` has eight absent-to-present changes to the
   expected existing pin/net anchors. `diff.changes` is empty.
4. After that verified result, use the same apply request file, plan hash and
   operation ID for CLI replay. Run this CLI entry point through C1's
   lookup-only host, which restricts the invocation to one receipt lookup.

   ```powershell
   cadence-mcp-bridge layout apply --settings $settings --context $context --request $applyRequest
   ```

   The replay returned the same receipt with `executed=false` and
   `replayed=true`. The protected state and job count were identical before
   and after replay. On a timeout or `OUTCOME_UNKNOWN`, retain the original
   request and have C1 reconcile that operation ID.

The verified result establishes eight OpenAccess associations on the saved
and reopened child. Physical body contacts, extracted connectivity and
post-layout behavior require separate evidence. DRC/LVS/PEX were `NOT_RUN`.

CLI success prints one JSON document and exits 0. Invalid requests/configuration
return the existing sanitized error envelope and exit 1. MCP stdout carries only
the protocol; server diagnostics use stderr. No arbitrary shell, SKILL, scripts,
provider modules, remote paths, or original-layout overwrite is exposed.

## Registered CMOS delay result

`cadence_cmos_delay_result` accepts one `request` with `operation_id`,
`expected_plan_sha256`, `definition` (the explicit `DelayDefinition` windows,
rails and sampling conditions), and `supply_signal` (a separate registered node).
Inspect the exact query schema with `cadence-mcp-bridge cmos-delay schema`, then
use the same JSON via `cadence-mcp-bridge cmos-delay result --request query.json
--settings runtime.json --context registered-context`.

The operator registration must contain an already succeeded TRAN with bounded
Vin/Vout/supply samples. Both entry points use the production registered native
result service; they accept no waveform, provider, script or remote path and start
no simulation, extraction or reservation. Missing/changed identities or supply
evidence reject. The separate source checks do not turn the local sampled delay
estimate into native logic/physical qualification: `NOT_ATTESTED`,
`vm_logic_physical_qualification=NOT_ASSESSED`; transient power is unsupported.
The supply node is caller-designated and voltage-checked, not topology-attested.
Actual VM use of this new adapter remains untested.
