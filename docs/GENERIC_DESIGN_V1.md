# Registered design descriptions v1

GENERIC-DESIGN-01 adds operator-owned local registration and read-only MCP
introspection. A registered description is not an environment observation,
PDK adapter implementation, electrical range review or execution authorization.
Existing fixed/native execution still uses its original contracts and guards.

## Operator workflow

Use the existing CLI and `CADENCE_MCP_` settings namespace. Keep actual registry
files outside the public repository, in operator-controlled private storage.
The fictional example is a format demonstration, not a qualified design.

```powershell
uv run cadence-mcp-bridge design schema
uv run cadence-mcp-bridge design validate --registry C:\private\proposed-designs.json
uv run cadence-mcp-bridge design register --registry C:\private\proposed-designs.json --output C:\private\registered-designs.json
$env:CADENCE_MCP_DESIGN_REGISTRY_PATH = 'C:\private\registered-designs.json'
uv run cadence-mcp-bridge config-check
uv run cadence-mcp-bridge serve
```

`register` validates and exclusively creates a byte-preserving local copy.
An existing destination, including a dangling symlink, is refused. It never
contacts Cadence, deploys, discovers a source, opens ADE or modifies OA. Local
file permissions depend on the operator's storage ACL; mode 0600 is requested
where the OS implements it. Protect the containing directory before use.
A partial write is invalid and must not be used; registration never overwrites
an existing file as recovery.

The server validates and freezes a bounded snapshot at startup. A configured
invalid, missing, oversized or symlink registry blocks startup with a closed
error; it does not silently restore the reference registry. An explicit empty
registry lists no designs. Changes require a reviewed configuration and restart.
Without the setting, the reference amplifier description is available by default.
Changing this registry changes only the two design introspection tools; it does
not change the allowlists of legacy tools or redirect their execution.

## Contract

See [JSON Schema](schemas/design-registry-v1.schema.json) and
[fictional example](examples/design-registry-v1.fictional.json).

| Field | Meaning |
| --- | --- |
| `schema_version` | Exact integer 1 at registry/profile level |
| `design_id` | Unique lowercase logical ID, at most 64 characters |
| `environment_id` | Logical reference to an environment description; unresolved by this phase |
| `pdk_adapter_id` | Logical adapter reference; unresolved by this phase |
| `binding` | Private bounded library/cell/view and ADE kind/state names |
| `allowed_analyses` | Declared subset of DC/AC/TRAN; no analysis activation |
| `allowed_variables` | Logical IDs only; no electrical ranges, values or mutation authority |
| `allowed_measurements` | Logical IDs only; no executable expressions or spec targets |
| `allowed_corners` | Logical IDs only; no model-file or section selection |
| `protected_source` | Exact boolean true; source writes cannot be registered |
| `work_copy_policy` | `read_only` or `owned_copy_only`; neither grants a write |

At most 16 designs, 32 entries per variable/measurement/corner list, three
analyses and 65,536 input bytes are accepted. Duplicate JSON keys, IDs or
allowlist entries, nonfinite JSON, unknown fields, paths, code, netlists and
qualification/authorization flags are rejected. Empty allowlists are valid.
ADE kind names describe a binding only; they do not claim qualification for
Explorer, Assembler or ADE XL. Cross-environment/adapter resolution and
scientific capability qualification remain future gates.

## MCP interface

- `cadence_list_designs()` returns IDs, environment/adapter references and
  explicit registration/qualification/execution states.
- `cadence_describe_design(design_id)` performs an exact local lookup and
  returns logical allowlists, protection/copy policy and unresolved statuses.

Both tools are typed, bounded, read-only, idempotent and independent of SSH.
Unknown IDs and extra arguments are rejected. Library/cell/view/state names,
physical paths, registry contents and hashes are excluded from MCP projection.
All generic designs report `qualification_status=unqualified`,
`execution_authorized=false`, `variable_ranges_status=unqualified` and
`spec_evaluation=not_evaluated`. No model-facing registration or execution
tool accepts a design profile, binding, path or script.

## Reference and compatibility

`reference-differential-amplifier-tb2` represents the existing source/ADE
identity and native DC/AC/TRAN, variable, measurement and five-corner descriptions.
Its gpdk090 reference is an adapter description, not a universal PDK runtime.
The reference generic profile is unqualified even though preserved fixed/native
routes have real evidence. Registration does not promote the candidate to an
optimum or evaluate a specification. The fixed 320/702 mV candidate, VDD 1 V,
original saved-state evidence, budgets, protected fingerprints and replay domain
remain enforced by the existing execution layer.

Another operator can now register their own design descriptions and inspect
logical contracts from an MCP client without source-code edits. Running that
design requires later environment/PDK/variable/analysis qualification and the
generic lifecycle adapter. Next proposed phase: GENERIC-VAR-01, with explicit
binding/unit/type/default/mutation contracts and evidence-qualified ranges.
