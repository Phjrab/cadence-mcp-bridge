# Registered measurement contracts v1

GENERIC-MEAS-01 adds design registry **v4**, three read-only MCP interfaces and
projections of validated bounded native analysis results. Measurement is separate
from simulation and specification evaluation. Existing v1/v2/v3 schemas, analysis
plan hashes and durable admission identities are retained. See the
[v4 schema](schemas/design-registry-v4.schema.json) and
[fictional unqualified example](examples/design-registry-v4.fictional.json).

## Operator registration

Use the existing design registry and configuration mechanism:

```powershell
uv run cadence-mcp-bridge design schema --schema-version 4
uv run cadence-mcp-bridge design validate --registry C:\private\proposed-v4.json
uv run cadence-mcp-bridge design register --registry C:\private\proposed-v4.json --output C:\private\new-registered-v4.json
```

Registration exclusively copies a new local file. The server snapshots
`CADENCE_MCP_DESIGN_REGISTRY_PATH` at startup. Migration is explicit: old versions
remain valid and expose declared measurement IDs but no registered readers.
The built-in reference defaults to v4 without changing its profile, variables,
analyses, fixed inputs, PDK or original admission hashes. Operator-owned
configuration/ACL remains a trust boundary; MCP cannot register/change it.

| Measurement contract field | Meaning |
| --- | --- |
| contract_version | Integer 1 |
| design_id / measurement_id | Exact registered design and allowed logical measurement ID |
| analysis_id | Exact analysis registered under that design |
| analysis_contract_sha256 | Canonical hash of the whole analysis contract, transitively binding profile/variables/adapter |
| reader | native-bounded-result-v1 or unqualified |
| output_id / definition_sha256 | Exact compiled definition and canonical hash; both null when unqualified |

Compiled readers require the reviewed fixed native analysis and matching mode.
Changing design/environment/PDK and recomputing hashes cannot activate them.
Duplicate/orphan/undeclared IDs, stale hashes, wrong modes, arbitrary expressions,
signals, scripts, paths, targets and unknown versions are rejected. Existing
65,536-byte registry, 16-design and 32-ID-per-allowlist limits remain; at most 512
measurement contracts fit the schema subject to the stricter serialized bound.
Hashing identifies exact contracts; it does not certify a new circuit.

## Qualified definitions

| Reference measurement ID | Compiled output ID | Meaning and bounds |
| --- | --- | --- |
| dc-scalars | dc-node-scalars-v1 | Exactly seven node/derived voltage scalars, V; validated native DC relationships |
| ac-spectrum | ac-differential-spectrum-v1 | 70–72 existing differential transfer samples; Hz, V/V, dB and degrees; validated frequency/gain relationships |
| tran-summary | native-tran-summary-v1 | One native adaptive transient summary: timing/count, extrema and verified fixed stimulus; no raw waveform/FFT |

Method: `validated_native_result_projection_v1`. Units, quantity and bounds come
from compiled original definitions. This phase does not calculate bandwidth,
phase margin, power or transistor OP metrics; those require their own qualified
definitions/extraction evidence. Existing synthetic ADC APIs remain separate.

The physical reader covers the pinned reference native revision/operating point,
not the latest FS work copy or every historical PVT/OP job. Existing native
guards validate effective inputs. Candidates 320/702 mV and VDD=1 V constraint
retain their semantics; no optimality or numerical specification is claimed.

## MCP workflow

1. `cadence_list_measurements(design_id)` returns declared IDs, registered
   method/units/bounds and read eligibility locally, without SSH.
2. `cadence_describe_measurement(request={design_id, measurement_id})` returns
   the current `contract_sha256`, bound analysis plan and qualification.
3. `cadence_measurement_result(request={design_id, measurement_id,
   operation_id, expected_contract_sha256})` reads one completed admitted UUID4.

The operation must already be admitted through registered analysis lifecycle.
Knowledge of a legacy job UUID does not grant admission. This reader never
adopts/registers jobs, submits simulation, reserves results, changes circuits,
repeats PSF extraction or creates a measurement journal. It reads the existing
analysis journal without adding/resetting records. Retries/restart read the same
durable identity. Eligibility is compatibility, not arbitrary job completion,
fresh environment qualification or execution authority.

Stale/unqualified/unadmitted requests fail before remote result transport.
The existing analysis path enforces PDK compatibility, plan/admission identity
and native job/analysis identity. Full native result validation precedes a valid
measurement. Simulator/extraction/shape/provenance failures remain errors.

## Results and scientific integrity

The result projects only the validated scalar set, spectrum or transient summary,
with IDs, definition, contract hash and provenance. Provenance retains analysis
plan/contract/definition hashes, canonical whole native-result hash, PSF/frame
hashes, source/copy/state/model/circuit/input/owned-variable fingerprints,
revision/operating point, effective fixed settings and warning/notice counts.
No private source bindings, paths, PSF/netlist/model bytes, license data or caller
arrays are exposed. Existing transport caps and typed output bounds apply.

`quality = valid` denotes qualified extraction/shape.
`spec_evaluation = not_evaluated` is unconditional. There is no specification
target, threshold, score, pass/fail or optimization setter. Results are
observations of their identified revision, not new design claims.

## Verification and recovery

Tests cover projection/provenance/restart, unchanged journal bytes, rejection
before transport, invalid-result rejection, closed MCP schemas, old schema/plan
compatibility and exclusive v4 registration. Actual SDK stdio from Codex/Claude
settings compares three measurements to preserved native DC/AC/TRAN including
hashes/restart; fresh protected/job/counter checks are equal without simulation.
This does not qualify either real desktop application.

Restore the reviewed v4 snapshot/settings and preserve the existing admission
journal. Never reset/recreate it to adopt an unadmitted result. Missing physical
adapters, electrical ranges, desktop E2E and imported rights remain explicit.
See [phase result](GENERIC_MEAS_01_RESULT_V1.md).
