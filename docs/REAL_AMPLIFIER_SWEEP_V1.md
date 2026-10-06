# Registered finite reference amplifier sweeps

The compiled adapter reuses the existing `SweepStore`/`SweepSupervisor` engine,
SQLite journal, deterministic UUID5 child identities and shared EDA/resource
ledger. It adds explicit version2 engine codecs; legacy RC/v1 identities and all
prior78 MCP schemas remain unchanged. The five additive tools are:

- `cadence_prepare_amplifier_sweep`
- `cadence_submit_amplifier_sweep`
- `cadence_amplifier_sweep_status`
- `cadence_amplifier_sweep_result`
- `cadence_cancel_amplifier_sweep`

## Registered scope

Operator selection of [the qualified numeric registry](config/reference-amplifier-finite-grid-v1.json)
and the exact registered reference PDK adapter is required. Other registries,
including the default unqualified reference and the general v8 catalog, cannot
activate this route. The registry carries reviewed logical bindings and evidence
digests; it contains no PDK models, private absolute paths or license values.
It remains numeric-only for the legacy generic analysis interface. This compiled
adapter supplies the separately versioned DC/AC execution binding.

| Binding | Permitted value |
| --- | --- |
| Design | `reference-differential-amplifier-tb2` |
| Variable / unit | `vbiasn` / `V` |
| Values | One to three unique members of `0.319`, `0.32`, `0.321` |
| Fixed values | `vbiasp=0.702`, `vdd=1` |
| DC analysis / measurement | `grid-dc-v1` / `dc-supply-power-grid-v2` |
| AC analysis / measurement | `grid-ac-v1` / `gain-10hz-grid-v1` |
| Conditions | NN,27 C,VCM0.5 V,existing topology,no added external load |

No linear interval, caller variable name, path, script, expression, raw result or
netlist is accepted. Canonical decimal formatting cannot create a fourth point.
This is finite nominal simulation qualification; continuous-range safety,
device reliability/ratings, another PDK/version/load/PVT and optimization remain
outside its evidence. The original source/ADE and saved300/650mV state are retained.

## Scientific definitions

Gain is differential voltage gain at10 Hz, from the original bounded qualified
AC reader. It is neither a DC gain nor loop gain/Phase Margin.

`signed-dc-supply-rail-power-grid-v2` is a separate definition from the preserved
center-only power reader. Each of six registered voltage sources contributes
`-Vterminal * Ipositive_into_source`; current sign is never discarded. Supply rails
VDD/VSS form the main sum; bias and input sources and the all-source total are
reported separately, without duplication. Zero-volt VSS contributes zero power
while retaining its signed current. This is static supply-rail delivered power,
not a DUT-only boundary or transient mean power. Missing current/voltage,
inventory/sign/condition mismatch, nonfinite data or unacceptable simulator quality
cannot produce a qualified measurement.

Each successful point includes effective values, versioned definition digest,
source input/PSF/frame/result hashes, deterministic child identity, its admission
counter and bounded measurement. PM/Offset remain UNQUALIFIED and are not required
for success. Targets are absent; no PASS/FAIL design assessment follows.

## Replay, guards and cancellation

Preparation binds the complete plan hash; submission requires that hash and an
experiment UUID. Same key/plan resumes or reads the same journal identity. A key
cannot be rebound to another plan. Reservation and submit are distinct durable
steps; lost responses use exact-child lookup and never blindly resubmit. A
terminal successful point is retained across replay and server restart. Unknown
outcomes require reconciliation. Failed points remain explicit and do not become
specification failures; bounded partial results retain successful point facts.

The immutable reference qualification activation allows six new128MiB
reservations starting at76 attempts/8,993,636,352 reserved bytes. It uses the same
500-attempt/10GiB cumulative limit and existing disk floor. Successful replay
does not reserve or execute again; consumed reservations are never refunded.
This activation does not authorize unlimited further experiments after its six
slots. An advanced external ledger makes this strict campaign verifier refuse
rather than silently ignore new accounting; a later timeless reader requires a
separate reviewed version if necessary.

Cancellation stops unstarted points only. An active point continues under the
existing EDA lock, and its completion is recorded. The parent remains RUNNING
while that active point is being reconciled, then CANCELLED with successful facts
retained. Cancelling a completed sweep is a no-op. There is no qualified active
simulator termination. A reservation interrupted before launch can consume a slot
without executing; it is never automatically refunded or restarted.

Prepared-input reads use exact no-follow copied-input/reversed-source hashes
while the owned worker is active. Full original/ADE/PDK/prior-evidence checks are
required before launch and after extraction. This avoids falsifying the old
quiescent protection checkpoint. Manifest checks, exclusive creation, owned
leases, bounded time/file/output guards and whole-result receipts remain required.

## Configuration and evidence

The operator sets `CADENCE_MCP_DESIGN_REGISTRY_PATH` to the reviewed registry and
retains a valid registered PDK catalog. Both engines select the same
`CADENCE_MCP_SWEEP_JOURNAL_PATH`; separate client configurations should deliberately
select the journal containing their evidence. Global app configuration is not
changed by qualification. Observe loaded versions/digests with
`cadence_runtime_info_v2` before use.

The [phase result](REAL_AMPLIFIER_SWEEP_01_RESULT_V1.md) distinguishes synthetic
guard tests, actual Cadence runs, SDK subprocess protocol evidence and actual app
qualification. Claude's full gate remains `CLAUDE_REAL_CLIENT_UNVERIFIED`.
Apache2.0 covers original bridge code only. Cadence/PDK/client terms and imported
planning `LEGAL_REVIEW_REQUIRED` remain separate; publication is not authorized.
