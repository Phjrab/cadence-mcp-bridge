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
