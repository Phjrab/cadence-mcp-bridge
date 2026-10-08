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


## Analysis-specific measurement identity review correction

Independent review32906b3 found P2: allowlist membership alone permitted an AC/TRAN
frame to report dc-output identity. The generic reader now requires an exact
analysis-specific RegisteredMeasurement from existing registry v4 or later,
plus its canonical SHA256; missing/wrong-analysis/stale contracts are rejected.
Qualified fixed historical definitions cannot be rebound to this generic reader.
Unqualified declarations remain unqualified after local preparation. No registry
schema or MCP schema/version changes were needed. Tests and installed disposable
operator contexts now register explicit matching mappings for each analysis.
Earlier32906b3 software/CI/artifact receipts are historical after this correction.

At32906b3: hosted Windows2587 PASS/four POSIX skips/56 warnings/249.34s,
Ubuntu73 PASS/no skips/3.57s; run37718061280, jobs113119066492/113119066331.
Installed32-state preservation and curated79/80-member artifacts matched local:
wheel d2b7a6cef53458bd97878a13cac164d0a285843f93d43db45af3f28b16530257;
sdist a9beadee05818b082651001dfcb8a29343ca83f567435f52bceca09e9a5e7d4f.
Final current-source revalidation follows; none of this is native qualification.
