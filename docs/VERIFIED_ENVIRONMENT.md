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
