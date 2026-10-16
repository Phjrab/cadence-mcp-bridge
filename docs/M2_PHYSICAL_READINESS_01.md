# M2 physical readiness investigation, 2026-10-16

This is the bounded continuation after the owned-inverter PR160 merge. It
reconciles the available read routes and defines the next finite collection
scope. It does not implement or qualify a physical backend. The authority is
the user's continuation instruction; this document is not an approval record.

## Integrated baseline and current observations

PR160 merged normally as `06f407a3bba814ad2823323bed9604624f7b3061`.
Its tree is identical to approved head `fb75f0dc9e02f8c940407a0967a844bddf0d1b3a`.
Both post-merge Windows and Linux jobs passed in
[run38850326785](https://github.com/Phjrab/cadence-mcp-bridge/actions/runs/38850326785).
This is source/package verification, not physical execution evidence.

The connected QA server reports bridge2.0.0, an operator-supplied v4 design
catalog with two entries and a v2 PDK catalog with one entry. This local response
assesses neither remote connectivity nor execution authority nor qualification.
Its version alone cannot identify the newly integrated development source.

One call to the existing allowlisted `cadence_list_libraries` returned
`invalid_configuration`, `RUNNER_SETUP_REQUIRED`, `retryable=false`.
No inspect request, bootstrap, deployment or fallback followed. The fresh result
agrees with the older attempt in [the foundation inventory](M2_PHYSICAL_OBSERVATIONS.md).
It does not prove that a physical tool or technology library is absent.

The exact retained installed99af package then performed the existing native
read-only preflight against the existing owned-inverter bundle. It passed at
ordinary UID500, with changed_files0. The same resource domain reports128 shared
attempts and15,721,299,968 reserved bytes. Both local journal states are preserved,
including the absence of the configured unused sweep journal. No empty journal
was created. The first local observation harness stopped before transport because
it assumed that journal existed; that failed harness is preserved separately.

The actual preflight demonstrates that the native registered route is available.
It retains its existing version/identity probes; these do not collect physical
API, tool, deck or license evidence. No new collector, simulation, extraction,
reservation, runtime update or administrator operation was performed in this
continuation. Prior DC/TRAN evidence remains
attributed to its [actual execution source](M2_OWNED_INVERTER_ACCEPTANCE_20261015.md).

## Why the metadata route rejects

`OpenSshBackend._invoke_at_path` explicitly rejects `OperatorTransport` before
process creation because the legacy operator runner is not attested. The local
operator context selects that transport. Changing the configured alias or the
native grant cannot supply the missing runner attestation.

The legacy `remote/bin/cadence-runner` metadata commands were reviewed in the
foundation. They inspect only their fixed project schematic/symbol allowlist;
they provide no physical backend or technology inventory. The operator runner
pin also differs from that legacy runner. Replacing a pin to match local code,
constructing a legacy BridgeConfig to evade the operator gate, or inventing a
second raw SSH path would defeat the intended boundary. None was done.

Native setup preflight uses authenticated package assets and the registered
environment through a separate fixed protocol. Its success therefore does not
contradict the legacy metadata rejection. Enabling legacy metadata is not a
prerequisite for a future dedicated physical collector, and no generic fallback
should be added to the public MCP surface.

## Current acceptance matrix

| Capability | Current observation | Next evidence needed |
| --- | --- | --- |
| Registered native route and accounting | Current preflight PASS, UID500, changed0 | Recheck immediately before any newly authorized action |
| Legacy operator metadata route | BLOCKED by missing attestation | Dedicated reviewed physical route; do not weaken the legacy gate |
| Physical tool installation | UNKNOWN | Exact registered installation metadata, without launching candidates |
| DRC/LVS/PEX deck binding | UNKNOWN | Operator-bound deck identity and compatibility evidence |
| Layout/PCell/technology/DBU/LPP/vias | UNKNOWN | Fixed typed API observation for the registered technology |
| Physical license entitlement | LICENSE_UNVERIFIED | Separately scoped feature-specific observation |
| DRC/LVS/PEX and post-layout execution | EXECUTION_UNVERIFIED | Later same-revision lifecycle and clean/bad controls |

`UNKNOWN` is not `unsupported` and is not `VERIFIED`. An installed executable,
deck filename or configured license variable cannot qualify their combination.
No exact physical tool/version/deck combination was freshly observed here.

## Next bounded slice: PHYSICAL-METADATA-01, proposed

The next useful slice is one fixed ordinary-user collector, rather than a
physical computation or another inverter performance experiment. Its initial
target set must come from the current registered standard-VM environment and
PDK bindings, retained privately with their hashes. Do not use historical version
numbers or guessed installation/deck paths as observed facts.

1. Prepare one fixed package-owned collector and host parser. Accept only the
   exact registered environment/PDK binding and a fixed operation identifier;
   expose no arbitrary path, shell, SKILL, expression or executable input.
2. Inventory metadata only under the exact registered installation/PDK locations.
   Resolve links and record typed identity/trust/hash information privately.
   Maximum128 exact candidate entries, no recursive search, no reading license
   contents, no invoking candidate binaries, version/help switches or license
   utilities. Overflow, missing bindings and ambiguous links are errors.
3. Use the existing authenticated operator transport and resource lock. Review
   the exact immutable source, target manifest and containment/trust checks before
   invocation. Stage only inside a fresh owned runtime directory; preserve a
   failed or partial stage. Do not replace the active simulation bundle or
   modify configuration to make a failed attestation pass.
4. Bound the complete action to60s and1MiB per output stream, with one invocation
   and no automatic corrective redeployment. Return path-free capability facets
   and evidence hashes; keep installation paths and raw diagnostic data private.
5. Compare protected source/model/journal and accounting state before/after.
   Expected new attempts/reservations/extractions are0. Stop on any drift,
   source mismatch, output truncation, lock conflict or unexpected process.

This first metadata slice cannot observe the callable layout APIs by filesystem
presence alone. Any OCEAN/Virtuoso startup for technology/DBU/LPP/via reads needs
its own reviewed invocation and declared log/cache/license effects. Do not hide
that invocation inside an installation inventory. Physical calculation,
layout writes, DRC/LVS/PEX and optimization are outside the proposed slice.

The consumed source record remains34/34 under V16; this investigation changes
no collector/generator or protected native source. A new collector is not a way
to reset that history. Before implementation/deployment, obtain one explicit
bounded extension retaining34 and allowing one additional collector version
(proposed total35), with no automatic correction allowance. Preserve prior
policies, grants, failures and journals. Do not mint another simulation grant.
Approval of PR160's merge covered integration only, not this new deployment.

## Evidence and verification scope

Private receipts are in the physical-readiness worktree's ignored `.tmp/`:
the connected-server library response, installed preflight receipt, local
failure record and current route/source identities. They are not distribution
files or new execution authority. The original owned-inverter worktree is retained.

This branch changes documentation only. Validate whitespace and local document
links and confirm no package, native source or policy changes. Existing source
CI at the identical integrated tree remains applicable; do not rerun Cadence or
call the physical acceptance criteria complete to validate prose.
