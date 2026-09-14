# Current Phase Plan — Post-v1 Baseline and Capability Preparation

## Authority and boundary

This is the only active phase plan after the `v1.0.0` release baseline. The complete long-term
direction is recorded in `docs/AUTONOMOUS_CADENCE_MCP_FULL_ROADMAP.md`, but that roadmap is not an
execution instruction. An execution reads only the roadmap sections needed for its active WP.

The Git, security, approval, testing, completion-report, and STOP rules in
`CODEX_MASTER_PROMPT.md` remain binding. WP-00 through WP-11 are completed v1 history and must not
be reopened or treated as incomplete. Existing evidence from later exploratory branches remains
historical evidence and is not authority to perform a new mutation.

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
next execution after WP-12 integration is WP-13 only.
