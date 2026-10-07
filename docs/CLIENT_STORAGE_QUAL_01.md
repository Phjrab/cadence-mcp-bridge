# CLIENT-STORAGE-QUAL-01 — Actual Codex Storage reads

## Result and exact scope

**ACTUAL_CODEX_STORAGE_READS_VERIFIED**, 2026-10-07 (Asia/Seoul).
The user restarted the Cadence MCP connection; this chat then exposed all26
configured read tools, including the four existing Storage summary/list/describe/
plan tools. Actual calls succeeded against the registered reference environment.
Cleanup execution is excluded from this profile. No new engine/API/schema,
simulation, reservation, deployment, consent or deletion was introduced.

Start: 9cbb17530da2b79efdb067ae06a0a3553f7a66d0 (merged PR139).
Branch: feat/client-storage-qual-01. Final candidate/review/merge/main identities
are bound by the containing PR and private integration receipts.

The prior [native selected-deletion result](STORAGE_REAL_QUAL_01_RESULT_V1.md)
remains distinct: it qualified one synthetic A payload via SDK/native IO after
separate selection and operator consent. This phase qualifies actual app reads
and planning only; it does not add app deletion or general lifecycle evidence.

## Actual app observations

| Check | Result |
| --- | --- |
| Exposed inventory |26 configured read names, including four Storage reads; execute absent |
| Runtime v2 | Loaded amplifier design registryv2 (one entry), PDK registryv2 (two entries), operator journals; exact SDK equality |
| Summary | Exact stable fields and snapshot versus preserved post-delete/SDK evidence |
| Pagination |7 +7 +2 records; all16 full artifact records equal; complete six-group coverage |
| Descriptions | A, B, representative replay-required and evidence-required groups equal complete listed records |
| Exact A/B plan and repeat | Stable full plan/hash; A protected exclusion; B eligible12288 bytes; deleted=false |
| Repeated summary | Stable snapshot/fields; filesystem free-space telemetry compared separately |
| Negative requests | Stale snapshot, unknown opaque ID, path-like ID and limit21 all rejected |
| Actual execute/dry-run | NOT_RUN in this app phase; execute tool remains excluded |

A is the retained empty container from the earlier approved deletion. B is the
12288-byte synthetic control the user chose to retain. Server eligibility and
inclusion in a read-only plan are not new human selection or deletion consent.
No historical simulation result was reclassified or removed.

Runtime info attests loaded catalogs/journal choices, not exact source/build
identity, app version, remote health or execution authority. Full85 server
schemas and all configured read annotations are verified through SDK subprocess;
that is not a complete actual app schema dump or lifecycle qualification.
Calls are sequential because the remote backend shares a nonblocking EDA lock.

## Storage and conservation

| Quantity | Observed value |
| --- | ---: |
| Registered artifacts / aggregate jobs |16 /446 |
| Logical managed bytes |18030073 |
| Allocated managed bytes |48308224 |
| Replay-required logical bytes |10782193 |
| Evidence-required logical bytes |7235592 |
| Server-classified candidate bytes |12288 |
| Cumulative Spectre attempts |82 /500 |
| Cumulative reserved result bytes |9798942720 /10737418240 |
| New attempts / reservations / deletions |0 /0 /0 |

Coverage is the six compiled registered groups, not whole-VM usage or all phase
roots. Logical bytes, allocated bytes, changing filesystem-free telemetry and
cumulative reservations have different meanings. The disk floor is OK at the
observation. Age metadata remains unavailable and no oldest-artifact inference
was made.

All2122 prior private evidence hashes and the complete original live checkpoint
match the phase baseline. Original OA/ADE/PDK/vendor/source, prior results,
protected scientific evidence, replay/admissions and resource ledgers remain
unchanged. The unrelated stat-only local slew extractor change is preserved.

Only the bridge enabled_tools list was changed from22 to26 after private backup,
parsed comparison and byte-preservation checks; original command/args/env,
registries, journals and prior22 names are retained. On restart, another server's
transport endpoint changed externally. The first whole-MCP-table comparison
rejected that drift; it was investigated, preserved and documented. The Cadence
entry itself still equals the exact prepared configuration.

## Gates and evidence classes

| Gate | Outcome |
| --- | --- |
| Fresh Storage/runtime/client/release tests |127 PASS /1 OS symlink SKIP /1 cache warning |
| Fresh security suite |18 PASS /1 cache warning |
| Final documentation/client regression |50 PASS /1 cache warning |
| Final source secret scan | PASS986 repository files |
| Ruff src/scripts/tests | PASS |
| Mypy src | PASS59 files |
| Full contract audit / SDK schema equality | PASS85 tools; v1-v8 compatibility preserved |
| Locked dependency audit | PASS; no known vulnerabilities |
| Full unit suite | REUSED2245 PASS /5 OS symlink SKIP /57 warnings |
| Build, distribution, licenses | PASS; wheel67/sdist68 members, no unexpected/protected files |
| Isolated install, CLI, three SDK profiles, uninstall | PASS;85 tools/profile |
| Exact candidate secret scan / primary review / remote integration | Required before completion receipt |
| Independent review / remote CI | NOT_RUN unless an explicit integration receipt establishes otherwise |

Full unit evidence is reused from tested candidate
95f6b8f33cd0ff0ec264c5e9b904633d22a09b9a only after an empty content diff for
source/scripts/tests/remote/toolchain/contracts/policies/licenses. Documentation
and local client-filter changes do not change those tested inputs. This reuse
is explicit; skips and warnings are not counted as PASS.

Actual app evidence consists of the calls above. Native read-only conservation
is separate. SDK subprocess evidence covers full schemas and the preflight.
Synthetic evidence covers existing safety fixtures. No new Cadence simulation
or native fault/concurrency injection occurred.

Conservative correction count5/20: two Windows wildcard discovery corrections,
a command-length rejection before evidence writing, denied enumeration of old
private nested directories, and the external-config comparison investigation.
Initial failures remain recorded; no product/security guard was relaxed.
Historical correction usage from earlier phases remains unchanged.

## Completion boundary

Finish applicable gates, exact candidate review, feature PR, permitted merge
and remote SHA/tree verification; retain receipts privately. No tag/version,
publication, compaction, extra deletion or next phase is activated.

Suggested next phase: CLIENT-LIFECYCLE-QUAL-01, scoped investigation/qualification
of remaining actual app source/schema/version and preserved-result lifecycle
evidence, reusing existing results where possible. Report this phase and ask
once before starting it. Native fault injection or additional simulation would
need their own bounded scope and remaining resource gates.

Claude PR127 retains its verified dated scope; complete Claude, other hosts,
Cadence versions and PDKs remain deferred. Apache-2.0 covers original bridge
material where rights exist; external Cadence/PDK terms remain separate.
Imported planning LEGAL_REVIEW_REQUIRED and PUBLICATION_NOT_AUTHORIZED persist.
