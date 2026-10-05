# RELEASE-LICENSE-01 result v1

Starting main: `19f8bfb95661f30fd2458d019b3cc9fe6857ea75` (merged #111).
Branch: `feat/release-license-01`. Integration is the dedicated containing
feature PR; the private final checkpoint records exact head, PR, resulting main
and remote verification. No state-sync-only PR, tag, release or package-index
publication is created. Selected license: **Apache License 2.0**.

## Implemented

Canonical root LICENSE, conservative `Copyright 2026 Phjrab` NOTICE, actual
third-party/scope notices and modern SPDX/License-File package metadata are
present. LICENSE is protected from Git newline conversion. README and operator/
release documentation separate original bridge code from user-provided Cadence,
PDKs, license entitlement, clients and separately installed dependencies.
Independent status and no vendor endorsement are explicit. Package version
remains 1.0.0; historical tag/release remains unchanged.

The exact curated wheel/sdist auditor is part of the canonical package gate.
It validates sizes/paths/links, expected files, source/notice bytes, canonical
license, modern metadata and secret/model patterns before isolated installation.
No MCP/API or execution semantics change: 48 tools, 22 legacy names retained.
No arbitrary execution/path/script or license bypass capability is added.

## Audit and qualification

See [licensing audit](LICENSING_AUDIT_V1.md) for 754-file baseline, 1,473-blob
history review and 72-distribution installed dependency inventory. Direct
runtime MIT grants were inspected; dependencies are not vendored. Actual
gpdk090 PDK contents are absent; only original reference integration/local
bindings are present. No proprietary model/deck/binary or operational credential
was identified. Two historical credential-pattern matches are mocked redaction
test literals; no destructive history remediation was performed.

`docs/agent_plan/` imported-package ownership/redistribution terms remain
**LEGAL_REVIEW_REQUIRED**. Prior material/history is preserved; it is not
relicensed by LICENSE. New packages exclude it. This blocks a blanket Apache
claim or unconditional readiness for a full repository distribution. A human
must establish rights/terms before that scope is included.

## Gates and E2E

| Gate | Actual result |
| --- | --- |
| Frozen dependency sync | Pass |
| Ruff / mypy | Pass / 31 source files |
| Full unit | 1,482 passed; three OS symlink skips; 56 existing deprecation warnings |
| Final focused distribution/release tests | 28 passed |
| Security tests / dependency vulnerability scan | 18 passed; one pytest cache-permission warning; no known locked dependency vulnerabilities |
| Actual wheel / sdist | Pass; 39 / 40 files; License-Expression Apache-2.0; all three license files; canonical hash and byte equality; zero unexpected files/pattern findings |
| Isolated installed package | Pass; CLI/version, fictional contracts, Codex/MCP JSON/Claude exported stdio, 48 tools/22 legacy names, denied unqualified admission, uninstall/import absence and cleanup |
| Native Cadence regression | Completed DC/AC/TRAN evidence reused with exact unchanged production source bytes; fresh protected/job/counter checks equal; no new simulation E2E claimed |

No client desktop-application qualification is added. Claude remains
CLAUDE_REAL_CLIENT_UNVERIFIED. No remote deployment or new circuit claim.
Canonical package build creates the wheel from the curated sdist; artifacts
exclude private journals/keys/license configuration/job/raw/PSF/PDK/vendor data
and imported planning files. Existing public fixed-reference source bindings
remain. The sdist is package source, not the full operator/deployment checkout.

## Corrections, resources and protection

Corrections: **3/3**, with failed transcripts/artifacts preserved privately:
initial test lint, attempted .gitignore exclusion, then inspected Hatch's forced
VCS-file behavior and retained only the reviewed exact file. No runtime or
canonical license byte change. Gates passed after the last package correction.

New Spectre attempts: **0**. New result reservation: **0 bytes**. Remote
deployment: **0 bytes**. Fresh counter remains 62 attempts and 7,114,588,160
historically reserved bytes; this phase does not reset/expand existing budgets
or interpret preserved counters as new free capacity. Removed elapsed ceiling
stays absent. Protected source/PDK, job trees, old private checkpoints and
production source bytes are unchanged. Local audit/build files remain private.

## Public distribution and next phase

**CONDITIONALLY_READY**: original-code license/package boundaries are verified;
whole-repository imported rights remain unresolved. No public release is
authorized by this preparation. Exact candidate/version, actual desktop
qualification and truthful scope remain public-release gates; generic new
physical environment/design execution is still unqualified.

Another user can now inspect the explicit original-code Apache grant, distinguish
external licensing obligations, and rebuild/install an audited package source
distribution without imported/private/vendor material. They cannot assume the
entire repository, Cadence installation or a PDK is Apache licensed.

Recommend **GENERIC-MEAS-01**, reusing established scalar/spectrum/operating-point
extraction and keeping specification evaluation separate. Obtain imported
rights clearance before any full repository bundle and complete client/candidate
gates before a significant public release. Report once and stop for the next
major-phase choice; no next phase is activated here.
