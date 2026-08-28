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
