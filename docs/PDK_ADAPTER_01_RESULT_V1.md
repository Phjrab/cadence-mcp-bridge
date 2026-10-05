# PDK-ADAPTER-01 result v1

Starting main: `e8c451b6c64fba264a50979bc25563e865f432e2` (merged PR #107).
Feature branch: `feat/pdk-adapter-01`,
[PR #108](https://github.com/Phjrab/cadence-mcp-bridge/pull/108). The containing
PR and actual GitHub merge state identify integration/ending SHA; the private
final checkpoint records exact remote SHA/tree equality. No state-sync-only PR.

## Implementation

Runtime PDK registry v2, operator schema/validate/register, immutable configured
snapshots and three closed read-only MCP tools (48 total). gpdk090 reference
identity/capabilities are separated from generic contracts. Registered analysis
dispatch requires the exact loaded reference and native digest. Historical v1
technology files, design registry v1/v2/v3, plan hashes, native workers, protected
write policies and preserved evidence remain unchanged.

## Verification

Frozen sync, Ruff and strict mypy (30 files) passed. Final full unit gate:
1,416 passed, two Windows symlink permission skips, 56 existing warnings.
Resumed focused tests: 290 passed, two OS symlink skips. Security: 18 passed, secret scan passed,
no known dependency vulnerabilities. Package build/install/version/uninstall/
cleanup passed with copy installation.

Actual subprocess stdio exposes 48 tools. Configured PDK metadata/resolution
match projections; path/extra fields are denied. Legacy and registered native
DC/AC/trap TRAN equal preserved results. The prior closed admission catalog was
copied to new private state; old plan hashes and restart lookup are preserved.
An explicitly empty PDK catalog blocks before admission/transport. Terminal
cancel remains no-op. Fresh guards, job trees and accounting match before/after.
New Spectre attempts, reservations, deployment bytes and paid resources: zero.
Current private accounting remains 62/500 attempts and 7,114,588,160 reserved
bytes; broader private storage ceiling and narrower native-v2 gate are unchanged.

Initial full unit gate: 1,413 passed, three failed, two OS symlink skips and 56 existing
warnings. Two failures are stale 45-tool expectations (actual 48):

- `tests/unit/test_native_diagnostics.py:356`, native MCP schema/validation.
- `tests/unit/test_variable_contracts.py:370`, local variable MCP validation.

The third failure was the delegation fixture's Git remote check because the
full-suite invocation lacked the established safe-directory/Git runtime settings.
That exact test passed with those settings (one pass), with no code changes.
The original full gate remains failed; it is not reported as passed.

The initial checkpoint exhausted three corrections and stopped with a draft
[PR #108](https://github.com/Phjrab/cadence-mcp-bridge/pull/108). The user explicitly
allowed one additional correction: both exact counts 45 → 48. That fourth
correction is applied; resumed focused tests have 290 passes and two OS symlink
skips, Ruff/mypy/frozen sync pass, and final full validation passes with the
established Git settings. Original audits and failure evidence remain intact.
This is a phase-specific extra allowance, not a general budget reset.

Production source bytes match the successful sealed E2E. Fresh resume postflight
again proves protection, preserved job trees and accounting unchanged. No new
simulation, reservation or deployment is needed. GitHub had no checks/reviews
at the blocked checkpoint; actual checks/reviews/rules are re-read on the final
feature head before permitted merge. Absence is not CI success.

Corrections: (1) import/style and literal tuple typing; (2) exact server tool set
and short pytest IDs for Windows temporary names; (3) the separate exact read-only
tool set. Failed transcripts remain private. First E2E lacked the established Git
safe-directory runtime settings and was denied locally before transport. Applying
that operator environment succeeded without changing code or authority bytes.
Correction (4), explicitly authorized by the user for this phase only, updates
the two exact tool counts. Total used: 4/4 including the additional one allowance.

## Remaining limits and next phase

Registration describes capabilities; arbitrary PDKs and physical bindings remain
unqualified. Generic device/CDF/PCell mappings, statistics, layout and DRC/LVS/PEX
are not implemented. PVT observations do not establish specification compliance.
No numeric goal or continuous safe bias range is invented. Generic environment
preflight still rejects writable executable wrappers; installation is unchanged.

After integration, recommended next phase: ONBOARD-CLI-01, joining the environment/design/
variable/analysis/PDK workflow for another operator and clearly reporting missing
execution qualification. Real-design sweeps still require reviewed ranges and
qualified adapters. Report and ask once before another major phase. FS stays paused.
