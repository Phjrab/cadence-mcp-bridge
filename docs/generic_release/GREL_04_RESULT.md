## Current GREL04 parameter-scope review correction, 2026-10-09

Current direct user authority allows continuous GREL02-08, normal conditional
related PR merges and the current managed VM retained16GiB ceiling. Spectre500,
corrections20, disk floors, original/vendor contents, results and journals remain
binding. Exact-candidate tag/Release/upload still requires final public approval.
Earlier overlays below are historical and do not cancel that direct authority.

Latest PR145 e90b786 hosted checks passed, but independent review found a P1:
extracting nested parameters as global values could accept moved top-level input.
The corrected local comparator tracks named subckt/inline-subckt scopes, preserves
static structure and rejects nested parameter/include/analysis controls or unbalanced
scope. Top-level parameters with ordinary static subcircuits remain supported.
Regression covers DC/AC/TRAN and inline subcircuits. Related190 PASS, Ruff/mypy69
PASS. Exact corrected installation PASS: isolated CLI/SDK/configured bootstrap and
reinstall/uninstall preserve19 synthetic operator state files. Final hosted
checks/review remain pending. This compiler
alone is native-unqualified and never authorizes or dispatches a simulation.

PR142-144 normally merged; latest checked main eda060e1a1a984134e25490839c60ec2c2a93eb4.
Existing changes and evidence are retained. This correction adds0 simulations and0
reservations. Actual standard-VM execution is tracked separately in PR152; actual
Codex new-job acceptance and exact GREL08 candidate remain incomplete. Release BLOCKED.

# GREL-04 local generic-input checkpoint, 2026-10-08

Status: PARTIAL_LOCAL_INPUT_IMPLEMENTED_NATIVE_UNQUALIFIED. The user authorized
continuous GREL-02 through GREL-07 and use of the existing 895 MiB remainder.
This checkpoint uses that scope for independent local implementation while the
last native qualification remains blocked on executable_permissions. No native
qualification was rerun, no protected permission repair was attempted and there
were zero simulations, reservations, deployments or deletions.

Latest origin/main was freshly fetched and remains
553276d28c54d8e87092229d102bfd05ec98e74f. PR144 remains open/unmerged at455b05a;
this work branches from it as feat/grel-04-generic-ade-inputs. Existing GREL03
source/tests/replay and other operators' changes are preserved. No merge or
publication is authorized.

The installed CLI now exposes closed generic ADE L registrations, exclusive
job-bound input compilation and bounded effective-Spectre-input comparison.
The same template covers DC/AC/TRAN and two distinct fictional RC/MOS registrations.
Explicit scalar variable contracts, protected model includes, opaque source/state/
static-input hashes, and complete supported analysis conditions are checked.
No per-circuit Python enum/helper change is needed to render different registrations.
The manifest binds the additional execution-input identity; the legacy operation
plan alone cannot authorize these inputs. Public output contains no private
bindings, model paths, circuit text or scripts. Unsupported syntax fails closed.

This is not production provider integration or actual native ADE execution.
Owned OA/ADE copy/attestation, setter/API qualification, physical ledger/operator
attestation, reader/extraction/Sweep and clean actual-client jobs remain incomplete.
All local/synthetic receipts explicitly deny execution authority. The existing
85 MCP schemas and v1-v8 registries remain unchanged. See
[operator workflow](GENERIC_ADE_INPUTS_V1.md).

Validation receipts will be appended after observed checks; prior GREL03 source
receipts remain scoped to their original commits. General release stays BLOCKED.

Observed local checks before the implementation commit: new generic-input tests
50 PASS; combined generic/operations/lifecycle/analysis165 PASS; adjacent context/
bootstrap/generic121 PASS/two Windows unprivileged-symlink skips. Ruff PASS;
strict mypy69 source files PASS; security18 PASS and dependency audit reports no
known vulnerabilities after process-local PYTHONUTF8=1 retry. The initial audit
failed in pip_api decoding a Korean-path pip version; no dependency was changed.
Full unit run is still in progress and is not recorded as PASS here.

Curated final README artifacts and isolated installation PASS: wheel77 members,
SHA256cb6ddc9b60fbe541bedd5a4621853b7b0ce2c3e8c66585974127311d54836b5f;
sdist78 members,SHA25605d9460179871cdec8f1ace1b093a288fd1f51730d2309aa5324939e1b82bb66.
Source/license/notices exact, protected/unexpected content0. Installed85 schemas/
three SDK clients/context routing/generic compilation and effective comparison/
read-only copy denial/bootstrap/reinstall/uninstall PASS;19 synthetic state files
preserved. This is same-version synthetic preservation, not native migration.

Final279 source/test/script/package inputs snapshot
004be6a3f0c6b11fa1a9778fa865bf6d5503623b1b209cc2f360c142445e4ac9.
Exact tested commit and hosted/review receipts follow after observation.

Fresh reviewed storage read retains82 attempts/9,798,942,720 reserved/10GiB
ceiling/895MiB remainder,18,030,073 logical/48,308,224 allocated bytes and snapshot
1ff1794c7ff2d75b3aeed475d587a68e2d39bc5157a8704107397cc7610b09e2.
Free25,689,890,816 bytes/floor6,238,251,418/OK (free telemetry may fluctuate).
Only registered result roots were scanned. The unrelated original OCN hash
2cf3673f4e80cb3c2bd6815f919c0d2aaf9b20a944b2ef1b8eb231589c634b32 remains exact.
Prior whole-selected-tree preservation is historical, not freshly rerun.

## Exact implementation source CI and independent review

Implementation sourcea3f5fb89840d2a83b661115509f878b63f80cf39 is pushed and
PR145 is open/ready, stacked on unmerged PR144. Hosted run37708446152/
job113088339472 SUCCESS:2473 PASS/no skips/56 warnings/204.08s. Ruff/mypy69/
security18/locked dependency audit/85 schemas/curated package/installed generic
CLI/context/bootstrap/reinstall/uninstall19-state preservation PASS.
Independent automated review completed2026-10-08T00:39:27.449797Z with no inline
findings and bot+1 at00:39:30Z. No formal APPROVED review or merge authority follows.
CI backend initially returnedHTTP502 for the job-log read; supported-tool retry
succeeded, without a source-control CLI diagnostic fallback.

Hosted committed-source wheel SHA256
73c971a25396873087b00de429321ed2f9fbc030d311bd72d77522f337c38cc4;
sdist SHA256e9e29d439dc8c1f1ac524f92786cb7e02db7c210b2acdaf3f169f2365164fb3e.
These differ from the local CRLF-working-copy artifacts above. Bounded raw-byte
comparison against Git objects found only CRLF-to-LF differences in the five
edited source/test/script/README files; all other package sources match. Both
artifact sets were independently curated and installed; they are separate
receipts, never claimed byte-identical. No native experiment was run.

Local full run completed:2466 PASS/seven Windows unprivileged-symlink fixture
skips/56 warnings/795.02s. Original279 input hashes have zero drift across that
run. This was the CRLF representation documented above. After completion, only
the five edited files' line endings were normalized to their exact committed
Git bytes; no Python/template content or public Git diff changed. Canonical279
snapshotdc7572cf8e219864f8cc454c1b6adf2af0a566f9205369e790970f487e99a221.
Committed LF-source hosted2473 PASS covers every test without skips. Canonical
local package comparison is in progress; earlier artifacts remain historical.

## Final package representation and preservation

Local normalization comparison completed. Four edited Python files now have
exact committed LF bytes; README is restored to its original Windows checkout
CRLF representation (like the hosted checkout's root packaging files). An
intermediate fully-LF README sdist is a separate historical artifact. Final
local wheel and sdist hashes are BOTH byte-identical to the hosted sourcea3f5fb8
artifacts recorded above. The matching wheel passed another isolated installed
CLI/SDK/bootstrap/reinstall/uninstall19-state preservation run. Final artifacts
are retained privately in .tmp/grel04-final-artifacts. Root packaging CRLF bytes
must not be confused with an LF Git object or with Python-source differences.

Final279 checkout inputs snapshot: 77feae150e4a89481dd321c6e24aca00ded42693b140ff0ed0dece8dda630d38.
Python/template content, tests, package/workflow definitions and Git source have
no semantic change since hosted sourcea3f5fb8. All full/native limitations above
remain. Fresh final origin/main is still553276d; original OCN unchanged. This
receipt-only follow-up does not activate dispatch, merge, GREL08 or publication.
