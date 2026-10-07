# CLIENT-REAL-QUAL-CODEX-03: operator-bound actual Codex reads

Observed 2026-10-07 KST. Starting main:
`15bcd9ce61753b3f63af657981d7db415182428c` (PR136).
Branch: `feat/client-real-qual-codex-operator-03`.
Status: **Scoped existing-result reads VERIFIED**; exact containing-PR
review/integration receipts govern phase completion.
Overall current client qualification remains **PARTIALLY_VERIFIED**.
The exact containing-PR candidate/review/integration receipts govern completion.

## Authorized scope and configuration

Apply the two previously prepared read-only operator profiles in sequence,
preserving existing registries, PDK metadata and admissions/Sweep journals.
Each selects22 read tools from the unchanged85-tool server. No submit, cancel,
execute or cleanup tool is enabled in this client profile. This is an intentional
client filter, not removal of server APIs or a new execution qualification.
The measurement v8 and pinned finite-grid v2 registries are separate contexts;
their version numbers do not order their scientific qualification.

Only the bridge stanza is replaced. Each application has a private backup,
parsed equality check and byte-exact preservation of all other current settings.
After the first user-reported reboot, external changes to other config tables
were observed; their author is not independently established. The stale whole-
config byte guard failed before the second application. That initial failure
and both snapshots are preserved. Rebase the targeted replacement on the newly
observed configuration and preserve those changes; never restore the old global
backup over unrelated settings. Original prepared fragments remain immutable.

## Actual application evidence

Calls use this Codex chat's reviewed bridge tools. SDK subprocess observations
are recorded separately and never substitute for application evidence.

| Check | Observed result |
| --- | --- |
| Measurement runtime after user-reported reboot | Operator design v8/two entries and PDK v2/two entries; exact prepared semantic digests; both journals operator supplied |
| Application-visible names | Exactly22 configured read tools, rather than the full85 server inventory |
| Catalog | Six analog definitions, separate signed DC reader and one no-target power contract; full payload equals historical record |
| DC/AC/TRAN bounded measurements | Existing admitted IDs; full historical payload equality |
| Gain | QUALIFIED,78.95196190699784 dB; differential voltage gain at10 Hz; full historical payload equality |
| Signed DC supply power | QUALIFIED,0.00008242816 W; full historical payload equality, six source entries and separate bias/input/all-source totals |
| Goal evaluation | Existing no-target contract: NOT_EVALUATED, measurement null; no invented numerical goal or source read |
| Gain/power repeat | Identical complete responses; existing-result reads, not resubmission |
| Unknown design/stale power contract hash | Bounded errors; no authority expansion |
| Amplifier reconnect | User reported complete; first observation still v8, subsequent observation matches pinned operator-v2 digest/one design and existing journals |
| DC/AC Sweep status | Both SUCCEEDED; the complete status-contract projection matches the preserved engine |
| DC/AC Sweep results | Full historical payload equality for two admitted three-point Sweeps |
| Six specification facts | Full historical evaluation/provenance equality; all NOT_EVALUATED with no target |
| Repeat and malformed/stale requests | DC result and AC evaluation repeat equal; stale source hash and malformed sweep ID reject |

Gain is not DC gain or closed-loop gain. Power is signed DC rail-delivered
power with voltage/current/sign/unit definitions and preserved conditions;
it is not DUT-only or transient average power. Original power-v1 and grid-v2
definitions stay distinct, including their recorded numeric precision.
These reads preserve the source-result hashes and qualification; they generate
no new simulation fact or broader PVT/continuous-range validation.

## Limits and remaining work

Runtime digests attest selected catalogs/journal selection, not process build
identity, source SHA, app version, health or execution authority. Actual full
tools/list schemas/annotations, initialize negotiation, stderr/EOF, previous
process termination and new job lifecycle remain NOT_TESTED. User-reported
reboot/reconnect is not independent process-lifecycle attestation.

Both exact launch profiles pass independent current-source SDK runtime/full85
schema/22 read-only annotation checks without remote contact. That SDK check is
not actual Codex qualification. Actual amplifier runtime/catalog/two three-point
Sweep results/six specification facts and repeated reads now match preserved
evidence. The final installed context is the amplifier profile with22 read tools;
historical generic measurement reads require selecting the separate measurement
profile and reconnecting. No simultaneous registry combination is claimed.
No app-wide restart is inferred from a click.

The first concurrent amplifier read batch returned three bounded remote_failure
responses (DC result, AC result and AC evaluation), while the DC evaluation
succeeded. The fixed result reader takes the shared nonblocking EDA lock;
these failures are consistent with contention, but the exact remote exit is not
exposed by MCP. Preserve every initial response and run the existing read-only
queries sequentially with the same IDs: all succeed and match historical data.
Do not weaken the lock or claim unrestricted concurrent remote reads.

The first status comparison incorrectly compared a narrow status response to the
broader result-engine schema. It failed; all shared fields were already equal.
Correct the evidence verifier to use the unchanged authoritative AmplifierStatus
field projection, while separately retaining complete result payload equality.
No product schema or historical fixture is altered. A later precommit config
comparison incorrectly stripped generated pre-header comments; that failure is
preserved. Exact reconstruction of both original header-span replacements now
matches candidate bytes and also proves unrelated parsed settings unchanged.

## Gates and protection

Fresh19 client/runtime/public-contract tests PASS, one OS cache-permission warning.
Ruff at README's `src scripts tests` scope, mypy59, exact85 contract audit,
security18 and locked dependency audit PASS; security has one cache warning.
The initial overbroad `ruff check .` includes preserved legacy Python2 helpers
and fails730 checks; keep the failure, use the canonical README scope without
modifying legacy code. Full2,234 PASS/five OS symlink SKIP/56 warnings is explicitly
REUSED after exact source/tests/toolchain/policy equality, not a fresh full run.
Fresh README package/install verification PASS (wheel67/sdist68, exact content
and notices, isolated CLI/three SDK stdio formats85/uninstall); final exact
candidate review/integration still govern completion.

Nine conservative setup/discovery/evidence corrections of20 are retained;
no product correction. Zero new simulations/reservations/deployments/deletions,
no counter refund/reset. Shared ledger82/500 and9,798,942,720/10,737,418,240 reserved
bytes. Preserve all1,987 baseline private hashes and the whole live checkpoint,
original OA/ADE/PDK/vendor/results/evidence/replay/admissions/ledgers. Six Sweep
jobs occupy1,105,799 logical and1,511,424 allocated bytes, not whole-VM storage.
The stat-only local slew extractor change is preserved with zero content diff.

Apache-2.0 applies to original bridge code; vendor/PDK/client licenses are
separate. Imported planning rights remain LEGAL_REVIEW_REQUIRED and publication
PUBLICATION_NOT_AUTHORIZED. No version/tag/release/MCPB/index or historical
release edit. [Claude PR127](validation/claude-desktop/20261006T0407Z/REPORT.md)
actual Code-tab reads/restart remain verified in their dated scope; complete
current Claude app qualification and other hosts/versions/PDKs stay deferred.

Finish this phase through final applicable gates, reviewed
feature PR, permitted normal merge and remote verification. Report and stop;
ask once before a further major phase. No new science target or experiment is
activated by these read-only checks.
