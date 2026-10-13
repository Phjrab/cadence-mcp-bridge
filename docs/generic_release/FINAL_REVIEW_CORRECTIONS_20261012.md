# Final review corrections, 2026-10-12

## Later full-frame and cross-directory durability correction

The initially proposed64KiB registration restriction below rejected all four
previously enrolled AC/TRAN routes at their declared256-sample ceiling. This
installed local preparation failure is retained; no remote deployment or new
reservation occurred. The final implementation preserves those registrations
and aligns native validation and typed retrieval with the generic reader's
existing262,144-byte frame limit. Result envelopes alone allow1,048,576 bytes
for the frame plus authenticated registration/receipt metadata. Request, control,
storage and ordinary migration responses retain their262,144-byte limits. The
JSON duplicate/nonfinite checks also run at the fixed result envelope bound.
No arbitrary caller-selected transport limit or unlimited read is exposed.

Maximum1536-row AC/TRAN fixtures with six long IDs and finite supported decimal
values exceed64KiB, pass complete native identity/inventory validation, and still
reject above262,144 bytes. Typed result-envelope tests include an exact maximum
frame and metadata above262,144 bytes; the1MiB result-only transport/parser bound
accepts it, and an oversized frame rejects. These are synthetic tests, not new
Cadence waveform or performance qualification.

Independent36982ad review4247041065 additionally found cross-directory rename
durability ordering. V6 now fsyncs the destination registry before the source
root after rename; exact-file and destination resync remain on repeat/recovery.
A dedicated regression observes both publication directory barriers and the
retained helper's final barrier. Failed fixture assertions remain preserved.

Native source corrections are conservatively counted from the originalGREL03
implementation. This final adjustment consumes the20th of20 recorded changes;
no counter/history is reset. Exact final installed/hosted/review/VM gates still
apply. Additional actual regression is separately bounded to2 jobs/256MiB under
the direct user's necessary post-fix validation authority, with a freshly read
existing ledger, disk floors and all previously spent grants retained. The
document/plan is not a separate user approval. Public posting remains excluded.

The preceding64KiB proposal is preserved below as historical diagnosis and must
not be followed as the current operator restriction.

Independent review of189b5ae found three P2 issues. Its previously passing CI,
installed transition tests and runtime-equality receipt remain source-specific
history. They do not qualify the corrected executable assets below.

The retained V6 policy now writes/fsyncs an exclusive private candidate outside
the strict reservation registry, verifies complete bytes, and renames it under
the existing operator lock. Same-plan recovery repeats file/directory durability
barriers. Interrupted candidates are retained; no ledger or spent grant changes.
Disposable tests inject partial write, prepublication failure and postrename
interruption, then recover/repeat while preserving the original files.

The worker's copy preflight now includes existing job occupancy, filesystem
allocation units, rounded file payloads and per-entry directory growth before
materializing either OA/ADE tree. Terminal overhead remains reserved separately.
Many-small-file and larger-allocation-unit tests reject logical-byte-only false
fits without copying or touching the original source. The supported standard
VM filesystem remains part of qualification; this is not a universal filesystem
allocation guarantee or a new storage policy.

Native AC/TRAN registration now rejects a worst-case serialized frame above
64KiB before bundle creation/admission. The estimate includes every signal row,
index/separator/newline, identity header and current row; finite %.16g numbers
are bounded to24 bytes. The256-sample/1536 aggregate ceiling still applies, but
the byte ceiling can require fewer signals/samples. Generic local reader limits
remain separate. No native/transport size check is disabled or expanded.
Both AC/TRAN large logical-ID cases reject without a bundle/journal; the same
signals with64 samples validate. Operators should choose a smaller bounded grid
when native registration reports serialization bound exceeded.

Current local affected213 PASS/27 Windows platform skips; Ruff and mypy99 PASS.
Initial test fixture errors (Windows separator comparison, wrong AC field names,
strict Python list/tuple validation), formatting errors and failed logs remain
retained. Corrected fixtures use canonical paths/JSON and supported AC fields;
no product failure is masked by skipping a test.

Changed native worker and migration helper require renewed exact installed,
hosted POSIX/Windows, independent-review and supported-VM qualification. The
host runtime/manifest equivalence claim for189b5ae no longer qualifies those
changed assets. Do not publish its previously built wheel as the final candidate.
Original successful six-route/Sweep/app evidence remains; affected resource and
registration guards are rechecked separately. Final release files and hashes
are not frozen until these gates and normal PR152 integration finish.

Last actual accounting110/13,557,039,104 is historical until refreshed. Existing
final8-job/1GiB grants are fully spent and must not be renewed/reset. Any necessary
new bounded regression records its purpose/conditions/reservation/stop criteria
before admission under the direct user's16GiB/500/same-change20/GREL02–08 scope,
with the same retained ledger. No new experiment is authorized by this document.
Publication still requires approval of the identical final candidate.
