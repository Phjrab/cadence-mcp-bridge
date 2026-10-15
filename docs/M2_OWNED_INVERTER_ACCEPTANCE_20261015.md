# M2 owned inverter: acceptance and operator integration

This is unpublished development behind draft PR160. Published2.0.0 does not include
this generator. The supported observation is the current professor-provided
standard VM and its existing PDK, with the exact observed single-finger MOS form.
No other version, PDK, host or physical signoff is qualified.

## Operator-only API and runner obligations

`cadence_mcp_bridge.m2_cdf` provides `CdfSource`, a fixed bounded collector and
typed frame parsing. `cadence_mcp_bridge.m2_inverter` provides `OwnedInverterPlan`,
`observed_devices`, `render_generator` and `verify_generated_netlist`.
These are package APIs, not a new turnkey CLI or public MCP write tool.

The runner must bind a `RevisionBinding`, complete authenticated CDF frame/hash,
exact registered source masters and fresh owned destination library/cell names.
It must hold the existing resource lock, snapshot original source/model/state,
use the trusted ordinary-user OCEAN binding, bound time/output and preserve partials.
Calling the renderer alone does not provide these execution or protection gates.

The observed form preserves w/fw/l/m/fingers/model/areas/perimeters and accepts
only one finger with w=fw and the two observed derived expressions. It evaluates
no CDF callbacks and infers no general nf meaning or PDK parameter range. Unknown
metadata, expressions, collisions and connectivity/property drift block writes.
The writer creates a new DUT, symbol and hierarchical bench, checking before save
and after reopen. It never copies an existing DUT as evidence of creation.

After common-template netlisting, call `verify_generated_netlist(plan, frame,
native_bytes)` in addition to existing model/include/analysis/effective-input
guards. This independent check binds topology and effective device/stimulus/load
values to the observed plan; a candidate-derived static hash alone is insufficient.
Register only qualified owned inputs through the existing operator runtime path.
Activation and every execution retain existing confirmation/grant/budget/replay
checks. Import, parsing or dry-run never activates or executes a design.

## Actual execution and replay evidence

Exact installed commit: `0ae58c5d374d69c26d63f31cf1ebd0a1c72e8bf6`.
Native manifest: `3962c6deccf25a52bee35ba8cde783877bb5859a8922721fa9dc013543e6b3e0`.

| Route | Retained operation ID | Actual outcome |
| --- | --- | --- |
| DC | cada0681-b028-4cc7-b39e-95619f60b3ff | SUCCEEDED, automatic extraction, bounded result |
| TRAN | 5a3b4e62-b4a0-4c96-8647-7d7b6701d044 | SUCCEEDED, automatic extraction,98 samples/node |
| Same-process repeats | Same two IDs | Same status/results, no additional spend |
| New-process submit/query/result | Same two IDs and plan hashes | Same status/results, no additional spend |

The admitted conditions and numerical limits are in [the current outcome](M2_OWNED_INVERTER_01.md).
DC output is0.4046511906222007V at0.5V input; supply power is
1.619951780607305e-5W. TRAN output remains0.8317364241357567–0.9999859756429078V
over6ns with1pF load. Values are finite and within the observed rails, but this
does **not** establish logic switching, settling, slew or any performance target.
No specification was evaluated. The result is execution/extraction acceptance.

Before:126 attempts/15,452,864,512 reserved bytes. After:128 attempts/
15,721,299,968 bytes. Delta2/268,435,456 bytes; ceilings500/17,179,869,184.
New-process verification delta0/0. Reservation accounting is not actual disk size,
and cumulative shared attempts include earlier non-Spectre recovery accounting.
Original journal/domain/lock, spent grants and all prior source/failure evidence
remain. The admitted grant has no unused execution allowance.

Private evidence stays in ignored `.tmp/m2-actual-cdf-v4`,
`m2-actual-owned-inverter-v3`, `m2-actual-owned-input-v2`, `m2-owned-runtime-v1`
and the exact installed artifact directory. Raw CDF/PDK/netlists/PSF, connection
settings and approvals are intentionally excluded from the repository/package.

## Final review and source scope

Review4284403269's pulse vdc-unit requirement was fixed in0ae58c5.
Review4284536573's instance-identifier gap is corrected by matching the parser's
full hyphen/hash/64-character grammar. Both retained actual netlists pass the
corrected verifier and six extra-device mutations reject. Writer output and all
native runtime assets are unchanged, so no additional simulation is needed.
V15/checkpointV8 retain32 source versions and spend one local correction:33/33.
Direct human approval is the authority, not the generated policy record.

Final corrected-source artifacts/hosted checks and refreshed automated review
are pending until their exact source SHA is recorded. Automated review is never
formal human APPROVED. No PR160 merge or publication is inferred.

Actual app submission is NOT_TESTED_THIS_M2_SLICE; local installed SDK execution
does not substitute for actual Codex/Claude app evidence. Claude is excluded.
Layout, DRC/LVS/PEX, post-layout and optimization remain unimplemented/unverified.
