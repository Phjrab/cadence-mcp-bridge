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

The existing `layout plan` command and `cadence_layout_plan` tool accept
`connect_terminal` edits for an operator-qualified owned child. The edit fields
are `kind`, `object_id` (existing instance), `expected_master_id`, `terminal`
(case-sensitive master terminal), and `pin_object_id` (existing top-level pin
whose net anchors the association). Submit the qualified eight-edit batch by
itself. Qualification is configured by the operator; unqualified requests are
rejected with `layout_instance_terminal_qualification_required`.

`instance_terminals` in inspect records the observed scope. An omitted field
or missing row leaves that terminal unobserved. Eight `present: false` rows
record eight observed absences. The plan and apply diff can carry
`instance_terminal_changes`. Check the saved and reopened result for the expected
OA associations. Physical connectivity and DRC/LVS/PEX require separate evidence.

CLI success prints one JSON document and exits 0. Invalid requests/configuration
return the existing sanitized error envelope and exit 1. MCP stdout carries only
the protocol; server diagnostics use stderr. No arbitrary shell, SKILL, scripts,
provider modules, remote paths, or original-layout overwrite is exposed.

## One CMOS design: existing interfaces and handoff

This sequence is conditional on C1's observed device/CDF and registered runtime.
Run remote stages through C1 only. Preparation below does not grant execution.

| Required C1 input | Source / boundary |
| --- | --- |
| NMOS/PMOS masters, terminal order, effective parameters, model/PDK pins | Fresh CDF/netlist observations; no inferred dimensions or callbacks |
| VDD, input stimulus, load, DC statement and TRAN time bounds | Observed/qualified registration; no values selected by this example |
| One logical `design_id`, registered DC/TRAN `analysis_id`s and explicit value inventory | Runtime registry and grant; analysis names are logical IDs, not arbitrary simulator strings |
| Schematic/symbol/testbench revision and effective netlist fingerprints | C1 generator save/reopen and input verification evidence |
| Layout `RevisionBinding`, source digest, object IDs, grid and LPP | Registered layout inspect result; a matching design ID alone does not prove schematic/layout equivalence |
| Grants/provider pins, reservation limits, operation IDs, measurement/spec contracts | Existing operator registration/accounting; never reset or synthesize authority |

Local preparation works now:

```powershell
cadence-mcp-bridge operator-design example --output .\cmos-fictional-plan
cadence-mcp-bridge operator-design validate --plan .\cmos-fictional-plan\plan.json --registry .\cmos-fictional-plan\registry.json --binding .\cmos-fictional-plan\binding.json
cadence-mcp-bridge operation request-schema
cadence-mcp-bridge layout schema --action plan
```

The first two commands use a fictional inverter and perform no schematic write.
`operator-design` has no execution backend. The internal
`m2_inverter.OwnedInverterPlan` / `render_generator` can generate observed-CDF-bound
schematic, symbol and testbench code, but expose no public transport/tool.
That slice fixes supply to 1 V, load to 1 pF and supports observed single-finger,
equal-width `w`/`fw` devices. C1 must verify applicability or the owner must extend
it; those historical constants are not the requested design's selected values.
Until generation, save/reopen and explicit native/layout registration exist for
this design, stop before the remote sequence.

Once C1 supplies those registrations, the existing MCP sequence is:

| Stage | Exact tool and arguments | Retained output / next input |
| --- | --- | --- |
| Discover | `cadence_describe_design`, `cadence_list_design_variables`, `cadence_list_analyses` with `design_id` | Qualified IDs, units and explicit value inventory |
| Plan DC, then separately TRAN | `cadence_plan_operation` with `request` | `plan` and its `plan_sha256`; no execution authority |
| Submit each | `cadence_submit_operation` with `submission` | `{operation_id, expected_plan_sha256, request}`; separate stable UUID per analysis |
| Observe / retrieve | `cadence_operation_status`, then `cadence_operation_result` with `request` | `{operation_id, expected_plan_sha256}`; preserve exact hash/ID and registered reader result |
| Evaluate selected target | `cadence_evaluate_native_specification` with `request` | Registered `spec_id`, `expected_contract_sha256`, same operation ID/plan hash |
| Physical edit | All six `cadence_layout_*` tools above, each with `request` | Inspect → exclusive fork → plan → exact apply → diff → select preserved revision |

The native operation request is exactly
`{schema_version: 1, design_id, analysis_id, values: [{logical_id, value, unit}], result_reservation_bytes}`.
`value` is decimal text; provide the complete registered value set. VDD, timing,
model and source bindings live in the qualified registration; do not add guessed
request fields. Native tools appear only with a configured native service; check
`tools/list` before using them. Source/view registration is not automatic promotion
from the local fictional plan. Layout and simulation hashes belong to different
contracts: preserve both and C1's mapping instead of substituting one for another.

Equivalent explicit CLI analysis stages (PowerShell 7, executed by C1) are below.
`$runtime` is `@('--settings', $settings, '--context', $context)`;
`$grantArgs` is `@('--grant', $grantFile, '--expected-grant-sha256', $grantHash)`;
`$providerArgs` is `@('--provider-binding', $providerFile, '--expected-provider-sha256', $providerHash)`.
All variables and `$requestFile` come from C1's qualified case. Repeat with a new
stable operation ID and the TRAN request after DC's terminal outcome is retained.

```powershell
cadence-mcp-bridge operation plan @runtime @grantArgs --request $requestFile > operation-plan.json
$op = Get-Content operation-plan.json -Raw | ConvertFrom-Json
cadence-mcp-bridge operation submit @runtime @grantArgs @providerArgs --request $requestFile --operation-id $operationId --expected-plan-sha256 $op.plan_sha256
cadence-mcp-bridge operation reconcile @runtime @providerArgs --operation-id $operationId --expected-plan-sha256 $op.plan_sha256
# Retrieve only after the retained terminal state is SUCCEEDED; never auto-resubmit a failure.
cadence-mcp-bridge operation result @runtime @providerArgs --operation-id $operationId --expected-plan-sha256 $op.plan_sha256 > operation-result.json
cadence-mcp-bridge native-specification evaluate @runtime --spec-id $specId --expected-contract-sha256 $specHash --operation-id $operationId --expected-plan-sha256 $op.plan_sha256
```

For layout, use the six CLI commands above with the same registered design ID and
C1's full layout binding. Save each JSON result and check the exit code before the
next command. Prepare the apply envelope from the entire returned layout plan;
keep its `plan_sha256` distinct from `operation-plan.json`'s analysis hash.
Do not mutate the revision after its first apply; fork the next revision instead.

Keep four outcomes separate: schematic creation/reopen evidence, DC/TRAN terminal
and registered measurements, layout edit/reopen evidence, and DRC/LVS/PEX.
`SUCCEEDED` means the job completed; electrical PASS requires the selected target's
evaluation. Existing native target metrics are `dc_voltage`, `dc_supply_power`,
`ac_gain_db`, `tran_last`, and `tran_mean`. They do not implement an inverter truth
table, propagation delay, noise margin, or automatic schematic-to-layout LVS PASS.
No target means no selected electrical acceptance; an edited layout remains
physically unqualified until the corresponding verification actually runs.

### Registered CMOS delay result

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
