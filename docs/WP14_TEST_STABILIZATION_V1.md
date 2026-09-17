# WP-14 isolated local test stabilization v1

## Scope and provenance

Continued the clean feature branch wp/WP-14-approved-narrow-deployment from the
verified local/remote HEAD 4dce2dbb07ae0f56cf6e820d5c0da12ef5999d7d.
Only test code, synthetic fixtures and checkpoint documentation are changed.
No real authorization, claim, remote command, deployment or design operation occurs.
The historical PARTIAL results in WP14_RECOVERY_IMPLEMENTATION_V1.md are preserved.

## Encoding correction

The narrow-deployer test module now explicitly reads and writes all text as UTF-8.
The fake Python process also reads package/activation fixtures as UTF-8, and its
PowerShell harness explicitly reads the call journal as UTF-8. Two AST regression
tests require explicit UTF-8 on read_text/write_text calls in the relevant Python
files. This exercises Korean temporary paths without relying on PYTHONUTF8=1.

A separate legacy synthetic write-metadata helper fixture now sets child output
PYTHONIOENCODING=utf-8 to match its parent's explicit UTF-8 decoder. Python
deprecation warnings contain the Korean helper path; previously they caused an
asynchronous decoder warning even though the test assertion passed. One regression
test captures a Korean character from a local Python child. This changes only
the test fixture, never the actual design helper or a Cadence execution environment.

## Separate startup, timeout and output checks

Output overflow, stderr and invalid-UTF-8 tests no longer shorten the production
300-second budget to three seconds. They retain the external 30-second harness
timeout, assert timely rejection and exactly one fake call, suppress payloads,
and check that the owned fake child has exited.

The hanging-child, concurrency and shared-deadline tests configure a short budget
ONLY in the temporary rewritten fake fixture, starting once after the first child
starts. It is not restarted for subsequent calls. Thus the shared-deadline case
still has to fail before all 25 stages, while the hanging-child case must terminate
its owned fake process. Existing pre-start expiry tests independently retain the
production stopwatch and reject before transport. The original 300-second total
budget and all security checks in both production executors are unchanged.

The fixture helper accepts only its temporary fixture and one of three fixed
budgets. No production test mode, CLI override or arbitrary transport hook is added.
Production hashes remain:

- Original deployer: 3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc
- Recovery candidate: e4ed2610aa0cb6a5b930b0ce6a52f1a6d2273c390195f0b58ff3e17c0d976374

## Reproducible isolation

The test tree is a new Git-index export, initialized as a local fixture-validation
repository with no remote. It contains no ignored real activation files or operator
ledger. Synthetic grants remain inside pytest fixtures. The original working-copy
activation and both consumed claims are preserved; they are not deleted to satisfy
the historical inactive-repository tests.

The full local command is `uv run --frozen pytest -m "not integration"
-W error::pytest.PytestUnhandledThreadExceptionWarning -q` with
CADENCE_MCP_RUN_INTEGRATION=0. No forced UTF-8 mode is needed for this test run.
Ruff and strict mypy are also run in the same clean export.

The security gate is `scripts/verify-security.ps1` in that export. Its first attempt
passed secret/security checks but third-party pip_api could not decode pip's CP949
output containing a Korean path. Running that unchanged gate with child-output
environment PYTHONIOENCODING=utf-8 resolves the tool-to-tool encoding mismatch.
This is not a skipped vulnerability check, dependency change or production setting.

## Boundary retained

Local verification does not authorize recovery execution or scientific baseline
confirmation. PUBLIC and deployment_enabled=false remain unchanged. No SSH/SCP,
Cadence/SKILL/discovery/simulation, OA/ADE/design/PDK mutation, merge, main push,
tag/release change or WP-15 work is performed. Final execution authority, current
preimage validity and feature review remain separate gates.

## Final acceptance results

- One clean full run: 365 passed, three real integrations skipped, five real
  integrations deselected, 56 existing deprecation warnings, 445.96 seconds.
  Asynchronous thread exceptions were promoted to errors; none occurred.
- Earlier full run: 364 passed with the legacy child-output decoder warning;
  that fixture was corrected and the entire suite rerun, not merely filtered.
- Ruff and strict mypy (17 source files): PASS in the clean copy.
- Secret scan and all 18 security tests: PASS; strict locked dependency audit
  passed with no known vulnerabilities using the documented UTF-8 child output.
- Production executors, eleven assets, existing plans/packages/evidence and local
  consumed records are preserved. No activation or operator-ledger writes occur.

The requested local stabilization is PASS. This supersedes only the local-test
blocker, not the preserved historical report or independent remote execution gates.
Next action is review and explicitly authorized PR integration of the feature;
do not automatically deploy or reuse the consumed original authorization.
