# MEAS-CONTRACT-02 result

Date: 2026-10-06. Starting main:
`0e85a12804d550279a9da0c5ebe9f92acabcc62e`, merged archive-boundary #124.
Branch: `feat/power-measurement-contract-binding`.
One containing feature PR completes review and permitted integration; exact
candidate/ending remote SHA and tree are recorded privately after verification.
No separate state-sync PR or publication is authorized.

## Implemented scope

- One bounded measurement catalog discovers legacy analog and separate signed
  DC power definitions, reader routes/hashes and complete goal descriptions.
- Operator registry v8 adds version-2 signed-power goals with exact definition,
  reader/DC binding and collision/combined-limit enforcement.
- Version-2 specification evaluation preserves the actual PowerResult envelope
  and reuses the existing admission reader and shared comparator/conditions.
- Version-2 local runtime observation reports the actual loaded v8 catalog.
  Original v1-v7 observation/schema remains exact; v8 requires the new tool.

Current tools72 ->75; all old72 full schemas and v1-v7 registry schemas remain
exact. Package version1.0.0 and default registry v4 stay unchanged. Original v7
goals and analog v1 power remain unchanged/UNQUALIFIED. Complete execution
projection, admission and durable sweep identity are preserved.
See [workflow and contracts](MEASUREMENT_BINDINGS_V2.md).

## Scientific evidence

The existing qualified `dc-supply-power-v1` read returns the identical
**82.42816 microW** at NN/27 C/VDD1 V/applied bias320/702 mV. Six signed source
currents/voltages, VDD/VSS rail subtotal, separate bias/input/all-source totals
and original definition/input/PSF/frame/extraction provenance are preserved.
No new extraction, simulation or wider circuit/PVT qualification occurred.

Preserved real DC/AC/TRAN and RC sweep results equal earlier evidence under
new v8 stdio configuration; restart catalog/evaluation/power reads remain equal.
The real-result regression uses a private **targetless** contract envelope:
NOT_EVALUATED, no target PASS/FAIL or fabricated requirement. Actual qualified
fact comparison paths are tested with explicitly synthetic fictional goals.
Real reference goal arrays remain empty.

## Gate classification

| Gate | Evidence/status |
| --- | --- |
| Focused unit/contract/server/runtime regression | PASS:147 tests |
| Full unit | PASS:1,813 passed,4 OS symlink skips,56 warnings,481.33s |
| Ruff | PASS:source/tests/current verification scripts |
| mypy | PASS:50 source modules |
| Exact schema/declaration audit | PASS:75 tools, old72 exact, old v1-v7 exact, new v8 schema |
| Security tests | PASS:18 tests; one existing cache-permission warning |
| Secret preflight | PASS:869 repository files |
| Dependency audit | PASS:no known locked dependency vulnerabilities |
| Distribution audit | PASS:wheel58/sdist59; canonical Apache license/notices, no unexpected files/protected patterns/imported planning |
| Isolated installed CLI/stdio/uninstall | PASS:75 tools in Codex/Claude/generic JSON SDK configurations, v8 discovery/v2 targetless evaluation |
| Preserved actual Cadence result reads | PASS:existing native power/DC/AC/TRAN/sweep identity and postflight protections |
| Actual current Codex app additions | NOT_RUN; historical five real reads preserved |
| Actual Claude app | DEFERRED_BY_USER / CLAUDE_REAL_CLIENT_UNVERIFIED |
| New Spectre/extraction/deployment/deletion | NOT_RUN; no authority/need in this phase |
| Other Cadence/PDK/host qualification | DEFERRED_BY_USER |

The installed subprocess checks are SDK evidence, not actual desktop-app E2E.
Synthetic sources/targets do not establish another physical measurement.
The final README/distributions/security/docs were rechecked before commit.

## Failures, resources and protection

Initial static/type failures and their second tuple-inference correction,
the stale72 inventory assertion, process-scoped Git ownership setup failure
and the first E2E authority refusal are retained privately. Successful retries
do not erase failures or weaken authority. Conservative corrections:5 of20;
prior phase histories remain unchanged. A proposed broad test-update command
was rejected by automatic approval review and never executed; only explicit
current-count assertions were patched and v8 uses a separate fixture.

New Spectre attempts0; new reservation0; new owned remote artifacts0 bytes;
deployments/deletions0. Cumulative attempts **62/500** and reserved results
**7,114,588,160/10,737,418,240 bytes** are unchanged. Cumulative reservations
are not live storage occupancy; full managed/VM disk usage was not measured
in this phase. Existing500/10 GiB/20 limits and removed elapsed ceiling remain.

Fixed pre/postflight verifies original OA/ADE/PDK and historical jobs/results/
counter protections. Shared admission bytes and all **1,342** prior top-level
private records retain baseline hashes. Previous failures/evidence, vendor/PDK
material, Apache notices, immutable policies and imported181 files are preserved.
No source/PDK is imported to implement these adapters. Archive export exclusion
and preserved rights review remain distinct; LEGAL_REVIEW_REQUIRED and
PUBLICATION_NOT_AUTHORIZED remain. Historical missing legacy package inputs
are not waived. No tag/release/version/index/body change is performed.

## User capability and next boundary

A client using an explicitly configured v8 catalog can discover the validated
signed-power definition and evaluate operator-recorded user goals through its
existing admitted source reader. Without a target it receives NOT_EVALUATED.
Scientific qualification is still limited to the existing fixed reference.
Actual current app lifecycle and deferred external/rights/publication gates
remain open. Recommend **BANDWIDTH-QUAL-02** next, with separate user confirmation.
