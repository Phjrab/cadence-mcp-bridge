# Existing WP to ICF Evidence Crosswalk

## Rules

The repository `WP-*`, recovered legacy capability `P*-*`, and package `ICF-*` identifiers are
independent namespaces. A row below maps intent and reusable evidence; it never renumbers a task,
reopens completed history, imports an old approval, or automatically marks an `ICF-*` task complete.
Detailed legacy `P*-*` mappings remain in the package planning catalogs and must be verified against
the current repository before use.

| Existing repository work | Reusable capability/evidence | Related new ICF scope | Mapping status |
|---|---|---|---|
| WP-00 Repository bootstrap | Repository, policy, and environment baseline | ICF-00-01, ICF-00-02, ICF-00-05 | Reference only; current facts require fresh checks |
| WP-01 Windows scaffold | Typed local contracts and packaging scaffold | ICF-01-01, ICF-01-09 | Partial evidence; no automatic completion |
| WP-02 CentOS runner | Restricted runner and job-root controls | ICF-01-03 through ICF-01-05 | Partial implementation evidence |
| WP-03 SSH backend | Allowlisted transport and host validation | ICF-01-02, ICF-01-04 | Partial implementation evidence |
| WP-04 MCP server | Typed MCP surface and result contracts | ICF-01-02, ICF-01-09 | Partial implementation evidence |
| WP-05 End-to-end lifecycle | Submit/status/result/cancel lifecycle | ICF-01-03 through ICF-01-05 | Partial real-environment evidence |
| WP-06 Codex registration | Registration and operator setup | ICF-15-02 | Historical deployment evidence only |
| WP-07 Security hardening | Isolation, audit, bounds, recovery, and secret checks | ICF-00-02, ICF-01-02 through ICF-01-09 | Strong reusable controls; new acceptance still required |
| WP-08 OCEAN/SKILL discovery | Fixed read-only OA/ADE metadata discovery | ICF-02-01, ICF-05-02 | Partial read-only capability evidence |
| WP-09 ADE profiles | Actual fixed profile and provenance | ICF-02-01 through ICF-02-03 | Partial; freshness and variable binding unresolved |
| WP-10 ADC measurements | Synthetic measurement contract | ICF-02-05, ICF-09-01 through ICF-09-05 | Synthetic-only evidence; not actual ADC signoff |
| WP-11 Controlled writes and v1 release | Staged write, backup, rollback, audit, release | ICF-01-07, ICF-01-08, ICF-15-04 | Specific V1-V4 evidence only; no general write authority |
| WP-12 Baseline reconciliation (merged implementation) | Fixed read-only actual-profile audit and fingerprints | ICF-00-03, ICF-02-01 | Evidence input; decision/freshness remain unresolved |
| WP-12 Roadmap integration (merged documentation) | Post-v1 authority and bounded phase plan | ICF-00-01, ICF-00-06 | Documentation reference; does not complete ICF tasks |
| PKG-INTEGRATE-01 | Package import, authority decisions, and this crosswalk | ICF-00-01 planning prerequisite | Documentation integration only; review pending |
| WP-13 Actual ADE Profile Baseline and Capability Audit | Next bounded read-only audit | ICF-00-03 plus read-only portion of ICF-02-01 | **Next actual task after merge; not started here** |

## Current selection

The duplicate historical use of `WP-12` is disambiguated by title and merged commit history, not by
rewriting old entries. PKG-INTEGRATE-01 is an orthogonal documentation task and does not consume the
next implementation number. The single next task remains WP-13 as defined in
`docs/CURRENT_PHASE_PLAN.md`.

Only these package sections are relevant to WP-13:

- `docs/agent_plan/prompts/work_packages/ICF-00-03.md` for compatibility/research baseline separation;
- `docs/agent_plan/prompts/work_packages/ICF-02-01.md` for fixed read-only ADE introspection.

WP-13 must use the root contract's stronger boundary: no remote runner deployment, MCP tool change,
simulation, OA write/save, ADE-state modification, schematic/layout/work-library/PDK mutation, or
parameterized execution. Unknown or stale evidence remains unresolved rather than inferred.
