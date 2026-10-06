# ANALOG-POWER-01: preserved native DC supply power

## Current contract integration

MEAS-CONTRACT-02 adds bounded combined discovery and operator v8/version-2
power specifications using this unchanged reader/definition. Original v7 goals
and analog v1 power remain unchanged. Reference goals are still absent;
NOT_EVALUATED is not PASS. See [versioned binding](MEASUREMENT_BINDINGS_V2.md).
The sections below preserve the original power-phase architecture/evidence.

## Definition and qualification scope

`dc-supply-power-v1` measures **DC power delivered by the reference VDD/VSS
rails** at NN, 27 C, VDD 1 V and the applied 320/702 mV bias candidate. It is
qualified for one preserved admitted reference native DC operation only. This
is not transient/average/peak power, a PVT qualification, device-by-device
dissipation, an optimized candidate or specification PASS.

The complete six-source inventory includes the two rails, two ideal bias sources
and two ideal input sources. Bias/input contributions are separate from rail
power. `all_sources_delivered_power_w` includes all six sources. Ground is an
explicit zero-volt supply: its measured current is still required. A zero voltage
does not justify treating missing current as zero.

The installed simulator's voltage-source documentation establishes current in A
as positive from the positive terminal, through the source, to the negative
terminal. The measured voltage is positive minus negative terminal voltage in V.
Delivered power is **-V × I**, summed with signs retained. An absorbing source
contributes negative delivered power; no absolute value is taken. Fixed DC
terminal-current samples independently agree with the same PSF's source OP `i`
fields, and V × I agrees with OP passive `pwr` fields for all six sources.
Vendor documentation and raw frames remain private. Printed scalar precision is
retained; no greater numerical accuracy or energy-balance claim is made.

## Registration and read workflow

Existing operator registry v6/v7 supplies the registered power analog ID plus
one qualified `dc-node-scalars-v1` source. The description binds the original
analog contract, exact registered DC contract and separate power definition
digests. No second configuration system, new registry version or default
catalog change is introduced. Default v4 has no registered analog power metric.

1. `cadence_describe_power_measurement(request={design_id, measurement_id})`
   gives the separate power contract hash, definition and source measurement ID.
   `read_eligible` assesses registration/adapter compatibility; artifact
   availability is explicitly not assessed and no execution is authorized.
2. `cadence_power_measurement_result(request={design_id, measurement_id,
   operation_id, expected_contract_sha256})` reads the reviewed pre-extracted
   reference operation. It checks existing durable admission and native/PDK
   validation first, then input/PSF/frame and whole extraction receipt identity.
   Other operations, stale contracts, missing admission and modified receipts
   fail closed. The operation UUID comes from existing admitted analysis evidence.

The result contains W, definition, six signed sources, separated contributions,
the original source-measurement provenance and distinct power-frame/extraction
digests. No raw PSF, path, circuit, formula or execution argument is accepted.
MCP cannot deploy the helper, initiate extraction or run a new simulation.
Repeated/restarted requests only read the same admitted source and artifact.
Transport errors preserve their stable category without helper traceback paths.
The immutable v2 result-only adapter permits valid ledger state at the 500-attempt
or 10 GiB ceiling: reading consumes no reservation. Invalid/over-ceiling accounting
is still denied. The original v1 extraction/receipt remains unchanged.

The original `analog-power` v1 definition/result remains UNQUALIFIED through
`cadence_analog_measurement_result`: that historical source contract has no
signed currents. The separate API prevents changing old schemas or goal hashes.
Current v7 specifications still bind original analog v1; connecting this power
definition to goals requires a separately versioned future contract. Reference
numerical targets remain absent and `spec_evaluation=not_evaluated` is unchanged.
The old `cadence_measure_dc_power` remains an ADC synthetic fixture.

## Fixed operator extraction and protection

`scripts/analog_power_extract.py` is an operator-only, exact-policy/private-
delegation-bound workflow. It stages three reviewed files immutably and creates
one bounded owned extraction record under the registered managed root. Deployment
and read intents are exclusively reserved before transport; uncertain outcomes
are preserved for investigation. A separately sealed `deploy-read-adapter` adds
only the v2 result reader. Existing runtime `result` is a fixed read only.

The extraction uses existing EDA lock, idle-worker check, native environment/disk
floor, manifest, containment, complete fixed source inventory, input and PSF
fingerprints. It writes no preserved native job, OA/ADE/PDK or accounting file.
Its bounded 8 MiB output allowance is checked against unused capacity in the
existing source-job 128 MiB reservation. It consumes zero new Spectre attempts
and zero new reservations. The independent OP crosscheck is another small owned
evidence directory; its bytes are included in that allowance. Nothing is deleted.
The fixed stage is reference specific; onboarding a new design does not create
a current reader or qualify its supplies.

No API/schema changes to the prior 70 tools or v1-v7 registries. Version remains
1.0.0; no release is created. Claude actual app remains deferred/unverified.
Apache-2.0 covers the bridge code only; installed vendor/PDK materials stay
separately licensed and outside the repository. Existing imported planning
`LEGAL_REVIEW_REQUIRED` is unchanged. See [phase result](ANALOG_POWER_01_RESULT_V1.md).
