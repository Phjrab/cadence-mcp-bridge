# Registered variable contracts

GENERIC-VAR-01 extends the existing operator design registry to version 2.
It adds local numeric inspection and checking, without Cadence execution or
mutation. Version 1, its published schema and list/describe projections remain
compatible. A configured v1 registry has no implicit variable contracts.

## Operator workflow

```powershell
uv run cadence-mcp-bridge design schema --schema-version 2
uv run cadence-mcp-bridge design validate --registry C:\private\proposed-v2.json
uv run cadence-mcp-bridge design register --registry C:\private\proposed-v2.json --output C:\private\registered-v2.json
$env:CADENCE_MCP_DESIGN_REGISTRY_PATH='C:\private\registered-v2.json'
uv run cadence-mcp-bridge config-check
uv run cadence-mcp-bridge serve
```

The existing settings namespace, bounded loader, exclusive registration and
startup snapshot are reused. The file and containing directory must be owned
and protected by the operator. Nothing is deployed. Restart stdio to load a
new snapshot; MCP cannot register, modify or qualify a contract.
`design schema` still defaults to version 1. See the
[v2 schema](schemas/design-registry-v2.schema.json) and
[fictional unqualified example](examples/design-registry-v2.fictional.json).

Version 2 contains `designs` (unchanged v1 profiles), `variable_sets` and
`range_reviews`. A variable set binds one exact profile through its canonical
SHA-256; its logical IDs must equal that profile's declared variables. Duplicate
sets, IDs and private Cadence binding aliases are rejected. A missing set is
reported as missing contracts; it never inherits the reference defaults.

## Numeric and mutation policy

| Field | Meaning |
| --- | --- |
| `logical_id` | Bounded model-facing name, exact local lookup |
| `cadence_binding` | Private bounded variable name, excluded from MCP |
| `unit` | Exact unit: V, A, ohm, F, s, Hz, K, degC or dimensionless 1 |
| `value_type` | Real or integer; integers require integral contract/input values |
| `default` | Reviewed declaration only; never implicitly filled, applied or observed |
| `mutation_policy` | read_only, fixed or owned_copy_only; does not enable mutation |
| `range_status` | unqualified or qualified for the local reviewed numeric contract |
| `minimum`, `maximum` | Inclusive bounds, required only for a reviewed range |
| `step_policy`, `step` | Continuous, exact grid relative to minimum, unqualified or fixed |
| `fixed_value` | Exact fixed user constraint, distinct from a qualified range |
| `review_id` | Private reference to a separate bound numeric review |

Numbers are **decimal strings** in base units, such as `"0.320"` V or `"1e3"`
ohm. JSON numbers/booleans, NaN/Inf, whitespace, Unicode digits, code and unknown
units are rejected. Inputs/canonical values are limited to 48 characters,
decimal exponent magnitude to 40 and adjusted magnitude to 30. Values normalize
exactly; range and grid comparisons use Decimal without binary-float tolerance.
No silent unit conversion occurs. Use `"0.320"` V, not `"320"` mV.

An unqualified nonfixed variable has no default, bounds, step or review. A fixed
constraint has equal fixed/default values, no bounds and an unqualified range.
A reviewed range requires minimum < maximum, a continuous or positive grid
step policy, and a matching review. Any declared default must match that range,
grid and type. Read-only variables reject supplied values; owned-copy variables
also require the design's owned-copy policy.

## Separate review authority

A range review records its ID, design ID, canonical design-profile SHA-256,
canonical complete variable-contract SHA-256, evidence ID/SHA-256 and the exact
scope `operator_reviewed_project_numeric_contract`. The loader requires a
one-to-one match for every qualified variable and rejects absent, duplicate,
orphan, substituted and stale reviews. Changing bindings, environment, PDK,
copy policy, bounds, default, step or unit invalidates the old match.

Canonical contract digests use normalized validated models: serialize
`model_dump(mode="json")` with `json.dumps(..., sort_keys=True,
separators=(",", ":"))`, encode UTF-8 and hash SHA-256. The existing helper
`variable_contracts.canonical_digest` provides this algorithm. File/evidence
hashes bind operator-reviewed bytes; the operator independently establishes
their meaning and protects their review records. Reviews are trusted local
configuration, not signatures, automatic evidence inspection or PDK safety
certification. A hash alone cannot prove a safe electrical range.

Local `range_status=qualified` means the declared numeric range has its matching
operator review. It does not resolve the environment or PDK, authorize a run,
certify electrical safety, or evaluate a design specification. Generic execution
is disabled for all registries in this phase. The legacy design description's
`variable_ranges_status=unqualified` remains the conservative generic execution
status; the separate variable tool reports local numeric review status.

## MCP interface

- `cadence_list_design_variables(design_id)` returns declared IDs, mapped
  contracts and missing IDs, without bindings, review/evidence IDs or hashes.
- `cadence_check_variable_values(request)` checks only explicit logical
  value/unit entries. It returns canonical values, per-variable reasons and
  `locally_admissible`; it never fills defaults, changes a file or contacts SSH.

Example input:

```json
{
  "request": {
    "design_id": "reference-differential-amplifier-tb2",
    "values": {"vdd": {"value": "1.0", "unit": "V"}}
  }
}
```

This matches the fixed VDD constraint locally. `execution_authorized=false`
and `spec_evaluation=not_evaluated` always remain. Unknown designs are errors;
unknown variables, wrong units, read-only/copy denial, unqualified range,
nonintegral input, fixed mismatch, outside-range and off-grid values return
distinct denials. Extra top-level/nested fields are rejected. No tool accepts
a private binding, path, script, raw netlist or qualification flag.

## Reference facts and limits

The default reference profile maps vbiasn/VBIASN, vbiasp/VBIASP and vdd/VDD.
Both bias ranges remain **unqualified**, with null defaults. Historical fixed
320/702 mV candidates and finite paired experiments do not establish continuous
bias bounds. VDD=1 V is the user's fixed constraint, not a new safe voltage range
or observation of current source values. Existing fixed/native execution guards
retain their own effective-input, budget, replay and fingerprint requirements.

Another operator can register and inspect explicit private variable bindings,
units/types/mutation policies and reviewed numeric contracts without editing
source. Running newly registered designs still requires environment/PDK and
analysis qualification plus a guarded generic lifecycle adapter. Next proposed
phase is GENERIC-SIM-01; it must preserve these unresolved gates.
