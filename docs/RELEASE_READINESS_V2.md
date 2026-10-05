# Release readiness reassessment v2

Date: 2026-10-06. Phase: RELEASE-READINESS-02. Starting main:
`4ea17e2641f316ec0899c9c91f8bea97c6b4086f`, merged SPEC-CONTRACT-01 #119.
This supersedes the **current assessment** in v1; old reports/qualification history
remain preserved. Reassessment, release-candidate preparation and publication
are separate operations. This phase selects no release commit or version update.

## Decision by distribution scope

| Scope | Status | Meaning / open gate |
| --- | --- | --- |
| Current reviewed original-code wheel and curated package-source sdist | CONDITIONALLY_READY | Build/license/install/contract evidence is verified; new-version candidate and publication authority remain separate |
| New significant public release claiming both Codex and Claude Desktop | BLOCKED_PENDING_QUALIFICATION | Exported config/SDK protocol tests do not establish actual Desktop app qualification |
| Full repository bundle or blanket Apache-2.0 repository claim | BLOCKED_LEGAL_REVIEW_REQUIRED | Imported planning ownership/redistribution terms remain unresolved |
| New GitHub release at current main | NOT_READY | Source archives represent the whole tagged tree, including imported planning; curated asset exclusion does not clear those archives. Client, exact-candidate/version and publication gates also remain |
| Another user describing/registering/inspecting private contracts | VERIFIED within documented local workflow | Does not qualify a new physical execution route |
| Arbitrary new Cadence project/PDK execution | UNQUALIFIED | Only compiled reviewed bindings execute; new profiles do not grant arbitrary routing |

No unqualified READY claim is made. Current public Git history already contains
the imported package; this reassessment does not delete it, rewrite history or
interpret its presence as permission to redistribute it. Curated wheel/sdist
exclude `docs/agent_plan`, and are distinct from GitHub's repository source archives.

## Actual repository, release and license state

| Item | Observed state |
| --- | --- |
| Repository | Public, default branch main |
| Latest merged implementation | SPEC-CONTRACT-01 #119 at the starting SHA above |
| Existing tag | Only v1.0.0; annotated tag peels to `8a0d44fab90e2095cc39322baef60fc09d741cd6` |
| GitHub release | v1.0.0 stable, published `2026-08-31T09:21:18Z`, zero uploaded assets |
| Historical release body | Still contains “not yet published”/private candidate wording; actual release metadata proves publication. Body/tag/history preserved |
| Package/runtime/uv.lock | 1.0.0, mutually consistent; no version bump |
| Current MCP surface | 69 tools; 47 additions relative to the 22-tool v1 declaration baseline |
| License | Canonical Apache-2.0 for original bridge code; modern package metadata and LICENSE/NOTICE/THIRD_PARTY_NOTICES present; GitHub recognizes Apache-2.0 |
| External products | Cadence/Virtuoso/Spectre/ADE, PDKs, clients and dependencies retain their own terms; none is supplied/relicensed |
| Imported planning | LEGAL_REVIEW_REQUIRED, unchanged and excluded from curated package artifacts |
| GitHub controls at audit | No required checks/reviews or enforced rulesets; absent CI is not a CI PASS. Local gates and exact-head review remain required |

Historical v1 notes/body are evidence, not the current installation or release
status. No existing GitHub body is silently corrected by this phase.

## Compatibility and semver

The new local audit reflects all **69 complete current tool schemas**, comparing
them with the reviewed snapshot at the starting main. It also checks the actual
v1 tag-bound **22 declarations**, both unchanged legacy shared models, v1–v7
registry schemas, source/runtime/lock versions and canonical license metadata.
Shared models use canonical LF bytes for a portable comparison; Git separately
confirms no model differences against v1.0.0. The snapshot is generated from
previous preserved actual stdio inventory, not a hand-written success list.

```powershell
uv run python scripts/verify-release-readiness.py
```

Exit 0 means `technical_contract_audit = PASS`. The result **always** keeps
`publication_authorized = false` and lists externally unverified gates. It does
not contact GitHub/Cadence, construct service/backend/job stores, call tools,
modify goals or simulate. CLI paths/credentials/client assertions are not inputs.
Empty/substituted baselines, schema/declaration/model drift, duplicate JSON keys,
nonfinite data, oversized audit files, registry drift, altered licensing or
inconsistent versions fail. The operator uses a reviewed checkout/dependency lock;
the audit is not a sandbox against someone able to rewrite that checkout.

**Conditional next-version recommendation: v1.1.0.** Evidence shows an additive
tool/CLI surface and preserved legacy declarations/shared models. New registry
versions are explicit and old schemas retained. No interface removal requiring
a major version was identified. This is not a claim of equivalence for every
possible client or formerly unsafe input: safety/identity/resource checks and
release-specific behavior remain qualification requirements. Recheck the exact
future candidate; do not mechanically apply the recommendation to later changes.

## Honest public capability matrix

| Capability | Qualification |
| --- | --- |
| Local MCP stdio, initialization/schema/list/call/error/concurrent reads/EOF | PROTOCOL_VERIFIED, independently tested wire and SDK clients |
| Codex/Claude/common JSON launch adapters | CONFIG_PREPARED and installed-package SDK subprocess verification; same server |
| Reference native DC/AC/trap TRAN and fixed-candidate/PVT/OP diagnostics | Existing bounded real reference evidence retained; preserved native result/replay/restart behavior verified |
| Environment/design/variable/analysis/PDK registration and local onboarding | Contract/local validation qualified; another physical execution route is not automatically qualified |
| Registered 1D sweep | Existing bounded RC fixture lifecycle/replay/resume/cancellation qualified; physical amplifier ranges/execution remain UNQUALIFIED |
| Storage | Reference inventory/classification/plan/dry-run verified; selected deletion has contract/fixture tests, real reference-host deletion NOT_RUN; no automatic deletion/compaction |
| Differential gain | QUALIFIED at 10 Hz, pinned native conditions only |
| Bandwidth | PARTIALLY_QUALIFIED sampled-reference 3.0 dB crossing estimate; no DC plateau/interpolation-error/unity-gain/closed-loop qualification |
| Phase margin/power/offset/slew | UNQUALIFIED; missing scientific/extraction requirements recorded |
| Specifications | Registered exact-condition comparator contracts tested; actual reference has no selected numerical goal and stays NOT_EVALUATED |
| New project/PDK physical execution, other Cadence versions/PDKs | UNQUALIFIED/DEFERRED; no additional equipment is requested by this reassessment |
| Optimization, multidimensional sweeps, automatic range/candidate/circuit changes, layout/DRC/LVS/PEX and statistics/Monte Carlo | PLANNED/UNQUALIFIED in public product scope; existing narrow diagnostics are not universal support |

The generic preflight's writable-executable rejection still applies to the
reference environment. Its historical fixed registered execution evidence is
separate. No chmod/install/source/PDK change is made to improve a readiness label.
No numerical specification or optimality claim is inferred from observed values.

## Application evidence

| Client | Registration | tools/list | tools/call | Cadence through that app |
| --- | --- | --- | --- | --- |
| Codex launch adapter / SDK subprocess | CONFIG_PREPARED | PROTOCOL_VERIFIED | PROTOCOL_VERIFIED | Preserved native SDK E2E; fresh actual app NOT_TESTED |
| Claude Desktop launch adapter / SDK subprocess | CONFIG_PREPARED | PROTOCOL_VERIFIED | PROTOCOL_VERIFIED | CLAUDE_REAL_CLIENT_UNVERIFIED |
| Other MCP applications | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED |

Current controls expose browser automation only, not native Desktop-app control.
The bounded Windows uninstall-registry query returned no Claude entry, which
does not prove absence for every installation format. No actual Desktop E2E
is fabricated. Follow the [69-tool manual procedure](CLIENT_COMPATIBILITY_V1.md)
and [current schema snapshot](contracts/MCP_RELEASE_READINESS_V2_SNAPSHOT.json).
Use discovery and an existing admitted completed result only where needed;
submitting a new Spectre job is unnecessary for client compatibility.

## Package, security and regression evidence

The canonical package gate builds a wheel from curated sdist, audits exact
members/license/source bytes and secret/model patterns, then installs under
isolated Python. It registers fictional v7 catalogs and starts all three exported
config formats from another working directory. Each exposes 69 tools and keeps
the 22 historical names, rejects unqualified admission/reads and exercises
targetless specification list/describe/evaluate without remote transport.
CLI/version/uninstall are checked. Artifacts are package-only; a full reviewed
operator checkout remains necessary for deployment helpers.

Current runtime and remote source bytes remain unchanged. SPEC-CONTRACT-01's
exact native/analog/sweep/storage/protection/counter/restart evidence is reused;
no scientifically redundant E2E simulation or deployment occurs. Local static,
full unit, contract, protocol, security/dependency and rebuilt installed-package
checks are recorded in the [phase result](RELEASE_READINESS_02_RESULT_V1.md).
Private baselines retain prior failures/checkpoints and immutable evidence.

## Exact remaining publication gates

1. **CLIENT-REAL-QUAL-01:** record direct Codex/Claude app version, registration,
   actual inventory/calls and lifecycle against the same bridge/guard configuration.
   SDK/config preparation never upgrades the application matrix by itself.
2. **Imported rights:** human review must establish author/rights/terms for the
   imported planning package before a whole-tree source archive/blanket Apache
   claim. No speculative legal conclusion or historical deletion is substituted.
3. **Exact candidate/version:** after prerequisite decisions, select a reviewed
   candidate, apply consistent version metadata in its separately activated phase
   and run candidate-specific gates. This audit commit is not an approved release
   candidate merely because its local checks pass.
4. **Publication authority:** approve exact tag/release/assets/index and any
   historical release-body correction only after a concrete reviewed result exists.
   Autonomous feature-PR authority does not include those external actions.

Current assessment can finish while these gates remain open. Recommend actual
client qualification next; rights review can proceed independently. No automatic
release, MCPB packaging, source removal or optimization phase is activated.
