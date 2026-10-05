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
| GENERIC-SIM-01 | Registered DC/AC/TRAN lifecycle adapter around existing jobs, UUID/replay/locks/budgets/fingerprints and bounded results | Planned |
| GENERIC-SWEEP-01 | Qualified real-design 1D variable sweeps with effective inputs, durable resume, reservation and cancellation | Planned |
| GENERIC-MEAS-01 | Measurements with established extraction evidence; keep specification evaluation separate | Planned |
| PDK-ADAPTER-01 | Minimal runtime adapter from the existing WP-15 design; gpdk090 as a reference, private physical bindings | Planned |
| ONBOARD-CLI-01 | Complete operator registration/verification/client installation workflow using the current CLI and contracts | Planned |
| PUBLIC-RELEASE-01 | Review actual release history, interface compatibility and semver after onboarding works | Planned |

These phases are not chained execution approval. Dependency review may adjust
their order: design registration can describe an unqualified technology binding,
but cannot execute it before its adapter and analysis qualify. Scientific ranges
and measurement definitions must come from reviewed evidence or the user.
Optimization, multidimensional sweep, layout, DRC/LVS/PEX, Monte Carlo, chip
orders and final submission are outside this phase.

## GENERIC-DESIGN-01 activation

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
