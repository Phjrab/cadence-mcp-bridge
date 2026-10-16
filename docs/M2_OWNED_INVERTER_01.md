## Current actual outcome and final review correction, 2026-10-15

The ordinary UID500 path created a new owned inverter, symbol and hierarchical
testbench from the complete observed CDF frame. Saved/reopened connectivity and
properties passed. Independent DC/TRAN effective-input checks passed, including
the intended PMOS effective width. Exact installed source
`0ae58c5d374d69c26d63f31cf1ebd0a1c72e8bf6` then completed both new analyses and
automatic extraction. Same-process and new-process same-ID submit/query/result
repeats passed without another dispatch or reservation. Original OA/ADE, registered
models, previous results, failure artifacts and accounting history remain retained.

Actual cumulative shared accounting is128/500 attempts and15,721,299,968 /
17,179,869,184 reserved bytes; remaining1,458,569,216 bytes (1391MiB).
This slice spent exactly2 attempts/256MiB. The two-job grant is fully consumed;
this record authorizes no replacement IDs, additional simulation or refund.

Conditions: NN/27C,1V supply,1pF load; DC input0.5V; TRAN0–1V pulse,
1ns delay,100ps rise/fall,2ns width,4ns period,6ns stop,100ps maxstep.
The earlier netlisting diagnostic used20ps; the admitted experiment explicitly
selected100ps before execution to stay within the unchanged256-sample reader.
DC output0.4046511906V; TRAN98 saved samples per registered node. Output spans
0.8317364241–0.9999859756V in this short loaded window. This verifies execution
and extraction, **not successful logic switching, settling, slew or signoff**.

Fresh review4284536573 found a local topology verifier omitted parser-legal
hyphen/hash instance identifiers. Source33 matches the parser grammar and rejects
extra hyphen/hash/max-length devices. Both retained actual netlists pass and six
mutations reject locally; no new Cadence calculation or changed writer/runtime
is needed. V15 preserves32 consumed source versions and records one finite local
review correction, reaching33/33. The user's direct additional approval is the
authority; policy/checkpoint files only record its bounded use.

Subsequent local reproduction found set comparison could accept the same MOS
statements relocated outside the DUT. Source34 compares the exact ordered
hierarchy/device/global sequence. Review4284696734 additionally found unexpected
global declarations were discarded; only one top-level `global 0` now matches.
Both retained actual inputs pass; all sixteen extra-device, scope-relocation and
global-declaration mutations reject. The rendered generator is byte-identical
to the actual OA writer (SHA256faff12552314872cb83b6bf9cae2e4f0212d8f2ff7428f7b7dc12a64666dcfdf).
V16 retains33 and records one necessary local correction:34/34. V15/source33 and
the failing local regression remain preserved; no additional VM calculation,
activation, attempt or reservation occurred.

PR160 remains draft/unmerged. Final corrected-source hosted, package and review
evidence is recorded separately in [the acceptance/runbook](M2_OWNED_INVERTER_ACCEPTANCE_20261015.md).
Actual Codex submission is NOT_TESTED_THIS_M2_SLICE; Claude is EXCLUDED_BY_USER.
Layout/DRC/LVS/PEX and publication remain outside this completed execution slice.
All older pending/failure sections below are historical, superseded only where
the actual evidence above applies. Published2.0.0 remains unchanged.

## Independent review disposition in current source32 correction

PR160 automated review4284403269 found vpulse vdc was written without requiring
its observed CDF unit in the accepted fixture. The actual standard-VM frame does
observe vdc with voltage units; the pending source32 now requires that field and
rejects missing/wrong-unit pulse vdc before generation. Seventeen focused tests
pass, including effective PMOS width/topology drift and both review regressions.
This review is not formal human APPROVED. Actual-source32 OA/netlist validation
and exact installed/hosted checks are still pending; no simulation was admitted.

## Source31 OA passes but effective PMOS width fails; correction32

Fresh owned DUT/symbol/hierarchical testbench generation and saved/reopened
terminal/property checks passed at UID500. Common DC/TRAN template netlisting
and generic input checks also passed without simulation/reservation. Independent
comparison then found PMOS netlist width120nm despite OA w350nm. The generic
candidate-derived static hash alone did not establish agreement with design intent.
Preserve the successful structural read-back and the failed semantic qualification
as separate outcomes. Do not call this an actual simulation or acceptance PASS.

Retained source CDF explains the mismatch: simW references fw, and simM references
m*fingers. Source devices have one finger, w=fw, and observed derived areas and
perimeters. The bounded correction preserves those exact observed fields, rejects
unknown derived expressions/multifinger meanings, and adds an independent verifier
for effective MOS widths/lengths/multiplicities/geometry, hierarchy, rails, pulse
and load. It never evaluates CDF callbacks or invents ranges/nf semantics.

Direct broad additional authority covers this minimum source32 correction. V14
retains all31 consumed source versions, previous policies, mismatched revision and
netlists; finite ceiling32, no further experiment allowance. Actual resource ledger
remains126/15,452,864,512 bytes with500/16GiB and DC1/TRAN1/256MiB unchanged.
The next generated revision is fresh; failed/unqualified old cells stay intact.

## First generated OA failed connectivity; minimum correction, 2026-10-15

Source30 reached schematic extraction/check on a new owned inverter and correctly
rejected terminal shorts between vin and rails. Its fixed0.25 wire stubs can cross
nearby MOS terminals; the old primitive-only QA wiring did not establish safety
for those smaller symbols. The correction derives each stub length from one-eighth
of the nearest observed terminal spacing, caps it at0.0625, uses that snap spacing,
and places ports far from devices. Before/after connectivity checks remain.
Keep source30, its failed owned library, panic files and diagnostic logs intact;
never retry or modify that failed revision. The next attempt uses a new owned
library/revision and cannot become a simulation PASS merely by creation.

Direct broad additional human authority covers the minimum correction. V13 keeps
all policies/checkpoints and the failed generator identity; finite ceiling31
counts collector29, failed generator30 and correction31. DC1/TRAN1/256MiB and
500/16GiB are unchanged. Actual UID500 original libraries, seven model contents,
workspace cds.lib and ledger all matched after failure:126/15,452,864,512 bytes.
No grant, netlist, Spectre, extraction, merge, publication or physical work occurred.

## Observed-CDF-bound generator prepared, 2026-10-15

Complete source28 VM CDF evidence was replayed successfully by source29's local
bounded data parser. Both MOS terminal orders, exact effective W/L/m/model and
vdc/vpulse/cap parameter units are observed. No MOS nf meaning or PDK-wide range
is inferred. CheckpointV5 pins successful observation/parser identity and all
failed source versions remain retained. V12 ceiling30 is reached conservatively
by the one pending generator source; no new simulation or reservation occurred.

The new operator-only m2_inverter model binds RevisionBinding, raw CDF hash,
exact source masters and fresh owned DUT/symbol/testbench names. It reuses typed
contracts without relabeling the synthetic DeviceRegistry. It rejects unknown
required metadata, expression-valued MOS sizes, collisions and malformed names.
The fixed writer checks connections/properties before save and after reopen;
runner snapshots/lock/trusted ordinary-user OCEAN are required independently.
No public MCP code/path/command input or startup action is added. Local generator
14 tests and type checks pass; actual OA/netlist/DC/TRAN are still NOT_RUN.
PR160 remains draft; published2.0.0 and all excluded physical/Claude work stay.

## Complete actual CDF frame; host parser correction, 2026-10-15

The fixed source28 OCEAN collector completed normally and emitted a COMPLETE
five-device frame: two original MOS instances plus analogLib vdc/vpulse/cap.
Original library snapshots, seven model contents and ledger matched before/after.
The host rejected standard SKILL symbol-headed list printing in instParameters
(e.g. a(b c)); this is a parser compatibility defect, not failed VM collection.
Keep the complete raw frame and failed parse. Correct only that typed list-data
position and replay the retained frame locally; no new OCEAN run is necessary.
Direct broad additional authority is bounded in V12: retain28, ceiling30 for one
host parser correction and unused generator. DC1/TRAN1/256MiB and500/16GiB stay.
Actual attempts126/reserved15,452,864,512 bytes unchanged; no OA generation or
simulation yet. Production semantics still need assessment, not a PASS label.

## Retained source27 and exact basic port exclusion, 2026-10-15

Source27 passed the legacy API point and observed both MOS CDF scopes, then
failed cleanly on basic/opin, a schematic port marker with no base CDF. Preserve
that failure, partial frame and all prior policy/checkpoint history. The minimum
collector correction omits only exact basic ipin/opin/iopin markers; unknown
instances still require CDF and block. Direct broad additional user authority
covers this necessary correction: V11 retains27, finite ceiling29, one collector
and the unused generator. No new experiment or result ceiling is introduced.
Ordinary UID500 before/after library/model-content/ledger checks passed;
126 attempts and15,452,864,512 reserved bytes remain unchanged. Actual complete
CDF, owned OA, netlisting and DC/TRAN are still unqualified. PR160 stays draft;
no merge/publication, Claude, DRC/LVS/PEX or protected-data modification.

## Current broad additional delegation and bounded legacy API correction

The human subsequently explicitly approved all additional approvals required
for this current inverter slice and asked to continue. Apply that latest direct
instruction to the necessary minimum correction: preserve consumed26, retain
V8/V9 and consumedV1/V2, and set V10 ceiling28 for one legacy-API correction and
the still-unused generator. This is a finite recording of the necessary source
work, not an unlimited experiment, reset or installation default. The500/16GiB,
DC1/TRAN1/256MiB and original domain/ledger/locks/replay remain unchanged.

Source26 cleanly exited1 because symbolName is undefined on this standard VM.
Both root CDF simInfo and Spectre descriptors were observed as lists before
that error. Use symbolToString, already present in the retained standard-VM API
probe, while retaining defensive property access and immediate error exit.
All original registered libraries/seven model contents/ledger stayed equal;
count126 and15,452,864,512 bytes, no new reservation or OA save. The failed
source26/frame/logs are preserved. Latest instruction, rather than these
policy files, is the authority. Earlier narrower approvals remain history.

## Approved corrected collector continuation, 2026-10-15

The human explicitly approved the preceding concrete continuation and all its
listed additional approvals. Active source ceiling27 retains consumed25: one
corrected collector version plus the still-unused generator. DC1/TRAN1 at128MiB
each/256MiB total,500 cumulative attempts,16GiB cumulative reservations and the
original domain/ledger/locks/replay remain binding. V8 and consumedV1 are retained;
V9 records this extension. It is not a fresh ledger or another operator default.
PR160 continues on its existing branch; new phase merge/publication and physical
DRC/LVS/PEX are outside the proposed continuation. Earlier proposal/unapproved
paragraphs below remain dated history. Further Claude work stays excluded.

Current actual ordinary-user preflight126/15,452,864,512 matches the retained
counter. The corrected collector adds typed field observations and a clean
nonzero exit after load errors. Complete output is observation only: missing
or wrong-type required production metadata still blocks OA/simulation.

# M2 owned inverter: active bounded authorization, 2026-10-15

The direct human response approving the concrete M2 proposal authorizes normal
merge of PR159 (completed at f572fd9fea286e34bc62cc964a90b18a3c8afd7b), one fixed
CDF collector, one fixed owned-inverter generator and at most DC1 plus TRAN1.
This document records that instruction; it is not independent consent.
Earlier not-authorized statements remain historical and are superseded only
within this slice. Published2.0.0 is unchanged. This feature PR is not authorized
for merge or publication.

Preserve consumed24 source changes; the approved ceiling is26, with exactly one
collector and one generator source version, no automatic corrective deployment.
Preserve the old POST guard/checkpoint/policies. A phase overlay checks the old
frozen source tree and counts the new source paths separately, including pending
changes. This managed-VM policy is not an installation default.

Latest ordinary UID500 retained preflight:126/500 attempts and15,452,864,512 /
17,179,869,184 bytes. Remaining1,727,004,672 bytes. This observation made no new
reservation. All old finite grants are spent. A new bounded grant, if reached,
must use the same journals/resource lock/domain and refreshed current counters.
DC and TRAN each reserve at most134,217,728 bytes, combined268,435,456 bytes.
No AC/Sweep, optimization, new-ID retry, reset/refund, deletion or compaction.

Collector startup may check out an OCEAN license and create logs/cache only in
an exclusive owned diagnostic directory. Source views open read-only; no CDF
callbacks are evaluated or OA saved. Snapshot registered libraries before/after,
use the existing accounting lock, bounded program/time/output and trusted tool
binding. Keep raw PDK/CDF metadata private. Observe only registered inverter
instances and analogLib vdc/vpulse/cap primitives needed for this testbench.

Generation requires observed CDF/terminal/parameter semantics, a reviewed typed
plan and new collision-free owned DUT/testbench. Read-back connectivity and
parameter equality, effective netlist and existing source/model protections are
mandatory. Synthetic fixtures cannot establish production trust. Unknown CDF,
tool failure, source drift, read-back/netlist mismatch, extraction failure or a
disk/resource guard failure stops actual work and retains partials/failures.
No DRC/LVS/PEX, vendor/PDK/license changes, administrator repair or result ceiling
increase is included. Claude remains EXCLUDED_BY_USER.

Local tests, installed checks, actual metadata, OA creation, simulator/extractor
and actual app evidence are separate. None is inherited merely from PR159 merge.

## Actual collector failure and enforced stop

Frozen collector e0d10f13d8a23fc1fac596e31fea62ff9c4b4c49 was invoked once under
the retained accounting lock at UID500. It produced an incomplete private frame:
one device, four terminals and46 parameter records, without a Spectre record or
COMPLETE marker. A nested CDF Spectre metadata accessor encountered an empty
string where SKILL expected a symbol/list/structure/object. The exact member of
that chain is not isolated. Do not infer simulator semantics from the partials.
The load error prevented normal exit; the60-second owned-process guard terminated
only its own process group. This is a collector failure, not evidence that the
PDK, installation or source circuit is corrupt or unsupported.

Before/after registered library snapshots matched. All seven registered model
file contents and the existing ledger matched; latest retained preflight passed.
The model-content check is not an independent whole-model metadata attestation.
OCEAN diagnostic logs/frame and its panic/lock artifacts remain preserved under
the exclusive owned diagnostic job. No original OA/ADE was saved, no DUT/bench
was created, no netlisting/Spectre/extraction or grant activation occurred.
Attempts remain126 and result reservations15,452,864,512 bytes; this slice adds0/0.

One fixed collector version is consumed:25/26 total. The remaining version is
reserved for the generator and cannot silently become a collector correction.
The durable M2 consumed checkpoint pins the failed commit/script/wrapper hashes;
squashing history, changing source or creating another name cannot refund it.
The old POST24 checkpoint and policies are unchanged. The generator, DC and TRAN
are blocked on complete observed CDF and have not consumed their proposed scope.

Read-only evidence retrieval initially rejected a whole diagnostic snapshot due
to retained panic/lock artifacts. A separate fixed-leaf observation read the
existing logs/frame with content/metadata stability checks, without removing or
ignoring artifacts for any execution admission. It started no Cadence process.

Next proposed scope, **not authorized by this record**: preserve consumed25 and
raise the source ceiling26 to27 for one defensive collector correction plus the
still-unspent generator. Retain at most DC1/TRAN1 and256MiB combined, unchanged
500/16GiB cumulative limits, original domain/ledger and all stop conditions.
The correction must record missing/wrong-type Spectre metadata as unknown,
validate complete evidence before OA generation and exit cleanly on load errors.
No extra simulation allowance, repeated blind collector deployment, phase PR
merge or publication is implied. Exact implementation/review and any source
deployment require that separate bounded decision.

## Local evidence at feature freeze

Collector/design/retained POST guard regression:107 passed,6 Windows symlink
fixture skips. New collector/source-accounting/security batch:42 passed.
The new checkpoint fixtures initially hashed CRLF while the guard correctly
normalizes LF; only disposable fixture hashing was corrected, not the deployed
collector. Whole src/scripts/tests Ruff and strict mypy113 source files passed.
Secret preflight1195 files and85-tool/22-legacy compatibility check passed.
The initial temporary test-path invocation and fixture failures are retained.
Exact unpublished package/installed lifecycle and hosted checks remain pending
until recorded against their source SHA; none can qualify the failed VM path.
