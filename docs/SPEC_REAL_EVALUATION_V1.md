# Real amplifier specification evaluation v1

The existing condition/comparison engine now accepts explicitly versioned
finite-grid gain and signed DC supply-rail power facts. Original specification
v1/v2, NativeSettings, power definitions, registry v1–v8 and Sweep identities
remain unchanged. This companion specification contract is version3; fact
settings/provenance and the companion registry are version1.

## Read-only workflow

1. Select the qualified finite-grid design/PDK registry and its existing Sweep
   journal as described in [the Sweep guide](REAL_AMPLIFIER_SWEEP_V1.md).
2. Read `cadence_amplifier_specification_catalog(design_id)` and its registry hash.
3. Read `cadence_amplifier_sweep_result` for an already admitted Sweep.
4. Call `cadence_evaluate_amplifier_specifications` with that registered design,
   Sweep ID, `expected_sweep_result_sha256`, and
   `expected_specification_registry_sha256`.

Digests use SHA-256 over the validated contract's canonical sorted compact JSON,
as implemented by `variable_contracts.canonical_digest`. The server rereads the
admitted source and plan and rejects stale digests. The client supplies no target,
observed value, expression, script or filesystem path. There is no submission,
optimization or cleanup in this read path.

## Operator goals

The companion catalog is empty by default. **No real numerical design goals are
registered: actual results are NOT_EVALUATED.** Synthetic test targets are not
project requirements. Goals must come from an explicit user requirement or an
authoritative design document; values are never fitted to observed measurements.

An operator may configure `CADENCE_MCP_AMPLIFIER_SPECIFICATION_REGISTRY_PATH`
locally. This setting is not an MCP input. The JSON file is regular/no-follow,
at most65,536 bytes, with integer `schema_version: 1` and `specifications` containing
at most16 unique version3 contracts. Duplicate JSON fields, nonfinite numbers,
ambiguous versions and stale bindings are rejected. Do not add credentials,
private paths or proprietary content to a catalog committed to the repository.

Each goal retains `spec_id`, `goal_id`, `design_id`, `measurement_id`, exact
measurement-binding/definition hashes, comparison, decimal-string target/unit,
and exact conditions. Comparisons reuse `>=`, `<=`, `>`, `<`, inclusive `range`.
Only `gain-10hz-grid-v1`/dB and `dc-supply-power-grid-v2`/W are eligible. No implicit
unit conversion, tolerance, cross-definition substitution or other PVT claim.

Conditions include analysis/plan, revision, operating-point identity, NN/27C,
VDD1V, applied VBIASN319/320/321mV and fixed VBIASP702mV. The effective-settings
hash additionally binds VCM0.5V, existing topology/no added external load,
reader/input policy and finite nominal scope. Saved300/650mV values remain
historical settings, distinct from effective applied values.

## Results and failure meaning

At most48 evaluation rows and three fact-provenance records are returned, with
an explicit65,536-byte serialized evaluation cap. Results retain the complete
bounded source, source/catalog/specification/measurement hashes, UUID5 child
identity, definition, input/PSF/frame/source hashes, effective settings and scope.
No raw PSF, netlist, PDK or private path is returned.

| Status | Meaning |
| --- | --- |
| NOT_EVALUATED | No registered/selected target; measured facts are retained. |
| PASS / FAIL | Qualified fact meets/does not meet an exact registered goal. |
| UNQUALIFIED | Partial, unqualified or missing numeric qualification cannot pass. |
| CONDITION_MISMATCH | Analysis/plan/revision/point/settings/PVT differ. |
| MISSING_MEASUREMENT | A selected goal has no completed fact, including cancellation. |
| SIMULATION_ERROR | Source point explicitly failed; not a design requirement FAIL. |
| SOURCE_UNAVAILABLE | Source outcome uncertain; not a design requirement FAIL. |

Absence of a target takes precedence in the evaluation row; the included source
still preserves simulation state/errors. Unknown source IDs or stale definitions,
catalog/result hashes, point/fact inventory or mode substitutions fail closed.
Restart rereads the same Sweep journal. Consumption counters are never refunded.

The evidence report separates real admitted Cadence facts reused from current
SDK subprocess checks, synthetic comparator/guard tests and actual desktop apps.
No new simulation is needed for this phase. PM/generic Offset remain unqualified;
Bandwidth/Slew/selected Offset diagnostics retain their separate partial scope.
Apache-2.0 covers original bridge code only; Cadence/PDKs retain their terms.
Imported planning remains LEGAL_REVIEW_REQUIRED; PUBLICATION_NOT_AUTHORIZED.
