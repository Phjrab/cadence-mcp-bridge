# Registered PDK capability adapters v2

PDK-ADAPTER-01 implements the minimum runtime part of WP-15. The historical
technology v1 schema and draft seed remain unchanged and are not accepted by
the runtime v2 loader. This catalog contains logical capabilities, not PDK data.

## Operator workflow

```powershell
uv run cadence-mcp-bridge pdk schema
uv run cadence-mcp-bridge pdk validate --registry C:\private\proposed-pdks.json
uv run cadence-mcp-bridge pdk register --registry C:\private\proposed-pdks.json --output C:\private\registered-pdks.json
$env:CADENCE_MCP_PDK_REGISTRY_PATH='C:\private\registered-pdks.json'
uv run cadence-mcp-bridge config-check
uv run cadence-mcp-bridge serve
```

Use [the schema](schemas/pdk-registry-v2.schema.json) and
[fictional example](examples/pdk-registry-v2.fictional.json). Registration creates
a new file exclusively, preserving validated bytes. A configured catalog replaces
the default; missing reference entries are not filled automatically. Startup takes
an immutable snapshot. Invalid configuration stops startup without fallback.

The catalog has at most 16 adapters and 65,536 bytes. Each adapter contains
logical technology/adapter/environment IDs, separate process/RC corner IDs and
at most 16 unique capabilities. Unknown fields, paths/code, duplicate keys,
nonfinite JSON, invalid versions, symlink input and oversized files fail closed.
Errors exclude private validation payloads. No physical binding resolver is added.

## Capability semantics

| Status | Meaning |
| --- | --- |
| `unqualified` | Description only; no executable binding or qualification |
| `observed` | Operator metadata refers to an observation; not independently verified qualification or an execution grant |
| `fixed_native_compatibility` | Exact compiled regression adapter matches the existing native route; independent runtime guards still apply |

`pdk_reference.py` owns gpdk090 regression identity/capabilities. Generic contract
logic has no gpdk090-specific models, devices, layers or corner rules.
[The reference catalog](technology/gpdk090-runtime-regression-v2.json) describes
fixed DC/AC/trap TRAN compatibility, observed PVT corners and operating-point
extraction. Statistical support, generic device mappings, layout and DRC/LVS/PEX
are unqualified. Observation is not signoff, equivalence or target compliance.

Only the exact complete reference can claim fixed compatibility. Identity,
environment, corners, capabilities and native binding digest must match.
Recomputed hashes cannot redirect to another PDK/design/environment. A target
adapter may register unqualified descriptions and logical observation references
without source edits; editing JSON cannot give it an executable binding.
Physical masters/CDF/PCell/pins/models/sections/layers/decks/license mappings stay
protected in existing reviewed workers. New physical bindings require a later
bounded qualification/routing implementation; none is implemented here.

## MCP and analysis admission

- `cadence_list_pdk_adapters()` returns bounded logical descriptions.
- `cadence_describe_pdk_adapter(adapter_id)` looks up one registered ID.
- `cadence_design_pdk_status(design_id)` resolves the design's PDK/environment
  reference locally. Native modes mean PDK compatibility only; analysis eligibility
  also requires exact design, variable and analysis contracts.

These three read-only tools accept closed inputs. They expose no registration,
paths, physical bindings, private binding digests or environment binding lists.
Execution authority and generic qualification remain false. The old design
description schema is preserved; use the new tool for current PDK resolution.

Registered analysis plans consult the catalog before dispatch. Missing,
unqualified or mismatched adapters block before admission or transport. The v3
plan hash/protocol stays unchanged; prior exact-reference admissions can resume.
Removing the reference blocks registered queries/submissions; restoring the same
reviewed catalog allows lookup-only resume. Legacy fixed APIs retain independent
guards; generic environment qualification is not bypassed.

Another user can describe/inspect their PDK capabilities and bind a design to a
logical ID. Executing their design/PDK remains unqualified. No arbitrary execution,
model files, protected data, electrical range, default bias or specification is
added. 320/702 mV remain candidates; VDD=1 V remains a fixed constraint.
See [phase evidence](PDK_ADAPTER_01_RESULT_V1.md).
