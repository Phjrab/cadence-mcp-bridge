# Installed helper diagnostic failure checkpoint, 2026-10-12

Status: **METADATA_CAPTURE_FAILED_BEFORE_ADMIN_APPLY / GENERIC_RELEASE_BLOCKED**.
The user requested that a test failure be recorded and this run ended after a
bounded amount of progress. This checkpoint preserves that boundary. It does
not revoke the earlier GREL02-08,16GiB or minimum administrator delegation.

## Progress and verified source

Source inspected and installed: `952c39c3dad2b4f8220cbd1b5a3d9d25cd3a77d5`.
Source/scripts/tests/remote/package metadata are identical to tested291010d;
only dated checkpoint documents changed. The exact Git archive produced a new
isolated2.0.0 installation. Distribution/license/content allowlist checks PASS:
112 wheel members/113 sdist members, no unexpected or protected content patterns.
Installed fixed bootstrap and existing/fresh domain synthetic checks PASS.
These checks do not qualify actual Cadence execution or a release candidate.

Private diagnostic artifacts, retained locally and not approved release files:

| Artifact | SHA-256 |
| --- | --- |
| cadence_mcp_bridge-2.0.0-py3-none-any.whl | df36b6fac2b18e8850b55a4d9cdaaa866d7b3ecd618c0f355a0278888bd667d6 |
| cadence_mcp_bridge-2.0.0.tar.gz | beb349d91f60a634153ec14fcb1de2a656984072457ee44a101252c6a9167d49 |
| Installed repair helper | b792173c6bfcbcd5d84859eff4cd2a254270f573ce24d88bd3e2a22fc4f5c52d |

GitHub connection was restored after the human reconnected it. Mandatory CI
plugin reads confirmed all four Windows/POSIX checks PASS for final heads148
2c3acbc,14930deec7,150cd79587,15123d4147 and152952c39c. Final root automatic
review6117583132 reports no major issues for952c39c. That bot result is not a
formal GitHub APPROVED, and unresolved inline threads must still be individually
triaged before normal dependency merges. No PR was merged during this run.

Actual installed normal-user read-only repair inventory PASS:569 exact targets,
233 planned metadata corrections. Its target/content/owner/identity/mode and
normalized ACL values match the retained291010d observation. The installed
helper/frame hashes, exact plan, target ACL/content hashes and rollback method
were privately retained. No target was applied or trusted by exemption.

## Failure, effects and preserved evidence

The additional pre-apply private diagnostic attempted to capture full lstat/link/
xattr/SELinux metadata for the exact installed plan. It failed on the actual
Python2.6 VM at `ctypes.c_ssize_t`: that attribute is absent. The exception occurred
while declaring libc return types, before iterating target paths. This is a
compatibility error in the new private diagnostic, not a failing Spectre job,
corrupted vendor binary or failed core repair-plan. No successful full xattr or
SELinux capture is claimed. Its script, empty stdout, stderr and failure summary
remain in the private installed-952c39c-20261012-v1 evidence directory.

No administrator application started:0 target metadata changes,0 new Spectre
runs and0 new reservations. No original OA/ADE, Cadence/PDK content, license,
existing journal/ledger/result/replay was written. The prior four-directory and
older authorized metadata receipts remain history; the additional233 targets
are still pending. No cleanup/refund/reset, new paid resource or publication.
Last verified shared accounting remains102/12,483,297,280 reserved bytes, leaving
4,696,571,904 of the current managed VM's16GiB; an actual fresh read is required
before any new admission.500 and same-change20 remain and correction consumption
is not fabricated or reset.

## Resume order

Correct only the private diagnostic's ssize_t return declaration using the
observed i686 ABI and a Python2.6-compatible signed ctypes type. Validate that
size/error return conversion on disposable data before the real target capture.
Keep the failed source/evidence; write a new diagnostic/evidence version. Finish
full pre-change recovery metadata, reread the current installed inventory and
actual lock state, then apply only the approved exact target list through the
existing administrator access. Capture post-state, verify identical content/
ownership/identity and only intended mode/ACL/ctime differences, repeat changes0,
and recheck normal-user trust/qualification/preflight. Do not run MCP/EDA as root.

Finish inline-review triage/normal parent integration; reconcile active20-change
correction scope and existing500/16GiB ledger/disk before the bounded final8-job/
1GiB validation. Final installed two-circuit DC/AC/TRAN, AC2 Sweep/spec/extraction,
actual Codex submit/query/same-ID retry/reconnect, operational matrix and exact
GREL08 candidate remain. Historical40c/bf6 successes are not current-source PASS.
The app connection works; no app configuration was changed and no restart is
required now. If a later prepared QA configuration requires restart, preserve
state, end the turn and resume after the human says restart complete.
Tag/Release/upload still needs approval of the exact qualified candidate.
