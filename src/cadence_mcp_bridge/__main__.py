"""Safe command-line entry point for local validation."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.environments import (
    EnvironmentProfile,
    EnvironmentRejected,
    load_environment,
    prepare_environment,
    qualify_environment,
)
from cadence_mcp_bridge.server import run_stdio_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cadence-mcp-bridge",
        description="Validate the local Cadence MCP bridge installation.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "config-check",
        help="Validate configuration without connecting to Cadence.",
    )
    subparsers.add_parser(
        "serve",
        help="Run the Cadence MCP server over stdio (the default).",
    )
    subparsers.add_parser("doctor", help="Inspect local prerequisites without remote contact.")
    environment = subparsers.add_parser(
        "environment", help="Operator-only environment contracts; does not activate MCP execution."
    )
    actions = environment.add_subparsers(dest="environment_action", required=True)
    actions.add_parser("schema", help="Print the versioned environment JSON schema.")
    for action in ("validate", "prepare", "qualify"):
        command = actions.add_parser(action)
        command.add_argument("--profile", type=Path, required=True)
        if action == "prepare":
            command.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "doctor":
        config_valid = True
        try:
            BridgeConfig()
        except ValueError:
            config_valid = False
        print(
            json.dumps(
                {
                    "python": platform.python_version(),
                    "host_os": {"win32": "Windows", "linux": "Linux", "darwin": "Darwin"}.get(
                        sys.platform, "unknown"
                    ),
                    "ssh_available": shutil.which("ssh.exe") is not None,
                    "legacy_config_valid": config_valid,
                    "remote_contact": False,
                    "execution_authorized": False,
                }
            )
        )
        return 0 if config_valid and shutil.which("ssh.exe") is not None else 1
    if arguments.command == "environment":
        try:
            action = arguments.environment_action
            if action == "schema":
                result = EnvironmentProfile.model_json_schema()
            elif action == "validate":
                profile, _ = load_environment(arguments.profile)
                result = {
                    "environment_id": profile.environment_id,
                    "status": "valid_description",
                    "execution_authorized": False,
                }
            elif action == "prepare":
                result = prepare_environment(arguments.profile, arguments.output)
            else:
                result = qualify_environment(arguments.profile)
        except (OSError, ValueError, TimeoutError, subprocess.SubprocessError) as failure:
            # Validation/transport messages may contain private operator configuration.
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "reason": failure.reason
                        if isinstance(failure, EnvironmentRejected)
                        else "environment_contract_or_probe_failed",
                        "execution_authorized": False,
                    }
                )
            )
            return 1
        print(json.dumps(result, sort_keys=True))
        return 0
    if arguments.command == "config-check":
        BridgeConfig()
        print("configuration: valid")
        return 0

    run_stdio_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
