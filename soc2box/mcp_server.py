"""SOC2BOX MCP server — exposes soc2box tools for Cognis.Studio."""
from __future__ import annotations

import json
import sys


def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-soc2box[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print(
            "Install the MCP extra: pip install 'cognis-soc2box[mcp]'",
            file=sys.stderr,
        )
        return 1

    # Lazy import so the server module itself is always importable without
    # the mcp extra installed.
    from soc2box.core import load_program, program_readiness, gap_list

    app = FastMCP("soc2box")

    @app.tool()
    def soc2box_report(program_file: str) -> str:
        """Return a JSON audit-readiness report for the given program file."""
        try:
            prog = load_program(program_file)
            return json.dumps(program_readiness(prog), indent=2, sort_keys=True)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    @app.tool()
    def soc2box_gaps(program_file: str) -> str:
        """Return JSON list of controls needing attention, most urgent first."""
        try:
            prog = load_program(program_file)
            return json.dumps(gap_list(prog), indent=2, sort_keys=True)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    app.run()
    return 0
