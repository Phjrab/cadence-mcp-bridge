# CLIENT-COMPAT-01 result

## Integration identity

- Starting main: `28d5313cbacbde2cdc3aba1389548d4c2e1115bb`, merged #110.
- Branch: `feat/client-compat-01`.
- Ending main / containing PR: verify the containing feature PR's actual merge
  commit through GitHub. This report is committed before integration; no
  follow-up state-sync PR is needed. Exact final identity is in the private
  checkpoint and user completion report.
- Bridge: 1.0.0; locked MCP SDK 2.1.1; isolated package gate resolved 2.3.0.
  No version, license, tag or release metadata was changed.

## Capability and API

The same stdio server now has a named Claude Desktop exporter using the existing
MCP JSON serializer; Codex TOML remains intact. Operator-only sweep journal
configuration removes package location as a requirement for explicitly
configured installations. Omission preserves the exact historical ledger path.
No journal migration/reset occurs. Shared profiles/PDK/analysis/sweep state
belong to the bridge, not the client. Both adapters launch the same package.

MCP tools before/after: **48 / 48**. All names, descriptions, annotations and
input/output schemas compare equal with starting main; 22 v1 declarations are
also checked by the installed package gate. No new execution capability or
caller path/script input is added. `--format claude-desktop` is additive;
`--sweep-journal` / `CADENCE_MCP_SWEEP_JOURNAL_PATH` are operator configuration.

Another operator can export reviewed Claude registration and use external local
sweep storage without editing source or a separate server implementation. A
registered new Cadence design/environment still needs physical qualification.

## Client outcomes

| Client | Registration | tools/list | tools/call | Actual Cadence E2E through the desktop app |
| --- | --- | --- | --- | --- |
| Codex | CONFIG_PREPARED; existing adapter retained | PROTOCOL_VERIFIED from exported TOML | PROTOCOL_VERIFIED from exported TOML | NOT_TESTED in this phase |
| Claude Desktop | CONFIG_PREPARED from official local MCP format | PROTOCOL_VERIFIED from exported JSON | PROTOCOL_VERIFIED from exported JSON | CLAUDE_REAL_CLIENT_UNVERIFIED |

Both adapter formats passed actual SDK subprocess native-result regression,
but those are not the named desktop applications. Independent JSON-RPC clients
also demonstrate protocol use without SDK/client hidden context. Current Claude
installation/config/process checks did not establish availability; Appx inventory
was unavailable and native app automation is unavailable. No false absence or
real-client PASS is claimed. The [matrix/manual procedure](CLIENT_COMPATIBILITY_V1.md)
states exactly what remains, and records official registration/MCPB sources.

## Audit and protection

No core dependency on Codex software/config/request semantics was found. Codex
registration/export remains CLIENT_ADAPTER. Public guidance is DOCUMENTATION_ONLY;
tests TEST_ONLY; old authority/evidence references and retained default storage
are HISTORICAL. The one core project-layout assumption can now be configured
without erasing historical state. The private file/line census and whole-schema
comparison are preserved. No source/PDK/SSH/license raw data is published.

Security boundary changes: **none**. Existing server validation, fixed compiled
routes, one EDA worker, locks, cumulative budgets, UUID admission, replay and
bounded extraction are retained. No remote MCP, arbitrary shell/SSH/SKILL/OCEAN,
raw netlist/path/PSF interface, OA mutation, ports or firewall changes.

Fresh deployed guard/postflight checks validate original/PDK/prior evidence,
protected job trees and counters. Existing local admission/sweep journal bytes
are unchanged; prior private checkpoints and seals retain their hashes. Completed
native DC/AC/TRAN results equal preserved values using both exports and after
restart. No submit/cancel/deploy/simulation action was needed for this E2E.

## Gates and corrections

- Frozen all-groups sync: 72 packages.
- Ruff src/scripts/tests and mypy src: pass, 31 source files.
- Full unit: **1,458 passed, three OS symlink skips, 56 existing warnings**.
- Focused protocol/onboarding/sweep: **51 passed, one OS skip**.
- Security: **18 passed**; secret scan; locked dependencies: no known vulnerabilities.
- Installed-wheel build/CLI/three exported stdio formats: **48 tools each**, 22
  legacy names retained, fictional execution denied before admission, uninstall
  and temporary cleanup verified.
- Independent wire: initialization/capabilities, all tool schemas, structured
  success/failure, method errors, repeated/concurrent reads, ping, stdout/stderr
  separation and clean EOF termination pass from a different cwd.
- Preserved real Cadence stdio: DC/AC/TRAN equal; restart lookup equal, two
  adapter formats; protection/counters/local ledgers/prior hashes unchanged.

Corrections used: **1/3**. New tests initially expected an uppercase error code
and lazy SQLite creation; corrected to established lowercase/eager behavior,
with a real preinitialized journal for byte-preservation checking. Failed
transcript retained. Runtime protocol did not require repair. Separate execution
environment issues were preserved: plain pytest lacked repository import root,
fixed with `python -m pytest`; remote authority initially lacked established
Git env and stopped before transport; temporary wheel cleanup encountered a
locked DLL while tests overlapped, resolved after those processes ended.

## Resources and remaining work

New Spectre attempts **0**; shared cumulative **62/500**. Result reservation
delta **0**, shared reserved bytes **7,114,588,160**. No new simulation results,
deployment bytes or paid resources. Removed elapsed ceiling remains absent;
other native/campaign gates and histories are preserved. Source, PDK, prior
evidence and local durable ledgers remain intact. FS work stays paused;
candidate 320/702 mV and VDD=1 V semantics are unchanged; no specification PASS.

MCPB is **PACKAGING_INVESTIGATION** only. The official current manifest includes
0.3 metadata and a 0.4+ uv runtime section; actual host/runtime/update behavior
needs qualification before packaging. No bundle, credentials, Cadence/PDK
material, release or extension submission is produced.

Remaining public-use blockers: actual Codex/Claude desktop qualification;
new physical environment/design/PDK routing and scientific variable ranges;
reference generic preflight executable-permission rejection; native live
cancellation; unresolved owner license/publication choice. Configuration or
protocol compatibility does not remove these boundaries.

Recommended next major phase: **GENERIC-MEAS-01**, registered measurement contracts
over existing qualified extraction, keeping measurement separate from absent
specification evaluation. Real desktop qualification remains pending before a
public candidate. Ask once and stop; this report does not activate that phase.
