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
| PKG-INTEGRATE-01 | Package import, authority decisions, and this crosswalk | ICF-00-01 planning prerequisite | Merged through PR #18 as `198900ecc96c9cadd3697022f96c90bd5baf937a` |
| WP-13 Actual ADE Profile Baseline and Capability Audit | Bounded actual read-only audit | ICF-00-03 plus read-only portion of ICF-02-01 | Merged through PR #19 as `b12cff904fe31a1d68490836c1fe6765734b9bf0`; profile drift remains |
| WP-14 VBIASN/VBIASP Source-of-Truth Confirmation | Versioned compatibility/research candidate decision package | ICF-00-03 baseline separation only | Proposal ready for review; scientific baseline confirmation blocked; no ICF task marked complete |

## Current selection

The duplicate historical use of `WP-12` is disambiguated by title and merged commit history, not by
rewriting old entries. PKG-INTEGRATE-01 is an orthogonal documentation task and does not consume the
next implementation number. WP-13 is now merged; WP-14 is the active documentation task defined in
`docs/CURRENT_PHASE_PLAN.md`. It prepares a decision package, keeps all approval fields unset, and
does not start WP-15.

The following references were used by WP-13 and remain dated evidence:

- `docs/agent_plan/prompts/work_packages/ICF-00-03.md` for compatibility/research baseline separation;
- `docs/agent_plan/prompts/work_packages/ICF-02-01.md` for fixed read-only ADE introspection.

WP-14 references only the compatibility/research baseline requirements of `ICF-00-03` and the
related historical context in `docs/agent_plan/docs/ENVIRONMENT_BASELINES.md`. Its namespace,
template approvals, proposed VDD, and next-task suggestions do not replace the active WP contract.
There is no WP-14 probe, remote runner deployment, MCP tool change, simulation, OA write/save,
ADE-state modification, schematic/layout/work-library/PDK mutation, or parameterized execution.
Unknown or stale evidence remains unresolved rather than inferred.
