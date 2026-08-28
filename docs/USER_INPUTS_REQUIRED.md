# User Inputs Required

## WP-09 actual ADE profile

The safe fixture profile and its complete MCP lifecycle are implemented. An actual circuit
profile is intentionally not registered until the following project-owned choices are provided.

Read-only discovery found these candidates without opening proprietary database content:

- `MyDesignLib/Inverter_TB/schematic`: current schematic candidate, but no saved ADE state was
  found beside it.
- `mylib/inv/adexl`: legacy ADE XL data dated 2016.
- `mylib#2dxxxxxx/inverter/adexl`: separate legacy ADE XL data dated 2016.

Please provide only:

1. The one library/cell/view and ADE state or test name that WP-09 should automate.
2. Confirmation that `gpdk090` is the intended PDK for that testbench, or the correct PDK name.
3. Each allowed design variable with unit, minimum, maximum, and default.
4. Allowed analysis type and corners.
5. Allowed output or measurement names.

Do not provide PDK model text, OA database files, full netlists, PSF/raw results, credentials, or
license values. After these inputs are supplied, WP-09 must continue on its existing feature
branch and add a separately classified `actual` profile without modifying the original ADE state.
