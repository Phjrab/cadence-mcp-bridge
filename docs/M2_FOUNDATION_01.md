## Superseding bounded M2 outcome, 2026-10-15

Direct human approval subsequently authorized PR159 normal merge and the finite
actual inverter proposal below, with source24 to26. PR159 merged at f572fd9.
The first fixed collector failed on CDF metadata typing and its60s timeout;
partial observations are unqualified. Source25/26 is retained, actual ledger
126/15,452,864,512 unchanged, and generator/DC/TRAN are blocked. No corrective
collector version, this new phase PR merge or publication is implied.
See [current boundary and proposed next decision](M2_OWNED_INVERTER_01.md).
Earlier pending/not-authorized sections below retain their original scope.

# M2-FOUNDATION-01: local design revision and inverter plan

This development feature provides the first local design foundation after POST.
It adds no public MCP tool or remote execution route. Published 2.0.0 remains
unchanged. The latest direct user request permits this implementation, tests,
installed-package verification and feature PR; it permits conditional normal
integration of POST PRs154–158, but does not authorize merging this M2 PR.
Earlier phase exclusions remain historical records, not current instructions.

## Current integration status, 2026-10-15

The conditionally authorized POST154–158 merges are complete at stable main
`b3ac2ea3f9e37ce16e670c762e32775d7bfb904a`. This foundation normally incorporates
that verified tree while retaining its own CLI, metadata store and synthetic
boundaries. Initial M2 tip2f96697 passed both hosted OS checks; integrated local
273 tests pass/13 Windows platform skips, Ruff/mypy112 and compatibility pass.
Final integrated package/installed/hosted evidence remains pending; historical
M2 and POST artifacts do not substitute for those exact-source checks.
See [the acceptance record](M2_FOUNDATION_ACCEPTANCE_20261015.md).

Final POST installed retained reads/report checks preserve original report,
settings and journal hashes. Ledger126/500,15,452,864,512/17,179,869,184 bytes and
source24/24 remain unchanged; the integration adds no VM work or consumption.
Published2.0.0 remains immutable. PR159 is still a reviewable unmerged feature;
this status does not authorize its merge or the actual inverter proposal below.

## Revision contract

`design_revisions.RevisionStore` uses its own explicitly initialized SQLite
metadata file. It has no resource policy, grant, budget or job dispatcher. Existing
analysis/sweep stores remain unchanged and are rejected as foreign databases.
Before opening SQLite, the fixed header and journal mode are checked without
triggering recovery; this also preserves a foreign hot rollback journal.
WAL-format revision databases are unsupported. Initialization never adopts an
existing blank/partial/foreign file. A failed initialization stays visible for
operator inspection, rather than overwriting or deleting it.

Each `RevisionRecord` binds workspace/design/revision IDs, optional parent ID and
digest, source-baseline digest, typed plan, device registry, deterministic hashes
and local dry-run result. Same-plan retry returns the retained record; different
content under the same ID rejects. `BEGIN IMMEDIATE`, rollback and exclusive
initial creation protect competing local writers. Reads revalidate the whole
bounded parent chain and stored dry-run, not just the payload checksum.
The limits are 16MiB, 1000 revisions/references each and at most64 revisions in a chain.
Symlinks, junctions and hardlinks at the selected store/sidecars are rejected.
These are local misuse/collision protections; hostile concurrent filesystem
replacement and cryptographic evidence authentication are outside this contract.

Status is `draft` or `plan_validated`. The latter means the explicitly synthetic
bounded plan passed local rules. It never means a fabricated, simulated, ERC/LVS
clean or signoff-qualified design. `execution_authorized` stays false.

`RevisionEvidence` associates an external operation UUID and result hash with
the exact revision, semantic digest and validation kind. It preserves the
operator-reported outcome, including failure, while provenance remains
`operator_supplied_reference_unverified`. Conflicting evidence IDs and revision
substitution reject. A local reference does not authenticate a remote result;
`show` reports `REFERENCE_UNVERIFIED` or `NOT_ASSESSED` for each kind. It cannot
combine another revision's simulation/DRC/LVS into an overall PASS.

## Typed bounded inverter plan

`schematic_plan` reuses the existing frozen model, logical ID, digest and numeric
contracts. It provides `RevisionBinding`, `DeviceRegistry`, `SchematicPlan`,
`synthetic_inverter_fixture` and `dry_run_plan`. The registry specifies registered
device IDs, terminals and parameter unit/range contracts. The plan separates a
two-MOS complementary DUT from a DC supply/capacitive-load testbench with an
explicit DUT reference and external input pin. This first plan does not yet
define an executable transient stimulus or a general circuit language.

Validation rejects unknown devices, terminals and parameters, duplicate IDs,
missing terminals, invalid units/numbers/ranges, and the explicitly bounded
bulk/rail/pin/wiring errors. It is `bounded_inverter_rules_only`, not full ERC.
Physical display coordinates and wires are independent of electrical net
membership; changing display wires does not change the electrical semantic hash.
Ordering and equivalent numeric spelling produce deterministic hashes.

A child requires a retained parent with the same workspace/design and exact
parent digest/source baseline. The dry-run exposes semantic differences against
that parent. The plan and display hashes preserve their own scope.
`erc_status` and `lvs_status` remain `NOT_RUN`; `oa_created` is false.

The packaged example registry is fictional. No production W/L/m/nf values,
device CDF semantics or PDK bounds are inferred from it. Production registry
validation remains `BLOCKED_PRODUCTION_CDF_UNVERIFIED` until a future bounded
actual registration path provides reviewed CDF evidence; changing a provenance
label cannot turn this fixture into qualified production data.

## Installed operator workflow

The complete first-run commands are in the repository/package README. They need
only the installed package and a new operator-owned working directory; no private
checkpoint, historical UUID, developer journal or runtime settings are inputs.
`example` exclusively creates a new directory with plan/registry/binding JSON.
`init`, `validate`, `record`, `show`, `attach-reference` and `physical-assess` have
explicit `--help` arguments. JSON inputs are capped at1MiB. Errors return a closed
reason with no raw paths or proprietary validation payloads.

For a child, select a new logical revision ID and copy the retained parent's
`revision_sha256` into `parent_revision_sha256`, keeping its source baseline.
Update the typed plan and matching binding together; use `validate --store DB`
to resolve the parent before `record`. Keep historical revisions immutable.
The API accepts only the typed models and local metadata path. No shell, SKILL,
OCEAN, arbitrary Python, SSH command or execution approval is accepted.

The installed verifier exports/validates/records/reads a fictional plan twice
across processes, checks an empty physical inventory, then preserves the store
and examples through package reinstall and uninstall. Reinstall is same-artifact
preservation evidence, not qualification of all future upgrades.

## Actual environment investigation and evidence limits

[The physical inventory record](M2_PHYSICAL_OBSERVATIONS.md) distinguishes local
model tests from actual metadata observations. Existing fixed discovery failed
its runner binding check before SSH; the connected allowlisted library discovery
also returned `RUNNER_SETUP_REQUIRED`. Neither path produced physical metadata.
Layout/PCell/technology/DBU/layers/vias/DRC/LVS/PEX therefore remain UNKNOWN,
with licenses and execution unverified. No whole-VM scan or alternative unpinned
transport was introduced. A read failure is not proof of missing installation.

Current preserved accounting observation is126/500 attempts and15,452,864,512 /
17,179,869,184 reserved bytes; remaining1,727,004,672 bytes (1647MiB), native source
changes were22/24 before POST integration fixes. The existing conservative source
path policy also counts the two host extraction-recovery protection corrections,
so current source consumption reaches24/24; deployed native assets stay unchanged.
Attempts include extraction recovery, not only new Spectre runs.
This foundation adds zero simulation/extraction/reservation/native deployment/admin changes.
Consumed grants are not reused. Original OA/ADE, PDK/vendor contents, retained
results/failures, journals, policy and replay remain protected.

## Proposed next actual inverter phase (not executed)

Use the same registered standard VM/PDK and ordinary guest account. First reconcile
the exact discovery runner binding and review a fixed bounded metadata collector.
Collect only registered MOS symbol/CDF terminal/parameter/unit/range/default
identities and bound technology/API metadata. Preserve private source contents;
return typed observations and hashes. Tool startup/license/cache effects must be
listed before invocation. No DRC/LVS/PEX computation belongs in this next slice.

Then bind one new owned `m2-inverter` workspace/design/revision to that evidence.
Prepare a fixed generator for one DUT schematic and one testbench in a new
operator-owned library/cell pair, never the original library/cell/ADE state.
Export exact intended changes and source snapshots before applying; refuse
collisions and preserve partial/failed cells under their original job identity.
Compare read-back terminal/net/parameter semantics with the approved plan and
verify source/vendor/journal protection. Screen wires alone cannot satisfy it.

Proposed finite execution: at most one fresh DC and one fresh TRAN, at most128MiB
per job (256MiB total), no automatic retry with a new ID, no budget reset and no
AC/Sweep/optimization. Stop on unknown CDF, unsafe tool behavior, source drift,
netlist mismatch, extraction failure, disk/resource guard failure or exceeded
scope. Reuse same IDs to verify no duplicate dispatch. The conservative source
counter is now24/24. The proposed next scope would require an explicit extension
to26, preserving consumed24, for at most one fixed metadata-collector version and
one owned-inverter-generator version. This is a proposal only, with no allowance
for extra automatic corrective deployments. If it cannot fit, stop and report.

The next approval must explicitly cover the new fixed collector/generator runtime,
bounded ordinary-user OA creation and the finite DC/TRAN grant, after latest
actual ledger and target bindings are refreshed. Metadata failure may permit
local preparation, but never an unverified production parameter or execution.
This proposal creates no approval or active grant. M2 PR merge is also pending
separate authorization.
