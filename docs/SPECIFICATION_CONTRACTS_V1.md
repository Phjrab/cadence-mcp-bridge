# Registered specification contracts v1

SPEC-CONTRACT-01 connects operator-owned goals to registered analog measurements.
Measurement facts and specification intent remain separate. A measured gain alone
does not establish a design PASS; no reference numerical goal has been selected.
`reference_specification_registry()` consequently has **zero specifications**.
Existing measurement/analysis `spec_evaluation = not_evaluated` fields are unchanged.

## Operator contract and onboarding

Registry **v7** adds `specification_contracts` to v6. Registration remains outside
MCP, using the same private registry and launch configuration for every client:

```powershell
uv run cadence-mcp-bridge design schema --schema-version 7
uv run cadence-mcp-bridge design validate --registry C:\private\designs-v7.json
uv run cadence-mcp-bridge design register --registry C:\private\designs-v7.json --output C:\private\registered-v7.json
```

Use [schema v7](schemas/design-registry-v7.schema.json) and the
[fictional unselected-goal example](examples/design-registry-v7.fictional.json).
The example has no numerical target, no qualified execution route and placeholder
condition hashes. It is not a scientific baseline or a ready-to-run circuit.
To migrate v6, change only `schema_version` to 7 and add an empty
`specification_contracts` array first. Old explicit registries remain valid and
do not implicitly acquire goals. Default server registration does not acquire
reference goals either.

An operator may register a goal only when its target comes from user intent or
existing authoritative design requirements. Do not copy comparator test targets
into the physical reference registry or infer targets from measured results.

| Field | Meaning |
| --- | --- |
| `contract_version` | Strict integer 1 |
| `spec_id`, `design_id` | Registered logical identity; unique within the design |
| `measurement_id`, `measurement_contract_sha256` | Exact registered analog measurement contract |
| `definition_sha256`, `unit` | Exact compiled scientific definition and unit; no conversion |
| `comparison` | `>=`, `<=`, `>`, `<` or inclusive `range` |
| `target`, `upper_target` | Bounded canonical decimal strings; upper bound only for range |
| `goal_id` | Operator's opaque reference to the selected user requirement; required for a target |
| `conditions` | Expected analysis ID/plan hash, revision, operating point, corner, temperature, VDD, applied bias pair and complete effective-settings hash |

`target = null` requires `goal_id = null` and no upper bound. It means no target
was selected. Operator file ownership/ACL is the trust boundary: a goal ID is an
attribution reference, not cryptographic proof that the user supplied a target.
MCP clients cannot register, change or override targets, units or conditions.
Contract hashes include the goal, conditions, target and source bindings, so
changes invalidate old evaluation requests.

Registered specifications bind the current six analog definitions. The first
qualified physical reader is differential gain at **10 Hz**; it is not DC gain.
Bandwidth remains a partially qualified sampled-reference interpolation and
cannot yield specification PASS/FAIL. Phase margin, power, offset and slew rate
remain unqualified until their scientific extraction requirements are met.
Other measurement families/readers require a future reviewed extension; this
phase does not pretend to evaluate every possible Cadence quantity.

## MCP workflow

1. `cadence_list_specifications(design_id)` lists up to 32 registered descriptions.
   An empty reference list reports `target_status = not_selected` and
   `spec_evaluation = not_evaluated`.
2. `cadence_describe_specification(request={design_id, spec_id})` returns the full
   path-free contract and its current `contract_sha256`.
3. `cadence_evaluate_specification(request={design_id, spec_id,
   expected_contract_sha256, operation_id})` evaluates a registered goal against
   one admitted completed UUID4. `operation_id` may be omitted when no completed
   measurement has been selected. Facts are read through the existing registered
   analog/measurement/analysis chain, never accepted from the client.

All three tools are read-only. Requests reject unknown/extra fields, paths,
expressions, caller measurement payloads, targets and units. Unknown design/spec
IDs and stale contract hashes are errors before transport.

## Evaluation precedence and failures

After validating registered identity and the current contract hash:

| Order | Condition | Result |
| --- | --- | --- |
| 1 | No selected numerical target | `NOT_EVALUATED`, no source read |
| 2 | Registered measurement has no eligible qualified reader | `UNQUALIFIED`, no source read |
| 3 | No operation selected for an eligible reader | `MISSING_MEASUREMENT`, no source read |
| 4 | Unadmitted/wrong-design/wrong-analysis UUID, malformed/failed/unavailable source | Bounded tool error; never specification FAIL |
| 5 | Reader returned partial or unqualified measurement | `UNQUALIFIED`, preserve source facts when available |
| 6 | Qualified source differs from expected effective conditions | `CONDITION_MISMATCH`, preserve actual provenance |
| 7 | Qualified exact-condition measurement meets/misses target | `PASS` / `FAIL` |

`MISSING_MEASUREMENT` represents an omitted operation, not a swallowed transport
or simulator failure. Targetless evaluation does not validate or claim completion
of an optional UUID. Missing-target/reader responses make no measurement claim.
Neither partial measurements nor condition mismatches proceed to comparison.

Comparison uses Decimal against the source float's shortest round-trip decimal.
It never rounds to display precision, applies a tolerance, converts units,
extrapolates or adjusts goals. Equal endpoints are included in `range`. A displayed
rounded value must not be used to reproduce a near-boundary decision.

## Conditions, provenance and reproducibility

Evaluation includes the registered contract/hash, requested operation, status,
reason, source analog result and its canonical digest. That result preserves the
definition, unit, quality, source-result digest and complete measurement provenance:
analysis plan/contract, effective settings, revision, operating point, protected
fingerprints, model/circuit/input/frame/native-result hashes and warnings.
The specification's analysis ID must belong to the design and match a bound
source reader; runtime plan identity must equal the expected hash.

The full effective-settings hash additionally prevents matching just VDD/bias
while silently ignoring input common mode, load, stimulus or analysis settings.
Each returned decision has scope `one_operation_exact_registered_conditions`.
A PASS at NN/27 C/1 V is not a PASS across PVT, another revision, another
measurement definition or the latest FS improvement design. The reference reader
remains pinned to the previous native revision; broader corner readers are future
work. Condition-bound contracts permit separate future PVT goals without adding
automatic worst-case search now.

Repeated and concurrent evaluation/restart performs deterministic reads against
the same admission/result. No new goal/evaluation database, simulation, extraction,
reservation or replay domain is introduced. Stored measurement results remain
unchanged. v7's sweep identity is computed by revalidating its complete v6 projection,
which then revalidates the v5 execution projection. Only new read-only specification
and analog metadata are excluded; every execution field stays hashed.

## Security, qualification and release boundary

The server now has **69** typed tools. Previous 66 complete schemas remain
unchanged. No arbitrary command/path/script/netlist/PSF/PDK interface is introduced.
Source/ADE/PDK, historical jobs, ledgers, journals and evidence remain protected;
measurement evaluation grants no storage deletion authority. The same Codex and
Claude stdio package/configuration is used. SDK protocol qualification does not
establish Desktop app E2E: `CLAUDE_REAL_CLIENT_UNVERIFIED` remains explicit.

This phase preserves 62/500 Spectre attempts and 7,114,588,160 / 10,737,418,240
cumulative result-reservation bytes, the removed elapsed ceiling, shared EDA lock
and max(2 GiB, 10%) disk floor. No refunds/resets or new simulation are required.
Apache-2.0 covers original bridge code only; Cadence/PDK/client terms remain
separate. Imported planning redistribution remains `LEGAL_REVIEW_REQUIRED` and
excluded from curated distributions. No tag, release or version bump is activated.

Optimization, range expansion, candidate generation, bias search and schematic
editing remain future phases. The next recommendation is Release Readiness
reassessment, with actual client evidence and licensing blockers still tracked.
See [phase result](SPEC_CONTRACT_01_RESULT_V1.md).
