# GREL-05 generic reader implementation checkpoint

Status PARTIAL; generic native release BLOCKED. Continuous GREL02–07 and existing
895MiB are authorized. This feature is stacked on unmerged PR146 /17cb59a;
ancestors, main553276d and unrelated original OCN are preserved.

The installed package now has a generic reader compiler/projector bound to the
immutable runtime, generic ADE registration, logical measurement allowlist, plan,
UUID and execution-input digest. Registered node/source selectors configure one
fixed OCEAN program. DC projects voltages and signed source power with explicit
terminal difference and separate roles. Shared power arithmetic preserves exact
legacy six-source grouping/fSum order. AC divides measured complex differential
output by measured input at registered actual sample frequencies. TRAN summarizes
all bounded saved samples and reports their real resolution/time-weighted mean.
No source amplitude/frequency or circuit-specific names are compiled defaults.

Malformed/missing/extra/reordered rows, stale identities, unsafe selectors,
nonfinite/out-of-bound numeric text, unsupported inventories, unmatched axes,
missing gain samples, zero AC input, wrong transient interval/complex values,
per-wave and aggregate bounds are rejected without partial facts. Failed data
never becomes specification FAIL. Outputs remain native NOT_ATTESTED and targets
NOT_EVALUATED. No public MCP reader/path/tool schema changes. See
GENERIC_RESULT_READER_V1.md and installed README/schema/help.

Observed local related189 PASS /zero skips /11.08s; Ruff/mypy71 PASS and85 full
MCP schema compatibility PASS. Security18 PASS /1.32s and locked audit no known
vulnerabilities. Initial installed wheel CLI compile/project, bootstrap/protocol
and32-state reinstall/uninstall preservation PASS, but predates final aggregate
1536-row bound and README change. That log is retained as source-scoped history;
final exact-source package/hosted/independent review receipts follow separately.
Initial test1 failure was an overly exact floating total assertion; corrected to
numerical tolerance without changing signed arithmetic. Its log is preserved.

This is local development tooling and calculation infrastructure. It does not
close automatic terminal extraction or produce attested PSF/native facts. Production
provider, authentic operator confirmation/migration/renewal, trusted terminal
worker/lock integration and native copy/API/input/reader qualification remain
absent. Generic1D Sweep codec/SweepStore/Supervisor and specification fact binding
remain incomplete. Clean actual Codex new-job/restart acceptance has not run.
Native trust still blocked/executable_permissions, not requalified here. No native
script execution, simulation, reservation, deployment, result deletion, protected
repair, budget increase/reset, merge, GREL08 or publication was performed.
Two real new circuits and new DCACtran/Sweep jobs remain acceptance requirements;
analytical disposable frames and synthetic installed CLI are not substitutes.
