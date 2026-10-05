# PUBLIC-RELEASE-01 preparation result v1

Starting main: `fff725cdf64d084d7c55ab30d5a38da15f33fb49`, merged PR #109.
Feature branch: `feat/public-release-prep-01`. The containing feature PR and
private final checkpoint identify integration and exact ending main/tree.
The assessed preparation is separate from publication readiness or a new release.

## Audit and implementation

Actual GitHub v1.0.0 is stable and published on 2026-08-31, with zero assets,
despite stale “not yet published” wording in its body. Its immutable tag peels
to `8a0d44fab90e2095cc39322baef60fc09d741cd6`. Package/runtime/lock remain 1.0.0.
Repository visibility is public; GitHub detects no license and the project has
Proprietary metadata with no LICENSE file. Public visibility is not a general
software-use/redistribution grant. Owner choice remains unresolved.

The actual v1 tag has 22 MCP tools, current main 48. All 22 names and declared
parameter/return annotations remain equal; shared models.py/measurement_models.py
match the tag byte-for-byte in Git. Current legacy tests and preserved native
E2E provide regression evidence; declaration equality is not universal client
or deployment qualification. Conditional semver recommendation is **v1.1.0**
for additive capabilities, not a version applied by this phase.

Existing `verify-package.ps1` now reads expected version from project metadata
and invokes a new installed-wheel acceptance helper in isolated Python mode.
It verifies distribution/runtime/CLI version agreement and wheel import origin,
registers/joins fictional catalogs, exports both config formats and runs actual
stdio from the installed interpreter in a different temporary workspace. Both
have 48 tools and preserve all 22 baseline names; private registry settings are
honored, extra path input is rejected and unqualified submission is denied before
local database/admission creation. No Cadence transport or simulation occurs.
Uninstall/absence and bounded temporary cleanup are verified. The original
literal-version unit test now checks parsed metadata/lock/runtime agreement.

Added a tag-bound API declaration snapshot, current readiness matrix and proposed
next-release notes. Updated current installation/upgrade guidance and public
scope, preserving historical v1 notes and the actual GitHub body/tag. No license
grant, package version bump, new tool/API, remote helper or publication is applied.
See [readiness](RELEASE_READINESS_V1.md) and [proposed notes](RELEASE_NOTES_NEXT.md).

## Gates and evidence

Ruff, strict mypy (31 source files), frozen all-group synchronization (72 packages),
focused tests (43 pass, one Windows symlink skip), dedicated security tests (18),
secret preflight and frozen dependency audit pass. Audit reports no known
vulnerabilities. Final installed-package acceptance passes for both 48-tool
stdio configurations, all 22 baseline names, closed inputs and denied admission;
build/install/version/uninstall/cleanup pass. Final full unit gate: **1,453
passed, three Windows symlink skips, 56 existing warnings** (650.81 seconds).

One of three corrections was consumed: review found that an empty/substituted
legacy snapshot could produce a false package pass. Require exactly 22 tools
and the actual v1.0.0 tag/commit, then rerun installed acceptance. Narrow model
documentation to the two existing unchanged files. No runtime source changes.

Two operator-environment failures remain recorded privately: a guard invocation
lacked established Git safe-directory settings and was denied before transport;
a non-escalated focused invocation had 14 passes and 30 private-temp setup errors.
The established Git/UTF8 environment and approved private writes resolved them
without code/authority changes. Failed attempts are not reported as passed;
final focused results are from a new exclusive temporary identity.

## Resource and protection evidence

All runtime source bytes match the sealed prior ONBOARD-CLI-01 actual native
DC/AC/trap TRAN result/replay/restart E2E. That preserved evidence is reused;
new simulations are scientifically unnecessary for unchanged runtime code.
Current installed-wheel stdio provides new actual packaging evidence. Fresh fixed
postflight/guard and prior checkpoint hashes verify protected objects, existing
job trees and accounting unchanged.

New Spectre attempts, reservations, deployment bytes and paid resources: zero.
Shared ledger retains 62/500 attempts and 7,114,588,160 reserved bytes. All
independent storage/worker gates and prior correction histories remain binding;
the removed elapsed ceiling remains absent. No source/PDK/installation/evidence
mutation, FS work, user target or circuit-specification PASS is introduced.

## Completion meaning and remaining work

Another operator has a stronger repeatable installed-package test and accurate
version/compatibility/public-scope documentation. A clean build is no longer
accepted solely because a CLI version string prints. Existing v1 publication
is recognized correctly without republishing or rewriting its evidence.

The preparation phase completes through its reviewed feature PR. Formal new
publication still needs owner licensing, an exact reviewed candidate and version
update, honest reference/experimental scope, and separately explicit publication
authority. Generic physical execution and a second installation remain unqualified.
Recommend resolving licensing in LICENSE-POLICY-01 before release-candidate
preparation. Ask once for the owner's licensing choice; do not choose rights
autonomously or start another major phase without it.
