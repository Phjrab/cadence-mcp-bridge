# Security Baseline

## Trust boundary

Codex may call only narrow MCP tools. The Windows MCP server may call only a fixed remote runner through SSH alias `cadence-vm`. The remote runner may execute only registered profiles and fixed Cadence binaries.

## Forbidden capabilities

- generic shell execution
- arbitrary SSH command execution
- arbitrary SKILL evaluation
- arbitrary OCEAN script execution
- unrestricted file read/write/delete
- PDK or shared library writes
- returning credential or license values

## Protected data

Never commit or return SSH keys, passwords, PATs, OAuth tokens, license values/files, PDK models, proprietary netlists, full PSF/raw data, or unrestricted Cadence logs.

## Remote write scope

Before WP-11, remote writes are limited to:

```text
/home/buet/cds_work/.cadence_mcp
```

No root access or CentOS system modification is allowed.
