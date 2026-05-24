"""CLI entrypoint for openmcp."""

from __future__ import annotations

from openmcp import server


def main() -> None:
    """Run the openmcp FastMCP server over stdio."""
    server.mcp.run(transport="stdio")


__all__ = ["main"]
