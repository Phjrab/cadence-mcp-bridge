# User Inputs Required

## WP-09 actual ADE profile — resolved

The user supplied and approved the WP-09 project-owned choices on 2026-08-28. The reviewed actual
profile is `actual-differential-amplifier-tb2-transient`:

- `MyDesignLib/Differential_Amplifier_TB2/schematic`, ADE L `state1`
- gpdk090 v4.6, model section `NN`, 27 degrees C
- transient stop `4m` (0.004 seconds)
- no caller-controlled design variables
- no requested ADE outputs or measurements

Read-only validation found two bias parameter assignments in the ADE-generated input. They are
fixed inside the reviewed remote profile for reproducibility and are not exposed as design-variable
inputs. No PDK content, OA database, netlist, waveform, credential, or license value is committed or
returned through MCP. There are currently no outstanding WP-09 user inputs.

## WP-10 actual ADC measurement contract — required before execution

WP-10 validates only the non-proprietary `adc-synthetic-v1` fixture. No actual ADC circuit or
measurement definition has been supplied, so no actual-circuit measurement was attempted. Before
one can be added, the user must provide and approve:

- exact library/cell/view and reviewed simulation profile/state;
- supply voltage and the signed current expression used for DC power;
- offset output expression, reference value, and averaging interval;
- settling output expression, target, tolerance, start, and stay-within-band policy;
- sample frequency, input tone, sample count, analysis window, transient exclusion, window
  function, DC/fundamental/harmonic/noise-bin policies, differential signal expression, and ENOB
  equation;
- ADC bit count, input range, transition extraction method, and DNL/INL reference method;
- corner names/reference and the metric to compare;
- Monte Carlo sample population, standard-deviation/percentile policy, and acceptance limits;
- required units, numeric tolerances, and pass/fail limits for every metric.

These inputs must form a new versioned, reviewed contract. None will be inferred from the synthetic
fixture or from the existing differential-amplifier ADE profile.

## WP-11 controlled design write — validation resolved

The user supplied the complete fixed write contract and actual-apply approval on 2026-08-28.
`MCP_WorkLib` was created and registered, and the approved source copy was created at
`MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic`. Validation then failed before dry-run
completion because of a legacy IC6.1.5 property-query API mismatch. The approved property was not
applied, and no backup or rollback stage ran.

V1/V2/V3 attempts and recovery evidence remain preserved. The user subsequently approved immutable
V4 plan SHA-256 `c5b2f418c5a76bfe54adc24c2ee947a33d904122b404bba323706dfbe3cbdd66` and one fixed execution.
Run `e636eeba-80dc-4280-b2ea-4f23b0cd1139` passed all 18 criteria, restored the V4 target from its
fixed backup, and proved Source, PDK, and all prior evidence unchanged. No controlled-write domain
input remains outstanding.

The remaining user decision is repository/release authorization: review the WP-11 feature branch,
explicitly authorize its PR merge when satisfied, and separately authorize the final `v1.0.0`
version/tag/private-release step. No tag or release has been created.
