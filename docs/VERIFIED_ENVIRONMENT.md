## GREL-05 feasible-reader exact-source receipt, 2026-10-08

Tested source f5a1de2 in ready/unmerged PR147: local247 related PASS/no skips;
hosted Windows2622 PASS/four POSIX skips and Ubuntu73 PASS/no skips. Ruff/mypy71,
security18/audit/85 schemas, matching79/80-member artifacts, installed CLI and
32-state preservation PASS. Ten P2s fixed; automatic bot+1/no new findings is
not formal approval. Complete feasible AC/TRAN reader binding is local only;
native attestation/provider/extraction/Sweep/Spec/clean app remain incomplete.
Generic release BLOCKED. Continuous02–07/895MiB persists; no native side effects,
protected repair/budget reset/merge/GREL08/publication. Native trust/resource
observations remain historical, not refreshed here. Exact receipts and ordered
remaining work: docs/generic_release/GREL_05_RESULT.md and NATIVE_RESUME_BOUNDARY.md.
Later docs-only HEADs are separate from the tested code. Prior overlays are history.

## GREL-05 voltage/current identity correction, 2026-10-08

Second PR147 P2 fixed: voltage/current selector inventories must be disjoint;
known PLUS/MINUS branch spellings cannot be registered as node volts. Physical
PSF quantity/unit attestation remains absent. Corrected193-source receipts below
are historical; final quantity-corrected package/CI/review pending. Native trust/
provider/automatic extraction/Sweep/Spec/clean app remain incomplete; release
BLOCKED.02–07/895MiB persists; no native side effects/protected change/merge/
GREL08/publication. See GREL_05_RESULT.md. Earlier overlays remain history.

## GREL-05 measurement identity correction, 2026-10-08

Independent PR147 P2 fixed: generic reader requires exact existing registry v4+
analysis-specific measurement contract and canonical hash; allowlist-only/unknown/
wrong-analysis/stale binding rejects. Qualified fixed legacy definitions cannot
be rebound. Related193 PASS/no skips/12.64s, Ruff/mypy71 PASS. Final package/hosted/
review pending at corrected source;32906b3 CI/package is historical. Native trust/
provider/automatic extraction/Sweep/Spec/clean actual client remain incomplete;
release BLOCKED,02–07/895MiB persists. No native side effects/protected changes/
budget increase/merge/GREL08/publication. See GREL_05_RESULT.md.

## GREL-05 local generic result reader, 2026-10-08

Continuous02–07/895MiB persists. New stacked feature on unmerged PR146/17cb59a
implements a registered fixed OCEAN reader and bounded DC/AC/TRAN frame projection.
Signed role power reuses exact legacy math; AC uses measured complex input and
selected samples; TRAN reports saved-sample resolution and time-weighted mean.
Local189 PASS/no skips/11.08s, Ruff/mypy71/85 schemas PASS. Initial package32-state
preservation PASS predates final aggregate bound; final receipts pending. No public
MCP execution added. Native trust/authentic provider/automatic extraction/Sweep/
Spec facts/clean actual app remain incomplete. Release BLOCKED; native side effects0,
no protected repair/budget increase/merge/GREL08/publication. See GREL_05_RESULT.md.
Historical overlays below remain source-scoped history.

## GREL-03 sealed accounting source receipt, 2026-10-08

Sourceccd01ab in PR146: hosted Windows2544 PASS/four POSIX skips and Ubuntu73
PASS/no skips. Local230 PASS/five OS skips; Ruff/mypy70/security18/audit/85 schemas,
matching78/79-member artifacts and installed32-state preservation PASS. Actual
Python2.6 is grammar-only. Automatic review no new findings/bot+1, not formal
approval. Existing counter/lock with migration-bound immutable identity seals and
conservation implemented; production provider/operator confirmation/real migration/
terminal workers/native trust/new circuits/extraction/Sweep/clean app incomplete.
Main553276d and unrelated OCN preserved. Generic release BLOCKED;02–07/895MiB
continues. Native side effects0; no protected repairs/merge/GREL08/publication.
Exact source-scoped receipts: docs/generic_release/GREL_03_SHARED_RESERVATIONS_RESULT.md.
Historical overlays below remain history.

# Verified Environment Baseline

Date: 2026-08-28

## Host

- Windows 11
- Codex Desktop
- VMware Workstation Pro
- VMware NAT VMnet8
- Windows VMnet8 address: `192.168.85.1`
- SSH alias: `cadence-vm`
- Passwordless key authentication: verified

## Guest

- Hostname: `cadence`
- User: `buet`
- Address: `192.168.85.128`
- OS: CentOS release 6.5 (Final)
- Architecture: i686
- Shell: `/bin/bash`
- Python: 2.6.6
- Work root: `/home/buet/cds_work`

## Cadence

- Virtuoso executable: `/home/buet/cadence/IC615/tools/dfII/bin/virtuoso`
- Virtuoso version: `IC6.1.5.500.15`
- Spectre executable: `/home/buet/cadence/MMSIM121/tools/bin/spectre`
- Spectre version: `12.1.0.347.isr3`
- OCEAN executable: `/home/buet/cadence/IC615/tools/dfII/bin/ocean`
- lmutil executable: `/home/buet/cadence/IC615/tools/bin/lmutil`
- `CDS_LIC_FILE`: set; value intentionally not recorded

## Network and SSH evidence

- TCP port 22 reachable from Windows through VMnet8.
- Non-interactive SSH preserves Cadence PATH and license environment.
- Strict host alias is configured locally as `cadence-vm`.

## Spectre smoke evidence

A fixed RC transient simulation completed successfully:

- process exit code: 0
- Spectre summary: 0 errors, 0 warnings, 1 notice
- output artifacts: `smoke.log`, `smoke.raw/`
- license checkout occurred successfully

The trapezoidal ringing notice is accepted only for the infrastructure smoke fixture.

## Native MCP stdio observation, 2026-09-30

NATIVE-MCP-01 verified the bridge as an actual subprocess stdio server with 35
tools. Fixed native DC/AC/trap TRAN execution and bounded result reads passed;
details and immutable evidence digests are in `NATIVE_MCP_01_RESULT_V1.md`.
The MCP SDK's default Windows environment omits PROGRAMDATA, which this Windows
OpenSSH requires. The bridge restores that missing standard folder via the OS
known-folder API and isolates SSH stdin from the protocol pipe. Existing values,
strict host-key checks and BatchMode are preserved. This observation does not
change the historical OS/Cadence baseline or upgrade the guest.

## Protected PDK support observation, 2026-10-04

ADE-PVT-PREP-01 observed nine bound gpdk090 v4.6 model files and ten real model
sections, including NN/FF/SS/FS/SF and their highPerf variants. Mismatch statistics
declarations are present in the selected include graphs; process statistics were
not found there. Spectre Monte Carlo informational help and nine fixed OCEAN API
callable checks succeeded. No new circuit run was performed. Actual non-NN,
effective variation and corner/statistical license qualification remain unverified;
see `ADE_PVT_PREP_01_RESULT_V1.md`. No model section is added to the active runtime
profile, and the original/PDK/history and cumulative budgets remain preserved.
