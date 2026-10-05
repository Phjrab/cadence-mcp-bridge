# PDK-ADAPTER-01 result v1

Starting main: `e8c451b6c64fba264a50979bc25563e865f432e2` (merged PR #107).
Feature branch: `feat/pdk-adapter-01`. Integration is recorded by the containing
feature PR and verified GitHub merge state; no post-merge state-sync PR.

## Implementation

Runtime PDK registry v2, operator schema/validate/register, immutable configured
snapshots and three closed read-only MCP tools (48 total). gpdk090 reference
identity/capabilities are separated from generic contracts. Registered analysis
dispatch requires the exact loaded reference and native digest. Historical v1
technology files, design registry v1/v2/v3, plan hashes, native workers, protected
write policies and preserved evidence remain unchanged.

## Verification

Frozen sync, Ruff and strict mypy (30 files) passed. Focused tests: 171 passed,
two Windows symlink permission skips. Security: 18 passed, secret scan passed,
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

Full unit gate: 1,413 passed, three failed, two OS symlink skips and 56 existing
warnings. Two failures are stale 45-tool expectations (actual 48):

- `tests/unit/test_native_diagnostics.py:356`, native MCP schema/validation.
- `tests/unit/test_variable_contracts.py:370`, local variable MCP validation.

The third failure was the delegation fixture's Git remote check because the
full-suite invocation lacked the established safe-directory/Git runtime settings.
That exact test passed with those settings (one pass), with no code changes.
The original full gate remains failed; it is not reported as passed.

Three corrections are exhausted. No fourth code/test correction or merge is
performed. [Feature PR #108](https://github.com/Phjrab/cadence-mcp-bridge/pull/108)
remains draft. Resume requires an additional correction allowance for both exact
expected counts 45 → 48, full validation with established Git settings, review
and permitted integration. No new simulation or protection change is needed.
GitHub has no checks/reviews at this checkpoint; absence is not CI success.

Corrections: (1) import/style and literal tuple typing; (2) exact server tool set
and short pytest IDs for Windows temporary names; (3) the separate exact read-only
tool set. Failed transcripts remain private. First E2E lacked the established Git
safe-directory runtime settings and was denied locally before transport. Applying
that operator environment succeeded without changing code or authority bytes.

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
