"""Development CLI for the same typed layout operations exposed through MCP."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import BridgeError, InvalidInputError
from cadence_mcp_bridge.layout_models import (
    LayoutApplyRequest,
    LayoutDiffRequest,
    LayoutForkRequest,
    LayoutInspectRequest,
    LayoutPlanRequest,
    LayoutSelectRequest,
)
from cadence_mcp_bridge.layout_server import LAYOUT_ACTIONS, LazyLayoutService
from cadence_mcp_bridge.models import ErrorResponse

REQUEST_MODELS: dict[str, type[BaseModel]] = {
    "inspect": LayoutInspectRequest,
    "fork": LayoutForkRequest,
    "plan": LayoutPlanRequest,
    "apply": LayoutApplyRequest,
    "diff": LayoutDiffRequest,
    "select": LayoutSelectRequest,
}


def add_layout_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    parser = subparsers.add_parser("layout", help="Registered development layout revisions.")
    actions = parser.add_subparsers(dest="layout_action", required=True)
    schema = actions.add_parser("schema", help="Local typed request schemas; no VM contact.")
    schema.add_argument("--action", choices=LAYOUT_ACTIONS)
    for name in LAYOUT_ACTIONS:
        command = actions.add_parser(name)
        command.add_argument("--request", type=Path, required=True)
        command.add_argument("--settings", type=Path)
        command.add_argument("--context")


def read_layout_request(path: Path) -> bytes:
    # Local envelopes are bounded data; a file path is never forwarded to the worker.
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise InvalidInputError("Layout request must be a regular local JSON file")
    with path.open("rb") as stream:
        payload = stream.read(1_048_577)
    if len(payload) > 1_048_576:
        raise InvalidInputError("Layout request exceeds the local size limit")
    return payload


async def dispatch_layout(layout: LazyLayoutService, action: str, payload: bytes) -> BaseModel:
    # Keep all dispatch names fixed; no user-controlled callable/module lookup.
    if action == "inspect":
        return await layout.inspect(LayoutInspectRequest.model_validate_json(payload))
    if action == "fork":
        return await layout.fork(LayoutForkRequest.model_validate_json(payload))
    if action == "plan":
        return await layout.plan(LayoutPlanRequest.model_validate_json(payload))
    if action == "apply":
        return await layout.apply(LayoutApplyRequest.model_validate_json(payload))
    if action == "diff":
        return await layout.diff(LayoutDiffRequest.model_validate_json(payload))
    if action == "select":
        return await layout.select(LayoutSelectRequest.model_validate_json(payload))
    raise InvalidInputError("Unknown layout action")


def layout_cli(arguments: argparse.Namespace) -> int:
    try:
        if arguments.layout_action == "schema":
            schemas = {name: model.model_json_schema() for name, model in REQUEST_MODELS.items()}
            print(json.dumps(schemas[arguments.action] if arguments.action else schemas))
            return 0
        settings_args: dict[str, Any] = {"runtime_mode": "operator"}
        if arguments.settings is not None:
            settings_args["runtime_settings_path"] = arguments.settings
        if arguments.context is not None:
            settings_args["runtime_context_id"] = arguments.context
        settings = BridgeConfig(**settings_args)
        result = asyncio.run(dispatch_layout(
            LazyLayoutService(settings), arguments.layout_action,
            read_layout_request(arguments.request),
        ))
    except BridgeError as exc:
        print(ErrorResponse(error=exc.to_envelope()).model_dump_json())
        return 1
    except (OSError, ValidationError):
        error = InvalidInputError("Invalid layout request or development configuration")
        print(ErrorResponse(error=error.to_envelope()).model_dump_json())
        return 1
    except Exception:
        internal = BridgeError("Layout operation failed; inspect retained state before retrying")
        print(ErrorResponse(error=internal.to_envelope()).model_dump_json())
        return 1
    print(result.model_dump_json())
    return 0
