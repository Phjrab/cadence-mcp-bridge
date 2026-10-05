# Public release readiness v1

Audit date: 2026-10-05. Starting main:
`fff725cdf64d084d7c55ab30d5a38da15f33fb49` (merged PR #109).
This is PUBLIC-RELEASE-01 preparation, not publication or a version change.

## Actual release and version state

| Item | Observed state | Consequence |
| --- | --- | --- |
| Repository | Public, default branch main | Public visibility alone grants no general software license |
| v1.0.0 tag | Annotated, peels to `8a0d44fab90e2095cc39322baef60fc09d741cd6` | Historical baseline remains immutable |
| GitHub v1.0.0 release | Stable, published `2026-08-31T09:21:18Z`, zero assets | It is already published; do not repeat publication |
| Existing release body | Contains stale “not yet published” and private/candidate wording | Preserve history; any external metadata repair needs explicit scope |
| Source/runtime/lock metadata | 1.0.0 | No new release version is applied by this phase |
| Current MCP inventory | 48, compared with 22 at v1.0.0 | Post-v1 capabilities are not delivered by the old tag |
| Licensing | Proprietary metadata, no LICENSE file, GitHub license null | General external use/redistribution terms need owner decision |
| GitHub required checks/reviews | None at starting audit | Local gates are required evidence; absent CI is not a passed CI gate |

The versioned `RELEASE_NOTES_v1.0.0.md` remains historical. Read current readiness
and [proposed notes](RELEASE_NOTES_NEXT.md) for present claims.

## Compatibility and semver recommendation

The actual v1 tag supplies the [22-tool declaration snapshot](contracts/MCP_V1_COMPATIBILITY_SNAPSHOT.json).
Current source preserves all those names and declared parameter/return annotations.
Shared `models.py` and `measurement_models.py` have no changes relative to
that tag. Existing
closed request/response and legacy tests remain the behavioral regression basis.
The snapshot records declarations, not a claim of equivalence for every possible
client, deployment or unsafe edge case.

The 26 added tools cover actual/native diagnostics, fixture sweeps, registered
design/variable/analysis APIs and PDK capability inspection. Operator CLI and
versioned contracts are additive; old v1/v2 catalogs remain supported. Guards
still reject unauthorized inputs, mismatched identity, unqualified adapters,
stale/invalid contracts and resource-limit violations. Existing fixed-reference
deployment remains the regression environment.

**Conditional version recommendation: v1.1.0.** This follows the observed additive
public surface and preserved legacy contracts. No removal requiring a major
version has been identified. Final versioning must recheck the selected release
commit, compatibility, license and publication scope. A future incompatible
contract or changed existing semantics could require a different version.

## Installed-package acceptance

`scripts/verify-package.ps1` now reads the expected version from project metadata.
It invokes `scripts/verify-installed-package.py` with the temporary installed
interpreter under Python isolated mode. The helper proves its bridge import is
inside that environment, checks distribution/runtime/CLI version agreement,
registers coherent fictional catalogs and verifies joined contracts locally.

It exports both Codex TOML and common MCP JSON, starts actual stdio from each in
the new temporary workspace, verifies 48 tools and all 22 baseline names,
confirms the configured design catalog, denies an unqualified submission before
database/admission creation, and rejects extra path fields. Codex writes/prompt
settings are preserved. It contacts no Cadence host. It then uninstalls, verifies
absence under isolated mode and cleans only the validated temporary directory.
The private transcript records actual installed acceptance, not source checkout
imports. The historical literal-version test now checks parsed project/lock and
runtime version agreement, so future authorized version changes have one truth.

## Public claims and qualification

| Classification | Scope |
| --- | --- |
| Validated | Reference native DC/AC/trap TRAN and preserved result/replay/restart behavior; fixed PVT/OP evidence; actual stdio; isolated installed onboarding; local/security/dependency/package gates |
| Supported by contract | Bounded operator profiles/catalogs, local joined verification, private config export and exact compiled native compatibility, legacy catalog versions |
| Experimental | Positive generic preflight on another approved installation; fixtures cover positive observations but no second physical installation is qualified |
| Planned/unqualified | New physical environment/design/PDK execution adapters, parameterized real-design sweep, generic measurements, native live cancellation, statistics/Monte Carlo, layout/DRC/LVS/PEX and optimization |

The current reference's writable executable wrappers still fail generic
preflight. Another operator can describe/register/inspect their own contracts,
but that does not route arbitrary projects to execution. Numeric ranges cannot
be inferred, 320/702 mV are candidates, VDD=1 V is a constraint, and results
without scientific targets retain `spec_evaluation=not_evaluated`.

## Publication gates still open

1. Owner chooses licensing/use/redistribution terms; package metadata is not a
   substitute for a license grant. Dependencies, Cadence and PDK retain their own
   terms; protected vendor/design material is not distributable with this bridge.
2. Select an exact reviewed release candidate, apply consistent version metadata
   only in its authorized phase, and rerun gates on that candidate.
3. Choose whether publication claims only the validated reference and experimental
   local onboarding. A claim of general new-project execution requires qualified
   physical adapters and a second real environment, not wording changes.
4. Explicitly authorize the exact tag/release/distribution or old-body correction.
   Current preparation makes no such external changes. There are no wheel/sdist
   assets or package-index publication claims for the historical GitHub release.

These are concrete limits on publication, not permission requests for ordinary
implementation/review/feature-PR work. The current preparation phase can finish
its assessment, stronger installed acceptance and PR integration while those
publication decisions remain unresolved.
