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

CLI success prints one JSON document and exits 0. Invalid requests/configuration
return the existing sanitized error envelope and exit 1. MCP stdout carries only
the protocol; server diagnostics use stderr. No arbitrary shell, SKILL, scripts,
provider modules, remote paths, or original-layout overwrite is exposed.
