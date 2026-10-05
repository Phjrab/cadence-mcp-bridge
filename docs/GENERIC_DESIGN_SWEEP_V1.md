# Registered design 1D sweep preparation v1

GENERIC-SWEEP-01 **prepares contracts and plans**. It does not implement real-design
sweep execution. The existing fixture sweep lifecycle is retained. No new
registry version/configuration, physical adapter or numeric review is introduced.
Operator-owned registry v4 supplies variables/reviews, analyses and measurements.
The [request JSON schema](schemas/design-sweep-request-v1.schema.json) describes
the closed planning input; descriptions also expose the current contract hash.

## MCP workflow

1. Select exact registered design, analysis, variable and same-analysis measurement
   IDs from existing inspection tools. Call `cadence_describe_design_sweep` with
   `request={design_id, analysis_id, variable_id, measurement_ids}`.
2. Inspect its `contract_sha256`, axis contract, required fixed IDs and blockers.
   The hash binds the whole startup design registry (including separate numeric
   reviews), PDK registry, analysis plan and compiled planning policy. Hashing uses
   canonical JSON with the contract hash field replaced by 64 zeroes.
3. Call `cadence_plan_design_sweep` with that selection/hash, axis `unit`, exactly
   all other variable `fixed` values (each `{value, unit}`), and either explicit
   `values` or `linear={start, stop, step}`. Values are bounded decimal strings.

One axis, one analysis and 1–16 unique points only. Linear arithmetic uses exact
bounded decimal precision, accepts either direction, and must land exactly on
stop; no overshoot, implicit endpoint or automatic range expansion. Canonical
equivalent explicit/linear inputs generate equal plans. Fixed input order is
canonical; no defaults are filled. Units, integer/grid/range/fixed constraints,
mutation and owned-copy policy reuse existing variable checks.

Unknown IDs, cross-analysis measurements, stale hashes, extra fields, nonfinite
or non-string numbers, duplicate canonical values, missing/extra fixed values,
wrong axis unit and oversized/inexact sequences are rejected. Numeric denials
for known contracts are returned explicitly, including unqualified ranges and
fixed constraint mismatches. A fixed variable cannot become a sweep axis.

## Result semantics

Description/planning is local and read-only. Its content contains logical IDs,
opaque hashes, numeric contract metadata and bounded numeric checks. Private
Cadence bindings, review evidence content, paths, scripts, netlists, raw PSF and
targets are absent. Shared fixed checks appear once to bound output size.

Every point is **NOT_RUN**. No job UUID, durable admission, reservation, measurement,
effective input or circuit modification is created. `plan_hash` is reproducible
planning identity only: it hashes the complete returned plan with its own field
replaced by 64 zeroes. It is not a resume checkpoint for remote execution.

`locally_admissible` means explicit numbers match local reviewed contracts and
axis mutation policy. `execution_authorized=false` and
`parameterized_execution=unqualified` are unconditional in this phase, including
for numeric fixture contracts. `spec_evaluation=not_evaluated` remains unconditional.
No API accepts this plan for execution; the fixture submit tool retains its own
closed profile/plan/replay validation.

## Scientific and execution prerequisites

The reference amplifier's continuous bias ranges remain unqualified. Historical
finite candidate pairs, including 320/702 mV, do not establish a safe continuous
range. VDD=1 V remains a fixed constraint. A blocked plan is not a range review,
simulation, design PASS or claim that a candidate is optimal.

Actual real-design sweep execution still requires reviewed numeric bounds and a
parameterized physical adapter with effective-input verification. That later
adapter must reuse EDA locking, cumulative attempt/storage reservation, disk floor,
UUID/replay, durable resume and cancellation, protected fingerprints and bounded
registered measurements. No existing budget/cancellation/admission guard is
simulated or bypassed by this planner. Missing scientific authority and missing
code capability are separate prerequisites. New environments/PDKs, multidimensional
sweeps and optimization remain unqualified.

Old registry v1/v2/v3/v4 schemas, fixed native plan/admission hashes, measurement
contracts and fixture sweep contracts remain unchanged. Explicit older registries
without required contracts fail closed. Restore the reviewed registry snapshot to
reproduce a plan; preserve existing journals. See the
[phase result](GENERIC_SWEEP_01_RESULT_V1.md).
