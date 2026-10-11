# Release candidate preparation, 2026-10-11

Status: **NOT_FROZEN / NOT_RC_READY / GENERIC_RELEASE_GATE=BLOCKED**.
Provisional next version: **2.0.0**. No candidate commit, distribution hashes,
tag or public release exists. Package metadata, runtime and currently tested
artifacts remain **1.0.0**. The current documentation checkpoint is
`2267f6255be1a4ef61d0bb5d86a51b036090058d`; it is not an exact release candidate.

## Why 2.0.0 is the provisional recommendation

The published v1.0.0 commit `8a0d44fab90e2095cc39322baef60fc09d741cd6`
documented both a bare launch and explicit `serve` as equivalent. Its Codex
installer generated `args = ["-m", "cadence_mcp_bridge"]`, with no subcommand.
The current CLI intentionally routes a bare launch to the operator context and
returns SETUP_REQUIRED when no context is configured. It constructs no historical
reference backend in that state. This changes an existing documented launch and
saved client configuration, even though the original22 schemas are preserved.
A major version communicates the required configuration migration. Retain the
safe new default; do not restore implicit developer-reference routing to obtain
a minor version number.

Compatibility evidence is narrower than complete behavioral equivalence. The
original22 input/output schemas and annotations match the installed original
release and exact40c wheel; explicit `serve` retains the85-tool compatibility
surface. Eleven opt-in native tools give96 only with complete native bindings.
Tool counts do not establish environment or execution qualification. Old result
contracts and explicit legacy routing remain available under their own retained
policy. The original no-argument launch changes and must be stated prominently.

## Required migration

For an existing v1 client that intentionally uses historical reference behavior,
back up its configuration and add the explicit `serve` argument:

```toml
args = ["-m", "cadence_mcp_bridge", "serve"]
```

Preserve its original remote runner, results, authority, ledger and journals.
Do not point a new operator at that developer reference installation. For a new
operator, export the installed starter, register private environment/design/PDK
and journal settings, complete trust/domain/enrollment/confirmation, and export
the explicit `serve-operator` fragment. With missing setup, SETUP_REQUIRED is
expected. Configuration validity, actual environment preflight, execution authority
and successful analysis are separate facts.

Rollback to v1 requires restoring the exact old environment and reviewed explicit
legacy client settings. v1 has no `serve-operator`; a retained new fragment must
reject before stdio and must not be rewritten into an implicit fallback. Old
versions retain new operator state but cannot expose new generic APIs. Restoring
a qualified new version must read preserved durable identities without repeating
execution or resetting budget. Host wheel rollback does not qualify a remote
native bundle rollback; any bundle transition needs its own current integrity,
shared-lock, pending-job and retained-grant checks.

## Current evidence and remaining acceptance

Supported target: professor-provided standard CentOS/Cadence/PDK VM, or equivalent
reproduced installation, in personal VMware. Windows/Python3.12.10 host and
ordinary guest UID500 have actual evidence. Observed reference guest is
CentOS6.5 i686/Python2.6.6, Virtuoso IC6.1.5.500.15 and Spectre12.1.0.347.isr3;
OCEAN standalone version was not observed. Recheck the actual installation;
these values are observations, not identities to hardcode. Other hosts, Cadence
versions and PDKs remain deferred.

Exact installed source40c879b and native bundlebf6c20 have five fresh inverter/
comparator DC/AC/TRAN routes plus a later bounded two-point AC1D Sweep, automatic
extraction, effective-input and protected-original checks. Earlier same-VM
DC/AC/TRAN and DC3/AC2 Sweep evidence remains at its original bundle scope.
Actual Codex latest-bundle status/result reads pass. A fresh empty local journal
context retains the same remote domain and ledger; same-ID remote lookup adds
zero execution or reservation. That is current-VM host-context/replay evidence,
not a fresh blank-VM installation or a new app submission.

The latest observed ledger is101 attempts and12,349,079,552 reserved bytes under
500 attempts/16GiB (17,179,869,184 bytes); same-change corrections20 remain.
The separately confirmed remaining experimental scope is one job/128MiB for the
pending fresh app DC submission. Read the latest ledger, scope and disk floor
before admission. The grant remainder is not the global unspent capacity. No
result deletion, refund, accounting reset or automatic quota increase is allowed.

Fresh app submit/query/same-ID retry/connection restart remains incomplete.
Actual authentication or platform operations cannot be replaced by an SDK test.
The outstanding repair-helper and installer PR corrections change native assets;
therefore bf6c20 execution evidence does not automatically qualify their final
replacement bundle. Final ordered PR integration, exact candidate requalification,
artifact-only operator flow and versioned upgrade/downgrade are also pending.

A private installed rehearsal swaps published-v1 code to40c, restores v1, then
restores40c with current locked runtime dependencies. Original22 schemas/
annotations and protocol inventories match; eight disposable state files retain
their hashes, including generic durable success/admission and legacy success/
failed/unknown results. Restored40c refuses repeat admission; old v1 rejects
`serve-operator`. Both wheels still report1.0.0. This is an installed distinct-code
rehearsal, **not final 1.0.0-to-2.0.0 qualification** and not actual VM/app evidence.
Repeat the cycle with the final versioned artifact and supported dependency sets.

## Proposed exact artifact allowlist

After all mandatory gates and normal integration pass, freeze one exact remote
commit and derive every distribution from it. These are proposed filenames;
none is currently a verified2.0.0 asset:

| File | Purpose and permitted contents |
| --- | --- |
| `cadence_mcp_bridge-2.0.0-py3-none-any.whl` | Original bridge modules, fixed exported helpers/runner assets, `py.typed`, four fictional operator-starter resources, generated wheel metadata and reviewed LICENSE/NOTICE/THIRD_PARTY_NOTICES. |
| `cadence_mcp_bridge-2.0.0.tar.gz` | Curated rebuild source: the same package source/resources plus pyproject, uv.lock, README, .gitignore and notices; no full operator checkout. |
| `locked-runtime-2.0.0.txt` | Exact candidate runtime dependency versions/hashes exported from uv.lock; separately installed dependencies keep their own terms. |
| `INSTALL-2.0.0.md` | Install, private setup, explicit v1 migration, update/rollback, supported envelope and troubleshooting, without developer private inputs. |
| `RELEASE_NOTES-2.0.0.md` | Verified scope, breaking launch change, deferred/unsupported features and operator actions. |
| `GENERIC_RELEASE_GATE-2.0.0.json` | Sanitized actual/synthetic/app/install/rights results bound to the exact commit and native bundle; no private journals, addresses or UUIDs. |
| `SHA256SUMS` | SHA-256 for each final attached asset, computed after contents stop changing. |

A separate runner companion is optional because the wheel includes fixed export
commands and assets. If required, permit only an audited export of those exact
package assets, fictional zero-authority examples and instructions. Operator-bound
bundles, environment keys, actual grants and registration inputs stay private.
A convenience bundle must not introduce uninspected files or vendor dependencies.
GitHub automatic source ZIP/tar.gz are additional distribution surfaces and must
be inspected at the exact commit even if they are not uploaded as attachments.

Exclude `.git`, `.tmp`, private operator settings/state/journals/grants, VM images,
Cadence/PDK binaries/models, OA/ADE, proprietary netlists, raw PSF/results, SSH
keys, authentication/license data and imported `docs/agent_plan` from the relevant
release artifacts. License/secret scans complement exact member and byte checks;
a pattern scan alone cannot establish legal rights or data absence.

## Exact-candidate checks to execute after freeze

1. Review and normally merge the dependent PRs after their final CI, review and
   acceptance gates. Verify the final remote commit/tree. No direct main push,
   force push, protected-rule bypass or bot-as-human-approval substitution.
2. Align pyproject, `__version__`, uv.lock, package metadata and installed CLI
   version once the candidate is selected. Build wheel/sdist from a clean exact
   source snapshot; run `scripts/verify-distribution.py` against that same snapshot.
   Its allowlist compares all regular package modules/resources and notices;
   reject extra/missing files, links, secret patterns and model content.
3. Run required exact hosted Windows/Ubuntu CI and local security, compatibility,
   package/installed stdio/starter checks. Distinguish skips and synthetic fixtures
   from actual Cadence/app evidence. Reinstall/uninstall must preserve external
   state. Run the semantic version upgrade/rollback/re-upgrade cycle with explicit
   client settings and durable results/replay conservation.
4. Requalify changed native assets as the ordinary user with current environment,
   preflight, integrity, authority, ledger and disk checks. Record only actual new
   executions and their effective-input/extraction results. Protect source/ADE/
   PDK/vendor content and approved metadata-repair history.
5. Create canonical local exact-commit ZIP/TAR with Git export line conversion
   disabled. Obtain GitHub-generated ZIP/tar.gz for that exact commit. Run
   `scripts/verify-git-archive.py --commit EXACT_SHA --archives LOCAL_ZIP LOCAL_TAR
   GITHUB_ZIP GITHUB_TAR_GZ`; require all retained blobs to match and no imported
   planning members. Install/validate the inspected hosted source archive without
   `.git`, developer helpers or the imported planning folder.
6. Confirm per-file distribution rights, Apache scope and third-party notices.
   `docs/.gitattributes` excludes imported planning from new archives; it does not
   clear retained history, external adaptations, browsing, clones or forks.
   Keep LEGAL_REVIEW_REQUIRED and material included-content uncertainties distinct
   from exact artifact IMPORT_EXCLUDED_VERIFIED. Do not make a blanket repository
   Apache claim or publish a blocked artifact.
7. Produce sanitized public gate/install/release documents, asset inventory,
   SHA-256, build inputs and dependency/license inventory at a stated scope.
   Verify all final files and the exact candidate installation again if they change.

## Publication boundary

The preferred destination is `Phjrab/cadence-mcp-bridge` GitHub Releases. Candidate
preparation and tests are authorized; tag creation/push, Release publication,
attachments and prior release changes are not. Report version, exact commit,
verified scope/limitations, files/hashes, installation/security/rights results and
destination together for one final public approval. That approval applies only to
the identical candidate. PyPI, MCPB, marketplace and external promotion remain
separate decisions.
