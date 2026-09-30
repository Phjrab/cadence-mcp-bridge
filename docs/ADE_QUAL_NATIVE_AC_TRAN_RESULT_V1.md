# Native AC/TRAN qualification result

Date: 2026-09-30. User-selected bundle: `ADE-QUAL-NATIVE-AC-TRAN-01`.
Outcome: native AC and TRAN execution, extraction and arithmetic verified;
`spec_evaluation=not_evaluated`.

## Scope and predecessor

This bundle follows the completed native DC qualification merged through PR #93.
Its successful DC run, five-of-six correction history and protected checkpoint
were reused and preserved. The user's explicit request selected native AC/TRAN
as a separate analysis bundle. Campaign compute and result usage continue from
that DC result; no elapsed ceiling or numeric performance target was introduced.

Source, OA work copy, original ADE state, model, historical copied circuit/project
and earlier results remain fingerprinted. The native circuit body matches the
qualified DC circuit. Each job has its own state copy and project directory.
The saved state is loaded through the installed, documented ADE L APIs; only
the job session's analyses change. The session reloads its owned saved state
before quitting. Neither the original state nor any cellview is saved.

## Effective conditions and measurements

| Item | Observed or verified scope |
| --- | --- |
| Biases | Current saved/effective VBIASN=300 mV, VBIASP=650 mV |
| Candidate | 320/702 mV remains separate and was not applied |
| Supply | Native circuit VDD=1.0 V; all extracted TRAN samples verify 1.0 V |
| Model/temperature | NN, 27 C, bound in original state and native input |
| Input common mode | 0.5 V; TRAN samples independently confirm it |
| AC stimulus | Individual complex inputs +0.5 and -0.5 V; differential 1 V |
| TRAN stimulus | Opposed 1 kHz sine sources, each 50 mV peak about 0.5 V; differential 100 mV peak |
| AC analysis | Job session override: 10 Hz through 100 MHz, 10 points/decade; 71 extracted points |
| TRAN analysis | Saved disabled stop=4 ms enabled in job session; job maxstep=10 us |
| Outputs | Vop/Vom; differential Vop-Vom and common mode (Vop+Vom)/2 |
| Sampling | Adaptive native time points; no FFT or ENOB claims |

The saved state originally enables DC only. AC range and TRAN maxstep are
explicit job settings, not pre-existing enabled settings. The default TRAN run
has 611 points and one trapezoidal-ringing notice. A separate native TRAN run
with the documented simulator-recommended `method=trap` has 604 points and
zero notices. Both cover 0 through 4 ms with finite, strictly increasing, aligned
node time axes and observed steps no greater than 10 us within rounding tolerance.
Original and trap output extrema agree within 12 uV; full waveform equivalence
and integration-method convergence are not claimed.

AC, default TRAN and trap TRAN each completed with zero errors and two
allowlisted CMI-2477 warnings. Native `results()` must advertise the exact analysis
before selection. Separate selector proofs, complete bounded frames, PSF
fingerprints and input/circuit fingerprints bind every result. Independent local
calculations verified all AC complex gain magnitudes, dB and phases, individual
input excitations, and both TRAN supply/stimulus/differential arithmetic. The
numerical spectra and waveforms remain in private evidence.

The large TRAN excitation reaches the supply-limited output region. It cannot
be interpreted as the small-signal AC gain at that amplitude. No step settling,
THD/SNDR, phase margin, Noise/STB, PVT/statistics, Monte Carlo, added-load behavior,
PCell semantics or LVS equivalence is qualified by these runs. The circuit and
load connections were unchanged and bound to the preserved circuit revision.

## Implementation and preserved attempts

| Immutable version | Evidence | New Spectre attempts |
| --- | --- | --- |
| v1 / initial | Native AC generated; modified-session quit waited for response and timed out. Failure preserved | 0 |
| v2 / correction 1 | Owned-state reload resolved quit; native AC/TRAN generated. Closed stimulus parser rejected line continuations | 0 |
| v3 / correction 2 | Exact native controls and continuation-aware source validation; AC and default TRAN qualified | 2 |
| v4 / correction 3 | Reuses v3 AC and TRAN; only native trap TRAN comparison runs | 1 |

The three corrections for this change are consumed and cannot be reset by another
version. The earlier DC change remains at five of six. Fixed operator actions,
policy/file digests, explicit private delegation, predecessor result digests,
exclusive journals and a shared run lock gate the operations. A lost response
does not grant replay. No generic runtime command, path, SKILL or OCEAN interface
or new MCP tool was added. The existing snapshot MCP and fixture sweep interfaces
remain unchanged.

The reuse of the immutable DC guard retains original-source/state/model/copy
checks, exact circuit/header validation, shared disk floor and cumulative
reservation accounting. Native AC/TRAN ancillary controls are separately closed;
unexpected analyses, includes, parameters, output paths or stimuli fail before
simulation reservation. Historical failed versions and journals remain intact.

## Resources and verification

Three new Spectre attempts increased usage from 15 to 18 of 100. Reserved result
bytes are 1,209,008,128 under the cumulative 5 GiB ceiling. Successful AC,
default TRAN and trap jobs occupy 305,740, 619,483 and 617,354 bytes respectively.
Final free space is approximately 24.05 GiB. Active EDA count is zero.
Protected fingerprints, earlier DC bytes and v3 result digests were rechecked
after the trap run. Paid-resource usage is zero.

Local targeted validation: 108 tests passed, including 32 new AC/TRAN tests and
the existing DC, campaign, diagnostic and security tests. Deployment verifies
exact bytes, Bash syntax and compilation on actual Python 2.6. Ruff and mypy
passed. Secret preflight passed for 594 repository files.
The security gate passed all 18 tests and the frozen-dependency audit reported
no known vulnerabilities. Git attributes retain LF bytes for every native OCEAN
asset so a Windows checkout preserves the deployed policy hashes.

The full regression collected 749 tests: 733 passed, eight legacy fake-transport
tests failed, and eight opt-in integration tests were skipped. A diagnostic copy
of the fake process identified a Windows long staging-path file-open failure;
the production deployer and its tests were unchanged. The eight affected cases
were rerun with a shorter private temporary root: all eight passed. Across the
full run and this scoped rerun, all 741 runnable cases passed. Skipped integration
tests are not counted as PASS; the native
AC/TRAN live checks above are the separately scoped real-environment validation.

Private immutable final evidence: `.codex/native-ac-tran-01-result-v2.json`,
SHA-256 `b09d1faa742dda4f39371a4373057ce58ef780796f184f84a58571c30e4f9e82`.
Its predecessor result, independent-check records, original/trap frames and
deployment/action journals remain private. This report contains reviewed
capability, condition, quality and resource summaries; it contains no raw
OA/ADE/PDK/netlist/PSF/log or measurement frame.

## Phase exit

Native current-source/ADE-state DC, AC and TRAN are now qualified for these
specific conditions. This does not apply or qualify the 320/702 mV candidate
under native ADE. A further major phase requires the user's next choice; no
optimization, new bias range or statistical analysis starts automatically.
