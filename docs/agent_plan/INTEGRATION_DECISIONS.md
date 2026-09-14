# PKG-INTEGRATE-01 Integration Decisions

## Scope and provenance

The `CADENCE_MCP_FINAL_PROMPT_PACKAGE` was imported on 2026-09-14 from a user-provided local
package into `docs/agent_plan/`. The source package verifier passed before import. Its package
version `2.0.0` is a documentation-package version and does not change the software release
baseline `v1.0.0`.

Source integrity anchors:

- `PACKAGE_MANIFEST.json`: `c275a0319d364c25e2a811d736a48d2fb43bb6ca91aebbafd07a0a9dd50de28a`
- `CHECKSUMS.sha256`: `7a42058541d48f2f1d28c875373f4e29f0b02abec75769e84d3e3b7a81823f77`
- `START_HERE.md`: `324ff43ab154d8ef325e4aec287a86947bbaaf6ee677d2d6dd7e355cbce49d91`
- `IMPORT_PROMPT.md`: `f9a0a78e7a133f6a60f04ef561c04ac3fbd00422f7ecc720c5539a353fb3ad1a`
- pre-integration root contract and its archive:
  `3d291a8babee489f772937bb3c63ca8129396abaadad2ea2d2432bffc23405cd`
- integration base `origin/main`: `a3e6b4a1a5eedd183c994902917d60847bda0799`

## Authority resolution

1. Root `AGENTS.md` and `CODEX_MASTER_PROMPT.md` remain authoritative.
2. `PROJECT_STATE.md` selects the active work and `docs/CURRENT_PHASE_PLAN.md` bounds it.
3. Imported documents apply only when the active WP cites them through `WORK_ID_MAP.md`.
4. A conflict is resolved in favor of the narrower and safer existing approval, security, Git,
   testing, protected-data, evidence-preservation, and STOP rule.
5. Imported roadmaps, work-package prompts, templates, examples, recovered approvals, and archived
   history do not grant execution authority and do not mark capabilities complete.

The package's proposed root master was therefore retained at
`docs/agent_plan/CODEX_MASTER_PROMPT.md` rather than replacing the current root contract. The root
contract was linked to the package's compatible strengthening rules, and its pre-edit bytes were
archived at `docs/archive/CODEX_MASTER_PROMPT_pre_PKG-INTEGRATE-01.md`.

## Inclusion and exclusion

All 178 active package files were copied under `docs/agent_plan/` with their package-relative
layout. Of those, 177 remain byte-identical; `tools/verify_package.py` received style-only changes
required by the repository Ruff policy without changing its validation behavior. The original
validator remains anchored by the source package manifest and checksum above.
`archive/LEGACY_INPUTS.zip` was intentionally excluded because it is recovered historical
input, not active authority, and requires separate content and licensing review before any Git
addition. References to that ZIP are provenance descriptions, not a claim that the binary is in
this repository.

No runtime code, dependency, configuration, circuit, PDK, OA database, ADE state, remote runner,
job, or V1-V4 evidence was modified. No repository visibility, branch protection, tag, release, or
deployment state was changed.

## Baseline conflict handling

The package records `VDD=1.0 V` and distinguishes historical `300m/650m` compatibility evidence
from `370m/650m` research evidence. Neither pair is promoted to an active parameterized baseline by
this integration. Existing read-only WP-12 evidence remains historical input to WP-13; unresolved
source/state freshness and bias-variable ownership remain fail-closed.

## Status interpretation

`PKG_INTEGRATED_REVIEW_PENDING` means the documentation was locally integrated, verified, committed,
and feature-pushed but not merged. It does not mean that any `ICF-*` implementation, deployment,
real-environment validation, or release gate passed. The next bounded implementation task remains
repository WP-13 after explicit review and merge of this branch.
