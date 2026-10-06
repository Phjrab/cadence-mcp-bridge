# ANALOG-POWER-01 result

## Starting state and implemented capability

Starting main: `8009060edc076ccacb371c45d8f8fb3a335b150f`, after merged #123.
Branch: `feat/analog-power-extraction`. The original native DC/AC/TRAN, sweep,
storage, analog v1, specification v7, runtime info, Apache notices and prior
evidence are retained. This is one continuation phase, not a restart.

Two read-only MCP interfaces describe and read a separate `dc-supply-power-v1`
definition for the registered power metric and its unique qualified native DC
source. The current catalog is 72; all previous 70 complete schemas and v1-v7
registry schemas remain exact. No registry version, configuration system,
default catalog or package version change. See [workflow](ANALOG_POWER_V1.md).

The preserved reference DC PSF contains all six ideal-source terminal currents.
Complete source inventory and effective voltages are checked. Installed simulator
documentation establishes A units and passive current direction; independent
same-PSF OP `i` and `pwr` fields agree for all six sources. Supply-rail delivered
power is QUALIFIED for this fixed NN/27 C/1 V/320-702 mV operating point only;
bias/input contributions and all-source total are separate. Numerical frames and
vendor help stay private. No other corner, design, PDK, voltage, transient power,
optimality or specification PASS is inferred.

Original analog v1 power remains UNQUALIFIED through its original API. Its
definition, source and specification hashes are preserved. Reference numerical
targets remain absent and results remain `not_evaluated`. Current v7 goals do
not yet bind the new power definition.

## Qualification and corrections

Final focused power/remote/stdio/server/contract gate: **79 passed**. Ruff passes;
mypy passes **48 source modules**. Final exported Codex SDK stdio uses 72 tools,
checks all 70 previous schemas, qualified power, provenance, rejected path/script
arguments, restart equality, unchanged admission bytes and exact preserved native
DC/AC/TRAN and RC sweep results. This is SDK/subprocess evidence, not actual
current application qualification. Claude real app remains DEFERRED_BY_USER /
CLAUDE_REAL_CLIENT_UNVERIFIED; its adapter remains present.

Eight corrections of the active twenty are consumed: investigation helper name,
local quoting, initial style/type binding, snapshot loader, gate fixture/style,
backend method allowlist, read-only exhausted-budget boundary and final Git
deployment-file inclusion/LF preservation. Failed gates
and first drafts remain private. Environment failures are also retained: missing
Git safe-directory configuration, UTF-8 dependency-audit decoding and two long
Windows fixture path failures. The latter reproduce with long paths and pass
with a short isolated fixture root. They did not justify changing storage logic.

The initial full run is NOT_PASS: 1,754 passes, three failures, four OS symlink
skips and 56 warnings. The backend allowlist failure is corrected; both storage
tests pass with the short fixture root. The final full gate is recorded below
only after completion: **1,772 passed, four OS symlink skips, 56 warnings in
739.32 seconds**. No skipped platform test is represented as PASS.

Final wheel56/sdist57 audit: canonical Apache license and notices included,
curated source matches, no unexpected files or protected-content patterns.
Isolated installation verifies all three existing client-config formats with
72 tools, CLI/runtime/v7 behavior, unqualified example-power denial with no
admission/remote IO, and uninstall. Eighteen security tests pass; locked
dependencies have no known vulnerabilities. Source archives still require human
rights review for imported planning. No release/version/tag/publication occurs.

## Resources and protection

Zero new Spectre attempts and result reservations. Cumulative **62/500** and
**7,114,588,160 / 10,737,418,240 bytes** remain unchanged. The v1 operator
extraction, small independent crosscheck and immutable v2 result-only adapter
write new owned evidence only. Their final footprint is checked against the
8 MiB allowance and existing source-job 128 MiB reservation; final owned footprint
**39,314 bytes** (source job 271,200 bytes), with no budget refund.
The v2 reader allows valid exhausted ledgers without reserving resources and
denies invalid/over-ceiling accounting. Tests cover those boundaries.
Actual guest Python 2.6 boundary validation also passes without ledger mutation.

Fresh protected postflight and native source-tree/PSF guards pass. Source OA,
original ADE/PDK, preserved native jobs/results, previous phase jobs, ledgers and
admission state are unchanged. All **1,224 prior top-level private records**
match baseline hashes. No historical data or evidence is deleted or rewritten.
New evidence remains protected/unknown for storage cleanup. No OS, Cadence,
PDK, SSH/client configuration, license value or firewall change.

## Remaining scope and integration

Another operator can use the existing registered reference and admission to
retrieve scientifically defined signed rail power through the same MCP core.
Registration of another project does not supply/qualify a current extractor.
Power goal binding, broader source/analysis qualification and current real-app
exposure remain unverified. PM/offset/slew and multi-PDK/version qualification
retain their previous limitations. Imported planning LEGAL_REVIEW_REQUIRED and
publication authority gates remain open.

Recommend **MEAS-CONTRACT-02**: versioned integration of the qualified power
definition with generic measurement discovery and specification binding,
preserving old goal/schema identities and inventing no numerical targets.
This phase does not activate it. Integrate through one containing reviewed
feature PR; final remote SHA/tree and exact-head review are retained privately.
No state-sync-only PR is created.
