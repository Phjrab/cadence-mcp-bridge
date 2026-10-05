"""gpdk090 is a regression adapter, not a universal PDK or generic execution grant."""

from cadence_mcp_bridge.analyses import native_adapter_digest
from cadence_mcp_bridge.pdk_adapters import CapabilityId, PdkAdapter, PdkCapability, PdkRegistry

REFERENCE_ID = "gpdk090-reference-v1"


def reference_adapter() -> PdkAdapter:
    # Construct the trusted compiled constant without recursing through its validator.
    # All fields remain explicit; serialized operator inputs undergo full validation.
    native: tuple[CapabilityId, ...] = ("native-dc", "native-ac", "native-tran")
    unqualified: tuple[CapabilityId, ...] = (
        "statistical",
        "device-mapping",
        "layout",
        "drc",
        "lvs",
        "pex",
    )
    return PdkAdapter.model_construct(
        schema_version=2,
        adapter_id=REFERENCE_ID,
        technology_id="gpdk090",
        role="regression_reference",
        environment_ids=("cadence-vm",),
        process_corner_ids=("nn", "ff", "ss", "fs", "sf"),
        rc_corner_ids=(),
        binding_kind="compiled_native_reference_v1",
        binding_ref="native-fixed-reference-v1",
        binding_sha256=native_adapter_digest(),
        capabilities=tuple(
            PdkCapability(
                capability_id=capability,
                status="fixed_native_compatibility",
                evidence_ref="native-mcp-reference-dc-ac-tran",
            )
            for capability in native
        )
        + (
            PdkCapability(
                capability_id="process-corners", status="observed", evidence_ref="ade-pvt-qual-01"
            ),
            PdkCapability(
                capability_id="operating-point", status="observed", evidence_ref="ade-pvt-diag-01"
            ),
        )
        + tuple(
            PdkCapability(capability_id=capability, status="unqualified", evidence_ref=None)
            for capability in unqualified
        ),
    )


def reference_pdk_registry() -> PdkRegistry:
    return PdkRegistry(schema_version=2, adapters=(reference_adapter(),))
