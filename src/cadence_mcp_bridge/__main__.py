"""Safe command-line entry point for local validation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.config import BridgeConfig
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "config-check":
        BridgeConfig()
        print("configuration: valid")
        return 0

    run_stdio_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
