# GREL-01 result and general-release gate assessment

The user selected GREL-01 only. This phase implements operator-owned immutable
runtime routing and an installed local CLI/MCP foundation. General release is
**BLOCKED**: the package cannot yet install a qualified generic runner or execute
new operator circuits. GREL-02 is not authorized by this report.

## Candidate and baseline

- Baseline/main: 553276d28c54d8e87092229d102bfd05ec98e74f (PR #141).
  Fresh fetch/remote comparison confirmed this baseline before implementation and
  again during final verification on 2026-10-07 KST.
- Feature branch: feat/grel-01-runtime-context; merge: NOT_RUN.
  Implementation commit: 738b610d186aa6c62a68ee1591eb649dfca118d6.
  [Feature PR #142](https://github.com/Phjrab/cadence-mcp-bridge/pull/142) is open for review.
  Documentation receipts may advance the branch; final head is authoritative in
  Git/GitHub. Implementation tree: 9d05b8f789eaabfff1daa5cf92f35909a9197767.
- The original checkout remains on feat/client-lifecycle-qual-01, with its
  unrelated extract.ocn change preserved. Work uses a separate worktree.
- Package version remains 1.0.0 for this phase's local candidate. It is not a
  publication version or a released artifact. No tag/release/index/MCPB publish.
- Tested package/unit inputs manifest SHA256: 37b99af90a2dc8d41ded95b6402919b545de31322b0d18d8c9583134b7d62885.
  This hashes Windows checkout bytes; Git normalizes line endings. The package
  fingerprint identifies installed bytes, not imported memory or commit identity.

## Delivered behavior

Existing environment/design v1–v8/PDK v2 contracts now resolve logical designs to
a frozen private transport and fixed runner child under the registered managed
root. Backend creation receives the selected operator transport. A central
transport guard and isolated operator service deny every unqualified remote,
result-reader, simulation, Sweep, storage and write route. They never fall back
to a historical reference backend or open a journal.

Bare CLI launch and serve-operator use the new product path; absent settings give
SETUP_REQUIRED. Explicit serve and existing exporter fragments retain legacy
compatibility. Runtime schema/verify/resolve and context-aware fragment export
work locally from the installed package. Closed bounded settings bind current
raw hashes, capabilities, expected runner digest, authority/ledger references,
independent journals and declared resource domain. Hashes/references do not
create authority. Startup rejects stale/extra/duplicate/injected/conflicting
inputs. Active context snapshots stay fixed until reviewed restart.

Same declared host/architecture uses one OS lock across aliases and processes,
with consistent ledger/limits within one settings file. **Physical identity is
not attested**; independent state roots and cross-user provisioning remain
GREL-02/03 blockers. Execution stays disabled, so this local model grants no
extra simulator capacity. No ledger is created, reset or refunded.

CLI observations distinguish registration, preflight, analysis qualification,
authority and result validation. They expose logical IDs and digests, not private
paths, SSH aliases, OA/ADE bindings, credentials, license values or raw PDK data.
Installed source hash is self-reported/on-disk; commit SHA is null and installation
attestation false. Existing MCP runtime schemas are unchanged.

See [operator workflow](RUNTIME_CONTEXT_V1.md) for settings classification,
operator commands, error states and migration. GREL-01 does not require an
operator to patch core source to select a registered local design/context.

## Evidence, observed 2026-10-07 KST

| Check | Result | Evidence type and scope |
| --- | --- | --- |
| Final complete unit suite | PASS: 2298 passed, 6 OS symlink skips, 56 warnings (752.02s) | SOURCE_UNIT/SYNTHETIC; exact current inputs |
| Runtime + onboarding after last code edit | PASS: 75 passed, 2 OS symlink skips | SOURCE_UNIT; no Cadence |
| Runtime-specific suite | PASS: 37 passed, 1 OS symlink skip | SOURCE_UNIT/SYNTHETIC |
| Ruff check src/scripts/tests | PASS | Static source checks |
| mypy src | PASS: 60 source files | Static source checks |
| Formatting | New files PASS; broad check FAIL on 50 existing files, including pre-existing legacy regions of server/backend | Existing formatting debt preserved; no behavioral waiver |
| verify-release-readiness.py | PASS: exact 85 schemas, 22 legacy declarations, shared models, registry v1–v8 | SOURCE_UNIT/SDK_PROTOCOL; not universal behavior |
| Final installed schema audit | PASS: same exact 85 schemas | INSTALLED_PACKAGE/SDK_PROTOCOL; compatible resolved MCP 2.3.0 |
| verify-runtime-context-install.py | PASS: two synthetic contexts, restart 1→2→1, isolated designs, default SETUP_REQUIRED, zero journals | INSTALLED_PACKAGE/SDK_PROTOCOL/SYNTHETIC |
| verify-installed-package.py | PASS: Codex/mcp-json/Claude-desktop formats each 85, legacy v1–v8 local semantics, no admission | INSTALLED_PACKAGE/SDK_PROTOCOL; not actual app qualification |
| Final wheel uninstall | PASS: package no longer importable | INSTALLED_PACKAGE |
| verify-security.ps1 | PASS: secret preflight, 18 security tests, locked dependency audit has no known vulnerabilities | SOURCE_UNIT; dev MCP 2.1.1 |
| Distribution audit | PASS: wheel68/sdist69 allowlisted members, Apache-2.0/notices/source match, no unexpected or protected patterns | INSTALLED_PACKAGE; curated package, not all repository history rights |
| Original unrelated OCN selected hash | PASS | Local selected pre/post hash; no modification by this phase |
| Actual current app runtime_info_v2 | Observed existing operator catalogs/journals | ACTUAL_CODEX read-only; existing installation, not this candidate |
| This candidate in actual Codex/Claude | NOT_RUN | SDK/config format checks are not actual-client evidence |
| New native Cadence circuits/DC/AC/TRAN/Sweep | NOT_RUN | Outside GREL-01 |
| Independent review / hosted CI | NOT_RUN at report preparation | Feature PR review/checks remain separate |

Commands are the existing scripts above, plus:
~~~powershell
$env:PYTHONUTF8 = '1'
uv sync --locked --all-groups
.venv/Scripts/python.exe -m pytest tests/unit -q --basetemp .tmp/pytest-full-exact
.venv/Scripts/python.exe -m ruff check src scripts tests
.venv/Scripts/python.exe -m mypy src
uv build --out-dir .tmp/grel-final-dist
~~~
Installed verifiers ran with -I and absolute example/baseline/workspace arguments
under an isolated wheel environment. Those external public test fixtures are
acceptance inputs, not bundled generic runner/bootstrap assets. No SSH or native
simulator was contacted by these package checks. Fresh generic installation and
upgrade/downgrade with authority state still require later gates.

Final local artifacts (same tested source, not uploaded):

| Artifact | SHA256 |
| --- | --- |
| cadence_mcp_bridge-1.0.0-py3-none-any.whl | 16873a7834843b2d58de2373223e35d32d7d9b302e2b3b2d5ce48c718e43325c |
| cadence_mcp_bridge-1.0.0.tar.gz | 95c3f05dea63c790c387af405259754b1e2445b237a695530cad96f4a0b59e19 |

Installed .py fingerprint: 0d4ec878e74bf67f89f4413269dcbc0d2ae014b5d969351726363056b8dd6aa2.
These fingerprints bind evidence; they do not establish runner trust.

## General-release mandatory gates

Every assessment below is for the **whole required gate**, not a claim that a
synthetic foundation completes its missing native half.

| Gate | Status | Verified portion / remaining requirement |
| --- | --- | --- |
| G01 artifact-only installation/runner/docs | BLOCKED | CLI/core wheel works; generic runner assets/bootstrap and bundled install workflow still absent |
| G02 operator routing without core edits/fallback | BLOCKED | Local immutable selection and deny-fallback PASS; actual generic executable/ADE routing not yet qualified |
| G03 positive native preflight/trusted installation | NOT_RUN | Historical unsafe-permission rejection preserved; no chmod or mock promotion |
| G04 operator-owned reusable authority/budget/trust | BLOCKED | References are descriptive only; creation/lifecycle not implemented |
| G05 two genuinely new native circuits | NOT_RUN | Two synthetic fixtures are not new OA/ADE circuits |
| G06 new DC/AC/TRAN | NOT_RUN | No native jobs in this phase |
| G07 effective conditions of new jobs | NOT_RUN | No new jobs to inspect |
| G08 automatic new-result extraction | NOT_RUN | Historical readers preserved; generic runner/result path pending |
| G09 new native 1D Sweep/results/replay | NOT_RUN | Local contracts preserved; new native campaign pending |
| G10 reusable second job batch | NOT_RUN | Historical campaign is not proof of reusable operator authority |
| G11 retries/restarts/unknown/partial/policy changes | BLOCKED | Startup isolation tested; generic submission and recovery lifecycle pending |
| G12 shared native EDA reservation/concurrency | BLOCKED | Declared local cross-process lock PASS; attested physical domain/ledger provisioning pending |
| G13 legacy compatibility/evidence protection | PASS scoped | Full local schemas/registries/unit and installed compatibility; no remote writes. Whole live checkpoint not rehashed this phase |
| G14 clean operator context/build identity | BLOCKED | Synthetic installed clean contexts/on-disk fingerprint PASS; actual same-VM operator setup pending |
| G15 exact candidate in actual Codex app/new jobs/restart | NOT_RUN | Existing app read observation is not new-build/job evidence |
| G16 public CI/install/upgrade/downgrade/state protection | BLOCKED | Public synthetic tests and installed verifier supplied; hosted CI and full lifecycle matrix not run |
| G17 package content/license/privacy/installation | PASS scoped | Exact curated wheel/sdist/install/uninstall PASS; repository history/imported planning rights remain separately unresolved |
| G18 complete new-operator runbook/errors | BLOCKED | Registration vs qualification/errors/migration documented; runner/authority/new-job procedure pending |
| G19 publication candidate/version/exact qualification | BLOCKED | Local hashes known, version1.0.0 retained; final release candidate/version and separate publication consent absent |

Conditional capabilities: C01 fresh operator destructive storage disabled;
legacy behavior unchanged. Prior native storage qualification is retained as
history, not generic deletion authority. C02 active simulator termination remains
unsupported. C03 generic PM/Offset/Slew/other PVT/PDK qualification is NOT_RUN.
C04 actual Claude qualification remains deferred (SDK formats distinguished).
Other Cadence versions, PDKs and physical PCs remain deferred by the user.

## Resources, corrections and preservation

This phase: zero simulator attempts, reservations, deployments, result deletions,
license changes, protected permission changes or global client-config writes.
No new execution grant was generated. Live ledger/in-flight/logical/allocated/free
remote snapshot: NOT_OBSERVED this phase. Last recorded ledger is 82/500 attempts,
9,798,942,720/10,737,418,240 reserved bytes. Arithmetic only: 938,475,520 bytes =
895MiB = six complete128MiB slots +127MiB; not a fresh snapshot or authorization.
Current local test/build disk use is separate from simulator accounting.

Two earlier full runs retain the CLI test signature/UTF-8 fixture failures
(2293/2296 passes, 2 failures, 6 skips). A corrected interim full run passed
2298 with 6 skips before the final exporter wording change. These are retained
in ignored local .tmp logs. Other local correction groups cover digest typing,
Windows fixture-name size, platform type imports, UTF-8 audit output, absolute
installed-verifier paths and exporter state reporting. No remote correction
ledger was reset. Failed sandbox initialization/document-generation attempts are
retained; they do not imply completed writes. Broad formatting failure is
baseline debt, not a passed check.

Original OA/ADE/PDK/results/approvals/budgets/replay were not opened for writes.
Unrelated local OCN hash matches the selected inventory. The bounded selected
inventory contains 99,964 local records, skipped31 and rg exit2; it is explicitly
incomplete and is not whole-private or whole-remote preservation attestation.
No remote change was made; no live checkpoint-wide integrity claim is added.
Private raw logs/inventory and package files stay ignored; public documents carry
only bounded facts. No raw proprietary data, credentials, UUID authority or
license endpoint enters the PR or artifacts. Curated artifacts exclude imported
planning documents; this does not settle all Git history redistribution rights.

## Phase boundary

Final phase status: COMPLETE_FEATURE_PR_AWAITING_REVIEW. Primary diff review covers routing,
validation, isolation, package evidence and documentation; independent review is
NOT_RUN. Merge/publication and GREL-02 are not authorized by GREL-01 completion.
Next recommended phase is GREL-02: installable fixed runner assets/bootstrap,
trust and permission checks, with existing protection and budget gates intact.
The next-phase choice is requested once in the user-facing completion report.

Suggested continuation (same model/effort settings; no automatic dispatch):

~~~text
Phjrab/cadence-mcp-bridge의 최신 main과 GREL-01 PR/인계 기록부터 확인해.
GREL-02만 진행하고, 팩의 해당 runner/bootstrap 요구사항을 먼저 읽어.
기존 로컬 변경·OA/ADE·PDK·결과·권한·예산·replay를 보존해.
보호 설치/원격 쓰기는 해당 phase의 실제 권한·예산·보호 gate를 통과할 때만 수행해.
구현·테스트·문서·feature PR까지 마친 뒤 결과와 다음 phase 선택을 한 번만 물어봐.
게시·예산 증액·기존 결과 삭제·라이선스 변경은 승인하지 않는다.
~~~
