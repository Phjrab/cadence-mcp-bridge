# Release readiness reassessment v3

Phase: RELEASE-READINESS-03. Implementation baseline:
`61e7b1fdaa0ac0d2415dd1eecacaaa9f506dde89`, merged specification PR134.
The user's continuation activates this assessment only. Exact assessment
candidate/archive/build/review/main receipts belong to its containing feature PR.
This assessment supersedes current conclusions in v2; dated evidence is preserved.

## Distribution decision

| Scope | Readiness | Remaining decision or limitation |
| --- | --- | --- |
| Original bridge wheel and curated package-source sdist | CONDITIONALLY_READY | Candidate build/content/install gates, explicit version and exact publication authorization required. |
| Inspected new Git ZIP/TAR snapshots | IMPORT_EXCLUDED_VERIFIED only for the exact inspected commit | Subtree omission is verified; retained external adaptations still require rights review. |
| Whole repository, clone, fork, Git bundle/history, blanket Apache grant | BLOCKED / LEGAL_REVIEW_REQUIRED | Imported planning provenance does not establish redistribution rights. |
| Release claiming latest complete Codex/Claude app qualification | BLOCKED_PENDING_QUALIFICATION | Current85-tool actual app schema/version/lifecycle is NOT_RUN; complete Claude gate unverified. |
| Limited local-stdio/reference-environment release | CONDITIONALLY_READY for preparation | Declare only verified protocol/scientific scope and explicit app limitations; select exact version/candidate/assets before publication. |
| New tag, GitHub Release, PyPI, MCPB or historical release-body edit | PUBLICATION_NOT_AUTHORIZED | Requires separate explicit authorization for the concrete reviewed target. |

No unconditional READY claim is made. A limited release need not implement every
future measurement or optimization feature. A limited scope also cannot claim
missing actual app or scientific qualification. Claude and other environments
remain user-deferred; this phase does not request new equipment or app work.

## Current product scope

| Capability | Evidence and qualified scope |
| --- | --- |
| Standard local MCP stdio | SDK/config/independent wire protocol evidence: initialization, typed schemas, calls/errors, concurrent reads and shutdown. Current source85 inventory is separate from actual app inventory. |
| Codex, Claude and common JSON launch configurations | Same server and guards; isolated installed-package SDK subprocess checks. No client-specific execution privilege. |
| Environment/design/variable/analysis/PDK onboarding | Registered contracts and bounded local validation. Generic preflight's writable-executable rejection remains; another registered circuit is not automatically executable. |
| Native DC/AC/TRAN, power and existing diagnostics | Actual reference evidence and preserved-result/replay/restart checks at their exact registered conditions. No arbitrary circuit/expression/path route. |
| Finite bias grid | VBIASN319/320/321mV, fixed VBIASP702mV,VDD1V,VCM0.5V,NN27C,existing topology/no added external load. Finite simulation points only; no continuous range or device-rating qualification. |
| Real amplifier Sweep | Existing durable engine, two real three-point DC/AC sweeps, same-ID/restart and completed-cancel no-op verified. Pending-only cancellation; active termination is unavailable. Active cancellation/crash/partial failure paths have synthetic evidence, not real fault-injection qualification. Six-slot campaign activation is exhausted; no new experiment is authorized here. |
| Differential gain | QUALIFIED differential voltage gain at10Hz on the fixed reference/grid; not DC gain, closed-loop gain or another frequency. |
| Power | QUALIFIED signed `-V*I` DC supply-rail extraction/derivation. Bias/input/all-source totals separate. Not DUT-only or transient average power. Original power definition remains unchanged. |
| Bandwidth | PARTIALLY_QUALIFIED first3.0dB crossing relative to10Hz gain, with actual bounded grid-refinement agreement. No rigorous absolute error bound, unity-gain or closed-loop qualification. |
| Phase Margin | UNQUALIFIED/null: present reference lacks a defined application feedback loop. Installed STB/probe help is not an executed stability measurement. |
| Slew | Supplemental opposite-step20–80% rise/fall secants and resolution/edge agreement, PARTIALLY_QUALIFIED in nonlinear saturated open-loop conditions. Generic conventional slew remains UNQUALIFIED/null. |
| Offset | User-selected nominal open-loop input nulling `Vp−Vm` at `Vop−Vom=0`: supplemental PARTIALLY_QUALIFIED. Near-zero numerical residual is not femtovolt physical accuracy, mismatch statistics or PVT qualification. Generic Offset remains UNQUALIFIED/null. |
| Specifications | Existing exact-condition comparator with originalv1/v2 and explicit companionv3 grid facts. Six actual gain/power facts retain NOT_EVALUATED because no authoritative numerical goals exist. Synthetic target PASS/FAIL is not real design acceptance. |
| Storage | Native one-synthetic-payload selected deletion/audit/replay/restart verified in STORAGE-REAL-QUAL-01. Actual Codex summary/list/describe/plan reads verified in CLIENT-STORAGE-QUAL-01; app deletion NOT_RUN. No general historical-result cleanup or compaction. |
| New Cadence versions/PDKs/hosts | DEFERRED, no MULTI_CADENCE_VERSION_VERIFIED or MULTI_PDK_VERIFIED claim. |
| Optimization, multidimensional search, automatic expansion/modification, Layout/DRC/LVS/PEX/Monte Carlo, public MCP endpoint | Outside the present product qualification; no automatic activation. |

## Client evidence

Latest Storage checkpoint: [actual Codex Storage reads](CLIENT_STORAGE_QUAL_01.md)
verify26 filtered names and complete inventory/description/plan payload equality
with preserved evidence after reconnect. Execute is excluded; no extra deletion
or simulation occurred. This scoped update does not satisfy full app schema,
source/build/version or lifecycle qualification. Publication status above is
unchanged. Earlier client observations below retain their dated scope.

Latest operator checkpoint: [actual Codex reads](CLIENT_REAL_QUAL_CODEX_OPERATOR_03.md)
verify operator-v8 Gain/Power/DC/AC/TRAN and no-target evaluation with full
historical equality under22 client-filtered read tools. Separately selected
finite-grid runtime/two Sweep results/six no-target facts now match historical
evidence, with sequential shared-lock reads and preserved concurrent failures.
Full app schemas/source identity/version/new
lifecycle remain unverified. Explicit global bridge configuration was changed
only in this subsequent read qualification; the release reassessment itself
made no configuration changes. Earlier updates below remain dated history.


Update 2026-10-07: [current Codex checkpoint](CLIENT_REAL_QUAL_CODEX_CURRENT_02.md)
verifies85 actual app-visible names after the user restart and preserved native
DC re-reads. Full schemas, source/build identity, app version and new lifecycle
remain unverified; operator-bound current measurement/sweep/specification reads
remain blocked by unselected catalogs/journals. Earlier observations below
remain dated history. PR127 Claude Code-tab reads/restart are verified in that
limited scope; full-current Claude qualification remains separate.


Actual Codex historical discovery/native DC reads and runtime observation are
retained. The recorded runtime selected builtin registryv4/default journals,
distinct from current-source SDK finite-grid registry/journal qualification.
Latest85-tool full app schemas, source identity, new tool calls and lifecycle:
NOT_RUN. Do not upgrade that status from SDK subprocess results.

Claude PR127 records limited Code-tab existing-result reads/restart, with unknown
tested source tree. Preserve it as historical app evidence. Complete current
Desktop qualification remains **CLAUDE_REAL_CLIENT_UNVERIFIED / DEFERRED_BY_USER**.
Other MCP hosts are NOT_TESTED. No global app configuration is changed here.

## Compatibility and version

Package/runtime/uv.lock remain1.0.0. Only v1.0.0 tag/release was observed at phase
start; historical release metadata/body/assets remain untouched. Current source
has85 tools and explicit registryv1–v8, companion targetv3 and factv1 contracts.
The exact additive snapshots preserve all old schemas, including the83-tool
pre-specification baseline and22 historical v1 declarations/shared models.
Existing replay/admission/RC/compiled Sweep identities remain unchanged.

Conditional next-version recommendation remains **v1.1.0** for an appropriately
scoped additive release. This is not a version instruction, selected release SHA
or universal behavioral equivalence claim. Revalidate exact candidate/version,
dependencies, scope and client assertions when that later phase is authorized.

## Licensing and archive boundaries

Canonical Apache-2.0, NOTICE and THIRD_PARTY_NOTICES.md cover original bridge
material where rights exist. Cadence/Virtuoso/Spectre/ADE, PDKs, clients and
separately installed dependencies retain their respective terms. gpdk090 is a
local/reference adapter, not a bundled PDK or redistribution grant. No vendor
binary, netlist/model/PSF/result, key, credential or license configuration is added.

Direct installed MCP2.1.1/mcp-types2.1.1/Pydantic2.13.4/core2.46.4/settings2.15.0
metadata and license files confirm MIT/DEPENDENCY_ONLY at the locked-source
audit. Curated artifacts do not vendor them; freshly resolved installed-package
versions are recorded separately by the package gate. No dependency-wide future
version or license guarantee follows.

`docs/agent_plan` remains tracked and byte-identical, excluded from new inspected
Git archives and curated wheel/sdist. Export-ignore does not hide web/clone/fork/
bundle/history or alter old tags/downloads. Root/archived planning references and
decision adaptations outside the subtree retain separate LEGAL_REVIEW_REQUIRED;
subtree exclusion does not clear those rights. No infringement conclusion,
relicensing, import deletion or Git history rewrite is made.

## Repeatable verification

Use a full reviewed checkout for historical planning/package integrity gates.
Source archives intentionally omit that helper and its imported inputs; missing
historical inputs are not waived or relabeled as product installation success.
See [archive boundary and installation](AGENT_PLAN_EXPORT_BOUNDARY_V1.md).

```powershell
uv sync --frozen --all-groups
uv run ruff check src scripts tests
uv run mypy src
uv run python -m pytest tests/unit
uv run python scripts/verify-release-readiness.py
.\scripts\verify-security.ps1
.\scripts\verify-package.ps1
```

For an exact source archive, inspect all four formats against that Git commit
with `scripts/verify-git-archive.py`; then build/install the inspected hosted ZIP
in a fresh location without `.git` or imported planning. Current product install,
contract audit, CLI and stdio checks are separate from the historical helper.
Technical PASS is not app/scientific/legal/publication authorization.

## Resource and protection checkpoint

This phase0 simulations/0 reservations/deployments/deletions. Last live checkpoint
82/500 and9,798,942,720/10,737,418,240 reserved bytes; seven128MiB slots remain.
Deletion never refunds historical consumption. Existing Sweep six jobs occupy
1,105,799 logical/1,511,424 allocated bytes; this is not whole VM usage. Local
archive/build/audit storage is separate from simulation reservation accounting.
Preserve original OA/ADE/PDK/vendor, jobs/replay/admissions/ledgers, prior evidence,
all baseline private hashes and local changes.20-correction ceiling, prior usage
and removed elapsed ceiling remain active.

## Next phase decision

This phase ends after local/package/exact archive gates, reviewed feature PR and
remote verification. Before publishing, choose the exact scope/version/candidate/
assets and resolve material gates for that scope. Current actual Codex read-only
qualification can be a separate next phase; Claude remains deferred. Numerical
goals are needed only for real specification acceptance, not invented for release
readiness. No next phase or publication is automatically activated.
