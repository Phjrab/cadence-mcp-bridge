# Licensing and distribution audit v1

Audit date: 2026-10-05. Phase: RELEASE-LICENSE-01. Starting main:
`19f8bfb95661f30fd2458d019b3cc9fe6857ea75`, merged PR #111.
The owner explicitly selected Apache License 2.0 for original bridge code.
This audit prepares repository engineering/compliance evidence; it does not
resolve ambiguous third-party legal terms or authorize a new public release.

## Starting evidence and attribution

The baseline had no root LICENSE/NOTICE and declared Proprietary in package
metadata. It had 754 tracked UTF-8 files, no detected tracked binary/vendor
distribution and no identified original-code license conflict. Git history and
package metadata identify Phjrab (also Hajoon Park); first commit is in 2026.
NOTICE conservatively uses `Copyright 2026 Phjrab`. Tool-assisted commits do
not assign ownership to tool vendors. No corporate ownership is invented.

LICENSE is verbatim from <https://www.apache.org/licenses/LICENSE-2.0.txt>.
Canonical SHA-256:
`cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`.
Git disables text conversion for that file, retaining canonical bytes/appendix.
NOTICE records original-code attribution and separate external terms.
[Third-party/scope notices](../THIRD_PARTY_NOTICES.md) identify actual dependency
licenses and the imported-material exception; they do not replace MIT grants.
No blanket repository relicensing claim is made.

## Material classification

| Class | Evidence / disposition |
| --- | --- |
| PROJECT_ORIGINAL | Original bridge Python, bounded remote integration scripts and project metadata; synthetic fixtures/examples reviewed separately from vendor data |
| DEPENDENCY_ONLY | Separately installed runtime MCP 2.1.1, Pydantic 2.13.4 and pydantic-settings 2.15.0; installed grants are MIT; mcp-types 2.1.1 and pydantic-core 2.46.4 also MIT |
| COPIED_CONTENT | Imported `docs/agent_plan/` prompt package, including adapted verification helper; rights unresolved, preserved and excluded from package artifacts |
| GENERATED_CONTENT | Project schemas, contract snapshots and synthetic evidence references; generation does not grant rights to vendor content |
| VENDORED_SOURCE / BUNDLED_BINARY | None identified in the baseline inventory or curated artifacts; no dependency/Cadence/PDK binary or source bundle is included |

The private dependency audit records 72 installed distributions, observed
license metadata and available license-file hashes. Installed direct dependency
files contain actual MIT grant text. Optional/transitive/build/dev packages stay
separately installed under their own terms. This audit is not a licensing
clearance for a future dependency bundle or executable desktop extension.

## External EDA and gpdk090 boundary

Cadence Virtuoso, Spectre, ADE, license entitlement/server access, PDKs and MCP
clients are not supplied or relicensed. Users provide authorized installations,
licenses and SSH access. No license bypass, emulator or credentials are added.
License qualification remains bounded status, not secret configuration or proof
of entitlement. Apache-2.0 applies only where the bridge can grant rights.

gpdk090 occurrences are logical reference adapter IDs, local installation
references, capability checks and bounded read-only integration scripts. No
actual model file, technology file, rule deck or PDK distribution was identified.
Adapter code is distinct from user-installed PDK data; no gpdk090 redistribution
grant is asserted. Fixed public reference bindings in original source remain
compatibility configuration; they are not embedded vendor material.

## LEGAL_REVIEW_REQUIRED

Affected component: `docs/agent_plan/`, from user-provided
`CADENCE_MCP_FINAL_PROMPT_PACKAGE` in PKG-INTEGRATE-01. The integration record
reports 178 imported files and preserved hashes, including an adapted helper.
That provenance establishes integrity, not author ownership or a redistribution
grant. No explicit license/ownership grant was found. Human review must establish
the rights/terms for that package and imported content derived from it before
making a whole-repository Apache claim or distributing a repository bundle.

The directory and existing public Git history are preserved. Root LICENSE does
not relicense it. New curated wheel/sdist exclude it. The referenced
`archive/LEGACY_INPUTS.zip` is absent from Git. This uncertainty materially blocks
unconditional whole-repository distribution readiness; it does not assert a
license conflict or change the audited original-code package boundary.

## History / protected-content review

The locally reachable history scan covered 1,473 blobs / 23,312,172 bytes, with
no binary or actual BSIM model-definition finding. Two credential-pattern
matches were historical mocked redaction tests in `test_ssh_backend.py`: literal
test payloads, mocked failure transport and assertions that token/user text is
removed. Values were not published. No operational credential was identified;
no history remediation/rewrite occurred. Imported-rights uncertainty remains.
Pattern scanning is bounded evidence, not proof of every possible secret format.

Current tracked/new files also pass the canonical secret preflight. Original
runtime source byte seals, prior private checkpoints and remote protected
source/PDK/job/accounting checks remain equal. No private evidence is committed.

## Actual distribution contract

`pyproject.toml` uses modern `license = "Apache-2.0"` and `license-files` for
LICENSE, NOTICE and THIRD_PARTY_NOTICES.md with the existing Hatch toolchain.
Version stays 1.0.0. Wheel is package-only. Sdist contains package source,
metadata, uv.lock, README, reviewed .gitignore and those notices, plus generated
PKG-INFO. It rebuilds the wheel; a full reviewed checkout is needed for remote
deployment/operator helpers. It is not a full operator checkout or source archive
of all repository documentation/tests. No release/tag/index publication occurs.

`scripts/verify-distribution.py` reads ZIP/tar without extraction, limits size
and members, rejects links/unsafe paths, compares the exact allowlist and source/
notice bytes, scans secret/model patterns, verifies canonical LICENSE and modern
metadata. Both actual build formats pass: 39 wheel files, 40 sdist files,
Metadata-Version >=2.4, License-Expression Apache-2.0, all three License-File
entries, no obsolete License field, unexpected files zero. No private journal,
keys/license configuration, job/raw/PSF/PDK content or bundled vendor binary is
included. Known public compatibility references in source are retained.

The canonical package gate audits distributions before isolated installation,
checks the installed CLI/stdio and all 48 tool declarations / 22 historical
names, denies unqualified execution, then uninstalls and verifies removal.
Synthetic archive tests reject unexpected/private/import/PDK/binary/traversal
paths, missing/altered notices, source drift and secret/model patterns.

## Corrections and readiness

Three of three phase corrections used; failed transcripts/artifacts are private
and preserved. First fixed initial test lint. Second attempted an explicit
.gitignore exclusion. Hatch source inspection then proved VCS exclusions are
force-included; third retained the reviewed file with exact-byte validation,
preserving VCS safety. No production runtime or canonical license change.

**CONDITIONALLY_READY** for licensing preparation: original-code package scope
is audited, but whole-repository imported rights are LEGAL_REVIEW_REQUIRED.
Exact candidate/version, actual desktop qualification, truthful generic execution
scope and explicit release authorization remain separate publication gates.
See [phase results](RELEASE_LICENSE_01_RESULT_V1.md).
