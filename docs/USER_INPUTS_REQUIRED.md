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

## WP-11 controlled design write — blocking inputs

Read-only discovery found `MyDesignLib` and `MyFirstDesign`, but neither is approved as a dedicated
writable work library. To resume WP-11, provide one complete authorization containing:

- dedicated work library name and approved project location;
- exact source library/cell/view and destination copy cell/view;
- one narrowly predefined mutation and its typed parameter values;
- expected dry-run diff and post-save verification result;
- backup location/retention and rollback success criterion;
- explicit approval to apply that named mutation only to the destination copy.

Until all six items are supplied, no write tool, remote mutation command, v1 tag, or GitHub release
will be created. PDK/shared/source libraries remain read-only.
