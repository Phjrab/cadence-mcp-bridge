# MEAS-CONTRACT-02: signed DC power discovery and specification binding

## Client workflow

`cadence_measurement_catalog(design_id)` returns at most six legacy analog
descriptions, one separate signed DC power description and 32 complete operator
specification descriptions. It performs local registration/eligibility checks;
it does not read simulation artifacts or establish their scientific qualification.
Use the named reader in the catalog with that description's exact hash and an
existing admitted operation UUID. The same `analog-power` logical ID has two
explicit definition/hash/reader bindings:

| Binding | Reader | Meaning |
| --- | --- | --- |
| Original analog v1 power | `cadence_analog_measurement_result` | UNQUALIFIED; no signed-current source |
| `dc-supply-power-v1` | `cadence_power_measurement_result` | Previously qualified fixed-reference DC rail power |

Never substitute the old analog hash for the signed-power hash. The latter binds
the compiled definition, original analog registration and unique registered
native DC source. `read_eligible` does not mean an extraction exists for an
arbitrary operation. The existing reader still accepts only the reviewed admitted
reference DC operation and pins input/PSF/frame/extraction hashes.

Catalog specification descriptions contain the complete operator contract,
conditions, target status and digest. Call
`cadence_evaluate_specification_v2(request={design_id, spec_id,
expected_contract_sha256, operation_id?})`. No MCP target, unit conversion,
formula, registration, path, script or source-result payload is accepted.

## Operator registry v8

Use [schema v8](schemas/design-registry-v8.schema.json) and the
[fictional targetless example](examples/design-registry-v8.fictional.json).
Local CLI `design schema --schema-version 8`, `validate`, `register`, joined
`verify` and stdio client export reuse their existing operator paths. Explicit
configuration is required; the built-in registry remains v4.

v8 retains all v7 fields and adds `power_specification_contracts`. Its entries
have `contract_version=2` and unit W. They bind the signed power reader's exact
contract and compiled `PowerDefinition` hash, a registered power metric and its
unique native DC source's analysis ID. Spec IDs are unique across both arrays;
the combined limit is 32 per design/128 power entries per catalog. Missing or
ambiguous native DC sources, old power-definition hashes, other metrics/units
and duplicate IDs are rejected. Registration alone does not qualify a reader.

Execution/replay identity is the complete revalidated v7 -> v6 -> v5 projection.
Only new read metadata is excluded. Old goals, schemas and durable admissions
retain their hashes and semantics. v1-v7 files remain supported exactly.

`cadence_runtime_info_v2()` honestly reports v1-v8 loaded catalogs with observation
schema version 2. The original runtime-info schema is preserved and works for
v1-v7; a v8 process rejects that old observation with a bounded instruction to
use v2. No catalog version is clamped or misreported. Neither observation checks
journal health, licensing or execution entitlement.

## Scientific and evaluation boundary

The power definition and extraction are unchanged from
[ANALOG-POWER-01](ANALOG_POWER_V1.md): signed sum(-V*I), VDD/VSS rails only,
bias/input and all-source contributions separate, all six sources required.
The reused result is 82.42816 microW at NN/27 C/VDD 1 V/applied bias 320/702 mV.
This phase does not rerun Spectre or qualify another condition/design/job.

v2 evaluations contain the actual `PowerResult` (including six sources,
contributions, hashes and provenance) or the original `AnalogResult`. They do
not project power into the old analog result schema. Legacy goals delegate to
the original supervisor; power goals use the existing admitted power reader.
Both use the same Decimal comparator and complete effective-condition matcher.
No rounding, tolerance or unit conversion is introduced.

| Situation | Result |
| --- | --- |
| Target not selected | NOT_EVALUATED; no source read |
| Qualified binding, no selected operation | MISSING_MEASUREMENT |
| Reader/result unqualified | UNQUALIFIED |
| Plan/revision/point/corner/temperature/VDD/bias/full settings differ | CONDITION_MISMATCH |
| Qualified fact at exact selected conditions | PASS or FAIL against operator-recorded user goal |
| Unknown/stale/unadmitted/substituted/failed source | Bounded error, never specification FAIL |

No numerical reference goal exists. The reference v8 factory has empty goals.
The private real-result regression uses a targetless contract envelope and
reports NOT_EVALUATED. Fictional unit-test targets only exercise the comparator;
they are not design requirements or actual specification PASS evidence.

## Verification and preserved boundaries

The separate [additive schema snapshot](contracts/MCP_MEAS_CONTRACT_V2_SNAPSHOT.json)
records three read-only tools, total 75. All old 72 full schemas and published
v1-v7 registry schemas remain exact. The package version remains 1.0.0; release
version selection and publication require separate review/authority.

Tests cover exact bindings, decimal boundaries, every condition, malformed and
unknown/stale queries, unavailable/unadmitted/extraction failure, targetless
no-I/O, repeated/concurrent/restarted reads, CLI loading and old-engine dispatch.
Installed wheel checks exercise v8 plus legacy goal behavior in Codex, Claude
and generic JSON **SDK subprocess configurations**, not actual desktop apps.
Preserved real DC/AC/TRAN/sweep reads are checked without new simulation.
See [phase result](MEAS_CONTRACT_02_RESULT_V1.md).

Original OA/ADE, PDK, vendor installation, jobs/results, ledgers, replay/admission
and prior evidence remain protected. No deployment, deletion or compaction is
introduced; no resource counter is reset/refunded. Apache-2.0 applies to bridge
original code only. Imported planning/export/legal boundaries remain unchanged:
IMPORT_EXCLUDED_VERIFIED is candidate-specific; LEGAL_REVIEW_REQUIRED and
PUBLICATION_NOT_AUTHORIZED remain. Claude actual app and other environments
are deferred. No optimization or new scientific range is activated.
