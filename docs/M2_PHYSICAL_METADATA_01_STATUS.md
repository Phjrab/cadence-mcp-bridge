## Approved host-only correction overlay, 2026-10-16

The latest direct user reply explicitly approves retain35/ceiling36 and exactly
one host-only correction for review4291980402, followed by the original unused
single metadata stage/query only after tests and review pass. This supersedes
older statements that source36 is unapproved; those records remain historical.
The authority is the direct user reply, not this generated record or policy.

`physical_metadata.collect` now claims a fixed OS-account state location before
SSH, independent of the prepared plan, SSH alias, environment/bundle/request IDs
and process lifetime. The key uses the existing declared VM resource domain
(hostname/architecture), guest account and unchanged collector SHA. Even a changed
managed root cannot reset it. Exclusive creation arbitrates concurrent callers;
partial, malformed, failed and unknown claims remain spent. Private ownership,
Windows DACL/POSIX modes, symlink/junction checks and namespace revalidation reject
untrusted state. This trusted local state is evidence: preserve and migrate it with
the operator account; do not delete it to retry. It does not protect deliberate
external deletion by the owning operator/admin or substitution of the OS itself.

The remote collector remains LF SHA256
`42da5bd7a1bee41176e0578dc5e04c438b618735c667566db454421b7d6ff15d`.
V1 policies/consumption and the frozen POST/M2 guards are preserved. The additive
[version2 guard](../scripts/verify-physical-metadata-boundary-v2.py) enforces
35 retained plus one host correction, no remote source change or added query.
Final tests/review/exact installed checks and actual single query remain pending.
No simulation, extraction, reservation, administrator action, merge or publication
is authorized by this extension. PR161 stays draft/unmerged; published2.0.0 unchanged.

### Source36 local verification checkpoint

Frozen host correction: focused46 PASS/7 Windows POSIX skips; Ruff/mypy116
PASS; security18 PASS and strict locked dependency audit clean. Actual OS-account
home and read-only security validation PASS. SYSTEM ownership of a trusted Windows
home is accepted only as an ancestor; claim directory/file ownership still requires
the current token. Windows shared-write ACL and junction rejection are actual
owned disposable tests. Full local unit suite and package lifecycle are in progress;
hosted exact source/review and actual single metadata stage/query remain pending.

Development failure logs are preserved privately: an initial inaccessible Windows
system-temp selection, OWNER RIGHTS ACL handling, fixture CRLF pins, and unloaded
sandbox OS-profile refusal. These did not contact the VM or create the actual
singleton intent. Later focused results replace only their local test scope.
The prior broad7-failure/source35 record below remains unchanged.

# PHYSICAL-METADATA-01 status, 2026-10-16

**BLOCKED BEFORE DEPLOYMENT.** Source35883eb is implemented and locally installed,
but review4291980402 identifies a reproduced one-shot intent defect. Do not invoke
`collect` from this build. No collector was staged or queried on the VM.

## Fixed scope and accounting

The direct user reply approved one collector/host-parser version, retaining34
consumed source versions and extending the ceiling only to35. Source commit
`35883eba22e4d8697787a59462e497d29575be23` consumes that version. The unchanged
POST/M2 guards still report34; the additive guard reports35/35. Old policies,
failed sources, grants, journals and resource records remain unchanged.

At2026-10-16T07:29:18Z, existing native runtime inspection and storage inventory used the current owned
registration at ordinary UID500, changed0 runtime files and preserved the local
journals, including the absent unused sweep journal. No EDA/license command ran.
The separate connected QA app storage call rejected; it supplies no disk evidence.

| Actual managed VM | Observation |
| --- | --- |
| Shared attempts |128/500 |
| Reserved result bytes |15,721,299,968/17,179,869,184 |
| Remaining reservation capacity |1,458,569,216 bytes (1391MiB) |
| Filesystem free bytes |25,541,607,424 |
| Existing storage disk floor |6,238,251,418 bytes; OK |
| New simulations/extractions/reservations |0/0/0 |
| Actual collector stage/query |0; authorized one remains unused |

Installed local preparation authenticates four directory targets and a517,205-byte
request. The plan hash is
`64b689793bb1ba60d922170ea9b8ee6db9f45ccfd3caf2ffa643dff78033dc29`.
An earlier local-only plan is retained as superseded implementation evidence.
Neither local plan is a remote query or independent execution authority.

## Blocking review and minimum proposed correction

[Review4291980402](https://github.com/Phjrab/cadence-mcp-bridge/pull/161#discussion_r4291980402)
is valid: the local intent lives only under the caller-selected plan directory.
If transport fails before the remote source-hash claim exists, a fresh `prepare`
directory admits another transport call. The remote claim protects operations
that reach it; it does not close this earlier window.

An offline reproduction substitutes transport with a function that raises before
SSH. Two prepared directories produce **2 calls, expected1**. The assertion failure
is retained privately. It is not an actual retry, VM query or simulation. The
review thread remains unresolved, regardless of otherwise passing CI.

Minimum correction: a durable atomic host intent outside the plan directory,
keyed to the registered VM/account/resource identity and unchanged collector
source. New aliases, plan paths and process restarts must not reset it. Reject
symlinks/junctions and untrusted replacements; failed/partial/unknown outcomes
stay consumed. Regression checks must cover fresh plans, restart and concurrent
claims. Existing request/package bindings and remote claim remain intact.

This requires **retain35, ceiling36, one host-only local correction**, with remote
collector bytes unchanged. The still-unused single actual stage/query remains
one; no extra simulation budget is needed. No corrective source, policy extension,
deployment, retry, merge or publication was performed under this proposal.

## Exact development source and artifacts

| Source | LF SHA-256 |
| --- | --- |
| Remote collector |`42da5bd7a1bee41176e0578dc5e04c438b618735c667566db454421b7d6ff15d` |
| Host parser |`ed53fa30974425d11f038140c3fcb520fba339de706bb1e22ff34fc2f0433cc9` |

These are private verification artifacts of35883eb, **not new public2.0.0 files**:

| Artifact | SHA-256 |
| --- | --- |
| `cadence_mcp_bridge-2.0.0-py3-none-any.whl` |`c07fddfdabf586c6c4699637af1acff9a70e68d3af8dd699a0ecfa79fe9fa06b` |
| `cadence_mcp_bridge-2.0.0.tar.gz` |`ec208949959e182e3873a2a1440d7655b987a3c369154830f2911fa4f2ade5ab` |

Exact distribution/source/license/exclusion audit, isolated installed source pins,
local plan and installed85-tool/22-legacy protocol checks PASS. Final local focused
collector/guard plus targeted failure rerun30 PASS/6 Windows POSIX skips;
Ruff/mypy116 and contract audit PASS.
Both hosted jobs at35883eb PASS in
[run38867080476](https://github.com/Phjrab/cadence-mcp-bridge/actions/runs/38867080476).
Linux job116862274157 includes disposable filesystem/flock and the154-test
foundation/collector group with no skips. Windows job116862273908 reports4071 PASS,
387 platform skips,56 warnings, clean strict dependency audit and complete installed
package/reinstall/uninstall/state-preservation gates.
The original tests lack the reproduced cross-plan case and do not invalidate P1.

The broader local suite started before the final enumeration adjustment and is
not exact-final-source proof:7 failed/4047 passed/404 skipped. Three boundary tests
loaded fixture code before the BASELINE fixture update while dynamically loading
the newer guard, hence base-commit mismatches. Four storage/WP14 cases also failed
in the long workspace fixture path (one reports WinError3 while copying a deeply
nested checkout). All seven, plus the final collector suite, pass in a fresh process
with a short temporary root, with no storage/WP14 product change. Both broad failure
and focused rerun logs remain preserved; do not relabel the broad run as PASS.
Initial full-suite isolation and installed-verifier
relative-workspace failures are retained host harness failures. The exact installed
protocol rerun uses absolute paths and passes. The earlier package lifecycle
rehearsal passed43+20+5 disposable-state preservation but preceded the final change.

Private receipts/logs/manifests and failure reproduction remain in ignored `.tmp/`;
no private target paths, journal contents, raw metadata or candidate names enter
distribution files. Actual physical tools/decks/APIs remain UNKNOWN; licenses and
DRC/LVS/PEX execution remain unverified. Published2.0.0, main and PR161 draft state
are unchanged. No collector deployment or administrator mutation ran.
