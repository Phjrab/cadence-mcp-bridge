# 2.1.0 release notes — candidate preparation

Status: unpublished, candidate not frozen. Exact commit, assets, hashes, final
CI/review and installation receipts must accompany the finished candidate.
The published [v2.0.0](https://github.com/Phjrab/cadence-mcp-bridge/releases/tag/v2.0.0)
files are unchanged. These notes describe the candidate, not an available release.

## Added since published2.0.0

- `operator-setup`: step-by-step local fresh/existing installation guidance,
  contract checks and exclusive runtime/client exports using existing validators.
- `cadence://feature-guidance` and `operator-features`: available/blocked local
  capabilities and reasons, separating legacy, synthetic and native routes.
- `operator-results`: retained-job discovery, authenticated existing-result
  capture, local reports/search and exact-condition repeat comparison. Reporting
  runs no simulation or extraction. Native catalog/report resources are additive.
- Explicit experimental extraction-only recovery via `operator-recovery`,
  preserving the original failure/PSF and linking a separate admitted attempt.
  Actual qualification is limited to the tested registered inverter DC route.
- Explicit experimental analog readers: sampled-reference bandwidth, nominal
  sampled input nulling, signed sampled10/90 step averages and an ideal unilateral
  voltage-loop margin. Scientific eligibility, provenance and unavailable/null
  outcomes are preserved; these are not general device performance guarantees.
- Local immutable design revisions and bounded operator-only CDF/physical metadata
  APIs. The narrow owned-inverter execution example is evidence for its observed
  binding, not general automatic circuit or physical design.

The candidate also includes reviewed output-publication, retained-result guidance,
recovery-output, scientific-boundary and metadata replay/framing corrections.
Old failed/unknown attempts and spent claims remain preserved and charged.

## Compatibility and version

2.1.0 is additive to2.0.0: explicit legacy `serve`, configured `serve-operator`,
the safe unconfigured launch, existing v2 settings and public tool declarations
remain. No implicit developer connection is restored. Original22 contracts remain
preserved; the common85-tool and conditional96-tool surfaces keep their existing
eligibility. New resources and operator CLI commands do not grant execution.
The major bare-launch migration belongs to2.0.0 and is not repeated here.

Host installation and native activation are distinct. Recovery needs its exact
qualified native assets and separately confirmed bounded authority. Updating the
wheel cannot reset or enlarge grants, ledger consumption or OS-account claims.
See [installation/rollback](INSTALL.md) and [qualification](QUALIFICATION.md).

## Supported scope and limits

Support targets the professor-provided standard CentOS/Cadence/PDK VM in personal
VMware, with private operator-specific SSH, accounts, paths, circuit registration,
journals and limits. Earlier actual evidence is Windows/Python3.12.10 plus that
standard VM; package acceptance of Python3.13 is not actual qualification.
Another host, Cadence version, PDK or cloud/multi-user environment is untested.

General user-defined transistor W/L, finger/multiplicity semantics and mixed-input
candidate batches/comparison are unfinished and excluded. Existing analysis
requests require complete registered logical variable values; native Sweep stays
bounded1D, not multidimensional search. Existing repeat comparison retains strict
identical conditions. No automatic candidates, optimization, layout generation,
DRC/LVS/PEX backend, general historical deletion or compaction is supplied.
Claude app qualification is excluded by user; SDK evidence is separate.

M2 DC/TRAN proves generation, effective input, execution and extraction for its
registered example. Its short loaded TRAN does not prove useful logic switching,
settling, slew, analog performance or signoff. Negative sampled loop margins and
rejected measurements are not converted into circuit PASS.

## Distribution

Planned destination: GitHub Releases in Phjrab/cadence-mcp-bridge only, after
explicit approval of the exact candidate. Planned attachments are the wheel,
curated sdist, hash-locked runtime requirements, install guide, these notes,
qualification/release receipt, dependency/license inventory and SHA256SUMS.
No PyPI, MCPB or marketplace posting is included.

The original bridge code is Apache-2.0 within its rights. Dependencies and
Cadence/PDK/client software keep their own terms. Curated packages exclude
imported planning, VM/vendor content, OA/ADE, proprietary netlists/results,
credentials, licenses and journals. Exclusion does not clear whole Git history,
clones or imported/external adaptation rights; those remain LEGAL_REVIEW_REQUIRED.
