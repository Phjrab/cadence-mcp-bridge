# Current Phase Plan — Post-v1 Baseline and Capability Preparation

## AUTO-PHASE-01 active overlay, 2026-09-29

The user's explicit bounded delegation replaces this plan's project-level STOP,
per-read and per-PR approval gates for future in-scope operations. See
`policy/PHASE_AUTONOMY_V1.md` and `policy/PHASE_CAMPAIGN_V1.json`. The older
restrictions below describe the pre-transition phase and remain historical for
legacy records. A new implementation or remote operation still needs actual
capability, fresh evidence, integrity, budget, replay, and environmental checks.
WP-14 is the current circuit task; PR #57 and WP-15/WP-16 are complete and are
not repeated. The 2026-09-30 WP14-CLOSEOUT records completed work-copy
characterization with no numerical specification evaluation in
`WP14_CLOSEOUT_RESULT_V1.md`. The original source/ADE scientific baseline and
historical snapshot equivalence remain unverified. Stop after this closeout's
report and ask once before beginning the proposed `SIM-MCP-01` implementation.
The user subsequently selected SIM-MCP-01. Its fixed work-copy DC/AC MCP
implementation and real client E2E are recorded in `SIM_MCP_01_RESULT_V1.md`.
The next proposed phase, SWEEP-MCP-01, requires a separate user choice.
The transition was integrated through PR #58. Subsequent bounded observations
and copied-revision tests are reconciled in the closeout report. Candidate
biases remain 320/702 mV; VDD=1.0 V is a hard constraint. The observed VCM,
load scope, revision, and applied values are specific to the cited evidence,
not assumed for a future live design.

## Authority and boundary

This is the only active phase plan after the `v1.0.0` release baseline. The complete long-term
direction is recorded in `docs/AUTONOMOUS_CADENCE_MCP_FULL_ROADMAP.md`, but that roadmap is not an
execution instruction. An execution reads only the roadmap sections needed for its active WP.

The Git, security, approval, testing, completion-report, and STOP rules in
`CODEX_MASTER_PROMPT.md` remain binding. WP-00 through WP-11 are completed v1 history and must not
be reopened or treated as incomplete. Existing evidence from later exploratory branches remains
historical evidence and is not authority to perform a new mutation.

## Agent-plan integration overlay

The reviewed prompt package is available under `docs/agent_plan/` as a planning reference. Its
work-package IDs use the independent `ICF-*` namespace and do not renumber, reopen, or supersede
the repository's existing `WP-*` history. `docs/agent_plan/WORK_ID_MAP.md` is the required
crosswalk; mappings are evidence references, not automatic completion claims or execution
authority. The imported package templates and archive references are inactive by default.

The user explicitly selected **WP-16 — ADE and Sweep Capability Inventory** after PR #54
integrated the repository-only WP-15 design as
`239b1fc7e4fd0d59e1e17d089d2a16d16856dc13`. WP-13's audit was merged through PR #19 as
`b12cff904fe31a1d68490836c1fe6765734b9bf0`. WP-16's repository-only inventory
was merged through PR #55 as `b2239f5743034aa019d33dd29f6c1e4da230d17e`;
the active intent/fact/approval interaction rule was merged through PR #56 as
`85706385cfb82b60d829f44c1ac197339eebbafd`. WP-14 remains blocked: its
scientific baseline and fresh remote evidence are unconfirmed. A separately
approved one-time renewal local preflight returned `LOCAL_PREFLIGHT_READY` on
2026-09-29; it established only local prerequisites at that instant, not remote
or circuit facts. See `docs/WP16_ADE_SWEEP_CAPABILITY_INVENTORY_V1.md` and
`docs/interaction/GOALS_FACTS_AND_APPROVALS.md`. No unscoped remote probe,
parameterized execution, sweep, or WP-14 baseline promotion follows from these
merges or the local result. Other `ICF-*` tasks remain planning references, not
execution instructions.

## Phase objective

Reconcile the post-release repository and security truth, establish an authoritative read-only
actual ADE baseline, resolve the `VBIASN`/`VBIASP` source of truth, design a technology-neutral PDK
abstraction, and inventory legacy ADE/sweep capabilities before any parameterized implementation.

## Work packages

| WP | Scope | Required outcome | Mutation boundary |
|---|---|---|---|
| WP-12 — Roadmap Integration | Preserve the v1 contract, integrate the long-term roadmap, reconcile governance metadata, and establish this bounded phase. | Documentation authority is unambiguous and repository/security state is recorded. | Repository documentation only. |
| WP-13 — Actual ADE Profile Baseline and Capability Audit | Audit the approved actual profile, ADE state, source snapshot, fingerprints, freshness, and available read-only introspection paths. | A bounded evidence report identifies facts, drift, and unknowns without choosing values by inference. | Read-only; no runner deployment, simulation, OA save, ADE state change, or PDK/work-library write without a new explicit contract. |
| WP-14 — VBIASN/VBIASP Source-of-Truth Confirmation | Reconcile repository defaults, ADE state, source snapshot, prior evidence, and explicit user choice. | One versioned, user-approved baseline contract or a documented blocker. | No parameterized execution or sweep. |
| WP-15 — PDK Abstraction Design | Define a technology-adapter schema for devices, parameters, models, corners, layers, verification backends, and protected source-of-truth metadata. | Repository-only design and threat model with gpdk090 as a regression adapter and no proprietary PDK content. | Documentation/schema design only unless a later WP explicitly authorizes code. |
| WP-16 — ADE and Sweep Capability Inventory | Inventory IC6.1.5/ADE L/Spectre capabilities, fixed APIs, extraction paths, budgets, and fail-closed gaps required before implementation. | A capability matrix and implementation prerequisites for a later phase. | Read-only probes only when separately scoped and approved; no sweep or mutation. |

## Phase acceptance gates

The 2026-09-17 user-approved visibility policy is PUBLIC. WP-14 version-2 request
packages supersede only the active private-visibility prerequisite and related hash
bindings; version-1 packages and v1 release history remain preserved. Public operation
does not authorize transport or publication of fresh evidence. Exact evidence fields
require local publication review. Deployment remains disabled and existing operation,
data-protection, single-use, testing and Git approval controls remain mandatory.

- Repository visibility, release baseline, branch policy, and protected-data policy agree across
  GitHub metadata and repository documents.
- The actual ADE profile baseline is supported by bounded, reproducible evidence.
- `VBIASN` and `VBIASP` are never selected from conflicting evidence without explicit user
  confirmation.
- The PDK abstraction contains no proprietary model, rule deck, raw netlist, or guessed MyChip
  identifiers.
- ADE/sweep implementation remains disabled until the capability inventory and input contracts are
  complete.
- Each WP uses a dedicated feature branch from the latest approved `origin/main`, passes its
  acceptance checks, updates `PROJECT_STATE.md`, pushes only that feature branch, verifies its
  remote SHA, and stops.

## Explicit exclusions

This phase does not authorize arbitrary shell, SSH, SKILL, OCEAN, file-path, netlist, or PDK access.
It does not authorize remote runner deployment, Cadence execution, OA/database writes, ADE-state
changes, schematic/layout changes, work-library mutation, sweep execution, repository visibility
changes, direct `main` pushes, force-push, or automatic merge. Any such action needs a later exact
WP contract and any required separate user approval.

## Phase exit

The phase may advance to ADE/sweep implementation only after WP-13 through WP-16 are integrated and
all unresolved baseline, capability, approval, and proprietary-data questions are recorded. The
WP-14 blocker remains recorded even though the user explicitly selected the
repository-only WP-15 and WP-16 checkpoints. Neither selection authorizes WP-14
execution or satisfies phase exit. WP-16 must not start automatically after WP-15
is pushed or merged; this inventory follows a new explicit user request.
The older numbered implementation sequence in
`docs/NEXT_VERSION_SCOPE.md` is historical and cannot override this plan.
