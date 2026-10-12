# Final review corrections, 2026-10-12

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
