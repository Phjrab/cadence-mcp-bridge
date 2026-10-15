# M2 foundation acceptance record, 2026-10-15

These are development-source records. No artifact here replaces published2.0.0,
and M2 merge/publication or actual OA/EDA execution is not authorized by this file.

## Initial independent stable-main implementation

Source `90934aec46f596575e1d4784200e87df6cdd371d`, based on main67c21a7,
is reviewed as [PR159](https://github.com/Phjrab/cadence-mcp-bridge/pull/159).
The isolated verified build and a second build of that exact clean commit have
identical hashes:

| File | SHA-256 |
|---|---|
| cadence_mcp_bridge-2.0.0-py3-none-any.whl | 1bd8a60680f06dda66b15b2972dc80351902d19887dd80218bf7c22039167395 |
| cadence_mcp_bridge-2.0.0.tar.gz | bcf4a660ebd979444b17fe3e26dfd52722d9e614cb261149c2c194a087a6ef5b |

These unpublished files retain existing development metadata2.0.0. Identity is
the source commit and artifact hashes, not a claim that the public release now
contains this feature. Retained files are under the ignored local
`.tmp/m2-90934ae-artifacts-v1/` directory.

| Layer | Observed result | Boundary |
|---|---|---|
| Windows local contracts | 116 passed /6 symlink-creation skips | Synthetic fixtures only |
| Linux hosted M2 contracts | 122 passed, no skips | Disposable local files; not VM or host-platform qualification |
| Static and security | Ruff, strict mypy104, secret scan1155 files, security18, locked all-group audit passed | No known dependency vulnerabilities at this check |
| Compatibility | 85 common tools /22 preserved legacy declarations passed | No M2 public tool added |
| Build rights/content | wheel117 /sdist118 members passed | Canonical license/notices, no unexpected/protected content |
| Installed package | CLI/SDK/context/setup/bootstrap/domain and M2 lifecycle passed | No remote contact or execution authority |
| Reinstall/uninstall | 43 bootstrap +20 migration files and5 M2 files preserved | Same-artifact lifecycle, not every future upgrade |
| Independent review | Parent-chain/depth/capacity and foreign-hot-journal defects corrected and retested | Not a formal GitHub APPROVED review |
| Automatic review |90934ae completed without inline findings | No physical/EDA qualification inferred |

Linux run38688640676, job116269187838 passed. Windows hosted completion is
tracked on the same PR/source; final integration evidence must be recorded
separately if parent code changes. The actual receipt distinguishes local
Windows skips from the Linux test that exercises those link guards.

Initial local package execution could not launch uv inside the restricted
sandbox; the authorized isolated verification then passed. Security fixture
startup first hit an existing temporary-directory ACL; a new disposable test
root passed18 tests. Dependency export then hit a temporary-file lock, and a
standalone audit hit a non-UTF8 subprocess path. The same locked full dependency
set passed from a fresh workspace file with UTF8 enabled. No production guard,
dependency constraint or protected data was relaxed to obtain these results.

## Actual environment and accounting scope

The retained POST waveform reclassification is recorded under POST07 and remains
its own source-specific evidence. M2 performed no new simulation, extraction,
reservation, OA mutation, native deployment or administrator repair. Physical
discovery failures and all UNKNOWN/unverified states are recorded in
[physical observations](M2_PHYSICAL_OBSERVATIONS.md). Additional Claude testing
is EXCLUDED_BY_USER, not PASS.

The retained execution ledger is126/500 and15,452,864,512 /17,179,869,184 bytes.
The conservative source guard also counts two host recovery protection changes
during POST integration:22/24 before those changes becomes24/24, while installed
native assets stay unchanged. This does not refund an execution, create a grant,
or redefine the existing path policy. Historical counts remain historical.

The next actual CDF/owned-inverter/DC/TRAN proposal and its separate source
allowance requirement are in [M2 foundation](M2_FOUNDATION_01.md).
