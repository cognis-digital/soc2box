"""SOC2BOX MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from soc2box.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-soc2box[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-soc2box[mcp]'")
        return 1
    app = FastMCP("soc2box")

    @app.tool()
    def soc2box_scan(target: str) -> str:
        """SOC 2 evidence collector and control tracker, self-hosted. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
