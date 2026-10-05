# RELEASE-READINESS-02 result

Date: 2026-10-06. Starting main:
`4ea17e2641f316ec0899c9c91f8bea97c6b4086f` (merged SPEC-CONTRACT-01 #119).
Feature branch: `feat/release-readiness-02`. Integration uses the containing
reviewed feature PR; exact resulting remote SHA/tree verification is retained
privately after permitted merge. Package/server version stays **1.0.0**.

## Implementation

Added the local operator-only `scripts/verify-release-readiness.py` and a reviewed
snapshot of all **69 full MCP schemas**. The audit reflects typed closures with
a service-call denial sentinel; it constructs no service/backend/job store and
makes no tool call or remote contact. It checks 22 actual v1 tag-bound legacy
declarations, two unchanged legacy model files, seven registry schemas, consistent
source/runtime/lock versions and canonical Apache-2.0 metadata/notices.

Empty/substituted baselines, duplicate/nonfinite/oversized JSON, declaration/model/
schema drift and inconsistent version/license data fail closed. Technical PASS
always retains `publication_authorized: false` and unverified external gates.
MCP/API changes: **none; 69 before and after**. Runtime and remote source remain
unchanged; no executor, client-specific server or new execution authority.

Updated README, release/install/upgrade/uninstall guidance, proposed release notes,
the 69-tool client manual procedure and [readiness v2](RELEASE_READINESS_V2.md).
Historical release notes, existing published v1 body/tag and earlier evidence
remain preserved. The proposed next version **v1.1.0 is conditional**, based on
additive interfaces; no version bump, candidate selection, tag or publication.

## Verification

- Frozen dependency synchronization: pass; 72 installed packages.
- Ruff and mypy: pass, 45 source modules.
- Focused contract/protocol/distribution tests: **56 passed**, one cache warning.
- Full unit suite: **1,717 passed, four OS symlink skips, 57 warnings**, 737.07
  seconds; existing Python 2.6 helper deprecations and cache warning retained.
- Security suite: **18 passed**, one cache warning; secret preflight passes;
  locked dependency audit reports no known vulnerabilities.
- Local contract audit: pass, 69 schemas / 22 legacy declarations / two models /
  seven registry schemas; no app/legal/publication qualification implied.
- Canonical package gate: pass. Built wheel **53 members**, sdist **54 members**;
  Apache LICENSE/NOTICE/THIRD_PARTY_NOTICES included; unexpected files and protected
  content patterns **zero**; imported planning excluded. Exact source/notices match.
- Isolated installed wheel: Codex/common JSON/Claude configurations each expose
  69 tools from another working directory; targetless specification evaluation
  stays NOT_EVALUATED without admission or remote transport; CLI/version/uninstall pass.

One correction of **20** consumed: initial Ruff found two long lines; formatter
resolved them and final static verification passed. Failure evidence is retained.

## E2E, resources and integrity

All **45 runtime source modules** equal the starting private byte baseline.
Remote source and package/license metadata have no diff. Consequently the exact
SPEC-CONTRACT-01 exported-client SDK stdio native DC/AC/TRAN, analog, sweep,
storage, replay and restart evidence is reused; new simulation is unnecessary.
Fresh fixed reference postflight confirms protected source/OA/ADE/PDK, prior jobs
and counters equal. The union of **1,088 prior private evidence records** remains
byte-identical. Historical journals/admissions/ledgers and failures are preserved.

Spectre attempts consumed: **0**, cumulative **62/500**. Result reservations
consumed: **0**, cumulative **7,114,588,160 / 10,737,418,240 bytes (10 GiB)**.
Deployment, deletion, design mutation, extraction and optimization: **0**.
Shared EDA lock, disk floor, durable identity/replay and removed elapsed ceiling
remain intact. No storage cleanup is authorized by this assessment.

Codex/Claude launch configurations and installed SDK protocol are verified;
fresh actual Codex app remains **NOT_TESTED** and Claude remains
**CLAUDE_REAL_CLIENT_UNVERIFIED**. A bounded registry query did not return Claude;
this neither proves every installation absent nor qualifies an application.

## Distribution decision and remaining gates

| Scope | Decision |
| --- | --- |
| Curated original bridge wheel/package-source sdist | CONDITIONALLY_READY |
| New significant GitHub release at current main | NOT_READY |
| Full repository bundle or blanket Apache claim | BLOCKED_LEGAL_REVIEW_REQUIRED |

Imported `docs/agent_plan/` rights remain unconfirmed and human review is required.
Curated package exclusion does not exclude these files from GitHub's whole-tree
source archives. Cadence/PDK/client/dependency software retains its own licensing;
none is supplied or relicensed. No new legal interpretation or history rewrite.

Another operator can run a repeatable local contract audit and distinguish
package qualification from app/legal/publication readiness. New physical design
routes, real amplifier ranges, other Cadence versions/PDKs and four missing analog
measurements remain unqualified/deferred. No numerical reference goals exist:
physical specification evaluation remains NOT_EVALUATED.

Recommend **CLIENT-REAL-QUAL-01** next, with imported planning rights review in
parallel. Use bounded discovery and preserved results, not new Spectre execution.
An exact candidate/version and explicit publication authority remain separate
future gates. Complete this one phase and ask once before continuing.
