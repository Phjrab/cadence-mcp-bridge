"""Typed local DC and device OP response for a read-only MCP profile."""

import json

from cadence_mcp_bridge.research_adapters import DeviceOpResult
from cadence_mcp_bridge.research_measurements import (
    DeviceOpQuery,
    DeviceOpSourceBinding,
    read_retained_device_operating_points,
)
from cadence_mcp_bridge.runtime_context import ExecutionContext


def retained_device_op_result(context: ExecutionContext, request: DeviceOpQuery) -> DeviceOpResult:
    binding = context.binding
    path, digest = binding.device_op_catalog_path, binding.device_op_catalog_sha256
    source = (
        DeviceOpSourceBinding(catalog_path=path, catalog_sha256=digest)
        if path is not None and digest is not None
        else None
    )
    result = read_retained_device_operating_points(context, request, source=source)
    return DeviceOpResult.model_validate_json(json.dumps(result, allow_nan=False))
