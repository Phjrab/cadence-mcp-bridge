# WP14-CLOSEOUT — bounded work-copy characterization

Date: 2026-09-30. Outcome: `CHARACTERIZATION_COMPLETE_SPEC_NOT_EVALUATED`
for the pinned work-copy revision. This is a diagnostic closeout. It does not
claim a design-specification PASS, original OA/ADE bias change, or physical
verification signoff.

## Evidence and result

The closeout read the preserved private `AUTO-PHASE-01` journal and its result
bytes. Prior DC, AC, differential DC, scalar-reader, and MOS CDF operations have
terminal success records and matching local result digests. Older uncertain
reader/discovery claims remain preserved and were not replayed. The private
review also recalculated the reported scalar relationships, checked predecessor
result identity, and reconciled the limited CDF-to-generated-netlist comparison.
No simulation, Cadence read, deployment, or remote operation was repeated for
this closeout.

The user-proposed 320/702 mV bias pair was applied only to bounded job-local
copies. VDD=1.0 V was maintained in those jobs. The observed operating
conditions, measured values, individual job identities, protected fingerprints,
and exact calculations are retained in the ignored private local report
`.codex/wp14-closeout-private-result.json` and the existing private journal.
This repository document does not contain raw circuit results, PDK data,
generated netlists, PSF data, or device parameters.

The verified scope is requested candidate → job-local application → completed
simulation → scalar extraction → local arithmetic. The earlier original
OA/ADE settings were not changed. The current MCP interface does not expose
these operator-only job-local DC/AC/CDF workflows or a parameterized sweep.

## Limits and unresolved findings

The remaining cumulative resource limits and replay controls are unchanged.
The user-removed elapsed ceiling remains removed. Protected-object unchanged
reports apply to their recorded execution windows; this local closeout did not
make a fresh live-VM integrity claim.

No numerical design acceptance target was supplied, so specification evaluation
is `NOT_EVALUATED`. Original source/ADE semantic equivalence to an older
snapshot, candidate application to original OA/ADE, loaded behavior, PCell/LVS,
and stability margin remain unverified. Reader/CDF agreement for the pinned
revision does not establish PDK parameter semantics or physical signoff.

## Proposed next step

`SIM-MCP-01` is a proposed separate phase, pending the user's choice. It would
specify a fixed typed MCP input for a pinned work-copy revision and closed
analysis choices, returning bounded scalar summaries and provenance. It would
enforce replay, drift, single-job, disk, result-size, and cumulative simulation
limits. It would exclude arbitrary paths or SKILL/OCEAN, original OA/ADE writes,
optimization, PDK publication, layout, signoff, and an unsupported claim that
an old snapshot represents the live design.
