# Generic user onboarding program v1

## Fresh starting audit

The selected implementation phase starts from `origin/main`
`407cc401e5027070a54da190537e1b7d91e80a11`, merged PR #103. The repository is
public. GitHub's latest published release is v1.0.0, published on 2026-08-31;
the package version is still 1.0.0. No release or tag is changed by this program's
first phase. Release wording and semver require a later compatibility review.

The server exposes 35 typed MCP tools. Existing service/backend separation,
closed profiles, local measurement contracts, fixture sweep planning, native
diagnostics, protected fingerprints, locking, budget reservations and replay
remain the regression foundation. The environment baseline, source/copy/native
DC/AC/TRAN, fixed candidate, PVT and operating-point histories are existing work,
not tasks to repeat. Prior reports distinguish actual observations from absent
numerical specifications.

Remaining installation assumptions include the fixed `cadence-vm` BridgeConfig,
fixed remote runner/version routes, registered design identities, analysis and
result bindings, native candidate and gpdk090 model selectors. The technology
adapter schema is a design reference, not a runtime loader. The current public
installation uses `uv sync --all-groups`, the `cadence-mcp-bridge` entry point
and `scripts/install-codex-mcp.ps1`. It does not onboard arbitrary projects.

The user's current master prompt activates exactly GENERIC-ENV-01, including
feature PR integration under the existing autonomous development policy. It
requires one report and one continuation question at the end. Historical
per-WP/per-read/per-PR approvals and stale state records are not reopened.
Existing cumulative ceilings, removed elapsed ceiling and protected histories
remain binding. Runtime environment descriptions cannot replace those guards.

## Bounded implementation decomposition

| Phase | Deliverable and acceptance boundary | State |
| --- | --- | --- |
| GENERIC-ENV-01 | Operator-owned versioned environment description, local doctor/schema/validation/preparation, one fixed read-only qualification probe; no execution activation | Implemented; see result report |
| GENERIC-DESIGN-01 | Operator registry and logical design introspection with environment/technology references, source/copy policy and declared allowlists; preserve fixed/native compatibility; generic execution stays unqualified | Implemented; user selected this one phase |
| GENERIC-VAR-01 | Logical/Cadence bindings, exact units/types/defaults and separate bound numeric reviews; unqualified ranges reject values, generic execution stays disabled | Implemented; see variable workflow/result |
| GENERIC-SIM-01 | Registered DC/AC/TRAN lifecycle, durable UUID admission and bounded native results; fixed reference compatibility adapter, other designs blocked; native live cancellation unsupported | Implemented; see analysis workflow/result |
| GENERIC-SWEEP-01 | Qualified real-design 1D variable sweeps with effective inputs, durable resume, reservation and cancellation | Planned |
| GENERIC-MEAS-01 | Measurements with established extraction evidence; keep specification evaluation separate | Planned |
| PDK-ADAPTER-01 | Runtime logical registry and exact gpdk090 regression adapter; other PDK execution unqualified | Implemented and verified; see PDK workflow/result |
| ONBOARD-CLI-01 | Joined local registration/verification and reviewable client configuration export using existing contracts; other installations remain unqualified | Implemented; see onboarding workflow/result |
| CLIENT-COMPAT-01 | Same local stdio server and contract policy for MCP clients; Codex adapter regression, Claude registration, protocol integrity and honest desktop qualification matrix; MCPB investigation only | Merged #111; server/configuration qualified, actual desktop E2E unverified |
| RELEASE-LICENSE-01 | Apache-2.0 original-code boundary, modern metadata, notices, imported-rights review and actual curated distribution audit | Selected by explicit owner directive; whole-repository imported rights remain LEGAL_REVIEW_REQUIRED |
| PUBLIC-RELEASE-01 | Actual release/compatibility/license assessment and installed-wheel stdio acceptance; conditional semver and honest public scope | Preparation verified; publication/owner rights pending |

These phases are not chained execution approval. Dependency review may adjust
their order: design registration can describe an unqualified technology binding,
but cannot execute it before its adapter and analysis qualify. Scientific ranges
and measurement definitions must come from reviewed evidence or the user.
Optimization, multidimensional sweep, layout, DRC/LVS/PEX, Monte Carlo, chip
orders and final submission are outside this phase.

## GENERIC-DESIGN-01 activation

GENERIC-SIM-01 was explicitly selected after PR #106. It implements registered
analysis contracts and fixed-native compatibility with durable admission, not
qualification of arbitrary environments/designs. See
[workflow](GENERIC_ANALYSIS_V1.md) and [result](GENERIC_SIM_01_RESULT_V1.md).
Evidence supports preparing the PDK adapter before real-design generic sweeps:
actual bias continuous ranges and new execution bindings remain unqualified.

GENERIC-VAR-01 was subsequently selected explicitly after PR #105. It extends
the same operator registry and preserves v1/native behavior; see
[variable workflow](GENERIC_VARIABLES_V1.md) and
[phase result](GENERIC_VAR_01_RESULT_V1.md). No FS change, continuous bias range
or next major phase is activated by this implementation.

The user's later explicit instruction selects registered design profiles from
main `3d41404096a894d2fac0f9fe829a31af12ff4623` (merged PR #104).
Complete this one phase, verify the existing native behavior using preserved
results without new simulation, integrate its feature PR, then ask once before
another major phase. Previous FS circuit evidence stays preserved; no follow-up
FS structural circuit modification is activated. See
[design workflow](GENERIC_DESIGN_V1.md) and
[phase result](GENERIC_DESIGN_01_RESULT_V1.md).

## GENERIC-ENV-01 acceptance

- Another operator describes their own SSH alias, Linux host/runtime, tool
  bindings, protected/work/job/result roots and declared limits without source
  edits, using the version-1 contract.
- Invalid descriptions fail locally; no model-facing registration/path/command
  fields are added to MCP. The only remote operation is the bundled probe.
- Qualify only observed environment preflight. License entitlement and analysis
  capabilities remain unqualified; resource descriptions do not reset or
  activate a ledger. The default execution server remains fixed.
- Preserve existing native result/replay behavior with real stdio where the
  registered host is available, reusing completed jobs without simulation.
- Run existing lint/type/unit/security/dependency/package gates, review the
  public diff and integrate a dedicated feature PR. Retain private audit,
  deployment, failure, comparison and protected-object evidence.

See [environment operations](GENERIC_ENVIRONMENT_V1.md) and
[phase result](GENERIC_ENV_01_RESULT_V1.md). Prior roadmap and WP histories remain
dated reference material; this document does not rewrite them.

## ONBOARD-CLI-01 activation and result

The user selected this one phase after merged PR #108. Joined local contracts,
explicit client configuration export and documented installation are implemented
and verified; see [workflow](ONBOARDING_CLI_V1.md) and
[result](ONBOARD_CLI_01_RESULT_V1.md). Other physical execution routes remain
unqualified. PUBLIC-RELEASE-01 readiness is proposed, not activated; release/tag
publication and broader generic execution are not implied by this phase.

## PUBLIC-RELEASE-01 readiness result

The user selected readiness after merged #109. Existing v1.0.0 publication is
recognized; current 48-tool source preserves 22 legacy declarations. Installed
wheel CLI/stdio acceptance and candidate/readiness documents are verified; see
[result](PUBLIC_RELEASE_01_RESULT_V1.md). Conditional 1.1.0 is not applied.
Licensing, exact candidate and explicit publication scope remain decisions;
no license/version/tag/release change or next major phase is activated.

## Multi-client program authority, 2026-10-05

The user's later directive explicitly extends this program: Cadence MCP Bridge
is the product; Codex, Claude Desktop and future MCP hosts are clients. Shared
environment/design/PDK/storage configuration belongs to the bridge. Client
adapters only launch the same package; security is enforced server-side.
PUBLIC-RELEASE-01 preparation is already merged as #110. Existing foundations
permit CLIENT-COMPAT-01 now; generic sweep/measurement remain planned and are
not prerequisites for read-only client qualification. No earlier history is
restarted. Actual Claude verification may remain pending when inaccessible;
this does not become a false PASS or activate public MCP hosting. See
[compatibility workflow/matrix](CLIENT_COMPATIBILITY_V1.md). A new release
candidate should reassess both client evidence and unresolved licensing.

## Apache-2.0 authority and release ordering, 2026-10-05

The owner explicitly chose Apache-2.0 after CLIENT-COMPAT-01 merged as #111.
That completed phase is preserved. RELEASE-LICENSE-01 applies the selection to
original bridge material and audits actual artifacts; it must precede the next
significant public release. Imported planning material is preserved and excluded
from curated packages pending rights review. This choice is not a license grant
for Cadence/PDK/client/dependency content or a tag/release publication instruction.
See [audit](LICENSING_AUDIT_V1.md) and [result](RELEASE_LICENSE_01_RESULT_V1.md).

After this phase, GENERIC-MEAS-01 can reuse qualified extraction evidence without
requiring broader electrical ranges. Generic real-design sweeps remain dependent
on qualified numeric/physical contracts. Full-repository rights review, actual
desktop qualification, exact candidate/version and explicit publication scope
remain prerequisites for the corresponding public release claims. No next major
phase is automatically activated; report and ask once at the boundary.
